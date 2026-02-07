import streamlit as st
import asyncio
import os
import pandas as pd
from hunter import LeadHunter
from dotenv import load_dotenv

load_dotenv()
if os.path.exists(".env.local"):
    load_dotenv(".env.local", override=True)

st.set_page_config(page_title="Hunter Intelligence Console", layout="wide", page_icon="🏹")

# --- CUSTOM STYLING ---
st.markdown("""
    <style>
    .main { background-color: #0e1117; color: #ffffff; }
    div[data-testid="stMetricValue"] { font-size: 24px; color: #00FF00; }
    div[data-testid="stMetricLabel"] { font-size: 14px; color: #aaaaaa; }
    .stButton>button { border-radius: 5px; font-weight: bold; }
    .stTabs [data-baseweb="tab-list"] { gap: 24px; }
    .stTabs [data-baseweb="tab"] { height: 50px; white-space: pre-wrap; background-color: #1E1E1E; border-radius: 4px; gap: 1px; padding-top: 10px; padding-bottom: 10px; }
    .stTabs [aria-selected="true"] { background-color: #FF4B4B; color: white; }
    </style>
    """, unsafe_allow_html=True)

# --- 1. SESSION MANAGEMENT ---
if 'target_query' not in st.session_state:
    st.session_state.target_query = "Real Estate Agencies in Miami"
if 'search_mode' not in st.session_state:
    st.session_state.search_mode = "Dual-Scan (Deep Hunt)"
if 'is_running' not in st.session_state:
    st.session_state.is_running = False
if 'logs' not in st.session_state:
    st.session_state.logs = []
if 'results' not in st.session_state:
    st.session_state.results = []
if 'stats' not in st.session_state:
    st.session_state.stats = {"found": 0, "inserted": 0, "duplicates": 0}

# --- 2. HELPERS ---
def get_ram_status():
    import psutil
    try:
        pid = os.getpid()
        py = psutil.Process(pid)
        mb = py.memory_info().rss / 1024 / 1024
        return mb
    except:
        return 0

# --- 3. THE UI ("Mission Control") ---
st.title("🏹 Unified Intelligence Console")

# Top Intelligence Bar
c1, c2, c3, c4 = st.columns(4)
c1.metric("System Status", "HUNTING" if st.session_state.is_running else "STANDBY")
c2.metric("Leads Found", st.session_state.stats['found'])
c3.metric("Duplicates Skipped", st.session_state.stats['duplicates'])
ram = get_ram_status()
c4.metric("RAM Health", f"{ram:.0f} MB", "Safe" if ram < 450 else "High", delta_color="normal" if ram < 450 else "inverse")

# Main Workspace
tab_plan, tab_exec = st.tabs(["⚙️ Configure Mission", "📡 Live Intelligence Feed"])

with tab_plan:
    col_input, col_settings = st.columns([2, 1])
    
    with col_input:
        st.subheader("🎯 Target Definition")
        # Direct input that updates session state
        st.text_input("Target Keyword", key="target_query", help="E.g., 'Digital Marketing Agencies in London'")
        
        st.write("---")
        st.subheader("🧠 Intelligence Mode")
        mode = st.radio("Select Strategy", 
                 ["Dual-Scan (Deep Hunt)", "Google Maps (Local)", "LinkedIn X-Ray (Direct)"],
                 key="search_mode",
                 help="Dual-Scan: Finds Business on Maps -> Then Finds CEO on LinkedIn.\nGoogle Maps: Fast local data only.\nX-Ray: Direct people search.")
        
        if mode == "LinkedIn X-Ray (Direct)":
            with st.expander("🛠️ Boolean String Builder", expanded=True):
                c_role, c_niche, c_loc = st.columns(3)
                role = c_role.selectbox("Role", ["CEO", "Founder", "Owner", "Director", "Managing Director"])
                niche = c_niche.text_input("Niche/Industry", "SaaS")
                loc = c_loc.text_input("Location", "USA")
                
                generated_dork = f'site:linkedin.com/in ("{role}") AND "{niche}" AND "{loc}"'
                st.code(generated_dork, language="text")
                if st.button("Apply to Target"):
                    st.session_state.target_query = generated_dork
                    st.rerun()

    with col_settings:
        st.subheader("⚙️ Parameters")
        st.slider("Scrape Limit", 5, 50, 10, key="limit")
        st.info("Dual-Scan requires 2x API calls (Google + LinkedIn) per lead.")
        
        st.write("---")
        st.subheader("🚀 Launchpad")
        armed = st.toggle("ARMED / DISARMED", value=False)
        
        if armed:
            if st.button("🚀 LAUNCH MISSION", type="primary", use_container_width=True):
                st.session_state.is_running = True
                st.session_state.logs = []
                st.session_state.results = [] 
                st.session_state.stats = {"found": 0, "inserted": 0, "duplicates": 0}
                st.toast("Mission Launched!", icon="🚀")
                # Switch to tab 2 logic handled by rerunning and defaulting to it? 
                # Streamlit doesn't support programmatic tab switch easily, user must click.
                # But we can show a message.
                st.rerun()
        else:
            st.button("🚫 SYSTEMS DISARMED", disabled=True, use_container_width=True)

