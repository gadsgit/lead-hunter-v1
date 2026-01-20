import asyncio
import random
import time
import re
import os
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup
import pandas as pd
from gsheets_handler import GSheetsHandler
from dotenv import load_dotenv
import google.generativeai as genai

load_dotenv()

class LeadHunter:
    def __init__(self, keyword, limit=10):
        self.keyword = keyword
        self.limit = limit
        self.gsheets = GSheetsHandler()
        self.leads = []
        self.api_key = os.getenv("GEMINI_API_KEY")
        if self.api_key:
            genai.configure(api_key=self.api_key)
            self.model = genai.GenerativeModel('gemini-1.5-flash')
        else:
            self.model = None

    async def sleep_random(self, min_s=2, max_s=5):
        await asyncio.sleep(random.uniform(min_s, max_s))

    async def scrape_google_maps(self, page):
        print(f"Searching Google Maps for: {self.keyword}")
        try:
            await page.goto(f"https://www.google.com/maps/search/{self.keyword.replace(' ', '+')}", wait_until="domcontentloaded", timeout=60000)
        except Exception as e:
            print(f"Initial navigation slow/failed: {e}")
            await page.goto(f"https://www.google.com/maps/search/{self.keyword.replace(' ', '+')}")
        
        await self.sleep_random(5, 7)

        # 2. HANDLE CONSENT SCREEN (Common on new IPs like Render)
        try:
            consent_selectors = [
                'button[aria-label="Accept all"]',
                'button[aria-label="Agree"]',
                'button:has-text("Accept all")',
                'button:has-text("I agree")',
            ]
            for selector in consent_selectors:
                if await page.query_selector(selector):
                    print(f"Found consent screen, clicking {selector}...")
                    await page.click(selector)
                    await self.sleep_random(2, 4)
                    break
        except:
            pass

        # Check for "Google Maps can't find..."
        await page.screenshot(path="debug_search.png")
        if await page.query_selector('text="Google Maps can\'t find"'):
            print(f"No results found for {self.keyword}")
            return []

        results = []
        
        # Try to wait for the results container or at least one result
        try:
            await page.wait_for_selector('a.hfpxzc', timeout=10000)
        except:
            print("Timed out waiting for results selector. Page might be loading slow or different layout.")

        # Scroll down to load more results
        for _ in range(5):
            try:
                feed_selector = 'div[role="feed"]'
                feed = await page.query_selector(feed_selector)
                if feed:
                    await feed.focus()
                    await page.mouse.wheel(0, 3000)
                else:
                    await page.mouse.wheel(0, 5000)
                await self.sleep_random(2, 3)
            except:
                break

        # Primary selector for results links
        items = await page.query_selector_all('a.hfpxzc')
        if not items:
            # Secondary selector: company names
            items = await page.query_selector_all('.qBF1Pd')

        print(f"Found {len(items)} items in view. Processing up to {self.limit}...")

        processed_names = set()
        for item in items:
            if len(results) >= self.limit:
                break
                
            try:
                name = await item.get_attribute('aria-label')
                if not name:
                    name = await item.inner_text()
                
                name = name.strip() if name else ""
                if not name or name in processed_names:
                    continue
                
                processed_names.add(name)
                
                website = "N/A"
                # Locate the parent article to find the website button
                article = await page.evaluate_handle('el => el.closest(\'div[role="article"]\')', item)
                
                if article:
                    # Sometimes the website button is inside the article but not a direct child
                    website_el = await article.as_element().query_selector('a[data-value="Website"]')
                    if website_el:
                        website = await website_el.get_attribute('href')
                
                print(f"  + Scraped: {name} ({website})")
                results.append({"name": name, "website": website})
            except Exception as e:
                print(f"Error extracting item: {e}")
        
        if not results:
            print("⚠️ Re-checking with fallback extraction...")
            # If still nothing, one final attempt looking for any visible text that looks like a business name
            potential_names = await page.query_selector_all('.fontHeadlineSmall')
            for el in potential_names[:self.limit]:
                name = await el.inner_text()
                if name:
                    results.append({"name": name.strip(), "website": "N/A"})

        return results

    async def scrape_website(self, page, url):
        if not url or url == "N/A":
            return "", []

        print(f"Scraping website: {url}")
        try:
            await page.goto(url, wait_until="networkidle", timeout=30000)
            await self.sleep_random(2, 4)
            
            # Extract text for scoring
            content = await page.evaluate("() => document.body.innerText")
            
            # Extract emails
            html = await page.content()
            emails = list(set(re.findall(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', html)))
            # Filter out common junk emails
            emails = [e for e in emails if not e.endswith(('.png', '.jpg', '.jpeg', '.gif', '.svg'))]
            
            return content[:5000], emails # First 5000 chars for LLM
        except Exception as e:
            print(f"Error scraping {url}: {e}")
            return "", []

    async def search_linkedin(self, page, company_name):
        print(f"Searching LinkedIn for: {company_name}")
        search_query = f"{company_name} LinkedIn company"
        await page.goto(f"https://www.google.com/search?q={search_query.replace(' ', '+')}")
        await self.sleep_random(2, 4)
        
        # Look for linkedin.com/company links
        links = await page.query_selector_all('a')
        for link in links:
            href = await link.get_attribute('href')
            if href and "linkedin.com/company" in href:
                # Clean Google redirect if necessary
                if "/url?q=" in href:
                    match = re.search(r'url\?q=([^&]*)', href)
                    if match:
                        return match.group(1)
                return href.split('&')[0]
        return "N/A"

    async def score_lead_ai(self, lead_name, website_content):
        if not self.model:
            # Fallback: Mark as pending AI review
            return "Pending", "Pending", "Pending AI Review"

        prompt = f"""
        Analyze the following business information and website content for '{lead_name}'.
        Goal: Score this lead (0-100) based on their perceived 'vibe' (professionalism, modernity) and size.
        Also infer the age of the business if possible.
        
        Website Content:
        {website_content[:3000]}
        
        Return exactly in this JSON format:
        {{
            "score": <integer>,
            "inferred_age": "<string>",
            "reasoning": "<short sentence>"
        }}
        """
        try:
            response = self.model.generate_content(prompt)
            # Find JSON in response
            match = re.search(r'\{.*\}', response.text, re.DOTALL)
            if match:
                import json
                data = json.loads(match.group(0))
                return data.get("score", 0), data.get("inferred_age", "Unknown"), data.get("reasoning", "Analyzed by AI")
        except Exception as e:
            print(f"AI Scoring Error: {e}")
        
        return "Pending", "Pending", "Pending AI Review"

    async def run_mission(self, update_callback=None):
        async with async_playwright() as p:
            # Explicitly check for Render's browser path
            browser_path = os.environ.get("PLAYWRIGHT_BROWSERS_PATH")
            if browser_path:
                print(f"Using PLAYWRIGHT_BROWSERS_PATH: {browser_path}")
            
            # Launch browser with stealth settings
            browser = await p.chromium.launch(
                headless=True,
                args=[
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-blink-features=AutomationControlled", # Hides the "bot" flag
                ]
            )
            context = await browser.new_context(
                viewport={'width': 1280, 'height': 800},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
            page = await context.new_page()

            # 1. Search Google Maps
            if update_callback: update_callback(f"🚀 Starting Mission: {self.keyword}")
            companies = await self.scrape_google_maps(page)
            
            for company in companies:
                if update_callback:
                    update_callback(f"🔍 Analyzing {company['name']}...")
                
                # 2. Scrape Website and Extract Emails
                website_content, emails = await self.scrape_website(page, company["website"])
                company["email"] = ", ".join(emails) if emails else "N/A"
                
                # 3. LinkedIn Search
                company["linkedin"] = await self.search_linkedin(page, company["name"])
                
                # 4. AI Scoring
                score, age, reasoning = await self.score_lead_ai(company["name"], website_content)
                company["score"] = score
                company["age"] = age
                company["reasoning"] = reasoning

                # 5. Storage
                # Convert score to 0 if it's "Pending" for the comparison check
                comparison_score = score if isinstance(score, (int, float)) else 0
                
                if comparison_score > 70:
                    if update_callback:
                        update_callback(f"✅ QUALIFIED ({score}): {company['name']}. Saving to GSheets...")
                    self.gsheets.append_lead(company)
                else:
                    status_text = f"Low Score ({score})" if comparison_score < 70 else "Pending AI Review"
                    if update_callback:
                        update_callback(f"⚠️ {status_text}: {company['name']}. Skipping storage.")
                
                self.leads.append(company)
                await self.sleep_random(2, 5)

            await browser.close()
            if update_callback: update_callback("🏁 Mission Complete!")
            return self.leads

if __name__ == "__main__":
    # Test run
    try:
        keyword = os.getenv("KEYWORD", "Real Estate Agencies in Miami")
        limit = int(os.getenv("SCRAPE_LIMIT", 2))
        print(f"Starting test run for keyword: {keyword}, limit: {limit}")
        hunter = LeadHunter(keyword, limit=limit)
        asyncio.run(hunter.run_mission(print))
    except Exception as e:
        print(f"CRITICAL ERROR in hunter.py: {e}")
        import traceback
        traceback.print_exc()
        exit(1)
