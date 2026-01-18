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
        await page.goto(f"https://www.google.com/maps/search/{self.keyword.replace(' ', '+')}")
        await self.sleep_random(5, 7)

        results = []
        
        # Scroll down to load more results
        for _ in range(5):
            # Select the main results list container to scroll
            # Google Maps results are usually in a div with role="feed" or similar
            try:
                await page.mouse.wheel(0, 10000)
                await self.sleep_random(2, 3)
            except:
                break

        # Extract items
        # Selectors for Google Maps results often change, but 'div[role="article"]' or 'a.hfpxzc' are common
        # Let's try to find anchors that have an aria-label which is usually the company name
        items = await page.query_selector_all('a.hfpxzc')
        if not items:
            # Fallback to article role
            items = await page.query_selector_all('div[role="article"]')

        print(f"Found {len(items)} potential items.")

        for item in items[:self.limit]:
            try:
                name = await item.get_attribute('aria-label')
                # For hfpxzc, the name is in aria-label. For others, we might need a sub-selector
                if not name:
                    name_el = await item.query_selector('.qBF1Pd')
                    if name_el:
                        name = await name_el.inner_text()
                
                # To get the website, we often have to click the item or look for a specific button
                # For now, let's try to find it in the current item attributes or nearby
                # Usually, clicking is more reliable but slower.
                
                # Try to find website link in the article
                website = "N/A"
                website_el = await item.query_selector('a[data-value="Website"]')
                if website_el:
                    website = await website_el.get_attribute('href')
                
                if name:
                    results.append({"name": name, "website": website})
            except Exception as e:
                print(f"Error extracting item: {e}")
        
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
            # Launch browser
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                viewport={'width': 1280, 'height': 800},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"
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
                if score > 70:
                    if update_callback:
                        update_callback(f"✅ QUALIFIED ({score}): {company['name']}. Saving to GSheets...")
                    self.gsheets.append_lead(company)
                else:
                    if update_callback:
                        update_callback(f"⚠️ Low Score ({score}): {company['name']}. Skipping storage.")
                
                self.leads.append(company)
                await self.sleep_random(2, 5)

            await browser.close()
            if update_callback: update_callback("🏁 Mission Complete!")
            return self.leads

if __name__ == "__main__":
    hunter = LeadHunter("Real Estate Agencies in Miami", limit=2)
    asyncio.run(hunter.run_mission(print))
