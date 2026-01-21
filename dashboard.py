import streamlit as st
import asyncio
import os
import time
import psutil
from hunter import LeadHunter
from dotenv import load_dotenv

load_dotenv()
if os.path.exists(".env.local"):
    load_dotenv(".env.local", override=True)

st.set_page_config(page_title="Lead Hunter Mission Control", layout="wide", page_icon="🏹")

# Custom Styling
st.markdown("""
    <style>
    .main {
        background-color: #0e1117;
        color: #ffffff;
    }
    .stButton>button {
        width: 100%;
        border-radius: 5px;
        height: 3em;
        background-color: #ff4b4b;
        color: white;
    }
    .status-box {
        padding: 10px;
        border-radius: 5px;
        background-color: #262730;
        margin-bottom: 10px;
    }
    </style>
    """, unsafe_allow_html=True)

st.title("🏹 Lead Hunter: Mission Control")
st.markdown("Automated lead discovery, scoring, and storage.")
st.markdown("---")

# Sidebar Configuration
st.sidebar.header("📡 Mission Parameters")
target_keyword = st.sidebar.text_input("Target Keyword", value=os.getenv("KEYWORD", "Real Estate Agencies in Miami"))
scrape_limit = st.sidebar.slider("Scrape Limit", 5, 50, int(os.getenv("SCRAPE_LIMIT", 10)))

# Check for credentials
creds_path = os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE", "google-credentials.json")
creds_json = os.getenv("GOOGLE_CREDENTIALS_JSON") or os.getenv("GSHEETS_JSON")
creds_exists = os.path.exists(creds_path) or creds_json is not None
gemini_key = os.getenv("GEMINI_API_KEY")

if not creds_exists:
    st.sidebar.error("❌ google-credentials.json missing!")
    st.sidebar.info("Tip: You can set GOOGLE_CREDENTIALS_JSON as an environment variable.")
else:
    st.sidebar.success("✅ Google Credentials ready.")

if not gemini_key or "your_gemini_api_key" in gemini_key:
    st.sidebar.warning("⚠️ GEMINI_API_KEY not set. AI scoring will be disabled.")
else:
    st.sidebar.success("✅ Gemini AI ready.")

# --- RAM Usage Monitor ---
def get_ram_usage():
    try:
        process = psutil.Process(os.getpid())
        return process.memory_info().rss / 1024 / 1024  # Convert to MB
    except:
        return 0

ram_mb = get_ram_usage()
st.sidebar.metric("RAM Usage", f"{ram_mb:.2f} MB", delta_color="inverse")
if ram_mb > 450:
    st.sidebar.warning("⚠️ Critical: Approaching 512MB limit!")


# --- Auto-Start with Manual Pause/Resume ---
if 'hunting' not in st.session_state:
    st.session_state.hunting = False
if 'auto_start_timer' not in st.session_state:
    st.session_state.auto_start_timer = time.time()
if 'run_status' not in st.session_state:
    st.session_state.run_status = True  # True = running, False = paused

# UI Controls for Pause/Resume
col_pause, col_resume = st.columns(2)
with col_pause:
    if st.button("⏸️ Pause Hunter"):
        st.session_state.run_status = False
        st.warning("System Paused. Click 'Resume' to continue.")
with col_resume:
    if st.button("🚀 Resume Hunter"):
        st.session_state.run_status = True
        st.success("Resuming Lead Hunt...")

# Auto-start after 10 seconds if not paused
if not st.session_state.hunting and st.session_state.run_status:
    if time.time() - st.session_state.auto_start_timer > 10:
        if creds_exists:
            st.session_state.hunting = True
            st.session_state.logs = []
            st.session_state.results = []
            st.info("Auto-started lead hunting after 10 seconds of inactivity.")
        else:
            st.error("Cannot launch without Google Credentials.")

# Manual sidebar launch still works
if st.sidebar.button("🚀 Launch Hunter"):
    if not creds_exists:
        st.error("Cannot launch without Google Credentials.")
    else:
        st.session_state.hunting = True
        st.session_state.logs = []
        st.session_state.results = []
        st.session_state.auto_start_timer = time.time()

# Main UI Area
col1, col2 = st.columns([1, 2])

