import asyncio
import random
import time
import re
import os
from playwright.async_api import async_playwright
from playwright_stealth import stealth
import glob
import json
from bs4 import BeautifulSoup
from gsheets_handler import GSheetsHandler
from dotenv import load_dotenv
import google.generativeai as genai

load_dotenv()

# List of common User-Agents for randomization
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/119.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:109.0) Gecko/20100101 Firefox/118.0"
]
if os.path.exists(".env.local"):
    load_dotenv(".env.local", override=True)

IS_RENDER = os.getenv("RENDER") == "true"

class LeadHunter:
    def __init__(self, keyword=None, limit=10):
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

    async def extract_socials(self, page):
        """
        Scans the current page for social media patterns.
        """
        social_patterns = {
            "linkedin": "linkedin.com/company",
            "instagram": "instagram.com/",
            "facebook": "facebook.com/",
            "twitter": "x.com/"
        }
        found_socials = {k: "N/A" for k in social_patterns}
        
        try:
            # 1. Grab all hrefs
            hrefs = await page.evaluate(
                "() => Array.from(document.querySelectorAll('a[href]')).map(a => a.href)"
            )
            
            # 2. Match patterns
            for link in hrefs:
                link_lower = link.lower()
                for platform, pattern in social_patterns.items():
                    if pattern in link_lower and "sharer" not in link_lower and "intent" not in link_lower:
                        if found_socials[platform] == "N/A":
                            found_socials[platform] = link
        except Exception as e:
            print(f"Error extracting socials: {e}")
            
        return found_socials

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
            return "", [], {}, "N/A"

        print(f"Scraping website: {url}")
        content = ""
        emails = []
        socials = {}
        phone = "N/A"

        try:
            await page.goto(url, wait_until="networkidle", timeout=30000)
            await self.sleep_random(2, 4)
            
            # Extract text for scoring
            content = await page.evaluate("() => document.body.innerText")
            
            # Extract emails
            html = await page.content()
            emails = list(set(re.findall(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', html)))
            emails = [e for e in emails if not e.endswith(('.png', '.jpg', '.jpeg', '.gif', '.svg'))]
            
            # Phone Extraction (Simple regex)
            # Looks for common formats: (123) 456-7890, 123-456-7890, +1 123 456 7890
            phone_match = re.search(r'(\+\d{1,2}\s?)?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}', content)
            if phone_match:
                phone = phone_match.group(0).strip()

            # Socials - Round 1 (Homepage)
            socials = await self.extract_socials(page)
            
            # Contact Page Jump for deeper social extraction
            # If we missed major socials, try to find a 'Contact' or 'About' page
            if socials["linkedin"] == "N/A" or socials["instagram"] == "N/A":
                try:
                    # Look for Contact/About link
                    # We match flexible text or href containing 'contact'/'about'
                    contact_link = await page.query_selector('a[href*="contact"], a[href*="Contact"], a[href*="about"], a[href*="About"]')
                    if not contact_link:
                         # Fallback to text content
                         contact_link = await page.query_selector('a:has-text("Contact"), a:has-text("About")')

                    if contact_link:
                        href = await contact_link.get_attribute('href')
                        if href:
                            print(f"  -> Jumping to potential Contact/About page: {href[:30]}...")
                            # Construct absolute URL if relative
                            if not href.startswith('http'):
                                from urllib.parse import urljoin
                                href = urljoin(page.url, href)
                            
                            await page.goto(href, wait_until="networkidle", timeout=15000)
                            await self.sleep_random(1, 3)
                            
                            # Socials - Round 2 (Merge)
                            more_socials = await self.extract_socials(page)
                            for k, v in more_socials.items():
                                if socials[k] == "N/A" and v != "N/A":
                                    socials[k] = v
                except Exception as ex:
                    print(f"  -> Contact jump info: {ex}")
            
            return content[:5000], emails, socials, phone # First 5000 chars for LLM
        except Exception as e:
            print(f"Error scraping {url}: {e}")
            return "", [], {}, "N/A"

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
            return "Pending", "Pending", "Pending", "Pending AI Review"

        prompt = f"""
        Analyze the following business information and website content for '{lead_name}'.
        Goal: Score this lead (0-100) based on their perceived 'vibe' (professionalism, modernity) and size.
        Also infer the age of the business if possible.
        
        Website Content:
        {website_content[:3000]}
        
        Return exactly in this JSON format:
        {{
            "score": <integer>,
            "decision": "<Qualified, Not Qualified, or Neutral>",
            "inferred_age": "<string>",
            "reasoning": "<short summary for the summary column>"
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
            return data.get("score", 0), data.get("decision", "Neutral"), data.get("inferred_age", "Unknown"), data.get("reasoning", "Analyzed by AI")
        except Exception as e:
            print(f"AI Scoring Error: {e}")
            return 50, "Neutral", "Unknown", "AI parsing failed, using default score"

    async def run_mission(self, keyword=None, update_callback=None):
        target_keyword = keyword if keyword else self.keyword
        if not target_keyword:
            print("❌ No keyword provided for mission.")
            return []

        # 0. Checkpoint: Load History
        print("Loading mission history...")
        existing_websites = self.gsheets.get_existing_leads()

    async def get_browser_and_page(self, p):
        # Tell Python to look in the persistent Render folder
        render_browser_path = os.environ.get("PLAYWRIGHT_BROWSERS_PATH", "/opt/render/project/playwright")
        executable_path = None
        
        if os.path.exists(render_browser_path):
            # Search for the executable because the specific subfolder (e.g. chromium-1200) can vary
            matches = glob.glob(os.path.join(render_browser_path, "**/chrome-headless-shell"), recursive=True)
            if not matches:
                matches = glob.glob(os.path.join(render_browser_path, "**/chrome"), recursive=True)
            
            if matches:
                executable_path = matches[0]

        # Launch browser with "Slim" settings
        launch_kwargs = {
            "headless": True,
            "args": [
                "--no-sandbox", 
                "--disable-setuid-sandbox", 
                "--disable-dev-shm-usage", 
                "--disable-gpu",
                "--single-process"
            ]
        }
        if executable_path:
            launch_kwargs["executable_path"] = executable_path
        
        try:
            browser = await p.chromium.launch(**launch_kwargs)
        except Exception as e:
            # Use repr to avoid encoding issues with the error message
            print(f"Launch Error with custom path: {repr(e)}")
            browser = await p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
        
        context = await browser.new_context(
            user_agent=random.choice(USER_AGENTS),
            viewport={'width': random.randint(1280, 1440), 'height': random.randint(720, 900)}
        )
        page = await context.new_page()
        
        # Apply Stealth Mode
        await stealth(page)

        # AGGRESSIVE MEDIA BLOCKING
        await page.route("**/*", lambda route: 
            route.abort() if route.request.resource_type in ["image", "media", "font", "stylesheet"] 
            else route.continue_()
        )
        return browser, page

    def generate_dork(self, keyword):
        """Constructs surgical Google X-Ray dorks for LinkedIn to ensure high quality leads."""
        # Focus on profiles (/in/) to find decision makers
        base_dork = f'site:linkedin.com/in/ "{keyword}"'
        
        # Exclude common noise to save RAM and focus on real people
        final_dork = f"{base_dork} -intitle:jobs -inurl:jobs -inurl:posts"
        return final_dork

    async def scrape_linkedin_profiles(self, page, keyword):
        print(f"Executing X-Ray Hijack for: {keyword}")
        dork = self.generate_dork(keyword)
        search_url = f"https://www.google.com/search?q={dork.replace(' ', '+')}"
        
        try:
            await page.goto(search_url, wait_until="networkidle")
        except:
            await page.goto(f"https://www.google.com/search?q={dork.replace(' ', '+')}")
        
        # Jitter: Random sleep between searching and processing
        await self.sleep_random(5, 8) 

        results = []
        links = await page.query_selector_all('a')
        
        processed_urls = set()
        for link in links:
            if len(results) >= self.limit:
                break
            
            href = await link.get_attribute('href')
            if href and "linkedin.com/in/" in href:
                # Clean Google redirect
                if "/url?q=" in href:
                    match = re.search(r'url\?q=([^&]*)', href)
                    if match:
                        href = match.group(1)
                
                clean_url = href.split('&')[0].split('?')[0]
                if clean_url in processed_urls:
                    continue
                
                processed_urls.add(clean_url)
                
                # Try to get the name and snippet from the result container
                try:
                    # Google usually wraps results in a div. We find the closest wrapper.
                    container = await page.evaluate_handle('el => el.closest(".g, .MjjYud")', link)
                    if container:
                        h3 = await container.as_element().query_selector('h3')
                        name = await h3.inner_text() if h3 else "LinkedIn User"
                        
                        # Extract the snippet (usually a div with specific container class)
                        snippet_el = await container.as_element().query_selector('.VwiC3b, .y355M')
                        snippet = await snippet_el.inner_text() if snippet_el else "No snippet available"
                    else:
                        name = "LinkedIn User"
                        snippet = "No snippet available"
                except:
                    name = "LinkedIn User"
                    snippet = "No snippet available"
                
                results.append({"name": name, "url": clean_url, "snippet": snippet})
                print(f"  + Scraped LinkedIn: {name} (Snippet: {snippet[:50]}...)")

        return results

    async def score_linkedin_ai(self, profile_name, snippet_text):
        if not self.model:
            return "Pending", "Pending", "Pending", "Pending AI Review"

        prompt = f"""
        Analyze this LinkedIn profile snippet for '{profile_name}'.
        Snippet: {snippet_text}
        
        Goal: Score (0-100) based on relevance to a 'High Ticket B2B' target.
        Return exactly in this JSON format:
        {{
            "score": <integer>,
            "decision": "<Qualified/Neutral/Not Qualified>",
            "summary": "<1-sentence summary of their role>"
        }}
        """
        try:
            response = self.model.generate_content(prompt)
            clean_text = response.text.replace("```json", "").replace("```", "").strip()
            start = clean_text.find('{')
            end = clean_text.rfind('}') + 1
            data = json.loads(clean_text[start:end])
            return data.get("score", 50), data.get("decision", "Neutral"), "LinkedIn", data.get("summary", "Analyzed Profile")
        except:
            return 50, "Neutral", "LinkedIn", "AI Score Failed"

    async def run_mission(self, keyword=None, update_callback=None, progress_callback=None):
        target_keyword = keyword if keyword else self.keyword
        if not target_keyword:
            print("❌ No keyword provided for mission.")
            return []

        # 0. Checkpoint: Load History
        print("Loading mission history...")
        existing_websites = self.gsheets.get_existing_leads()

        # Step 1: Get list of leads from Google Maps
        if update_callback: update_callback(f"Scanning Google Maps for: {target_keyword}...")
        
        async with async_playwright() as p:
            browser, page = await self.get_browser_and_page(p)
            try:
                # pass page object, not strings or modules
                basic_companies = await self.scrape_google_maps(page)
            finally:
                await browser.close()

        # Step 2: Atomic Scraping (One Browser Session per Lead)
        leads_to_process = []
        count = 0
        total = len(basic_companies)
        
        for basic_info in basic_companies:
            count += 1
            if basic_info.get("website") in existing_websites:
                if update_callback: update_callback(f"Skipping {basic_info['name']} (Duplicate)")
                continue

            if update_callback: update_callback(f"Scouting Lead {count}/{total}: {basic_info['name']}")
            if progress_callback: progress_callback(count / total * 0.5) # First half is scouting

            # ATOMIC SESSION
            async with async_playwright() as p:
                browser, page = await self.get_browser_and_page(p)
                try:
                    company = basic_info.copy()
                    website_content, emails, socials, phone = await self.scrape_website(page, company["website"])
                    
                    company["email"] = ", ".join(emails) if emails else "N/A"
                    company["phone"] = phone
                    company.update(socials)
                    
                    if company.get("linkedin") == "N/A":
                        found_li = await self.search_linkedin(page, company["name"])
                        if found_li != "N/A":
                            company["linkedin"] = found_li
                    
                    leads_to_process.append({
                        "data": company,
                        "content": website_content[:3000]
                    })
                except Exception as e:
                    print(f"Scouting Error for {basic_info['name']}: {e}")
                finally:
                    await browser.close() # ENSURE BROWSER CLOSES EVERY TIME

        # Step 3: AI Thinking & Saving (Browser is already closed here)
        final_leads = []
        process_count = 0
        total_to_process = len(leads_to_process)
        
        for item in leads_to_process:
            process_count += 1
            company = item["data"]
            content = item["content"]
            
            if update_callback: update_callback(f"AI Analyzing {company['name']} ({process_count}/{total_to_process})...")
            if progress_callback: 
                progress_callback(0.5 + (process_count / total_to_process * 0.5))

            score, decision, age, summary = await self.score_lead_ai(company["name"], content)
            company["score"] = score
            company["decision"] = decision
            company["age"] = age
            company["summary"] = summary

            if update_callback: update_callback(f"Syncing {company['name']} to GSheets...")
            self.gsheets.save_lead(company, query=target_keyword, source="google")

            summary_lead = {
                "keyword": target_keyword,
                "name": company["name"],
                "website": company["website"],
                "email": company["email"],
                "score": company["score"],
                "decision": company.get("decision", "N/A"),
                "summary": company["summary"][:100] + "..." 
            }
            final_leads.append(summary_lead)
            
            # GC
            item = None
            company = None
            content = None

        if update_callback: update_callback(f"Mission Complete: {target_keyword}")
        return final_leads

    async def run_linkedin_mission(self, keyword=None, update_callback=None):
        target_keyword = keyword if keyword else self.keyword
        if not target_keyword:
            return []

        async with async_playwright() as p:
            browser, page = await self.get_browser_and_page(p)
            
            dork = self.generate_dork(target_keyword)
            if update_callback: update_callback(f"Starting X-Ray Mission Control: {target_keyword}")
            
            profiles = await self.scrape_linkedin_profiles(page, target_keyword)
            
            # CRITICAL: Close browser immediately after scraping profiles
            await browser.close()

            final_leads = []
            for profile in profiles:
                if update_callback: update_callback(f"AI Analyzing Profile Snippet: {profile['name']}...")
                
                # Analyze using the SNIPPET to stay logged out / safe
                score, decision, _, summary = await self.score_linkedin_ai(profile["name"], profile["snippet"])
                
                lead = {
                    "name": profile["name"],
                    "url": profile["url"],
                    "score": score,
                    "decision": decision,
                    "summary": summary
                }

                # Save to specific LinkedIn tab, passing either keyword or full dork
                self.gsheets.append_linkedin_lead(lead, query=dork)
                
                final_leads.append(lead)
                if update_callback: update_callback(f"SAVED: {profile['name']}")

            if update_callback: update_callback(f"LinkedIn Mission Complete: {target_keyword}")
            return final_leads

    async def start_global_hunt(self, targets=None):
        if not targets:
            targets = [self.keyword] if self.keyword else []
        
        # 1. Ask GSheets: "What have we already done?"
        finished = self.gsheets.get_finished_missions()
        
        for query in targets:
            # 2. CHECKPOINT: Skip if already in the Mission_Progress tab
            # We don't skip if the user force-triggered it from sidebar, but this is the CLI loop
            if query in finished:
                print(f"Skipping Mission '{query}' - Already completed.")
                continue
            # 2. CHECKPOINT: Skip if already in the Mission_Progress tab
            if query in finished:
                print(f"Skipping Mission '{query}' - Already completed.")
                continue
                
            print(f"Starting New Mission: {query}")
            
            # 3. Run search and save logic
            await self.run_mission(keyword=query, update_callback=print)
            
            # 4. MARK AS DONE
            self.gsheets.mark_mission_complete(query)

    async def run_automated_mission(self, dork_query, source="linkedin", update_callback=None, progress_callback=None):
        """
        Executes a mission using a SPECIFIC dork from the sidebar toolkit.
        Scrape → Analyze → Save logic to ensure 0 'Pending' results.
        """
        async with async_playwright() as p:
            browser, page = await self.get_browser_and_page(p)
            
            if update_callback: update_callback(f"Deploying Bot for X-Ray: {dork_query}")
            
            # Use Google results for safety
            try:
                await page.goto(f"https://www.google.com/search?q={dork_query.replace(' ', '+')}", wait_until="networkidle")
            except:
                await page.goto(f"https://www.google.com/search?q={dork_query.replace(' ', '+')}")
            
            await self.sleep_random(5, 8)
            
            links_elements = await page.query_selector_all('a')
            profiles = []
            processed_urls = set()
            
            for link in links_elements:
                if len(profiles) >= self.limit: break
                href = await link.get_attribute('href')
                if href and ("linkedin.com" in href or "instagram.com" in href):
                    # Basic cleaning
                    if "/url?q=" in href:
                        match = re.search(r'url\?q=([^&]*)', href)
                        if match: href = match.group(1)
                    clean_url = href.split('&')[0].split('?')[0]
                    if clean_url in processed_urls: continue
                    processed_urls.add(clean_url)
                    
                    try:
                        container = await page.evaluate_handle('el => el.closest(".g, .MjjYud")', link)
                        if container:
                            h3 = await container.as_element().query_selector('h3')
                            name = await h3.inner_text() if h3 else "Lead"
                            snippet_el = await container.as_element().query_selector('.VwiC3b, .y355M')
                            snippet = await snippet_el.inner_text() if snippet_el else "No snippet"
                        else:
                            name, snippet = "Lead", "No snippet"
                    except:
                        name, snippet = "Lead", "No snippet"
                        
                    profiles.append({"name": name, "url": clean_url, "snippet": snippet})

            # FREE RAM
            await browser.close()
            
            final_leads = []
            for i, profile in enumerate(profiles):
                if update_callback: update_callback(f"AI Analyzing: {profile['name']}")
                if progress_callback:
                    progress_callback((i + 1) / len(profiles))
                
                # Analyze snippet
                score, decision, _, summary = await self.score_linkedin_ai(profile["name"], profile["snippet"])
                
                lead = {
                    "name": profile["name"],
                    "url": profile["url"],
                    "score": score,
                    "decision": decision,
                    "summary": summary
                }
                
                # Save using the smart router
                self.gsheets.save_lead(lead, query=dork_query, source=source)
                final_leads.append(lead)
                
            if update_callback: update_callback(f"Mission Done. Leads saved to GSheets.")
            return final_leads

    def detect_source(self, query):
        """
        Smart detection: If it looks like a person search (CEO, Founder, Manager, LinkedIn)
        it goes to LinkedIn. Otherwise, it's Google Maps.
        """
        person_terms = ["ceo", "founder", "owner", "manager", "director", "head", "vp", "president", "linkedin", "profile"]
        q_lower = query.lower()
        if any(term in q_lower for term in person_terms):
            return "linkedin"
        return "google"

    async def run_smart_mission(self, query, update_callback=None):
        source = self.detect_source(query)
        if source == "linkedin":
            if update_callback: update_callback(f"🧠 Smart Routing: Detected LinkedIn target for '{query}'")
            return await self.run_linkedin_mission(query, update_callback)
        else:
            if update_callback: update_callback(f"🧠 Smart Routing: Detected Local Business target for '{query}'")
            return await self.run_mission(query, update_callback)

if __name__ == "__main__":
    # Test run
    try:
        keyword = os.getenv("KEYWORD", "Real Estate Agencies in Miami")
        limit = int(os.getenv("SCRAPE_LIMIT", 2))
        
        # Check if comma-separated list
        if "," in keyword:
            targets = [k.strip() for k in keyword.split(",")]
            print(f"Starting GLOBAL HUNT for targets: {targets}, limit: {limit}")
            hunter = LeadHunter(limit=limit)
            asyncio.run(hunter.start_global_hunt(targets))
        else:
            print(f"Starting Single Run for keyword: {keyword}, limit: {limit}")
            hunter = LeadHunter(keyword, limit=limit)
            # We use global hunt even for single to get the benefit of completion marking
            asyncio.run(hunter.start_global_hunt([keyword]))
    except Exception as e:
        print(f"CRITICAL ERROR in hunter.py: {e}")
        import traceback
        traceback.print_exc()
        exit(1)
