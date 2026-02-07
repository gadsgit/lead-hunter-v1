import streamlit as st
import asyncio
import os
import pandas as pd
from hunter import LeadHunter
from dotenv import load_dotenv

load_dotenv()
if os.path.exists(".env.local"):
    load_dotenv(".env.local", override=True)

st.set_page_config(page_title="Hunter Mission Control", layout="wide", page_icon="🏹")

# --- CUSTOM STYLING ---
st.markdown("""
    <style>
    .main { background-color: #0e1117; color: #ffffff; }
    div[data-testid="stMetricValue"] { font-size: 24px; color: #00FF00; }
    div[data-testid="stMetricLabel"] { font-size: 14px; color: #aaaaaa; }
    .stButton>button { border-radius: 5px; font-weight: bold; }
    </style>
    """, unsafe_allow_html=True)

# --- 1. SESSION MANAGEMENT (The "Brain") ---
if 'target_query' not in st.session_state:
    st.session_state.target_query = "Real Estate Agencies in Miami"
if 'search_mode' not in st.session_state:
    st.session_state.search_mode = "Google Maps"
if 'is_running' not in st.session_state:
    st.session_state.is_running = False
if 'logs' not in st.session_state:
    st.session_state.logs = []
if 'results' not in st.session_state:
    st.session_state.results = []
if 'stats' not in st.session_state:
    st.session_state.stats = {"found": 0, "inserted": 0, "duplicates": 0}

# --- 2. THE UI ("Mission Control") ---
st.title("🏹 Hunter Mission Control")

# Top Metrics Row
c1, c2, c3, c4 = st.columns(4)
c1.metric("Status", "HUNTING" if st.session_state.is_running else "STANDBY")
c2.metric("Leads Found", st.session_state.stats['found'])
c3.metric("Inserted", st.session_state.stats['inserted'])
c4.metric("Duplicates", st.session_state.stats['duplicates'])

# Tabbed Interface
tab_config, tab_live = st.tabs(["⚙️ Configure Mission", "📡 Live Intelligence Feed"])

with tab_config:
    st.subheader("🎯 Target Definition")
    
    # Input field that updates session state directly
    # We use key=... to bind directly to session state, simpler than manual assignment
    st.text_input("Target Keyword", key="target_query", help="E.g., 'Plumbers in Miami' or 'CEO Cosmetic Manufacturing'")
    
    st.radio("Intelligence Source", ["Google Maps", "LinkedIn X-Ray"], key="search_mode")

    limit = st.slider("Scrape Limit", 5, 50, 10, key="limit")
    
    st.write("---")
    st.subheader("🚀 Launch Sequence")
    
    # SAFETY TOGGLE
    armed = st.toggle("ARMED / DISARMED", value=False, help="Safety switch. Must be ON to launch.")
    
    if armed:
        if st.button("🚀 LAUNCH MISSION", type="primary", use_container_width=True):
            st.session_state.is_running = True
            st.session_state.logs = []        # Clear previous logs
            st.session_state.results = []     # Clear previous results
            st.session_state.stats = {"found": 0, "inserted": 0, "duplicates": 0}
            st.rerun()
    else:
        st.button("🚫 SYSTEMS DISARMED", disabled=True, use_container_width=True)

with tab_live:
    col_logs, col_results = st.columns([1, 1])
    
    with col_logs:
        st.subheader("📜 Live Event Log")
        log_placeholder = st.empty()
        
        # Always show logs if they exist
        if st.session_state.logs:
            log_placeholder.code("\n".join(st.session_state.logs[-15:]), language="text")
        else:
            log_placeholder.info("System Ready. Awaiting Launch.")

    with col_results:
        st.subheader("📊 Recent Leads")
        results_placeholder = st.empty()
        
        if st.session_state.results:
            df = pd.DataFrame(st.session_state.results)
            results_placeholder.dataframe(df)
            
            # Download Button
            csv = df.to_csv(index=False).encode('utf-8')
            st.download_button(
                "📥 Download CSV",
                csv,
                "leads.csv",
                "text/csv",
                key='download-csv'
            )
        else:
            results_placeholder.info("No leads captured in this session.")

# --- 3. THE ENGINE (Execution Logic) ---
if st.session_state.is_running:
    
    # Define the callback to update the UI in real-time
    def update_ui(msg):
        print(msg) # Print to console
        st.session_state.logs.append(msg)
        
        # Parse metrics from logs to update the top bar
        if "Discovered:" in msg or "Scraped:" in msg:
            st.session_state.stats['found'] += 1
        if "Saved" in msg or "SAVED" in msg:
            st.session_state.stats['inserted'] += 1
        if "Duplicate" in msg:
            st.session_state.stats['duplicates'] += 1
            
        # Force a refresh of the log placeholder
        log_placeholder.code("\n".join(st.session_state.logs[-15:]), language="text")

    try:
        # NOTE: We access session state via the keys bound in the widgets above
        hunter = LeadHunter(keyword=st.session_state.target_query, limit=st.session_state.limit)
        
        update_ui(f"🚀 Initializing Hunter for: {st.session_state.target_query}")
        update_ui(f"📡 Mode: {st.session_state.search_mode}")
        
        if st.session_state.search_mode == "Google Maps":
            leads = asyncio.run(hunter.run_mission(keyword=st.session_state.target_query, update_callback=update_ui))
        else:
            # LinkedIn Mode
            leads = asyncio.run(hunter.run_linkedin_mission(keyword=st.session_state.target_query, update_callback=update_ui))
            
        st.session_state.results = leads
        st.session_state.is_running = False # Mission Complete
        st.success("Mission Complete!")
        st.balloons()
        # Rerun to update the final state and show 'STANDBY'
        st.rerun()
        
    except Exception as e:
        update_ui(f"❌ Critical Error: {e}")
        st.session_state.is_running = False
        st.error(f"Error: {e}")