with col1:
    st.subheader("📡 Live Intelligence Feed")
    log_area = st.empty()
    
    # Updated log feed logic per user request
    def log_message(msg):
        if 'logs' not in st.session_state:
            st.session_state.logs = []
        st.session_state.logs.append(msg)
        # Display the last 10 lines in a code block
        display_text = "\n".join(st.session_state.logs[-10:])
        log_area.code(display_text)
        
        # If a debug screenshot exists, show it (optional sidebar update)
        if os.path.exists("debug_search.png"):
            st.sidebar.image("debug_search.png", caption="Last Browser View")

with col2:
    st.subheader("🎯 Qualified Lead Repository")
    results_area = st.empty()

async def run_hunter():
    hunter = LeadHunter(target_keyword, limit=scrape_limit)
    leads = await hunter.run_mission(update_callback=log_message)
    return leads


# --- Main Hunter Loop ---
if st.session_state.get("hunting"):
    if not st.session_state.run_status:
        st.info("System is idle. No credits being used.")
    else:
        st.session_state.results = []
        with st.spinner("Hunter is scanning the field..."):
            try:
                # We initialize the hunter here so we can call it
                hunter_instance = LeadHunter(target_keyword, limit=scrape_limit)
                
                # We use a custom callback that logs and writes to screen
                def streamlit_callback(msg):
                    log_message(msg)
                    st.write(msg)
                
                # Run the mission
                results = asyncio.run(hunter_instance.run_mission(update_callback=streamlit_callback))
                
                if results:
                    st.session_state.results = results
                    st.session_state.hunting = False
                    st.success(f"🎯 Mission Complete! Found {len(results)} leads.")
                else:
                    st.session_state.hunting = False
                    st.warning("No leads found. Check Render logs for 'Robot Check' or 'Consent Screen' blocks.")
            except Exception as e:
                st.error(f"Mission Failed: {e}")
                st.session_state.hunting = False

if st.session_state.get("results"):
    results = st.session_state.results
    if results:
        # Show a summary table
        st.write("### 🔎 Scan Results")
        st.table(results)
        
        # Stats
        # Handle cases where score might be 'Pending' string
        numeric_scores = [r.get('score', 0) for r in results if isinstance(r.get('score'), (int, float))]
        qualified_count = len([s for s in numeric_scores if s > 70])
        st.metric("Qualified Leads Found", qualified_count)
        
        # CSV Export with ALL columns
        headers = ["keyword", "name", "website", "email", "phone", "linkedin", "instagram", "facebook", "score", "decision", "reasoning"]
        csv_header = ",".join(headers) + "\n"
        
        csv_rows = []
        for r in results:
            reasoning = str(r.get('reasoning', 'N/A')).replace('"', "'")
            row = [
                str(r.get("keyword", "N/A")).replace(",", ""),
                str(r.get("name", "N/A")).replace(",", ""),
                str(r.get("website", "N/A")),
                str(r.get("email", "N/A")),
                str(r.get("phone", "N/A")),
                str(r.get("linkedin", "N/A")),
                str(r.get("instagram", "N/A")),
                str(r.get("facebook", "N/A")),
                str(r.get("score", "N/A")),
                str(r.get("decision", "N/A")),
                f'"{reasoning}"'
            ]
            csv_rows.append(",".join(row))
            
        csv_data = csv_header + "\n".join(csv_rows)
        
        st.download_button(
            "📥 Download Full Intel Report (CSV)",
            csv_data,
            f"leads_export_{int(time.time())}.csv",
            "text/csv",
            key='download-csv'
        )
    else:
        results_area.info("No leads found yet.")

st.markdown("---")
st.markdown("### 🛠️ Strategic Setup")
with st.expander("Detailed Instructions"):
    st.markdown("""
    1. **Google Sheets**: Ensure `google-credentials.json` is in the root and the Sheet is shared with the service account email.
    2. **Gemini AI**: Add your API key to `.env` to enable the 'Smart Filter' logic.
    3. **Strategy**: The Hunter saves leads with Score > 70 to GSheets. Use **Rows.com** to import this sheet and perform deep email discovery on the top 10% of leads.
    """)
