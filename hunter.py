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
import gc

# Try importing different stealth implementations to compatible with different versions
stealth_async = None
Stealth = None

try:
    from playwright_stealth import stealth_async
except ImportError:
    pass

try:
    from playwright_stealth import Stealth
except ImportError:
    pass

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

    def truncate_for_ai(self, html_content, max_chars=5000):
        """Clean and slice text so Gemini doesn't choke on RAM."""
        try:
            soup = BeautifulSoup(html_content, "html.parser")
            # Remove script and style elements
            for script_or_style in soup(["script", "style", "nav", "footer"]):
                script_or_style.decompose()
            
            clean_text = soup.get_text(separator=' ')
            # Collapse whitespace
            clean_text = " ".join(clean_text.split())
            return clean_text[:max_chars]
        except Exception as e:
            print(f"Truncation error: {e}")
            return html_content[:max_chars]

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

    async def scrape_google_maps(self, page, update_callback=None):
        print(f"Searching Google Maps for: {self.keyword}")
        if update_callback: update_callback(f"Searching Google Maps for: {self.keyword}")
        maps_url = f"https://www.google.com/maps/search/{self.keyword.replace(' ', '+')}?hl=en"
        
        try:
            await page.goto(maps_url, wait_until="networkidle", timeout=60000)
        except Exception as e:
            msg = f"Initial navigation slow/failed: {e}"
            print(msg)
            if update_callback: update_callback(msg)
            await page.goto(maps_url)
        
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
                    msg = f"Found consent screen, clicking {selector}..."
                    print(msg)
                    if update_callback: update_callback(msg)
                    await page.click(selector)
                    await self.sleep_random(2, 4)
                    break
        except:
            pass

        # Check for Google Maps failures
        if await page.query_selector('text="Google Maps can\'t find"'):
            msg = f"No results found for {self.keyword}"
            print(msg)
            if update_callback: update_callback(msg)
            return []

        results = []
        
        # Try to wait for the results container or at least one result
        try:
            await page.wait_for_selector('a.hfpxzc', timeout=10000)
        except:
            print("Timed out waiting for results selector.")
            if update_callback: update_callback("Timed out waiting for results selector.")

        # Scroll down to load more results
        if update_callback: update_callback("Scrolling to load results...")
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

        msg = f"Found {len(items)} items in view. Processing up to {self.limit}..."
        print(msg)
        if update_callback: update_callback(msg)

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
                reviews = 0
                is_closed = False
                
                # Locate the parent article to find the website button
                article = await page.evaluate_handle('el => el.closest(\'div[role="article"]\')', item)
                
                if article:
                    # Analysis for Opportunities
                    try:
                        txt = await article.inner_text()
                        # Reviews count like (15)
                        rev_match = re.search(r'\(([\d,]+)\)', txt)
                        if rev_match:
                            reviews = int(rev_match.group(1).replace(",", ""))
                        
                        if "Permanently closed" in txt:
                            is_closed = True
                            
                        # Check for Unclaimed status (heuristics)
                        # Often "Own this business?" is not visible on the search results card directly without clicking.
                        # But sometimes "Claim this business" appears. We'll search for it in `txt`.
                        if "Own this business?" in txt or "Claim this business" in txt:
                            # This needs to be passed out
                            pass 
                    except:
                        pass

                    # Sometimes the website button is inside the article but not a direct child
                    website_el = await article.as_element().query_selector('a[data-value="Website"]')
                    if website_el:
                        website = await website_el.get_attribute('href')
                
                print(f"  + Scraped: {name} ({website}) | Revs: {reviews}")
                if update_callback: update_callback(f"📍 Discovered: {name}")
                results.append({"name": name, "website": website, "reviews": reviews, "is_closed": is_closed})
            except Exception as e:
                print(f"Error extracting item: {e}")
        
        if not results:
            print("⚠️ Re-checking with fallback extraction...")
            if update_callback: update_callback("⚠️ Using fallback extraction...")
            # If still nothing, one final attempt looking for any visible text that looks like a business name
            potential_names = await page.query_selector_all('.fontHeadlineSmall')
            for el in potential_names[:self.limit]:
                name = await el.inner_text()
                if name:
                    name = name.strip()
                    if update_callback: update_callback(f"📍 Discovered: {name}")
                    results.append({"name": name.strip(), "website": "N/A", "reviews": 0, "is_closed": False})

        return results

    def detect_tech_stack(self, html):
        stack = []
        if "wp-content" in html: stack.append("WordPress")
        if "shopify" in html: stack.append("Shopify")
        if "fbevents.js" in html or "facebook-domain-verification" in html: stack.append("Meta Pixel")
        if "googletagmanager" in html: stack.append("GTM")
        if "wix.com" in html: stack.append("Wix")
        if "squarespace" in html: stack.append("Squarespace")
        return ", ".join(stack) if stack else "Unknown"

    async def scrape_website(self, page, url):
        if not url or url == "N/A":
            return "", [], {}, "N/A", "Unknown"

        print(f"Scraping website: {url}")
        content = ""
        emails = []
        socials = {}
        phone = "N/A"
        tech_stack = "Unknown"

        try:
            await page.goto(url, wait_until="networkidle", timeout=30000)
            await self.sleep_random(2, 4)
            
            # Extract HTML for Tech Stack and Emails
            html = await page.content()
            tech_stack = self.detect_tech_stack(html)
            
            # Extract text for scoring
            content = await page.evaluate("() => document.body.innerText")
            
            # Extract emails
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
            
            return content[:5000], emails, socials, phone, tech_stack # First 5000 chars for LLM
        except Exception as e:
            print(f"Error scraping {url}: {e}")
            return "", [], {}, "N/A", "Unknown"

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
        if stealth_async:
            await stealth_async(page)
        elif Stealth:
            stealth = Stealth()
            await stealth.apply_stealth_async(page)
        else:
            print("⚠️ Playwright Stealth not available or incompatible version.")

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

    async def scrape_linkedin_profiles(self, page, keyword, is_dork=False):
        """
        Scrapes LinkedIn profiles from Google search results.
        keyword: Either a plain keyword or a pre-built dork string
        is_dork: If True, use keyword as-is. If False, generate dork from keyword.
        """
        print(f"Executing X-Ray Hijack for: {keyword}")
        
        # Only generate dork if not already provided
        if is_dork:
            dork = keyword
        else:
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
                msg = f"💼 Scraped LinkedIn: {name}"
                print(msg)
                # The original code had update_callback here, but it's not passed to this method.
                # If it were, it would be: if update_callback: update_callback(msg)

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

    async def run_mission(self, keyword=None, update_callback=None, progress_callback=None, enrich_with_xray=False):
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
                basic_companies = await self.scrape_google_maps(page, update_callback)
            finally:
                await browser.close()

        # Step 2: Atomic Processing (Scrape -> Score -> Save)
        final_leads = []
        count = 0
        total = len(basic_companies)
        
        for basic_info in basic_companies:
            count += 1
            if basic_info.get("website") in existing_websites:
                if update_callback: update_callback(f"Skipping {basic_info['name']} (Duplicate)")
                continue

            if update_callback: update_callback(f"Processing Lead {count}/{total}: {basic_info['name']}")
            
            # ATOMIC SESSION
            company_data = None
            company_content = None
            
            # --- PHASE 1: THE BROWSER (RAM HEAVY) ---
            try:
                # Update approximate found count
                if progress_callback: progress_callback(count / total)
                
                async with async_playwright() as p:
                    browser, page = await self.get_browser_and_page(p)
                    
                    try:
                        company = basic_info.copy()
                        # Scrape with strict timeout
                        website_content, emails, socials, phone, tech_stack = await self.scrape_website(page, company["website"])
                        
                        company["email"] = ", ".join(emails) if emails else "N/A"
                        company["phone"] = phone
                        company["tech_stack"] = tech_stack
                        company.update(socials)

                        # OPPORTUNITY & BADGE DETECTION (3 Separate Columns)
                        
                        # Column 1: GMB STATUS
                        if company.get("is_unclaimed", False):
                            company["gmb_status"] = "🚩 Unclaimed"
                        elif company.get("reviews", 0) < 10:
                            company["gmb_status"] = "⚠️ Low Revs"
                        else:
                            company["gmb_status"] = "✅ Healthy"

                        # Column 2: WEB/TECH STATUS
                        if company.get("website", "N/A") == "N/A":
                            company["web_status"] = "🚫 No Site"
                        elif "Unknown" in tech_stack:
                            company["web_status"] = "🕸️ Basic"
                        elif "Meta Pixel" not in tech_stack:
                            company["web_status"] = "📉 No Pixel"
                        else:
                            company["web_status"] = "💎 Modern"
                            
                        # Column 3: PITCH/INTENT
                        pitch_reasons = []
                        
                        if company.get("is_unclaimed", False):
                            pitch_reasons.append("Claim GMB")
                        if company.get("reviews", 0) < 10:
                            pitch_reasons.append("Review Mgmt")
                        if company.get("website", "N/A") == "N/A":
                            pitch_reasons.append("New Website")
                        elif "Meta Pixel" not in tech_stack:
                            pitch_reasons.append("Pixel/CRO")
                        if company.get("is_closed", False):
                            pitch_reasons.append("SEO Fix")
                        if "emergency" in target_keyword.lower():
                            pitch_reasons.append("🚨 PPC Ads")
                        
                        company["pitch"] = ", ".join(list(set(pitch_reasons))) if pitch_reasons else "Lead Gen"
                        
                        # Track source
                        company["source"] = "Google Maps"
                        
                        # X-RAY ENRICHMENT (The "Dual Scan" Feature)
                        founder_info = "N/A"
                        if enrich_with_xray:
                            # If we didn't find a direct LinkedIn link, try X-Ray specifically for the Founder
                            xray_dork = f'site:linkedin.com/in "CEO" OR "Founder" "{company["name"]}"'
                            if update_callback: update_callback(f"   🔍 X-Raying Founder for: {company['name']}")
                            
                            # Reuse the existing page for X-Ray
                            # Temporarily set limit to 1 for founder search
                            original_limit = self.limit
                            self.limit = 1 
                            xray_results = await self.scrape_linkedin_profiles(page, xray_dork)
                            self.limit = original_limit # Reset limit
                            
                            if xray_results:
                                founder = xray_results[0] # Take top result
                                founder_info = f"{founder['name']} ({founder['url']})"
                                company['founder_match'] = founder_info
                                if update_callback: update_callback(f"   👤 Found: {founder['name']}")
                            else:
                                company['founder_match'] = "Not Found"
                        
                        if company.get("linkedin") == "N/A":
                            found_li = await self.search_linkedin(page, company["name"])
                            if found_li != "N/A":
                                company["linkedin"] = found_li
                                
                        company_data = company
                        # Truncate content specifically to save RAM
                        company_content = self.truncate_for_ai(website_content, 5000)
                    except Exception as e:
                        print(f"Scrape error for {basic_info['name']}: {e}")
                        company_data = basic_info.copy() # Fallback to basic info
                        company_content = ""
                    finally:
                         # Force close everything
                         await browser.close()
                         try:
                             await p.stop()
                         except: pass

            except Exception as e:
                print(f"Browser launch error: {e}")

            # --- PHASE 2: THE CLEANUP (MEMORY FLUSH) ---
            gc.collect()
            
            # --- PHASE 3: THE AI (RAM LIGHT) ---
            if company_data:
                try:
                    if update_callback: update_callback(f"AI Analyzing & Saving {company_data['name']}...")
                    
                    # Safe analysis even with empty content
                    score, decision, age, summary = await self.score_lead_ai(company_data["name"], company_content or "")
                    company_data["score"] = score
                    company_data["decision"] = decision
                    company_data["age"] = age
                    company_data["summary"] = summary

                    self.gsheets.save_lead(company_data, query=target_keyword, source="google")

                    summary_lead = {
                        "keyword": target_keyword,
                        "name": company_data["name"],
                        "source": company_data.get("source", "Google Maps"),
                        "website": company_data["website"],
                        "email": company_data["email"],
                        "founder": company_data.get("founder_match", "N/A"),
                        "tech": company_data.get("tech_stack", "Unknown"),
                        "gmb": company_data.get("gmb_status", "N/A"),
                        "web": company_data.get("web_status", "N/A"),
                        "pitch": company_data.get("pitch", "N/A"),
                        "score": company_data["score"],
                        "decision": company_data.get("decision", "N/A"),
                        "summary": company_data["summary"][:100] + "..." 
                    }
                    final_leads.append(summary_lead)
                except Exception as e:
                    print(f"AI/Save Error for {company_data['name']}: {e}")
                    if update_callback: update_callback(f"Error saving {company_data['name']}")

        if update_callback: update_callback(f"Mission Complete: {target_keyword}")
        return final_leads

    async def run_linkedin_mission(self, keyword=None, update_callback=None):
        target_keyword = keyword if keyword else self.keyword
        if not target_keyword:
            return []

        async with async_playwright() as p:
            browser, page = await self.get_browser_and_page(p)
            
            if update_callback: update_callback(f"Starting X-Ray Mission Control: {target_keyword}")
            
            # Pass raw keyword, let scraper generate the dork
            profiles = await self.scrape_linkedin_profiles(page, target_keyword, is_dork=False)
            
            # CRITICAL: Close browser immediately after scraping profiles
            await browser.close()

            final_leads = []
            for profile in profiles:
                if update_callback: update_callback(f"AI Analyzing Profile Snippet: {profile['name']}...")
                
                # Analyze using the SNIPPET to stay logged out / safe
                score, decision, _, summary = await self.score_linkedin_ai(profile["name"], profile["snippet"])
                
                lead = {
                    "name": profile["name"],
                    "source": "LinkedIn X-Ray",
                    "url": profile["url"],
                    "score": score,
                    "decision": decision,
                    "summary": summary
                }

                # Save to specific LinkedIn tab, passing the keyword
                self.gsheets.append_linkedin_lead(lead, query=target_keyword)
                
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
            
            # Handle Google Consent Screen (if any)
            try:
                consent_selectors = [
                    'button[aria-label="Accept all"]',
                    'button[aria-label="Agree"]',
                    'button:has-text("Accept all")',
                    'button:has-text("I agree")',
                    'div[role="button"]:has-text("Accept all")',
                ]
                for selector in consent_selectors:
                    if await page.query_selector(selector):
                        msg = f"Found consent screen, clicking {selector}..."
                        print(msg)
                        if update_callback: update_callback(msg)
                        await page.click(selector)
                        await self.sleep_random(2, 4)
                        break
            except:
                pass

            # Check for CAPTCHA/Blocking
            page_title = await page.title()
            if "Before you continue" in page_title or "Captcha" in page_title:
                print(f"⚠️ CAPTCHA/Consent block detected: {page_title}")
                if update_callback: update_callback(f"⚠️ Google Blocked Request ({page_title})")

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
                    if update_callback: update_callback(f"📍 Discovered: {name}")

            # FREE RAM
            await browser.close()
            
            if not profiles:
                 msg = f"⚠️ No profiles found via X-Ray. Page Title: {page_title}"
                 print(msg)
                 if update_callback: update_callback(msg)

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
                
            if update_callback: update_callback(f"Mission Done. {len(final_leads)} Leads saved to GSheets.")
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
        # If it looks like a business search, we default to the "Enriched" Google Mission now
        if source == "linkedin":
            if update_callback: update_callback(f"🧠 Smart Routing: Detected LinkedIn target for '{query}'")
            return await self.run_linkedin_mission(query, update_callback)
        else:
            if update_callback: update_callback(f"🧠 Smart Routing: Detected Local Business target for '{query}'")
            # Smart mode now defaults to Dual Scan (Enrichment)
            return await self.run_mission(query, update_callback, enrich_with_xray=True)

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
