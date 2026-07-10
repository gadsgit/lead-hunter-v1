import streamlit as st
import pandas as pd
import requests
import io
import os
import sys

# Ensure parent directory is in path so we can import project modules if needed
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dashboard import save_to_global_db, sync_to_cloud

st.set_page_config(page_title="Bulk Ingestion - Lead Hunter", page_icon="📥", layout="wide")

# Custom CSS for consistency
st.markdown("""
    <style>
    .main { background-color: #0e1117; color: #ffffff; }
    .stButton>button { font-size: 18px !important; height: 45px !important; font-weight: bold; border-radius: 8px; }
    </style>
    """, unsafe_allow_html=True)

st.title("Bulk Data Ingestion Engine")
st.caption("Paste multiple raw files or cloud spreadsheet URLs to sync leads instantly.")

# --- SECTION 1: DYNAMIC CLOUD URL ENGINE ---
st.subheader("🔗 Cloud Spreadsheet URLs (Google Sheets / OneDrive)")

def clean_to_direct_link(url, platform):
    if not url: return None
    try:
        if platform == "Google Sheets" and "/edit" in url:
            return url.split("/edit")[0] + "/export?format=csv"
        elif platform == "OneDrive" and "sharepoint.com" in url:
            return url.split("?")[0] + "?download=1"
    except Exception:
        pass
    return url

init_data = [{"Platform": "Google Sheets", "Source Tag": "Imported Campaign", "URL": ""}]
df_urls = pd.DataFrame(init_data)

edited_url_df = st.data_editor(
    df_urls, 
    num_rows="dynamic",
    use_container_width=True,
    column_config={
        "Platform": st.column_config.SelectboxColumn("Platform", options=["Google Sheets", "OneDrive"]),
        "Source Tag": st.column_config.TextColumn("Lead Source Label (e.g. Naukri, Maps)"),
        "URL": st.column_config.TextColumn("Spreadsheet Link")
    }
)

# --- SECTION 2: SIMULTANEOUS LOCAL FILE UPLOAD ---
st.subheader("📁 Local File Sync Upload")
uploaded_files = st.file_uploader(
    "Drag and drop multiple offline lead sheets simultaneously", 
    type=["csv", "xlsx"], 
    accept_multiple_files=True
)

# --- SECTION 3: THE PARSING PIPELINE ---
if st.button("🚀 Process & Sync All Active Repositories", type="primary"):
    all_leads = []
    
    # Process URLs
    for index, row in edited_url_df.iterrows():
        raw_url = row['URL']
        if raw_url and raw_url.strip():
            direct_csv_url = clean_to_direct_link(raw_url, row['Platform'])
            try:
                response = requests.get(direct_csv_url, timeout=10)
                if response.status_code == 200:
                    cloud_df = pd.read_csv(io.StringIO(response.text))
                    cloud_df.columns = cloud_df.columns.str.lower().str.strip()
                    cloud_df = cloud_df.rename(columns={"business name": "Company Name", "phone string": "Mobile", "full name": "Company Name", "name": "Company Name", "phone": "Mobile"})
                    cloud_df['Keyword'] = row['Source Tag'] if row['Source Tag'] else 'Cloud Spreadsheet'
                    cloud_df['Score'] = 50 # Default score
                    all_leads.append(cloud_df)
                    st.success(f"✅ Successfully scraped cloud index row #{index+1}!")
                else:
                    st.error(f"Failed to access row #{index+1}: Status {response.status_code}")
            except Exception as e:
                st.error(f"Failed to access link entry #{index+1}: {str(e)}")

    # Process local files
    if uploaded_files:
        for file in uploaded_files:
            try:
                local_df = pd.read_csv(file) if file.name.endswith('.csv') else pd.read_excel(file)
                local_df.columns = local_df.columns.str.lower().str.strip()
                local_df = local_df.rename(columns={"business name": "Company Name", "phone string": "Mobile", "full name": "Company Name", "name": "Company Name", "phone": "Mobile", "website": "Website", "emails": "Emails"})
                local_df['Keyword'] = "File Upload: " + file.name
                local_df['Score'] = 50 # Default score
                all_leads.append(local_df)
                st.success(f"✅ Successfully processed local file: {file.name}")
            except Exception as e:
                st.error(f"Failed parsing file {file.name}: {str(e)}")

    # --- SECTION 4: BULK STORAGE INTEGRATION ---
    if all_leads:
        master_leads_df = pd.concat(all_leads, ignore_index=True)
        # Drop rows missing company name
        if 'Company Name' in master_leads_df.columns:
            master_leads_df = master_leads_df.dropna(subset=['Company Name'])
            # Ensure essential columns exist
            for col in ['Website', 'Mobile', 'Emails', 'Keyword', 'Score']:
                if col not in master_leads_df.columns:
                    master_leads_df[col] = "N/A" if col != 'Score' else 50
                    
            payload = master_leads_df.to_dict(orient='records')
            
            try:
                # Use existing dashboard logic to merge into the local Master Database
                if 'global_db' not in st.session_state:
                    st.session_state.global_db = {}
                
                # We categorize these bulk uploads into "Bulk Imports"
                save_to_global_db(payload, "Bulk Imports")
                
                # Append directly to local backup CSV 
                local_backup = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "incremental_leads_backup.csv")
                df_new = pd.DataFrame(payload)
                
                if os.path.exists(local_backup):
                    df_old = pd.read_csv(local_backup)
                    combined = pd.concat([df_old, df_new], ignore_index=True)
                    # Simple deduplication by Name/Website
                    if 'Website' in combined.columns:
                        combined = combined.drop_duplicates(subset=['Website', 'Company Name'], keep='first')
                    combined.to_csv(local_backup, index=False)
                else:
                    df_new.to_csv(local_backup, index=False)
                    
                st.balloons()
                st.success(f"🎉 Database sync finalized. **{len(payload)} total leads** written directly to your master repository!")
                st.info("You can now view these leads in the CRM Dashboard tab on the main app.")
                
            except Exception as database_error:
                st.error(f"Database write interrupted: {str(database_error)}")
        else:
            st.error("No valid 'Name' or 'Company Name' column found in the uploaded data.")
    else:
        st.warning("No data inputs detected. Fill out the URL table rows or drop file records to execute.")
