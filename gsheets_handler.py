import gspread
from google.oauth2.service_account import Credentials
import os
import datetime
from dotenv import load_dotenv

load_dotenv()
if os.path.exists(".env.local"):
    load_dotenv(".env.local", override=True)

class GSheetsHandler:
    def __init__(self):
        self.scope = [
            "https://spreadsheets.google.com/feeds",
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive.file",
            "https://www.googleapis.com/auth/drive"
        ]
        self.credentials_file = os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE", "google-credentials.json")
        self.sheet_id = os.getenv("GOOGLE_SHEET_ID")
        self.sheet_gid = os.getenv("GOOGLE_SHEET_GID", "0") # Default to 0 (first tab)
        
        # CLEANING: If the user pasted a full URL, extract the ID
        if self.sheet_id and "docs.google.com" in self.sheet_id:
            try:
                # Extract ID from /d/ID_HERE/
                self.sheet_id = self.sheet_id.split("/d/")[1].split("/")[0]
                print(f"[INFO] Cleaned Sheet ID from URL: {self.sheet_id}")
            except Exception as e:
                print(f"[WARN] Failed to parse URL for Sheet ID: {e}")

        self.client = None
        self.sheet = None
        self.spreadsheet = None

    def get_wa_count(self):
        """Persistent daily counter for WhatsApp safety to survive reboots."""
        import datetime
        today = datetime.date.today().isoformat()
        path = "wa_stats.txt"
        if os.path.exists(path):
            try:
                with open(path, "r") as f:
                    content = f.read().split(',')
                    if content[0] == today:
                        return int(content[1])
            except: pass
        return 0

    def save_wa_count(self, count):
        """Saves current count with today's date."""
        import datetime
        today = datetime.date.today().isoformat()
        with open("wa_stats.txt", "w") as f:
            f.write(f"{today},{count}")

    def load_search_offsets_from_cloud(self):
        """Fetches cross-device search offsets to share keywords between PC and mobile."""
        if not self.spreadsheet:
            self.connect()
        offsets = {}
        try:
            sheet = self.spreadsheet.worksheet("Missions")
            records = sheet.get_all_records()
            for row in records:
                kw = str(row.get("Keyword", "")).lower().strip()
                if kw:
                    offsets[kw] = int(row.get("Offset", 0))
        except Exception as e:
            print(f"[WARN] No shared history setup found, using clean defaults: {e}")
        return offsets

    def update_cloud_search_offset(self, keyword, offset):
        """Saves a search checkpoint to Google Sheets instantly to sync with other devices."""
        if not self.spreadsheet:
            self.connect()
        try:
            try:
                sheet = self.spreadsheet.worksheet("Missions")
            except gspread.exceptions.WorksheetNotFound:
                sheet = self.spreadsheet.add_worksheet(title="Missions", rows="1000", cols="5")
                sheet.append_row(["Keyword", "Offset", "Timestamp"])
            
            import datetime
            sheet.append_row([keyword.lower().strip(), offset, datetime.datetime.now().strftime("%Y-%m-%d %H:%M")])
        except Exception as e:
            print(f"[ERROR] Failed syncing cross-device metadata: {e}")


    def connect(self):
        try:
            creds = None
            json_creds = os.getenv("GOOGLE_CREDENTIALS_JSON") or os.getenv("GSHEETS_JSON")
            
            if json_creds:
                import json
                try:
                    info = json.loads(json_creds)
                    creds = Credentials.from_service_account_info(info, scopes=self.scope)
                    print(f"[INFO] Credentials loaded. Service Account: {info.get('client_email')}")
                except Exception as e:
                    print(f"[ERROR] Error parsing GOOGLE_CREDENTIALS_JSON: {e}")

            if not creds:
                if not os.path.exists(self.credentials_file):
                    print(f"[ERROR] No credentials via ENV or FILE ({self.credentials_file}) found.")
                    return False
                creds = Credentials.from_service_account_file(self.credentials_file, scopes=self.scope)
            
            self.client = gspread.authorize(creds)
            
            if self.sheet_id:
                try:
                    print(f"[INFO] Opening spreadsheet by ID: {self.sheet_id}")
                    spreadsheet = self.client.open_by_key(self.sheet_id)
                    
                    # Target specific GID if provided
                    if self.sheet_gid and self.sheet_gid != "0":
                        try:
                            print(f"[INFO] Targeting specific GID (Tab): {self.sheet_gid}")
                            self.sheet = spreadsheet.get_worksheet_by_id(int(self.sheet_gid))
                            if not self.sheet:
                                print(f"[WARN] GID {self.sheet_gid} not found. Falling back to first tab.")
                                self.sheet = spreadsheet.get_worksheet(0)
                        except Exception as gid_err:
                            print(f"[WARN] GID Error: {gid_err}. Using first tab.")
                            self.sheet = spreadsheet.get_worksheet(0)
                    else:
                        self.sheet = spreadsheet.get_worksheet(0)
                        
                    self.spreadsheet = spreadsheet
                    print(f"[OK] Sheet '{self.sheet.title}' opened successfully.")
                except Exception as e:
                    print(f"[ERROR] Failed to open spreadsheet by ID: {e}")
                    return False
            else:
                try:
                    print("[INFO] No GOOGLE_SHEET_ID found. Attempting to open by name: 'Lead Hunter Results'")
                    self.spreadsheet = self.client.open("Lead Hunter Results")
                    self.sheet = self.spreadsheet.get_worksheet(0)
                    print(f"[OK] Found sheet by name: {self.sheet.title}")
                except Exception as e:
                    print(f"[ERROR] Failed to open 'Lead Hunter Results': {e}")
                    print("[TIP] Add GOOGLE_SHEET_ID to your Render Environment variables and share the sheet with the Service Account email.")
                    return False
            
            # Ensure headers are up to date
            self.sync_headers()
            
            return True
        except Exception as e:
            print(f"[ERROR] Error connecting to Google Sheets: {e}")
            return False

    def sync_headers(self, target_sheet=None):
        """Checks if headers match the expected layout and updates if necessary."""
        sheet = target_sheet if target_sheet else self.sheet
        if not sheet: return

        try:
            expected_headers = [
                "Keyword", "Company Name", "Website", "Emails", "Phone", "Address", "LinkedIn", 
                "Instagram", "Facebook", "Tech Stack",
                "Score", "Decision", "Summary", 
                "GMB Status", "GMB Opp", 
                "Ad Activity", "Ad Opp", 
                "Web Status", "Web Opp", 
                "Web Speed", "Speed Opp", 
                "X-Ray Match", "X-Ray Opp",
                "Icebreaker", "Source", "Date Added"
            ]
            
            # Special case for LinkedIn specific tab
            if "LinkedIn" in sheet.title:
                expected_headers = ["Keyword", "Name", "LinkedIn URL", "Score", "Summary", "Decision", "Signal", "Icebreaker", "Source", "Date Added"]

            current_vals = sheet.get_all_values()
            if not current_vals:
                print(f"[INFO] Sheet '{sheet.title}' empty. Initializing headers...")
                sheet.append_row(expected_headers)
                return

            current_row1 = [v.strip() for v in current_vals[0]]
            
            # Check if any expected header is missing or mismatch
            if len(current_row1) < len(expected_headers) or "Date Added" not in current_row1:
                print(f"[INFO] Headers in '{sheet.title}' outdated. Updating header row...")
                sheet.update('A1', [expected_headers])
        except Exception as e:
            print(f"[WARN] Header Sync Error: {e}")

    import time

    def safe_append(self, sheet, row_data):
        """Exponential backoff wrapper for append_row to handle 503 errors."""
        import time
        for attempt in range(4): # Try up to 4 times
            try:
                return sheet.append_row(row_data)
            except Exception as e:
                if "503" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
                    wait = 2 * (attempt + 1)
                    print(f"[WARN] GSheets Busy (503). Retrying in {wait}s...")
                    time.sleep(wait)
                else:
                    raise e
        return False

    def save_lead(self, data, query, source="google"):
        """
        Routes data to the correct worksheet based on source and app mode.
        """
        try:
            # Ensure connection is active
            if not self.client:
                self.connect()

            # Dynamic Worksheet Routing based on App Mode
            target_sheet_name = "Leads" # Default
            
            # Check for Streamlit session state if running in dashboard
            import sys
            app_mode = "Unified Hunter"
            if 'streamlit' in sys.modules:
                import streamlit as st
                if 'app_mode' in st.session_state:
                    app_mode = st.session_state.app_mode

            if source == "linkedin":
                target_sheet_name = "LinkedIn Leads"
            elif "Universal" in app_mode:
                target_sheet_name = "Universal Leads"
            elif "Naukri" in app_mode:
                target_sheet_name = "Naukri Leads"
            elif "99acres" in app_mode:
                target_sheet_name = "Property Leads"
            elif "Shiksha" in app_mode:
                target_sheet_name = "Education Leads"
            elif source == "google":
                target_sheet_name = "Google Leads"

            # Get or Create Worksheet
            sheet = self.get_or_create_worksheet(target_sheet_name, source)
            
            # Sync headers for this specific sheet
            self.sync_headers(sheet)

            # Build Row Data
            if target_sheet_name == "LinkedIn Leads" or source == "linkedin":
                row = [
                    query,
                    data.get('name', 'N/A'),
                    data.get('url', 'N/A'),
                    data.get('score', 0),
                    data.get('summary', 'N/A'),
                    data.get('decision', 'N/A'),
                    data.get('signal', 'N/A'),
                    data.get('icebreaker', 'N/A'),
                    data.get('source', "LinkedIn"),
                    data.get('date_added', (datetime.datetime.now() + datetime.timedelta(hours=5, minutes=30)).strftime("%Y-%m-%d %H:%M:%S IST"))
                ]
            else:
                # Full Enrichment Row for everything else
                row = [
                    query,
                    data.get('name', data.get('company_name', data.get('property_name', 'N/A'))),
                    data.get('website', data.get('source_url', 'N/A')),
                    data.get('email', data.get('email_guess', 'N/A')),
                    data.get('phone', 'N/A'),
                    data.get('address', 'N/A'),
                    data.get('linkedin', 'N/A'),
                    data.get('instagram', 'N/A'),
                    data.get('facebook', 'N/A'),
                    data.get('tech_stack', 'N/A'),
                    data.get('score', 0),
                    data.get('decision', 'N/A'),
                    data.get('summary', data.get('reasoning', 'N/A')),
                    data.get('gmb_status', 'N/A'),
                    data.get('gmb_opp', 'N/A'),
                    data.get('ad_status', 'N/A'),
                    data.get('ad_opp', 'N/A'),
                    data.get('web_status', 'N/A'),
                    data.get('web_opp', 'N/A'),
                    data.get('speed_status', 'N/A'),
                    data.get('speed_opp', 'N/A'),
                    data.get('xray_status', 'N/A'),
                    data.get('xray_opp', 'N/A'),
                    data.get('icebreaker', 'N/A'),
                    data.get('source', app_mode),
                    data.get('date_added', (datetime.datetime.now() + datetime.timedelta(hours=5, minutes=30)).strftime("%Y-%m-%d %H:%M:%S IST"))
                ]

            self.safe_append(sheet, row)
            
            # --- SECONDARY BACKUP: Master Archive ---
            try:
                master_sheet = self.get_or_create_worksheet("MASTER_ARCHIVE", source if source != "linkedin" else "google")
                self.sync_headers(master_sheet)
                
                # If it's a LinkedIn lead, we need to map it to the master headers
                if source == "linkedin":
                    # Map limited LinkedIn data to full schema
                    master_row = [
                        query, data.get('name', 'N/A'), data.get('url', 'N/A'), "N/A", "N/A", data.get('url', 'N/A'),
                        "N/A", "N/A", "N/A", data.get('score', 0), data.get('decision', 'N/A'), data.get('summary', 'N/A')
                    ] + ["N/A"] * 10 + [data.get('icebreaker', 'N/A'), "LinkedIn Master", data.get('date_added', datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))]
                    self.safe_append(master_sheet, master_row)
                else:
                    self.safe_append(master_sheet, row)
            except Exception as e_master:
                print(f"[WARN] Master Archive Backup failed: {e_master}")

            print(f"[OK] Lead saved to {target_sheet_name}: {data.get('name', 'Lead')}")
            return True

        except Exception as e:
            import traceback
            error_msg = f"{e}\n{traceback.format_exc()}"
            print(f"[ERROR] Routing Error: {error_msg}")
            return str(e)   # Return short error string (no full trace to keep UI clean)

    def get_or_create_worksheet(self, title, source):
        """Finds or creates a worksheet with the given title and appropriate headers."""
        if not self.spreadsheet:
            self.connect()
        try:
            return self.spreadsheet.worksheet(title)
        except gspread.exceptions.WorksheetNotFound:
            print(f"[INFO] Creating missing tab: '{title}'")
            if "LinkedIn" in title or source == "linkedin":
                headers = ["Keyword", "Name", "LinkedIn URL", "Score", "Summary", "Decision", "Signal", "Icebreaker", "Source", "Date Added"]
            else:
                headers = [
                    "Keyword", "Name", "Website", "Emails", "Phone", "Address", "LinkedIn", 
                    "Instagram", "Facebook", "Tech Stack",
                    "Score", "Decision", "Summary", 
                    "GMB Status", "GMB Opp", 
                    "Ad Activity", "Ad Opp", 
                    "Web Status", "Web Opp", 
                    "Web Speed", "Speed Opp", 
                    "X-Ray Match", "X-Ray Opp",
                    "Icebreaker", "Source", "Date Added"
                ]
            new_sheet = self.spreadsheet.add_worksheet(title=title, rows="1000", cols="25")
            new_sheet.append_row(headers)
            # Apply some formatting to header
            new_sheet.format('A1:Z1', {'textFormat': {'bold': True}, 'backgroundColor': {'red': 0.9, 'green': 0.9, 'blue': 0.9}})
            return new_sheet
        except Exception as e:
            print(f"[ERROR] get_or_create_worksheet error: {e}")
            raise   # Re-raise so save_lead catches it cleanly

    def get_linkedin_sheet(self):
        """Finds or creates the LinkedIn Leads tab."""
        if not self.spreadsheet:
            self.connect()
        try:
            return self.spreadsheet.worksheet("LinkedIn Leads")
        except gspread.exceptions.WorksheetNotFound:
            # Create sheet if missing
            headers = ["Keyword", "Name", "LinkedIn URL", "Score", "Summary", "Decision", "Signal", "Icebreaker", "Source", "Date Added"]
            new_sheet = self.spreadsheet.add_worksheet(title="LinkedIn Leads", rows="1000", cols="20")
            new_sheet.append_row(headers)
            return new_sheet

    def append_lead(self, company_data, query="N/A"):
        """Backward compatibility for existing code."""
        return self.save_lead(company_data, query, source="google")

    def append_linkedin_lead(self, data, query):
        """Backward compatibility for existing code."""
        return self.save_lead(data, query, source="linkedin")

    def get_existing_leads(self):
        """
        Returns a dictionary with 'urls' and 'names' sets from the sheet.
        """
        if not self.spreadsheet:
            self.connect()
            
        try:
            # Check multiple possible history sheets
            names = set()
            urls = set()
            
            for sheet_name in ["Google Leads", "Universal Leads", "LinkedIn Leads", "Leads", "Sheet1"]:
                try:
                    target_sheet = self.spreadsheet.worksheet(sheet_name)
                    all_vals = target_sheet.get_all_values()
                    if not all_vals or len(all_vals) < 2:
                        continue
                    
                    for row in all_vals[1:]: # Skip header
                        if len(row) > 1: names.add(row[1].strip())
                        if len(row) > 2:
                            url = row[2].strip()
                            if url.lower() not in ["n/a", "unknown", "none", ""]:
                                urls.add(url)
                except:
                    continue
                    
            return {"urls": urls, "names": names}
        except Exception as e:
            print(f"[WARN] Could not load history: {e}")
            return {"urls": set(), "names": set()}

    def get_finished_missions(self):
        """Returns a set of all search queries already completed."""
        if not self.spreadsheet:
            self.connect()

        try:
            mission_sheet = self.get_or_create_worksheet("Mission_Progress", source="google")
            return set(mission_sheet.col_values(1))
        except Exception:
            # If the tab doesn't exist yet, return an empty set
            return set()

    def mark_mission_complete(self, query):
        """Saves the completed query so we never search it again."""
        if not self.client:
            self.connect()
            
        try:
            spreadsheet = self.client.open_by_key(self.sheet_id)
            try:
                mission_sheet = spreadsheet.worksheet("Mission_Progress")
            except:
                # Create if it doesn't exist
                print("[INFO] Creating 'Mission_Progress' tab...")
                mission_sheet = spreadsheet.add_worksheet(title="Mission_Progress", rows=1000, cols=2)
                mission_sheet.append_row(["Completed_Queries"])
            
            mission_sheet.append_row([query])
            print(f"[OK] Mission Archived: {query}")
        except Exception as e:
            print(f"[WARN] Could not archive mission: {e}")

    def get_all_leads_for_outreach(self):
        """Fetches all leads from various tabs for the WhatsApp UI."""
        if not self.spreadsheet:
            self.connect()
        
        all_leads = []
        # FIX: Include ALL tabs so keywords like 'Manufacturing company in Netherlands' appear
        tabs_to_check = [
            "Google Leads", "Universal Leads", "Naukri Leads",
            "Property Leads", "Education Leads", "MASTER_ARCHIVE", "Leads", "Sheet1"
        ]
        
        for tab_name in tabs_to_check:
            try:
                sheet = self.spreadsheet.worksheet(tab_name)
                data = sheet.get_all_records()
                for row in data:
                    # FIX: Include Address, City, Region fields
                    raw_address = row.get("Address") or row.get("address") or ""
                    city_val   = row.get("City")   or row.get("city")   or ""
                    region_val = row.get("Region") or row.get("region") or ""
                    # If city/region blank, try extracting from address (last comma-parts)
                    if raw_address and (not city_val or not region_val):
                        parts = [p.strip() for p in raw_address.split(",")]
                        if not city_val and len(parts) >= 2:
                            city_val = parts[-2]
                        if not region_val and len(parts) >= 1:
                            region_val = parts[-1]

                    lead = {
                        "Company":    row.get("Company Name") or row.get("Name") or "Unknown",
                        "Website":    row.get("Website") or "N/A",
                        "Phone":      str(row.get("Phone", "N/A")),
                        "Email":      row.get("Emails") or row.get("Email") or "N/A",
                        "Address":    raw_address or "N/A",
                        "City":       city_val  or "N/A",
                        "Region":     region_val or "N/A",
                        "Source":     row.get("Source", tab_name),
                        "Keyword":    row.get("Keyword", "N/A"),
                        "Icebreaker": row.get("Icebreaker", "")
                    }
                    if lead["Phone"] != "N/A" and str(lead["Phone"]).strip():
                        all_leads.append(lead)
            except:
                continue
        return all_leads