with tab_exec:
    # Dual Panel Workspace
    col_feed, col_data = st.columns([1, 2])
    
    with col_feed:
        st.subheader("📡 Intelligence Feed")
        log_placeholder = st.empty()
        if st.session_state.logs:
            log_placeholder.code("\n".join(st.session_state.logs[-15:]), language="text")
        else:
            log_placeholder.info("Awaiting Mission Start...")

    with col_data:
        st.subheader("🎯 Enriched Lead Repository")
        results_placeholder = st.empty()
        
        if st.session_state.results:
            # Create a clean dataframe view
            df = pd.DataFrame(st.session_state.results)
            
            # Reorder columns for "Hard Signals" visibility
            desired_order = ["name", "founder", "tech", "website", "phone", "email", "score", "summary"]
            # Filter to existing columns
            cols = [c for c in desired_order if c in df.columns]
            # Add any remaining
            remaining = [c for c in df.columns if c not in cols]
            
            st.dataframe(
                df[cols + remaining], 
                hide_index=True,
                column_config={
                    "website": st.column_config.LinkColumn("Website"),
                    "founder": st.column_config.TextColumn("Founder Match"),
                    "tech": st.column_config.TextColumn("Tech Stack"),
                }
            )
            
            csv = df.to_csv(index=False).encode('utf-8')
            st.download_button("📥 Download CSV", csv, "leads.csv", "text/csv")
        else:
            results_placeholder.info("No leads captured in this session.")

# --- 4. EXECUTION ENGINE ---
if st.session_state.is_running:
    
    def update_ui(msg):
        print(msg)
        st.session_state.logs.append(msg)
        
        if "Discovered:" in msg or "Scraped:" in msg:
            st.session_state.stats['found'] += 1
        if "Saved" in msg or "SAVED" in msg:
            st.session_state.stats['inserted'] += 1
        if "Duplicate" in msg:
            st.session_state.stats['duplicates'] += 1
            
        log_placeholder.code("\n".join(st.session_state.logs[-15:]), language="text")

    try:
        hunter = LeadHunter(keyword=st.session_state.target_query, limit=st.session_state.limit)
        
        update_ui(f"🚀 Initializing Hunter for: {st.session_state.target_query}")
        mode = st.session_state.search_mode
        update_ui(f"📡 Mode: {mode}")
        
        if mode == "Dual-Scan (Deep Hunt)":
            leads = asyncio.run(hunter.run_mission(keyword=st.session_state.target_query, update_callback=update_ui, enrich_with_xray=True))
        elif mode == "Google Maps (Local)":
            leads = asyncio.run(hunter.run_mission(keyword=st.session_state.target_query, update_callback=update_ui, enrich_with_xray=False))
        else:
            # LinkedIn X-Ray
            leads = asyncio.run(hunter.run_linkedin_mission(keyword=st.session_state.target_query, update_callback=update_ui))
            
        st.session_state.results = leads
        st.session_state.is_running = False
        st.success("Mission Complete!")
        st.balloons()
        st.rerun()
        
    except Exception as e:
        update_ui(f"❌ Critical Error: {e}")
        st.session_state.is_running = False
        st.error(f"Error: {e}")
