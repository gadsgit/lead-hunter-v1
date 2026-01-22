import gspread
from google.oauth2.service_account import Credentials
import os
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
                print(f"Cleaned Sheet ID from URL: {self.sheet_id}")
            except Exception as e:
                print(f"Failed to parse URL for Sheet ID: {e}")

        self.client = None
        self.sheet = None
        self.spreadsheet = None

    def connect(self):
        try:
            creds = None
            json_creds = os.getenv("GOOGLE_CREDENTIALS_JSON") or os.getenv("GSHEETS_JSON")
            
            if json_creds:
                import json
                try:
                    info = json.loads(json_creds)
                    creds = Credentials.from_service_account_info(info, scopes=self.scope)
                    print(f"Credentials loaded. Service Account: {info.get('client_email')}")
                except Exception as e:
                    print(f"Error parsing GOOGLE_CREDENTIALS_JSON: {e}")

            if not creds:
                if not os.path.exists(self.credentials_file):
                    print(f"Error: No credentials via ENV or FILE ({self.credentials_file}) found.")
                    return False
                creds = Credentials.from_service_account_file(self.credentials_file, scopes=self.scope)
            
            self.client = gspread.authorize(creds)
            
            if self.sheet_id:
                try:
                    print(f"Opening spreadsheet by ID: {self.sheet_id}")
                    spreadsheet = self.client.open_by_key(self.sheet_id)
                    
                    # Target specific GID if provided
                    if self.sheet_gid and self.sheet_gid != "0":
                        try:
                            print(f"Targeting specific GID (Tab): {self.sheet_gid}")
                            self.sheet = spreadsheet.get_worksheet_by_id(int(self.sheet_gid))
                            if not self.sheet:
                                print(f"GID {self.sheet_gid} not found. Falling back to first tab.")
                                self.sheet = spreadsheet.get_worksheet(0)
                        except Exception as gid_err:
                            print(f"GID Error: {gid_err}. Using first tab.")
                            self.sheet = spreadsheet.get_worksheet(0)
                    else:
                        self.sheet = spreadsheet.get_worksheet(0)
                        
                    self.spreadsheet = spreadsheet
                    print(f"Sheet '{self.sheet.title}' opened successfully.")
                except Exception as e:
                    print(f"Failed to open spreadsheet by ID: {e}")
                    return False
            else:
                try:
                    print("No GOOGLE_SHEET_ID found. Attempting to open by name: 'Lead Hunter Results'")
                    self.spreadsheet = self.client.open("Lead Hunter Results")
                    self.sheet = self.spreadsheet.get_worksheet(0)
                    print(f"Found sheet by name: {self.sheet.title}")
                except Exception as e:
                    print(f"Failed to open 'Lead Hunter Results': {e}")
                    print("TIP: Add GOOGLE_SHEET_ID to your Render Environment variables and share the sheet with the Service Account email.")
                    return False
            
            # Initialize headers if sheet is empty
            if not self.sheet.get_all_values():
                headers = ["Keyword", "Company Name", "Website", "Emails", "Phone", "LinkedIn", "Instagram", "Facebook", "Score", "Decision", "Summary"]
                self.sheet.append_row(headers)
            
            return True
        except Exception as e:
            print(f"Error connecting to Google Sheets: {e}")
            return False

    def save_lead(self, data, query, source="google"):
        """
        Routes data to the correct worksheet based on source.
        source: 'google' or 'linkedin'
        """
        try:
            # Ensure connection is active
            if not self.client:
                self.connect()
                
            if source == "google":
                # Ensure sheet is selected
                if not self.sheet:
                    if self.spreadsheet:
                        self.sheet = self.spreadsheet.get_worksheet(0)
                    else:
                        self.connect()

                # Detailed row for Google Maps leads
                row = [
                    query,
                    data.get('name', 'N/A'),
                    data.get('website', 'N/A'),
                    data.get('email', 'N/A'),
                    data.get('phone', 'N/A'),
                    data.get('linkedin', 'N/A'),
                    data.get('instagram', 'N/A'),
                    data.get('facebook', 'N/A'),
                    data.get('score', 0),
                    data.get('decision', 'N/A'),
                    data.get('summary', 'N/A')
                ]
                # Targeting the main sheet (usually Sheet1)
                self.sheet.append_row(row)
                print(f"✅ Google Lead saved: {data.get('name')}")
            else:
                # Optimized row for LinkedIn leads
                sheet = self.get_linkedin_sheet()
                row = [
                    query,
                    data.get('name', 'N/A'),
                    data.get('url', 'N/A'),
                    data.get('score', 0),
                    data.get('summary', 'N/A'),
                    data.get('decision', 'N/A')
                ]
                sheet.append_row(row)
                print(f"✅ LinkedIn Lead saved: {data.get('name')}")
            return True
        except Exception as e:
            print(f"❌ Routing Error: {e}")
            # Try once more with fresh connection
            try:
                print("♻️ Attempting reconnection to save...")
                self.connect()
                if source == "google":
                   self.sheet.append_row(row)
                else:
                   self.get_linkedin_sheet().append_row(row)
                print(f"✅ Saved after reconnection: {data.get('name')}")
                return True
            except Exception as e2:
                print(f"❌ Final Save Error: {e2}")
                return False

    def get_linkedin_sheet(self):
        """Finds or creates the LinkedIn Leads tab."""
        if not self.spreadsheet:
            self.connect()
        try:
            return self.spreadsheet.worksheet("LinkedIn Leads")
        except gspread.exceptions.WorksheetNotFound:
            # Create sheet if missing
            headers = ["Keyword", "Name", "LinkedIn URL", "Score", "Summary", "Decision"]
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
        Returns a set of all websites already in the sheet.
        Using a 'set' makes the check nearly instant.
        """
        if not self.sheet:
            self.connect()
            
        try:
            # Get all values from the 'Website' column (Column C is index 3)
            # Since we added Keyword at Column A, Website moved to Column C
            existing_urls = self.sheet.col_values(3)
            # Filter out empty or header values if necessary, though set handles duplicates
            return set(url.strip() for url in existing_urls if url.strip() and url != "Website")
        except Exception as e:
            print(f"Could not load history: {e}")
            return set()

    def get_finished_missions(self):
        """Returns a set of all search queries already completed."""
        if not self.client:
            self.connect()

        try:
            # Open the specific 'Mission_Progress' tab
            mission_sheet = self.client.open_by_key(self.sheet_id).worksheet("Mission_Progress")
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
                print("Creating 'Mission_Progress' tab...")
                mission_sheet = spreadsheet.add_worksheet(title="Mission_Progress", rows=1000, cols=2)
                mission_sheet.append_row(["Completed_Queries"])
            
            mission_sheet.append_row([query])
            print(f"Mission Archived: {query}")
        except Exception as e:
            print(f"Could not archive mission: {e}")
