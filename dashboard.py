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
tab_google, tab_linkedin = st.tabs(["📍 Google Maps Leads", "💼 LinkedIn Leads"])

with tab_google:
    col1, col2 = st.columns([1, 2])
    with col1:
        st.subheader("📡 Google Intelligence Feed")
        log_area_g = st.empty()
        
        def log_message_g(msg):
            if 'logs_g' not in st.session_state: st.session_state.logs_g = []
            st.session_state.logs_g.append(msg)
            log_area_g.code("\n".join(st.session_state.logs_g[-10:]))

    with col2:
        st.subheader("🎯 Google Lead Repository")
        if st.session_state.get("results_g"):
            results = st.session_state.results_g
            st.table(results)
            
            # Stats
            numeric_scores = [r.get('score', 0) for r in results if isinstance(r.get('score'), (int, float))]
            qualified_count = len([s for s in numeric_scores if s > 70])
            st.metric("Qualified Leads Found", qualified_count)
            
            # CSV Export
            headers = ["keyword", "name", "website", "email", "phone", "linkedin", "instagram", "facebook", "score", "decision", "summary"]
            csv_header = ",".join(headers) + "\n"
            csv_rows = []
            for r in results:
                summary_text = str(r.get('summary', 'N/A')).replace('"', "'")
                row = [str(r.get(h, "N/A")).replace(",", "") for h in headers[:-1]] + [f'"{summary_text}"']
                csv_rows.append(",".join(row))
            
            st.download_button("📥 Download Google Leads (CSV)", csv_header + "\n".join(csv_rows), f"google_leads_{int(time.time())}.csv", "text/csv")

    if st.button("🚀 Launch Google Hunter", key="run_google"):
        st.session_state.results_g = []
        st.session_state.logs_g = []
        with st.spinner("Scanning Google Maps..."):
            hunter = LeadHunter(target_keyword, limit=scrape_limit)
            results = asyncio.run(hunter.run_mission(update_callback=log_message_g))
            st.session_state.results_g = results
            st.rerun()

with tab_linkedin:
    col1, col2 = st.columns([1, 2])
    with col1:
        st.subheader("📡 LinkedIn Intelligence Feed")
        log_area_l = st.empty()
        
        def log_message_l(msg):
            if 'logs_l' not in st.session_state: st.session_state.logs_l = []
            st.session_state.logs_l.append(msg)
            log_area_l.code("\n".join(st.session_state.logs_l[-10:]))

    with col2:
        st.subheader("🎯 LinkedIn Lead Repository")
        if st.session_state.get("results_l"):
            results = st.session_state.results_l
            st.table(results)
            
            # CSV Export
            headers = ["keyword", "name", "url", "score", "decision", "summary"]
            csv_header = ",".join(headers) + "\n"
            csv_rows = []
            for r in results:
                summary_text = str(r.get('summary', 'N/A')).replace('"', "'")
                row = [str(r.get(h, "N/A")).replace(",", "") for h in headers[:-1]] + [f'"{summary_text}"']
                csv_rows.append(",".join(row))
            
            st.download_button("📥 Download LinkedIn Leads (CSV)", csv_header + "\n".join(csv_rows), f"linkedin_leads_{int(time.time())}.csv", "text/csv")

    li_keyword = st.text_input("LinkedIn Search Keyword", value="CEO Real Estate Miami", key="li_kw")
    if st.button("💼 Launch LinkedIn Hijack", key="run_linkedin"):
        st.session_state.results_l = []
        st.session_state.logs_l = []
        with st.spinner("Hijacking Google for LinkedIn Profiles..."):
            hunter = LeadHunter(limit=scrape_limit)
            results = asyncio.run(hunter.run_linkedin_mission(keyword=li_keyword, update_callback=log_message_l))
            st.session_state.results_l = results
            st.rerun()

st.markdown("---")
st.markdown("### 🛠️ Strategic Setup")
with st.expander("Detailed Instructions"):
    st.markdown("""
    1. **Google Sheets**: Data is saved to 'Sheet1' (Google) and 'LinkedIn Leads' (LinkedIn) tabs.
    2. **LinkedIn Strategy**: Uses Google search hijacking to find profiles without logging in.
    3. **Strategy**: Google leads are local businesses; LinkedIn leads are high-ticket decision makers.
    """)
