import asyncio
import random
import time
import re
import os
from playwright.async_api import async_playwright
import glob
import json
from bs4 import BeautifulSoup
from gsheets_handler import GSheetsHandler
from dotenv import load_dotenv
import google.generativeai as genai

load_dotenv()
if os.path.exists(".env.local"):
    load_dotenv(".env.local", override=True)

IS_RENDER = os.getenv("RENDER") == "true"

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
            await page.goto(f"https://www.google.com/maps/search/{self.keyword.replace(' ', '+')}", wait_until="networkidle", timeout=60000)
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

        # Check for Google Maps failures
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
            # Handle possible markdown wrapping from LLM
            clean_text = response.text.replace("```json", "").replace("```", "").strip()
            # If there's still extra text around the JSON, try to find the first { and last }
            start = clean_text.find('{')
            end = clean_text.rfind('}') + 1
            if start != -1 and end != 0:
                clean_text = clean_text[start:end]
                
            data = json.loads(clean_text)
            return data.get("score", 0), data.get("inferred_age", "Unknown"), data.get("reasoning", "Analyzed by AI")
        except Exception as e:
            print(f"AI Scoring Error: {e}")
            return 50, "Unknown", "AI parsing failed, using default score"

    async def run_mission(self, update_callback=None):
        async with async_playwright() as p:
            # Tell Python to look in the persistent Render folder
            render_browser_path = os.environ.get("PLAYWRIGHT_BROWSERS_PATH", "/opt/render/project/playwright")
            executable_path = None
            
            if os.path.exists(render_browser_path):
                print(f"Seeking browser in persistent path: {render_browser_path}")
                # Search for the executable because the specific subfolder (e.g. chromium-1200) can vary
                matches = glob.glob(os.path.join(render_browser_path, "**/chrome-headless-shell"), recursive=True)
                if not matches:
                    matches = glob.glob(os.path.join(render_browser_path, "**/chrome"), recursive=True)
                
                if matches:
                    executable_path = matches[0]
                    print(f"Found browser executable at: {executable_path}")

            # Launch browser with "Slim" settings for 512MB limit
            try:
                launch_kwargs = {
                    "headless": True,
                    "args": [
                        "--no-sandbox", 
                        "--disable-setuid-sandbox", 
                        "--disable-dev-shm-usage", 
                        "--disable-gpu",
                        "--single-process" # Significantly reduces process overhead
                    ]
                }
                if executable_path:
                    launch_kwargs["executable_path"] = executable_path
                
                browser = await p.chromium.launch(**launch_kwargs)
            except Exception as e:
                print(f"Launch Error: {e}")
                browser = await p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
            
            context = await browser.new_context()
            page = await context.new_page()

            # AGGRESSIVE MEDIA BLOCKING (The #1 RAM Saver)
            await page.route("**/*", lambda route: 
                route.abort() if route.request.resource_type in ["image", "media", "font", "stylesheet"] 
                else route.continue_()
            )

            # 1. Search Google Maps
            if update_callback: update_callback(f"🚀 Starting Mission: {self.keyword}")
            basic_companies = await self.scrape_google_maps(page)
            
            final_leads = []

            for basic_info in basic_companies:
                if update_callback:
                    update_callback(f"🔍 Analyzing {basic_info['name']}...")
                
                # Create a fresh lead object for this individual step
                company = basic_info.copy()
                
                # 2. Scrape Website and Extract Emails
                # Heavy data (content) is only temporary here
                website_content, emails = await self.scrape_website(page, company["website"])
                company["email"] = ", ".join(emails) if emails else "N/A"
                
                # 3. LinkedIn Search
                company["linkedin"] = await self.search_linkedin(page, company["name"])
                
                # 4. AI Scoring (Uses content, then we can discard content)
                score, age, reasoning = await self.score_lead_ai(company["name"], website_content)
                company["score"] = score
                company["age"] = age
                company["reasoning"] = reasoning

                # 5. Storage
                # We save immediately as requested to avoid keeping all in RAM
                if update_callback:
                    update_callback(f"🚀 Attempting to save {company['name']} to GSheets...")
                
                save_success = self.gsheets.append_lead(company)
                
                if save_success:
                    if update_callback:
                        update_callback(f"✅ SUCCESSFULLY SAVED: {company['name']}.")
                else:
                    if update_callback:
                        update_callback(f"❌ FAILED to save to GSheets.")

                # Keep a LIGHTWEIGHT version for the UI results
                # We don't need to keep the full website_content or reasoning if RAM is tight
                summary_lead = {
                    "name": company["name"],
                    "website": company["website"],
                    "email": company["email"],
                    "score": company["score"],
                    "reasoning": company["reasoning"][:100] + "..." # Truncate reasoning 
                }
                final_leads.append(summary_lead)
                
                # CRITICAL: Clear heavy variables for GC
                company = None
                website_content = None
                
                await self.sleep_random(2, 5)

            await browser.close()
            if update_callback: update_callback("🏁 Mission Complete!")
            return final_leads

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
