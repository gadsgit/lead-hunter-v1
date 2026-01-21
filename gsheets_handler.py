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
        self.client = None
        self.sheet = None

    def connect(self):
        try:
            creds = None
            json_creds = os.getenv("GOOGLE_CREDENTIALS_JSON") or os.getenv("GSHEETS_JSON")
            
            if json_creds:
                import json
                try:
                    info = json.loads(json_creds)
                    creds = Credentials.from_service_account_info(info, scopes=self.scope)
                    print(f"✅ Credentials loaded. Service Account: {info.get('client_email')}")
                except Exception as e:
                    print(f"❌ Error parsing GOOGLE_CREDENTIALS_JSON: {e}")

            if not creds:
                if not os.path.exists(self.credentials_file):
                    print(f"❌ Error: No credentials via ENV or FILE ({self.credentials_file}) found.")
                    return False
                creds = Credentials.from_service_account_file(self.credentials_file, scopes=self.scope)
            
            self.client = gspread.authorize(creds)
            
            if self.sheet_id:
                try:
                    print(f"📡 Opening spreadsheet by ID: {self.sheet_id}")
                    self.sheet = self.client.open_by_key(self.sheet_id).get_worksheet(0)
                    print("✅ Spreadsheet opened successfully.")
                except Exception as e:
                    print(f"❌ Failed to open spreadsheet by ID: {e}")
                    return False
            else:
                try:
                    print("📡 No GOOGLE_SHEET_ID found. Attempting to open by name: 'Lead Hunter Results'")
                    self.sheet = self.client.open("Lead Hunter Results").get_worksheet(0)
                except Exception as e:
                    print(f"❌ Failed to open 'Lead Hunter Results': {e}")
                    print("💡 TIP: Add GOOGLE_SHEET_ID to your Render Environment variables and share the sheet with the Service Account email.")
                    return False
            
            # Initialize headers if sheet is empty
            if not self.sheet.get_all_values():
                headers = ["Company Name", "Website", "Email", "LinkedIn URL", "Score", "Inferred Age", "Reasoning"]
                self.sheet.append_row(headers)
            
            return True
        except Exception as e:
            print(f"Error connecting to Google Sheets: {e}")
            return False

    def append_lead(self, lead_data):
        if not self.sheet:
            print("📡 Connection to sheet not established. Attempting to connect...")
            if not self.connect():
                print("❌ Failed to establish connection during append_lead.")
                return False
        try:
            # Expected lead_data: dict
            if isinstance(lead_data, dict):
                score = lead_data.get("score")
                age = lead_data.get("age")
                reasoning = lead_data.get("reasoning")
                
                row = [
                    lead_data.get("name"),
                    lead_data.get("website"),
                    lead_data.get("email"),
                    lead_data.get("linkedin"),
                    score,
                    age,
                    reasoning
                ]
            else:
                row = lead_data
            
            self.sheet.append_row(row)
            print(f"✅ Successfully saved to GSheets: {row[0]}")
            return True
        except Exception as e:
            # This is the "Why" catcher requested
            print(f"❌ GSheets Error Detail: {str(e)}")
            if "PERMISSION_DENIED" in str(e).upper():
                print("💡 TIP: Ensure the sheet is SHARED with the service account email.")
            return False
