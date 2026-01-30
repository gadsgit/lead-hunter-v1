import streamlit as st
import asyncio
import os
import time
import psutil
import urllib.parse
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

# Create placeholder metrics
col_m1, col_m2 = st.sidebar.columns(2)
fetched_metric = col_m1.metric("Fetched", "0")
inserted_metric = col_m2.metric("Inserted", "0")

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
with st.sidebar:
    st.divider()
    if ram_mb < 350:
        st.success(f"📊 RAM: {ram_mb:.1f}MB / 512MB (Safe)")
    elif ram_mb < 450:
        st.warning(f"📊 RAM: {ram_mb:.1f}MB (High)")
    else:
        st.error(f"📊 RAM: {ram_mb:.1f}MB (CRITICAL)")
        st.warning("⚠️ Approaching 512MB limit! Browser will restart automatically.")
        if st.button("🗑️ Clear Cache"):
            st.cache_data.clear()

# --- Lead Dorking Toolkit ---
with st.sidebar:
    st.divider()
    st.subheader("🛠️ Lead Dorking Toolkit")
    st.markdown("Generate targeted Google X-Ray search links.")
    
    # User Input
    dork_niche = st.text_input("Dork Niche", "Cosmetic Manufacturing")
    dork_region = st.text_input("Dork Region", "USA")
    
    if dork_niche:
        # Define "Dork" Templates
        dorks = {
            "🏢 Find Companies": f'site:linkedin.com/company/ "{dork_niche}" AND "{dork_region}"',
            "👤 Find CEOs/Owners": f'site:linkedin.com/in/ "CEO" OR "Founder" AND "{dork_niche}"',
            "🧴 Private Label Mfrs": f'site:linkedin.com/company/ "Private Label" AND "{dork_niche}"',
            "📧 Email Discovery": f'site:linkedin.com/in/ "{dork_niche}" AND "@gmail.com"',
            "📸 Instagram Discovery": f'site:instagram.com "{dork_niche}" AND "{dork_region}"'
        }
        
        # Generate Clickable Buttons
        for label, query in dorks.items():
            encoded_query = urllib.parse.quote(query)
            google_url = f"https://www.google.com/search?q={encoded_query}"
            st.link_button(label, google_url, use_container_width=True)

        st.info("💡 Tip: Use these to verify leads before running the automated scraper.")

        st.divider()
        st.subheader("🤖 Automated Execution")
        selected_mission = st.selectbox("Select Strategy", list(dorks.keys()))
        
        if st.button(f"🚀 Launch {selected_mission}", use_container_width=True):
            st.session_state.hunting_mode = "automated"
            st.session_state.automated_query = dorks[selected_mission]
            # Route to correct tab for logs
            source = "linkedin" if "linkedin" in dorks[selected_mission].lower() else "google"
            st.session_state.automated_source = source
            st.session_state.launch_trigger = True
            st.toast(f"Starting mission for: {dork_niche}...", icon="📡")


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
col_g, col_li, col_smart = st.sidebar.columns(3)
with col_g:
    if st.button("📍 Google"):
        st.session_state.hunting_mode = "google"
        st.session_state.launch_trigger = True
with col_li:
    if st.button("💼 LinkedIn"):
        st.session_state.hunting_mode = "linkedin"
        st.session_state.launch_trigger = True
with col_smart:
    if st.button("🧠 Smart"):
        st.session_state.hunting_mode = "smart"
        st.session_state.launch_trigger = True

# Deployment logic for triggers
if st.session_state.get("launch_trigger"):
    st.session_state.launch_trigger = False
    if not creds_exists:
        st.error("Cannot launch without Google Credentials.")
    else:
        st.session_state.hunting = True
        st.session_state.logs_g = []
        st.session_state.results_l = []
        st.session_state.found_count = 0
        st.session_state.dup_count = 0
        st.session_state.ai_count = 0
        st.session_state.auto_start_timer = time.time()

# --- Logging Utilities ---
log_container_g = st.sidebar.empty()
log_container_l = st.sidebar.empty()

def log_message_g(msg):
    if 'logs_g' not in st.session_state: st.session_state.logs_g = []
    st.session_state.logs_g.append(msg)
    # We will update a placeholder in the tab later, or just sidebar for now
    print(f"[GOOGLE] {msg}")

def log_message_l(msg):
    if 'logs_l' not in st.session_state: st.session_state.logs_l = []
    st.session_state.logs_l.append(msg)
    print(f"[LINKEDIN] {msg}")

