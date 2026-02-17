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
import datetime

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

try:
    from fake_useragent import UserAgent
    ua_generator = UserAgent(browsers=['chrome', 'firefox', 'edge'])
except ImportError:
    ua_generator = None

# List of common User-Agents for randomization (Fallback)
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
        self.mission_id = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        self.archive_file = "intelligence_archive.txt"
        
        if self.api_key:
            genai.configure(api_key=self.api_key)
            self.model = genai.GenerativeModel('gemini-1.5-flash')
        else:
            self.model = None

    def archive_intelligence(self, category, content):
        """Persistent logging of all AI prompts, responses, and mission logs."""
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_entry = f"\n[{timestamp}] [{self.mission_id}] [{category.upper()}]\n{content}\n"
        log_entry += "-" * 50 + "\n"
        try:
            with open(self.archive_file, "a", encoding="utf-8") as f:
                f.write(log_entry)
        except Exception as e:
            print(f"Error archiving intelligence: {e}")

    async def sleep_random(self, min_s=2, max_s=5):
        await asyncio.sleep(random.uniform(min_s, max_s))

    def get_stealth_headers(self):
        """Generates real-world browser headers to bypass bot detection for Indian high-security targets."""
        user_agent = ua_generator.random if ua_generator else random.choice(USER_AGENTS)
        return {
            "User-Agent": user_agent,
            "Accept-Language": "en-IN,en;q=0.9,en-US;q=0.8",
            "Accept-Encoding": "gzip, deflate, br",
            "Referer": "https://www.google.co.in/",
            "Sec-CH-UA": '"Not A(Brand";v="8", "Chromium";v="132", "Google Chrome";v="132"',
            "Sec-CH-UA-Mobile": "?0",
            "Sec-CH-UA-Platform": '"Windows"',
            "DNT": "1"
        }

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

    async def universal_ai_extract(self, html_content, prompt_type="general"):
        """Uses Gemini to extract structured lead data from any page text."""
        if not self.model:
            return {"error": "Gemini API key not configured"}

        clean_text = self.truncate_for_ai(html_content, 8000)
        
        prompts = {
            "general": f"""
                Scan this page text and extract all business leads. 
                For each lead, find: Company Name, Industry, Contact Info (Email/Phone), and Location.
                Text: {clean_text}
                Return exactly a JSON list of objects: [{{"company_name": "...", "industry": "...", "contact": "...", "location": "..."}}].
            """,
            "naukri": f"""
                Extract company details from this Naukri job post.
                Text: {clean_text}
                Return exactly a JSON object: {{"company_name": "...", "location": "...", "industry": "...", "requirements": "..."}}.
            """,
            "99acres": f"""
                Extract property listing details.
                Text: {clean_text}
                Return exactly a JSON object: {{"property_name": "...", "owner": "...", "contact": "...", "price": "...", "location": "..."}}.
            """,
            "shiksha": f"""
                Extract college/course details.
                Text: {clean_text}
                Return exactly a JSON object: {{"college_name": "...", "courses": "...", "location": "...", "contact": "..."}}.
            """
        }

        prompt = prompts.get(prompt_type, prompts["general"])
        # Ensure JSON response
        prompt += "\nReturn exactly in valid JSON format. If it's a list, return [{}]. If single object, return {}."

        # ARCHIVE: Prompt
        self.archive_intelligence(f"PROMPT_EXTRACT_{prompt_type}", prompt)

        try:
            response = self.model.generate_content(prompt)
            text = response.text.replace("```json", "").replace("```", "").strip()
            
            # ARCHIVE: Response
            self.archive_intelligence(f"RESPONSE_EXTRACT_{prompt_type}", text)

            # Basic JSON extraction
            start = text.find('[') if '[' in text else text.find('{')
            end = (text.rfind(']') + 1) if ']' in text else (text.rfind('}') + 1)
            if start != -1 and end != -1:
                return json.loads(text[start:end])
            return None
        except Exception as e:
            self.archive_intelligence(f"ERROR_EXTRACT_{prompt_type}", str(e))
            print(f"Universal AI Extract Error: {e}")
            return None

    async def enrichment_waterfall(self, page, company_name):
        """
        The Enrichment Waterfall logic:
        1. Official Site Search
        2. Google Dorks for Founder/CEO
        3. Email Pattern Mining (Heuristics)
        4. Social Cross-ref
        """
        data = {
            "website": "N/A",
            "founder": "N/A",
            "linkedin": "N/A",
            "email_guess": "N/A",
            "socials": {}
        }
        
        print(f"🌊 Starting Enrichment Waterfall for: {company_name}")
        
        # Stage 1: Official Site
        data["website"] = await self.recover_website(page, company_name)
        
        # Stage 2: DNS/Dork Search for Founder
        dork = f'site:linkedin.com/in/ "CEO" OR "Founder" "{company_name}"'
        await page.goto(f"https://www.google.com/search?q={dork.replace(' ', '+')}")
        await self.sleep_random(3, 5)
        
        links = await page.query_selector_all('a')
        for link in links:
            href = await link.get_attribute('href')
            if href and "linkedin.com/in/" in href:
                if "/url?q=" in href:
                    match = re.search(r'url\?q=([^&]*)', href)
                    if match: href = match.group(1)
                data["linkedin"] = href.split('&')[0]
                # Try to get name
                try:
                    container = await page.evaluate_handle('el => el.closest(".g")', link)
                    if container:
                        h3 = await container.as_element().query_selector('h3')
                        data["founder"] = await h3.inner_text() if h3 else "Found on LinkedIn"
                except: pass
                break
        
        # Stage 4: Team Page Discovery (New - Suggested by User)
        if data["founder"] == "N/A" and data["website"] != "N/A":
            try:
                # Try common paths to find real names
                for path in ["/about", "/about-us", "/our-team", "/management", "/leadership"]:
                    try:
                        target = data["website"].rstrip('/') + path
                        await page.goto(target, wait_until="load", timeout=15000)
                        text = await page.inner_text("body")
                        # Simple semantic match for leadership names
                        match = re.search(r"([A-Z][a-z]+ [A-Z][a-z]+) (?:is the )?(Founder|CEO|Owner|Director|Managing Director|CMO|CTO)", text)
                        if match:
                            data["founder"] = f"{match.group(1)} ({match.group(2)})"
                            break
                    except: continue
            except: pass

        # Stage 5: Twitter/X Dorking (New - Suggested by User)
        if data["founder"] == "N/A":
            try:
                twitter_dork = f'site:twitter.com OR site:x.com "{company_name}" founder'
                await page.goto(f"https://www.google.com/search?q={twitter_dork.replace(' ', '+')}", wait_until="load", timeout=15000)
                await self.sleep_random(2, 4)
                tw_match = await page.evaluate("""() => {
                    const h3 = document.querySelector('h3');
                    return h3 ? h3.innerText : null;
                }""")
                if tw_match: data["founder"] = f"{tw_match} (via Twitter)"
            except: pass

        # Stage 6: Email Pattern Guessing (Final stage)
        if data["website"] != "N/A" and data["founder"] != "N/A":
            try:
                domain = data["website"].replace("https://", "").replace("http://", "").replace("www.", "").split('/')[0]
                name_parts = data["founder"].split(' ')
                first = name_parts[0].lower().strip()
                last = name_parts[-1].lower().strip() if len(name_parts) > 1 else ""
                if first:
                    if last: data["email_guess"] = f"{first}.{last}@{domain}"
                    else: data["email_guess"] = f"{first}@{domain}"
            except: pass

        # Stage 7: Social Cross-ref
        if data["website"] != "N/A":
            try:
                await page.goto(data["website"], wait_until="networkidle", timeout=20000)
                data["socials"] = await self.extract_socials(page)
            except: pass
            
        return data

    async def scrape_naukri_job(self, page, url):
        """Specific logic for Naukri job posts."""
        try:
            await page.goto(url, wait_until="load", timeout=35000)
            await self.sleep_random(3, 5)
            html = await page.content()
            data = await self.universal_ai_extract(html, prompt_type="naukri")
            if data and isinstance(data, dict):
                # Enrich with waterfall
                wf = await self.enrichment_waterfall(page, data.get('company_name', ''))
                data.update(wf)
            return data
        except Exception as e:
            print(f"Naukri Scrape Error: {e}")
            return None

    async def scrape_99acres(self, page, url):
        """Specific logic for 99acres property listings."""
        try:
            await page.goto(url, wait_until="networkidle", timeout=30000)
            await self.sleep_random(3, 5)
            html = await page.content()
            data = await self.universal_ai_extract(html, prompt_type="99acres")
            return data
        except Exception as e:
            print(f"99acres Scrape Error: {e}")
            return None

    async def scrape_shiksha(self, page, url):
        """Specific logic for Shiksha colleges."""
        try:
            await page.goto(url, wait_until="networkidle", timeout=30000)
            await self.sleep_random(3, 5)
            html = await page.content()
            data = await self.universal_ai_extract(html, prompt_type="shiksha")
            return data
        except Exception as e:
            print(f"Shiksha Scrape Error: {e}")
            return None

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
            return "", [], {}, "N/A", "Unknown", 0

        print(f"Scraping website: {url}")
        start_time = time.time()
        content = ""
        emails = []
        socials = {}
        phone = "N/A"
        tech_stack = "Unknown"
        load_time = 0

        try:
            await page.goto(url, wait_until="networkidle", timeout=30000)
            load_time = time.time() - start_time
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
            
            return content[:5000], emails, socials, phone, tech_stack, load_time # First 5000 chars for LLM
        except Exception as e:
            print(f"Error scraping {url}: {e}")
            load_time = time.time() - start_time if load_time == 0 else load_time
            return "", [], {}, "N/A", "Unknown", load_time

    async def recover_website(self, page, company_name):
        """Searches Google for the company's official website if Maps entry is empty."""
        try:
            print(f"  🔍 Recovery Sweep: Searching for {company_name} website...")
            search_query = f'"{company_name}" official website'
            await page.goto(f"https://www.google.com/search?q={search_query.replace(' ', '+')}")
            await self.sleep_random(3, 5)
            
            # Look for non-social, non-directory links
            links = await page.query_selector_all('a')
            for link in links:
                href = await link.get_attribute('href')
                if not href: continue
                # Basic cleaning
                if "/url?q=" in href:
                    match = re.search(r'url\?q=([^&]*)', href)
                    if match: href = match.group(1)
                
                clean_url = href.split('&')[0].split('?')[0].lower()
                
                # Exclude social and directories
                excl = ["facebook.com", "instagram.com", "linkedin.com", "yelp.com", "yellowpages.com", "mapquest.com", "google.com", "twitter.com"]
                if clean_url.startswith("http") and not any(x in clean_url for x in excl):
                    print(f"  ✨ Recovered Website: {clean_url}")
                    return clean_url
        except Exception as e:
            print(f"  ⚠️ Recovery failed: {e}")
        return "N/A"

    async def recover_social(self, page, company_name, platform="linkedin"):
        """Searches Google for the company's social profile."""
        try:
            print(f"  🔍 Social Hunting: Searching for {company_name} {platform}...")
            search_query = f'"{company_name}" {platform}'
            await page.goto(f"https://www.google.com/search?q={search_query.replace(' ', '+')}")
            await self.sleep_random(2, 4)
            
            links = await page.query_selector_all('a')
            for link in links:
                href = await link.get_attribute('href')
                if href and f"{platform}.com" in href.lower():
                    # Clean Google redirect
                    if "/url?q=" in href:
                        match = re.search(r'url\?q=([^&]*)', href)
                        if match: href = match.group(1)
                    clean_url = href.split('&')[0].split('?')[0]
                    print(f"  ✨ Recovered {platform.capitalize()}: {clean_url}")
                    return clean_url
        except:
            pass
        return "N/A"

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
    
        # ARCHIVE: Prompt
        self.archive_intelligence(f"PROMPT_SCORE_{lead_name}", prompt)

        try:
            response = self.model.generate_content(prompt)
            # Handle possible markdown wrapping from LLM
            clean_text = response.text.replace("```json", "").replace("```", "").strip()
            
            # ARCHIVE: Response
            self.archive_intelligence(f"RESPONSE_SCORE_{lead_name}", clean_text)

            # If there's still extra text around the JSON, try to find the first { and last }
            start = clean_text.find('{')
            end = clean_text.rfind('}') + 1
            if start != -1 and end != 0:
                clean_text = clean_text[start:end]
                
            data = json.loads(clean_text)
            return data.get("score", 0), data.get("decision", "Neutral"), data.get("inferred_age", "Unknown"), data.get("reasoning", "Analyzed by AI")
        except Exception as e:
            self.archive_intelligence(f"ERROR_SCORE_{lead_name}", str(e))
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
        
        headers = self.get_stealth_headers()
        context = await browser.new_context(
            user_agent=headers["User-Agent"],
            extra_http_headers=headers,
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
        keyword_clean = keyword.replace('"', '')
        
        # If user provided a specific dork, use it as-is
        if "site:" in keyword.lower():
            return keyword
            
        # Expanded titles for broader reach
        titles = '("CEO" OR "Founder" OR "Owner" OR "Managing Director" OR "Partner" OR "President" OR "CMO" OR "CTO")'
        
        # If it's a niche search, add decision maker terms
        if len(keyword_clean.split()) > 2:
            # Flexible dork: site:linkedin.com/in auto repair shop nj
            base_dork = f'site:linkedin.com/in/ {keyword_clean}'
        else:
            # Strict niche: site:linkedin.com/in/ "Plumbing"
            base_dork = f'site:linkedin.com/in/ "{keyword_clean}"'
        
        # Add titles and exclude job/hr noise
        final_dork = f'{base_dork} {titles} -intitle:jobs -inurl:jobs -inurl:recruiter'
        return final_dork

    async def scrape_linkedin_profiles(self, page, keyword, is_dork=False, update_callback=None):
        """
        Scrapes LinkedIn profiles from Google search results.
        """
        if is_dork:
            dork = keyword
        else:
            dork = self.generate_dork(keyword)
            
        search_url = f"https://www.google.com/search?q={dork.replace(' ', '+')}"
        if update_callback: update_callback(f"🧬 LinkedIn X-Ray: {search_url}")
        
        try:
            # Shift to 'load' for more stability against trackers
            await page.goto(search_url, wait_until="load", timeout=40000)
            await self.sleep_random(3, 5)
            
            # Handle Google Consent Screen
            consent_selectors = [
                'button[aria-label="Accept all"]', 'button[aria-label="Agree"]',
                'button:has-text("Accept all")', 'button:has-text("I agree")',
                'div[role="button"]:has-text("Accept all")'
            ]
            for selector in consent_selectors:
                if await page.query_selector(selector):
                    if update_callback: update_callback("🔓 Handling Google Consent...")
                    await page.click(selector)
                    await self.sleep_random(2, 4)
                    break
        except Exception as e:
            if update_callback: update_callback(f"⚠️ Navigation warning: {str(e)[:50]}")

        # Human Scroll to trick bot detection and load more results
        if update_callback: update_callback("🖱️ Simulating Human Scroll on Google...")
        for _ in range(2):
            await page.evaluate("window.scrollBy(0, document.body.scrollHeight / 4)")
            await asyncio.sleep(1.5)

        # Blocker Status check
        page_title = await page.title()
        if "Before you continue" in page_title or "Captcha" in page_title or "blocked" in page_title.lower():
             if update_callback: update_callback(f"🔴 Blocker Status: CAPTCHA / Bot Detected")
             return []

        results = []
        links = await page.query_selector_all('a')
        processed_urls = set()
        
        if update_callback: update_callback(f"🔍 Found {len(links)} links. Filtering for LinkedIn profiles...")

        for link in links:
            if len(results) >= self.limit: break
            
            href = await link.get_attribute('href')
            # Broad match for linkedin urls
            if href and ("linkedin.com/in/" in href or "linkedin.com/company/" in href):
                # Clean Google redirect
                if "/url?q=" in href:
                    match = re.search(r'url\?q=([^\&]*)', href)
                    if match: href = match.group(1)
                
                clean_url = href.split('&')[0].split('?')[0]
                if clean_url in processed_urls: continue
                processed_urls.add(clean_url)
                
                try:
                    # More robust container detection
                    container = await page.evaluate_handle('el => el.closest(".g, .MjjYud, div[data-hveid]")', link)
                    if container:
                        h3 = await container.as_element().query_selector('h3')
                        name = await h3.inner_text() if h3 else "LinkedIn User"
                        
                        # Broader snippet selectors
                        snippet_el = await container.as_element().query_selector('.VwiC3b, .y355M, .IsZvec, .MUY17c, .kb0BC')
                        snippet = await snippet_el.inner_text() if snippet_el else "No snippet available"
                    else:
                        name = await link.inner_text() or "LinkedIn User"
                        snippet = "No snippet available"
                except:
                    name = "LinkedIn User"
                    snippet = "No snippet available"
                
                # Check for "LinkedIn" in name to avoid false positives
                if "linkedin" in name.lower() and len(name) < 15: # Skip if name is just "LinkedIn"
                    continue

                results.append({"name": name, "url": clean_url, "snippet": snippet})
                if update_callback: update_callback(f"👤 Discovered: {name}")

        return results

    async def scrape_linkedin_posts(self, page, keyword, is_dork=False, update_callback=None):
        """
        Scrapes LinkedIn POSTS from Google search results to find buying signals.
        keyword: Either a plain keyword or a pre-built dork string
        is_dork: If True, use keyword as-is. If False, generate dork from keyword.
        Returns: (results, blocker_status)
        """
        print(f"🎯 Signal Scraper: Targeting LinkedIn Posts for: {keyword}")
        if update_callback: update_callback(f"🎯 Signal Scraper: {keyword}")
        
        # Generate dork if not already provided
        if is_dork:
            dork = keyword
    async def scrape_linkedin_posts(self, page, keyword, is_dork=False, update_callback=None):
        """
        Scrapes LinkedIn POSTS from Google search results to find buying signals.
        """
        if is_dork:
            dork = keyword
        else:
            dork = f'site:linkedin.com/posts "{keyword}"'
            
        search_url = f"https://www.google.com/search?q={dork.replace(' ', '+')}"
        if update_callback: update_callback(f"📡 Signal Search: {search_url}")
        
        blocker_status = "🟢 OK"
        
        try:
            await page.goto(search_url, wait_until="load", timeout=40000)
            await self.sleep_random(3, 5)
            
            # Handle Google Consent Screen
            consent_selectors = ['button[aria-label="Accept all"]', 'button[aria-label="Agree"]', 'div[role="button"]:has-text("Accept all")']
            for selector in consent_selectors:
                if await page.query_selector(selector):
                    await page.click(selector)
                    await self.sleep_random(2, 4)
                    blocker_status = "🟡 Consent Handled"
                    break
        except:
            blocker_status = "🟡 Navigation Slow"

        # Human Scroll
        await page.evaluate("window.scrollBy(0, 500)")
        await asyncio.sleep(1)

        # BLOCKER DETECTION
        page_title = await page.title()
        if "Before you continue" in page_title or "Captcha" in page_title or "blocked" in page_title.lower():
            blocker_status = "🔴 CAPTCHA/Consent Block"
            if update_callback: update_callback(f"⚠️ Blocker: {page_title}")
            return [], blocker_status
        
        results = []
        links = await page.query_selector_all('a')
        processed_urls = set()

        for link in links:
            if len(results) >= self.limit: break
            
            href = await link.get_attribute('href')
            if href and ("linkedin.com/posts/" in href or "linkedin.com/in/" in href):
                if "/url?q=" in href:
                    match = re.search(r'url\?q=([^\&]*)', href)
                    if match: href = match.group(1)
                
                clean_url = href.split('&')[0].split('?')[0]
                if clean_url in processed_urls: continue
                processed_urls.add(clean_url)
                
                try:
                    container = await page.evaluate_handle('el => el.closest(".g, .MjjYud, div[data-hveid]")', link)
                    if container:
                        h3 = await container.as_element().query_selector('h3')
                        name = await h3.inner_text() if h3 else "LinkedIn User"
                        
                        snippet_el = await container.as_element().query_selector('.VwiC3b, .y355M, .IsZvec, .MUY17c, .kb0BC')
                        snippet = await snippet_el.inner_text() if snippet_el else "No snippet available"
                    else:
                        name = "LinkedIn User"
                        snippet = "No snippet available"
                except:
                    name = "LinkedIn User"
                    snippet = "No snippet available"
                
                signal, signal_preview = self.detect_buying_signal(snippet)
                results.append({
                    "name": name, 
                    "url": clean_url, 
                    "snippet": snippet,
                    "signal": signal,
                    "content_preview": snippet[:100]
                })
                if update_callback: update_callback(f"🎯 Signal Found: {name}")

        return results, blocker_status

    async def score_linkedin_ai(self, profile_name, snippet_text, signal_type="👤 Profile"):
        if not self.model:
            return "Pending", "Pending", "LinkedIn", "Pending AI Review", "N/A"

        # Handle empty snippets to avoid AI confusion
        if snippet_text == "No snippet available" or len(snippet_text) < 10:
             return 40, "Neutral", "LinkedIn", "Minimal context available", "I saw your profile on LinkedIn."

        prompt = f"""
        Analyze this LinkedIn profile snippet for '{profile_name}'.
        Signal Category: {signal_type}
        Snippet: {snippet_text}
        
        Goal: Score (0-100) based on relevance to a 'High Ticket B2B' target.
        Also, write a highly personalized 'Automated AI Icebreaker' (1 sentence max).
        - If recent post signal: "I saw your recent post about [Topic]; I loved your point about [Detail]."
        - If hiring signal: "I saw you're looking for help with [Role]; I'd love to help automate your lead gen."
        - Be professional, surgical, and short.
        
        Return exactly in this JSON format:
        {{
            "score": <integer>,
            "decision": "<Qualified/Neutral/Not Qualified>",
            "summary": "<1-sentence summary of their role>",
            "icebreaker": "<the icebreaker text>"
        }}
        """
        # ARCHIVE: Prompt
        self.archive_intelligence(f"PROMPT_LINKEDIN_{profile_name}", prompt)

        try:
            response = self.model.generate_content(prompt)
            clean_text = response.text.replace("```json", "").replace("```", "").strip()
            
            # ARCHIVE: Response
            self.archive_intelligence(f"RESPONSE_LINKEDIN_{profile_name}", clean_text)

            start = clean_text.find('{')
            end = clean_text.rfind('}') + 1
            data = json.loads(clean_text[start:end])
            return (
                data.get("score", 50), 
                data.get("decision", "Neutral"), 
                "LinkedIn", 
                data.get("summary", "Analyzed Profile"),
                data.get("icebreaker", "I saw your profile on LinkedIn and was impressed by your work.")
            )
        except Exception as e:
            self.archive_intelligence(f"ERROR_LINKEDIN_{profile_name}", str(e))
            return 50, "Neutral", "LinkedIn", "AI Score Failed", "I saw your profile on LinkedIn."

    def detect_buying_signal(self, snippet_text):
        """
        Detects buying signals from Google snippet text.
        Returns: (signal_type, icebreaker_placeholder)
        """
        hiring_keywords = ["hiring", "looking for freelancer", "looking for a freelancer", "need a", "recruiting", "looking to hire", "looking for help"]
        frustration_keywords = ["frustrated with", "issues with", "problem with", "struggling with", "having trouble", "doesn't work"]
        advice_keywords = ["recommend a", "recommend an", "looking for agency", "looking for a", "need help with", "suggestions for", "anyone know"]
        
        snippet_lower = snippet_text.lower()
        
        # Premium/Open Profile detection
        is_open = "premium" in snippet_lower or "open profile" in snippet_lower
        
        if any(kw in snippet_lower for kw in hiring_keywords):
            signal = "📢 Hiring"
        elif any(kw in snippet_lower for kw in frustration_keywords):
            signal = "🛠️ Frustration"
        elif any(kw in snippet_lower for kw in advice_keywords):
            signal = "💡 Advice"
        else:
            signal = "👤 Profile"

        if is_open:
            signal = f"🔓 {signal}"
            
        return signal, "Analyzing via AI..."

    async def run_mission(self, keyword=None, update_callback=None, progress_callback=None, enrich_with_xray=False):
        target_keyword = keyword if keyword else self.keyword
        if not target_keyword:
            print("❌ No keyword provided for mission.")
            return []

        # 0. Checkpoint: Load History
        print("Loading mission history...")
        history = self.gsheets.get_existing_leads()
        existing_websites = history.get("urls", set())
        existing_names = history.get("names", set())

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
            website = basic_info.get("website", "N/A")
            name = basic_info.get("name", "Unknown")
            
            # Smart Duplicate Check
            is_duplicate = False
            if website.lower() not in ["n/a", "unknown", "none", ""] and website in existing_websites:
                is_duplicate = True
                msg = f"Skipping {name} (Duplicate Website)"
            elif name in existing_names:
                is_duplicate = True
                msg = f"Skipping {name} (Duplicate Name)"
                
            if is_duplicate:
                if update_callback: update_callback(msg)
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
                        
                        # --- WEBSITE RECOVERY SWEEP ---
                        if company.get("website") == "N/A":
                            company["website"] = await self.recover_website(page, company["name"])
                        
                        # Scrape with strict timeout
                        website_content, emails, socials, phone, tech_stack, load_time = await self.scrape_website(page, company["website"])
                        
                        # --- SOCIAL RECOVERY SWEEP ---
                        if socials.get("linkedin") == "N/A":
                            socials["linkedin"] = await self.recover_social(page, company["name"], "linkedin")
                        if socials.get("instagram") == "N/A":
                            socials["instagram"] = await self.recover_social(page, company["name"], "instagram")
                        if socials.get("facebook") == "N/A":
                            socials["facebook"] = await self.recover_social(page, company["name"], "facebook")

                        company["email"] = ", ".join(emails) if emails else "N/A"
                        company["phone"] = phone
                        company["tech_stack"] = tech_stack
                        company["source"] = "Google Maps"
                        company.update(socials)

                        # ENHANCED SIGNAL & OPPORTUNITY LOGIC
                        
                        # 1. GMB STATUS & OPP
                        if company.get("is_unclaimed", False):
                            company["gmb_status"] = "🚩 Unclaimed"
                            company["gmb_opp"] = "Pitch: Claim and Optimize GMB Profile."
                        elif company.get("reviews", 0) < 10:
                            company["gmb_status"] = f"⚠️ Low Reviews ({company.get('reviews')})"
                            company["gmb_opp"] = "Pitch: Automated Review Management."
                        else:
                            company["gmb_status"] = "✅ Healthy"
                            company["gmb_opp"] = "N/A"

                        # 2. AD ACTIVITY & OPP
                        if "Meta Pixel" not in tech_stack:
                            company["ad_status"] = "📉 Not running Meta Ads"
                            company["ad_opp"] = "Pitch: Lead Generation Automation."
                        else:
                            company["ad_status"] = "🚀 Active"
                            company["ad_opp"] = "N/A"
                            
                        # 3. WEB STATUS & OPP
                        if company.get("website", "N/A") == "N/A":
                            company["web_status"] = "🚫 No Site"
                            company["web_opp"] = "Pitch: High-Converting Landing Page Build."
                        elif "WordPress" in tech_stack or "Basic" in tech_stack:
                            company["web_status"] = "🕸️ Old WP / Basic"
                            company["web_opp"] = "Pitch: Performance Marketing / CRO."
                        else:
                            company["web_status"] = "💎 Modern"
                            company["web_opp"] = "N/A"

                        # 4. WEB SPEED & OPP
                        if company.get("website", "N/A") == "N/A":
                            company["speed_status"] = "N/A (No Site)"
                            company["speed_opp"] = "N/A"
                        elif load_time > 5:
                            company["speed_status"] = f"🐢 Slow ({load_time:.1f}s)"
                            company["speed_opp"] = "Pitch: Website Optimization / Speed."
                        else:
                            company["speed_status"] = f"⚡ Fast ({load_time:.1f}s)"
                            company["speed_opp"] = "N/A"
                            
                        # 5. X-RAY MATCH & OPP
                        company["xray_status"] = "❓ Not Found"
                        company["xray_opp"] = "Pitch: Direct Outreach / LinkedIn DM."

                        # QUERY-BASED OVERRIDES (High-Intent)
                        if "emergency" in target_keyword.lower():
                            company["ad_opp"] = "Pitch: PPC / Google Ads (Urgent need)."
                        if "new" in target_keyword.lower():
                            company["gmb_opp"] = "Pitch: Launch Marketing / Google Business Setup."
                        if "open now" in target_keyword.lower():
                            company["ad_opp"] = "Pitch: Real-Time Lead Engagement / Call-Only Campaigns."

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
                            xray_results = await self.scrape_linkedin_profiles(page, xray_dork, update_callback=update_callback)
                            self.limit = original_limit # Reset limit
                            
                            if xray_results:
                                founder = xray_results[0] # Take top result
                                founder_info = f"{founder['name']} ({founder['url']})"
                                company['founder_match'] = founder_info
                                company['xray_status'] = "👤 Found Founder"
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
                        "ad": company_data.get("ad_status", "N/A"),
                        "web": company_data.get("web_status", "N/A"),
                        "speed": company_data.get("speed_status", "N/A"),
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

    async def run_linkedin_mission(self, keyword=None, update_callback=None, signal_mode=False):
        target_keyword = keyword if keyword else self.keyword
        if not target_keyword:
            return []

        async with async_playwright() as p:
            browser, page = await self.get_browser_and_page(p)
            
            if update_callback: 
                mode_text = "Signal Mode (Posts)" if signal_mode else "Profile Mode"
                update_callback(f"Starting X-Ray Mission Control: {target_keyword} | {mode_text}")
            
            # Detect if keyword is already a dork (contains "site:")
            is_already_dork = "site:" in target_keyword.lower()
            
            # Choose scraping method based on signal_mode
            if signal_mode:
                # Use signal-based post scraping
                profiles, blocker_status = await self.scrape_linkedin_posts(page, target_keyword, is_dork=is_already_dork, update_callback=update_callback)
            else:
                # Use traditional profile scraping
                profiles = await self.scrape_linkedin_profiles(page, target_keyword, is_dork=is_already_dork)
                # Check for blocker status in profile mode too
                page_title = await page.title()
                if "Captcha" in page_title or "Before you continue" in page_title:
                    blocker_status = "🔴 CAPTCHA Block"
                elif not profiles:
                    # --- ATTEMPT 2: BROAD SEARCH FALLBACK ---
                    if update_callback: update_callback("⚠️ No specific results. Trying Broad LinkedIn Hunt...")
                    broad_dork = f'site:linkedin.com/in/ {target_keyword}'
                    profiles = await self.scrape_linkedin_profiles(page, broad_dork, is_dork=True, update_callback=update_callback)
                    
                    if not profiles:
                        # --- ATTEMPT 3: NATURAL LANGUAGE FALLBACK ---
                        if update_callback: update_callback("🧬 Aggressive Mode: Trying Natural Language Search...")
                        # Search without site: filter, and WITHOUT strict quotes for the full phrase
                        nat_query = f'{target_keyword} linkedin profiles'
                        profiles = await self.scrape_linkedin_profiles(page, nat_query, is_dork=False, update_callback=update_callback)
                        
                        if not profiles:
                            # --- ATTEMPT 4: NUCLEAR HUNT FALLBACK ---
                            if update_callback: update_callback("☢️ Final Attempt: Nuclear LinkedIn Hunt...")
                            nuke_query = f'{target_keyword} linkedin'
                            profiles = await self.scrape_linkedin_profiles(page, nuke_query, 
                                                   is_dork=True, update_callback=update_callback)
                            
                            if not profiles:
                                blocker_status = "🟡 No Results Found"
                            else:
                                blocker_status = "🟢 OK (Nuclear Hunt)"
                        else:
                            blocker_status = "🟢 OK (Natural Hunt)"
                    else:
                        blocker_status = "🟢 OK (Broad Hunt)"
                else:
                    blocker_status = "🟢 OK"
            
            # Report blocker status
            if update_callback: update_callback(f"Blocker Status: {blocker_status}")
            
            # CRITICAL: Close browser immediately after scraping profiles
            await browser.close()

            final_leads = []
            for profile in profiles:
                if update_callback: update_callback(f"AI Analyzing Profile Snippet: {profile['name']}...")
                
                # Analyze using the SNIPPET to stay logged out / safe
                score, decision, _, summary, icebreaker = await self.score_linkedin_ai(profile["name"], profile["snippet"], profile.get("signal", "Profile"))
                
                lead = {
                    "name": profile["name"],
                    "source": "LinkedIn Post" if signal_mode else "LinkedIn Profile",
                    "url": profile["url"],
                    "score": score,
                    "decision": decision,
                    "summary": summary,
                    "signal": profile.get("signal", "👤 Profile"),
                    "icebreaker": icebreaker,
                    "content_preview": profile.get("content_preview", profile["snippet"][:100])
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
                    "summary": summary,
                    "source": "LinkedIn " + ("Post" if "Post" in source.capitalize() else "Profile") if "linkedin" in source.lower() else source.capitalize()
                }
                
                # Save using the smart router
                self.gsheets.save_lead(lead, query=dork_query, source=source)
                final_leads.append(lead)
                
            if update_callback: update_callback(f"Mission Done. {len(final_leads)} Leads saved to GSheets.")
            return final_leads

    def detect_source(self, query):
        """
        Smart detection: If it looks like a person search (CEO, Founder, Manager, LinkedIn)
        it goes to LinkedIn. Otherwise, it detects niche-specific directories.
        """
        q_lower = query.lower()
        person_terms = ["ceo", "founder", "owner", "manager", "director", "head", "vp", "president", "linkedin", "profile"]
        job_terms = ["hiring", "job", "vacancy", "career", "work at"]
        property_terms = ["flat for sale", "property in", "resale property", "house for sale", "rent plot"]
        edu_terms = ["college", "university", "admission", "course info"]

        if any(term in q_lower for term in person_terms):
            return "linkedin"
        if any(term in q_lower for term in job_terms):
            return "naukri"
        if any(term in q_lower for term in property_terms):
            return "99acres"
        if any(term in q_lower for term in edu_terms):
            return "shiksha"
        return "google"

    async def run_smart_mission(self, query, update_callback=None):
        source = self.detect_source(query)
        if source == "linkedin":
            if update_callback: update_callback(f"🧠 Smart Routing: Detected LinkedIn target for '{query}'")
            return await self.run_linkedin_mission(query, update_callback)
        elif source == "naukri":
            if update_callback: update_callback(f"🧠 Smart Routing: Detected Job Market target. Searching Naukri...")
            # We need a search URL for Naukri, generate a basic one
            search_url = f"https://www.naukri.com/{query.replace(' ', '-')}-jobs"
            return await self.run_naukri_mission(search_url, update_callback)
        elif source == "99acres":
            if update_callback: update_callback(f"🧠 Smart Routing: Detected Real Estate target. Searching 99acres...")
            search_url = f"https://www.99acres.com/search/property/buy/residential-all/{query.replace(' ', '-')}"
            return await self.run_universal_mission([search_url], prompt_type="99acres", update_callback=update_callback)
        elif source == "shiksha":
            if update_callback: update_callback(f"🧠 Smart Routing: Detected Education target. Searching Shiksha...")
            search_url = f"https://www.shiksha.com/search-result?q={query.replace(' ', '+')}"
            return await self.run_universal_mission([search_url], prompt_type="shiksha", update_callback=update_callback)
        else:
            if update_callback: update_callback(f"🧠 Smart Routing: Detected Local Business target for '{query}'")
            return await self.run_mission(query, update_callback, enrich_with_xray=True)

    async def run_universal_mission(self, urls, prompt_type="general", update_callback=None):
        """Processes a list of URLs using the Universal AI Scraper."""
        results = []
        total = len(urls)
        
        async with async_playwright() as p:
            browser, page = await self.get_browser_and_page(p)
            try:
                for i, url in enumerate(urls):
                    if update_callback: update_callback(f"🌐 Scraping [{i+1}/{total}]: {url}")
                    
                    try:
                        await page.goto(url, wait_until="load", timeout=35000)
                        await self.sleep_random(2, 4)
                        
                        # Human Scroll for Lazy Loading
                        await page.evaluate("window.scrollBy(0, document.body.scrollHeight / 2)")
                        await asyncio.sleep(2)
                        
                        html = await page.content()
                        
                        extracted = await self.universal_ai_extract(html, prompt_type=prompt_type)
                        
                        if extracted:
                            # If it returns a list, extend, else append
                            if isinstance(extracted, list):
                                for item in extracted:
                                    item["source_url"] = url
                                    item["source"] = f"Universal ({prompt_type})"
                                    self.gsheets.save_lead(item, query=url, source="universal")
                                    results.append(item)
                            else:
                                extracted["source_url"] = url
                                extracted["source"] = f"Universal ({prompt_type})"
                                self.gsheets.save_lead(extracted, query=url, source="universal")
                                results.append(extracted)
                            
                            if update_callback: update_callback(f"✅ Extracted {len(extracted) if isinstance(extracted, list) else 1} leads from {url}")
                        else:
                            if update_callback: update_callback(f"⚠️ AI failed to extract data from {url}")
                            
                    except Exception as e:
                        if update_callback: update_callback(f"❌ Error on {url}: {e}")
            finally:
                await browser.close()
        
        return results

    async def run_naukri_mission(self, search_url, update_callback=None):
        """Specialized mission for Naukri: Scrape Job -> Company Name -> Enrichment Waterfall."""
        results = []
        job_links = []
        
        async with async_playwright() as p:
            browser, page = await self.get_browser_and_page(p)
            try:
                if update_callback: update_callback(f"💼 Searching Naukri: {search_url}")
                await page.goto(search_url, wait_until="load", timeout=40000)
                await self.sleep_random(3, 5)
                
                # Check for immediate block
                title = await page.title()
                if "Access Denied" in title or "Cloudflare" in title or not title or "blocked" in title.lower():
                    if update_callback: update_callback("🔴 Naukri Blocked Direct Access! Switching to SERP Backdoor (Google X-Ray)...")
                    
                    # Convert Naukri URL to a Google Query
                    # Extract keywords from URL if possible
                    query = "site:naukri.com/job-listings"
                    if "naukri.com" in search_url:
                        # Simple extraction of last part of URL as keywords
                        clean_search = search_url.split('/')[-1].replace('-', ' ')
                        query = f'site:naukri.com/job-listings "{clean_search}"'
                    
                    import urllib.parse
                    google_url = f"https://www.google.com/search?q={urllib.parse.quote(query)}"
                    await page.goto(google_url, wait_until="load")
                    await self.sleep_random(3, 5)
                    
                    # Extract from Google Results
                    job_links = await page.evaluate("""() => {
                        const links = Array.from(document.querySelectorAll('a[href*="naukri.com/job-listings-"]'));
                        return links.map(a => a.href).slice(0, 10);
                    }""")
                    if update_callback: update_callback(f"🧬 SERP Backdoor: Found {len(job_links)} jobs via Google.")
                else:
                    # Humanized Scroll Loop (using wheel to mimic human behavior)
                    if update_callback: update_callback("🖱️ Humanized Scroll: Simulating mouse interaction...")
                    for _ in range(3):
                        await page.mouse.wheel(0, random.randint(400, 900))
                        await asyncio.sleep(random.uniform(1.5, 3.0))
                    
                    # Extract job URLs
                    job_links = await page.evaluate("""() => {
                        const links = Array.from(document.querySelectorAll('a.title, a[href*="/job-listings-"]'));
                        return links.map(a => a.href).slice(0, 10);
                    }""")
            except Exception as e:
                if update_callback: update_callback(f"❌ Search Error: {e}")
            finally:
                await browser.close()
        
        if not job_links:
            if update_callback: update_callback("⚠️ No job links found. Mission stalled.")
            return []

        if update_callback: update_callback(f"🔍 Processing {len(job_links)} job posts...")

        # Phase 2: Fresh Browser per Job
        for i, job_url in enumerate(job_links):
            if update_callback: update_callback(f"📄 Analyzing Job [{i+1}/{len(job_links)}]: {job_url}")
            
            async with async_playwright() as p:
                browser, page = await self.get_browser_and_page(p)
                try:
                    job_data = await self.scrape_naukri_job(page, job_url)
                    if job_data:
                        job_data["source"] = "Naukri Intelligence"
                        job_data["source_url"] = job_url
                        self.gsheets.save_lead(job_data, query=search_url, source="naukri")
                        results.append(job_data)
                        name = job_data.get('company_name') or job_data.get('Company Name') or "Unknown"
                        if update_callback: update_callback(f"✅ Saved Company: {name}")
                except Exception as ex:
                    if update_callback: update_callback(f"⚠️ Error analyzing job: {ex}")
                finally:
                    await browser.close()
                    gc.collect() 
        
        return results

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
