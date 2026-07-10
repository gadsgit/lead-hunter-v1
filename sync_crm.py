import pandas as pd
import json
import re
import os

def sync_leads_to_crm(df=None):
    print("Fetching leads for CRM sync...")
    crm_js_path = r"E:\Lead Hunter\crm\crm.js"
    
    if df is None:
        csv_path = r"E:\Lead Hunter\incremental_leads_backup.csv"
        if not os.path.exists(csv_path):
            print("No local backup CSV found to sync.")
            return False, "No data available."
            
        try:
            df = pd.read_csv(csv_path)
        except pd.errors.EmptyDataError:
            print("No data in the local backup CSV to sync yet.")
            return False, "No data available."
            
    if df.empty:
        print("No leads available to sync.")
        return False, "No leads available."
        
    try:
        leads_list = []
        for i, row in enumerate(df.to_dict('records')):
            name = str(row.get('Company Name', 'Unknown'))
            if name.lower() == 'nan': name = 'Unknown'
            source = str(row.get('Keyword', 'Imported'))
            
            score_str = str(row.get('Score', '0'))
            try:
                score = int(re.sub(r'\D', '', score_str)) if re.search(r'\d', score_str) else 0
            except:
                score = 0
                
            if score >= 80: temp, status, stage = 'hot', 'SQL', 'sql'
            elif score >= 50: temp, status, stage = 'warm', 'MQL', 'mql'
            else: temp, status, stage = 'cold', 'Prospect', 'prospect'
            
            phone = str(row.get('Mobile', row.get('Phone', 'N/A')))
            if phone.lower() == 'nan': phone = 'N/A'
            email = str(row.get('Emails', 'N/A'))
            if email.lower() == 'nan': email = 'N/A'
            
            highlight = str(row.get('Chat Widget Available', 'No highlight available.'))
            if highlight.lower() == 'nan': highlight = 'No highlight available.'
            
            lead_obj = {
                "id": i + 1,
                "name": name,
                "source": source[:30],
                "score": score,
                "temp": temp,
                "status": status,
                "owner": "Advit",
                "touch": "Just now",
                "stage": stage,
                "acv": 0,
                "phone": phone,
                "email": email,
                "highlight": highlight[:100] + '...' if len(highlight) > 100 else highlight
            }
            leads_list.append(lead_obj)
            
        leads_json = json.dumps(leads_list, indent=2)
        
        with open(crm_js_path, 'r', encoding='utf-8') as f:
            content = f.read()
            
        pattern = r"const LEADS = \[\s*[\s\S]*?\s*\];"
        replacement = f"const LEADS = {leads_json};"
        new_content = re.sub(pattern, replacement, content, count=1)
        
        with open(crm_js_path, 'w', encoding='utf-8') as f:
            f.write(new_content)
            
        print(f"Successfully synced {len(leads_list)} leads to HTML CRM.")
        return True, f"Successfully synced {len(leads_list)} leads!"
    except Exception as e:
        print(f"Sync failed: {str(e)}")
        return False, f"Sync failed: {str(e)}"

if __name__ == "__main__":
    sync_leads_to_crm()