# --- Hunting Execution Block ---
if st.session_state.get("hunting"):
    mode = st.session_state.get("hunting_mode", "google")
    hunter = LeadHunter(target_keyword, limit=scrape_limit)
    
    # Universal Progress UI
    progress_bar = st.sidebar.progress(0)
    status_text = st.sidebar.empty()
    
    # Live Metrics
    m_col1, m_col2, m_col3, m_col4 = st.columns(4)
    fetched_metric = m_col1.metric("Leads Found", "0")
    ai_metric = m_col2.metric("AI Reviewed", "0")
    inserted_metric = m_col3.metric("Inserted", "0")
    ram_metric = m_col4.metric("RAM", f"{get_ram_usage():.1f} MB")
    
    st.sidebar.divider()
    duplicate_metric = st.sidebar.metric("Duplicates Skipped", "0")
    
    with st.status(f"📡 Hunter Active: {mode.upper()} mode...", expanded=True) as status:
        
        # Helper to track metrics using session state to avoid scope issues
        if 'dup_count' not in st.session_state: st.session_state.dup_count = 0
        if 'found_count' not in st.session_state: st.session_state.found_count = 0
        if 'ai_count' not in st.session_state: st.session_state.ai_count = 0

        def update_ram():
            ram_now = get_ram_usage()
            ram_metric.metric("RAM", f"{ram_now:.1f} MB")

        def live_logger_g(msg):
            st.write(msg)
            log_message_g(msg)
            update_ram()
            # Check for specific statuses to update metrics
            if "Saved" in msg or "SAVED" in msg:
                # Update Inserted count
                inserted_metric.metric("Inserted", str(len(st.session_state.results_g) + 1))
            if "Duplicate" in msg:
                st.session_state.dup_count += 1
                duplicate_metric.metric("Duplicates Skipped", str(st.session_state.dup_count))
            if "Discovered" in msg:
                st.session_state.found_count += 1
                fetched_metric.metric("Leads Found", str(st.session_state.found_count))
            if "AI Analyzing" in msg:
                st.session_state.ai_count += 1
                ai_metric.metric("AI Reviewed", str(st.session_state.ai_count))

        def live_logger_l(msg):
            st.write(msg)
            log_message_l(msg)
            update_ram()
            if "Saved" in msg or "SAVED" in msg:
                 inserted_metric.metric("Inserted", str(len(st.session_state.results_l) + 1))
            if "Duplicate" in msg:
                st.session_state.dup_count += 1
                duplicate_metric.metric("Duplicates Skipped", str(st.session_state.dup_count))
            if "Discovered" in msg or "Scraped LinkedIn" in msg:
                st.session_state.found_count += 1
                fetched_metric.metric("Leads Found", str(st.session_state.found_count))
            if "AI Analyzing" in msg:
                st.session_state.ai_count += 1
                ai_metric.metric("AI Reviewed", str(st.session_state.ai_count))
            
        def update_progress(val):
            progress_bar.progress(val)
            # Update 'Leads Found' estimate based on progress
            # In atomic mode, we find them all first, so we can't easily track "found" increments 
            # unless we change hunter.py to callback during the initial scan. 
            # For now, we will assume 'Leads Found' = Total Expected from progress?
            # Actually, hunter.py's update_callback sends "processing Lead X/Y", we can parse that!
            pass

        # Smart wrapper to parse messages for metrics
        def metric_aware_logger(msg):
            st.write(msg)
            if "processing Lead" in msg:
                # msg format: "processing Lead 1/10: Company Name"
                try:
                    parts = msg.split("/")[0].split(" ")[-1] # Gets '1' from '1/10'
                    fetched_metric.metric("Leads Found", parts)
                except:
                    pass
            
            if "Syncing" in msg or "Saving" in msg:
                # Increment AI Reviewed (since we only sync after AI)
                current = ai_metric.label # Using a hack to store state or just query session state
                # Better: clean implementation
                pass

        # We will use session state to track metrics dynamically
        if 'ai_reviewed_count' not in st.session_state:
            st.session_state.ai_reviewed_count = 0
        
        def smart_logger_g(msg):
            live_logger_g(msg)
            
            if "processing Lead" in msg:
                 try:
                    count = msg.split("Lead ")[1].split("/")[0]
                    fetched_metric.metric("Leads Found", count)
                 except: pass
            
            if "Syncing" in msg:
                st.session_state.ai_reviewed_count += 1
                ai_metric.metric("AI Reviewed", str(st.session_state.ai_reviewed_count))

        def smart_logger_l(msg):
            live_logger_l(msg)
            if "AI Analyzing" in msg:
                pass # LinkedIn does batch scanning then AI, diff flow
            if "SAVED" in msg:
                st.session_state.ai_reviewed_count += 1
                ai_metric.metric("AI Reviewed", str(st.session_state.ai_reviewed_count))

        try:
            if mode == "google":
                results = asyncio.run(hunter.run_mission(
                    update_callback=smart_logger_g, 
                    progress_callback=update_progress
                ))
                st.session_state.results_g = results
            elif mode == "linkedin":
                li_kw = st.session_state.get("li_kw", target_keyword)
                results = asyncio.run(hunter.run_linkedin_mission(
                    keyword=li_kw, 
                    update_callback=smart_logger_l
                ))
                st.session_state.results_l = results
            elif mode == "smart":
                source = hunter.detect_source(target_keyword)
                # Create a smart callback that writes to status + correct log list
                def smart_callback(msg):
                    st.write(msg)
                    if source == "linkedin":
                        log_message_l(msg)
                        if "Saved" in msg: inserted_metric.metric("Inserted", str(len(st.session_state.results_l) + 1))
                    else:
                        log_message_g(msg)
                        if "Saved" in msg: inserted_metric.metric("Inserted", str(len(st.session_state.results_g) + 1))
                        
                results = asyncio.run(hunter.run_smart_mission(
                    target_keyword, 
                    update_callback=smart_callback
                ))
                if source == "linkedin":
                    st.session_state.results_l = results
                else:
                    st.session_state.results_g = results
            elif mode == "automated":
                query = st.session_state.get("automated_query")
                source = st.session_state.get("automated_source", "linkedin")
                
                def auto_callback(msg):
                    st.write(msg)
                    if source == "linkedin":
                        log_message_l(msg)
                        if "Saved" in msg: inserted_metric.metric("Inserted", str(len(st.session_state.results_l) + 1))
                    else:
                        log_message_g(msg)
                        if "Saved" in msg: inserted_metric.metric("Inserted", str(len(st.session_state.results_g) + 1))
                
                results = asyncio.run(hunter.run_automated_mission(
                    query, 
                    source=source, 
                    update_callback=auto_callback,
                    progress_callback=update_progress
                ))
                
                if source == "linkedin":
                    st.session_state.results_l = results
                else:
                    st.session_state.results_g = results
                
                st.balloons()
            
            status.update(label="✅ Mission Accomplished!", state="complete")
            st.session_state.hunting = False
            # Short delay so user can see completion before rerun
            time.sleep(1) 
            st.rerun()
        except Exception as e:
            status.update(label="❌ Mission Failed", state="error")
            st.error(f"Mission Failed: {e}")
            st.session_state.hunting = False
