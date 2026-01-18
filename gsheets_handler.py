import gspread
from google.oauth2.service_account import Credentials
import os
from dotenv import load_dotenv

load_dotenv()

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
            if not os.path.exists(self.credentials_file):
                print(f"Error: Credentials file {self.credentials_file} not found.")
                return False
            
            creds = Credentials.from_service_account_file(self.credentials_file, scopes=self.scope)
            self.client = gspread.authorize(creds)
            
            if self.sheet_id:
                self.sheet = self.client.open_by_key(self.sheet_id).get_worksheet(0)
            else:
                # Fallback to opening by name if ID is missing (not recommended)
                self.sheet = self.client.open("Lead Hunter Results").get_worksheet(0)
            
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
            if not self.connect():
                return False
        try:
            # Expected lead_data: list or dict
            if isinstance(lead_data, dict):
                # If AI review is pending, fill in the appropriate fields
                score = lead_data.get("score")
                age = lead_data.get("age")
                reasoning = lead_data.get("reasoning")
                if score == "Pending":
                    score = "Pending AI Review"
                if age == "Pending":
                    age = "Pending AI Review"
                if reasoning == "Pending":
                    reasoning = "Pending AI Review"
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
            return True
        except Exception as e:
            print(f"Error appending row: {e}")
            return False