tab_google, tab_linkedin = st.tabs(["📍 Google Maps Leads", "💼 LinkedIn Leads"])

with tab_google:
    col1, col2 = st.columns([1, 2])
    with col1:
        st.subheader("📡 Google Intelligence Feed")
        if st.session_state.get("logs_g"):
            st.code("\n".join(st.session_state.logs_g[-15:]))
        else:
            st.info("Feed idle. Awaiting mission launch.")

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
        st.session_state.hunting_mode = "google"
        st.session_state.launch_trigger = True
        st.rerun()

with tab_linkedin:
    col1, col2 = st.columns([1, 2])
    with col1:
        st.subheader("📡 LinkedIn Intelligence Feed")
        if st.session_state.get("logs_l"):
            st.code("\n".join(st.session_state.logs_l[-15:]))
        else:
            st.info("Feed idle. Awaiting mission launch.")

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
        st.session_state.hunting_mode = "linkedin"
        st.session_state.launch_trigger = True
        st.rerun()

st.markdown("---")
st.markdown("### 🛠️ Strategic Setup")
with st.expander("Detailed Instructions"):
    st.markdown("""
    1. **Google Sheets**: Data is saved to 'Sheet1' (Google) and 'LinkedIn Leads' (LinkedIn) tabs.
    2. **LinkedIn Strategy**: Uses Google search hijacking to find profiles without logging in.
    3. **Strategy**: Google leads are local businesses; LinkedIn leads are high-ticket decision makers.
    """)
