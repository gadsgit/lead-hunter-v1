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
st.title("🏹 Lead Hunter - Unified Intelligence Console")

# --- CUSTOM STYLING ---
st.markdown("""
    <style>
    .main { background-color: #0e1117; color: #ffffff; }
    /* Top Bar Metrics (Big & Bold) */
    div[data-testid="stMetricValue"] { font-size: 36px !important; color: #00FF00; font-weight: 800; }
    div[data-testid="stMetricLabel"] { font-size: 18px !important; color: #aaaaaa; }
    
    /* Input Labels */
    .stTextInput > label, .stSelectbox > label, .stRadio > label { font-size: 20px !important; font-weight: 600; }
    
    /* Tabs (Large & Clickable) */
    .stTabs [data-baseweb="tab-list"] { gap: 20px; }
    .stTabs [data-baseweb="tab"] { height: 60px; font-size: 20px !important; background-color: #1E1E1E; border-radius: 8px; padding: 10px 20px; }
    .stTabs [aria-selected="true"] { background-color: #FF4B4B; color: white; }
    
    /* Buttons */
    .stButton>button { font-size: 22px !important; height: 55px !important; font-weight: bold; border-radius: 8px; }
    
    /* Dataframes - keep standard for readability */
    div[data-testid="stDataFrame"] { font-size: 14px; }
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
if 'blocker_status' not in st.session_state:
    st.session_state.blocker_status = "🟢 Standby"
if 'signal_mode' not in st.session_state:
    st.session_state.signal_mode = False

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

# Top Intelligence Bar
c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("System Status", "HUNTING" if st.session_state.is_running else "STANDBY")
c2.metric("Leads Found", st.session_state.stats['found'])
c3.metric("Inserted", st.session_state.stats['inserted'])
c4.metric("Duplicates", st.session_state.stats['duplicates'])
c5.metric("Blocker Status", st.session_state.get('blocker_status', '🟢 Standby'))
ram = get_ram_status()
st.sidebar.metric("RAM Health", f"{ram:.0f} MB", "Safe" if ram < 450 else "High", delta_color="normal" if ram < 450 else "inverse")

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
        
        # Power Presets
        with st.expander("⚡ High-Intent Power Filters", expanded=False):
            c_p1, c_p2, c_p3 = st.columns(3)
            if c_p1.button("🆕 New Business"):
                st.session_state.target_query = "New Restaurants in Miami" # Example
                st.session_state.search_mode = "Google Maps (Local)"
                st.rerun()
            if c_p2.button("🚨 Emergency Svc"):
                st.session_state.target_query = "Emergency Plumber in London"
                st.session_state.search_mode = "Google Maps (Local)"
                st.rerun()
            if c_p3.button("🟢 Open Now"):
                st.session_state.target_query = "Dentist Open Now New York"
                st.session_state.search_mode = "Google Maps (Local)"
                st.rerun()
        
        st.write("---")
        st.subheader("🎯 Buying Signal Presets")
        st.caption("Target high-intent LinkedIn posts with buying signals")
        c_s1, c_s2, c_s3 = st.columns(3)
        if c_s1.button("📢 Hiring Signal"):
            st.session_state.target_query = 'site:linkedin.com/posts "hiring" AND "freelancer" AND "marketing" "USA"'
            st.session_state.search_mode = "LinkedIn X-Ray (Direct)"
            st.session_state.signal_mode = True
            st.rerun()
        if c_s2.button("🛠️ Projects Signal"):
            st.session_state.target_query = 'site:linkedin.com/posts "looking for a developer" OR "recommend an agency" "USA"'
            st.session_state.search_mode = "LinkedIn X-Ray (Direct)"
            st.session_state.signal_mode = True
            st.rerun()
        if c_s3.button("💎 Decision Makers"):
            st.session_state.target_query = 'site:linkedin.com/in "Founder" AND "Shopify" AND "United States"'
            st.session_state.search_mode = "LinkedIn X-Ray (Direct)"
            st.session_state.signal_mode = False
            st.rerun()
                
        # Signal Mode Toggle
        signal_mode = st.toggle("🎯 Signal Mode (Posts)", value=st.session_state.get('signal_mode', False),
            help="Scrape LinkedIn POSTS for buying signals instead of profiles")
        st.session_state.signal_mode = signal_mode
        
        mode = st.radio("Select Strategy", 
                 ["Dual-Scan (Deep Hunt)", "Google Maps (Local)", "LinkedIn X-Ray (Direct)"],
                 key="search_mode",
                 help="Dual-Scan: Finds Business on Maps -> Then Finds CEO on LinkedIn.\nGoogle Maps: Fast local data only.\nX-Ray: Direct people search.")
        
        if mode == "LinkedIn X-Ray (Direct)":
            with st.expander("🛠️ Boolean String Builder", expanded=True):
                c_role, c_niche, c_loc = st.columns(3)
                role = c_role.selectbox("Role", ["Any", "CEO", "Founder", "Owner", "Director", "Managing Director"])
                niche = c_niche.text_input("Niche", "", placeholder="Leave empty for Any")
                loc = c_loc.text_input("Location", "", placeholder="Leave empty for Any")
                
                # Dynamic Dork Construction
                parts = []
                if role and role != "Any": 
                    parts.append(f'("{role}")')
                if niche.strip(): 
                    parts.append(f'"{niche.strip()}"')
                if loc.strip(): 
                    parts.append(f'"{loc.strip()}"')
                
                # Join with AND
                if parts:
                    query_body = " AND ".join(parts)
                    generated_dork = f'site:linkedin.com/in {query_body}'
                else:
                    generated_dork = 'site:linkedin.com/in'

                st.code(generated_dork, language="text")
                
                # Callback to avoid "set state after instantiation" error
                def apply_dork(dork):
                    st.session_state.target_query = dork
                
                st.button("Apply to Target", on_click=apply_dork, args=(generated_dork,))

    with col_settings:
        st.subheader("⚙️ Parameters")
        st.slider("Scrape Limit", 5, 50, 10, key="limit")
        
        # Batch Mode
        batch_mode = st.checkbox("🔄 Batch Mode (Multiple Cycles)", value=False, 
                                 help="Run multiple scraping cycles with 30s cooldown between each. Safer for large datasets.")
        if batch_mode:
            st.slider("Batch Cycles", 1, 5, 2, key="batch_cycles", 
                     help="Number of cycles to run. Total leads = Limit × Cycles")
        else:
            st.session_state.batch_cycles = 1
            
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
            desired_order = [
                "name", "source", "signal", "icebreaker", "content_preview", 
                "gmb", "ad", "web", "speed", 
                "gmb_opp", "ad_opp", "web_opp", "speed_opp", "xray_opp",
                "founder", "tech", "website", "instagram", "facebook", "phone", "email", "score", "summary"
            ]
            # Filter to existing columns
            cols = [c for c in desired_order if c in df.columns]
            # Add any remaining
            remaining = [c for c in df.columns if c not in cols]
            
            st.dataframe(
                df[cols + remaining], 
                hide_index=True,
                column_config={
                    "website": st.column_config.LinkColumn("Website"),
                    "instagram": st.column_config.LinkColumn("Instagram"),
                    "facebook": st.column_config.LinkColumn("Facebook"),
                    "founder": st.column_config.TextColumn("Founder Match"),
                    "tech": st.column_config.TextColumn("Tech Stack"),
                    "gmb": st.column_config.TextColumn("GMB Status", width="small"),
                    "ad": st.column_config.TextColumn("Ads", width="small"),
                    "web": st.column_config.TextColumn("Web Status", width="small"),
                    "speed": st.column_config.TextColumn("Speed", width="small"),
                    "gmb_opp": st.column_config.TextColumn("GMB Opp", width="medium"),
                    "ad_opp": st.column_config.TextColumn("Ad Opp", width="medium"),
                    "web_opp": st.column_config.TextColumn("Web Opp", width="medium"),
                    "speed_opp": st.column_config.TextColumn("Speed Opp", width="medium"),
                    "xray_opp": st.column_config.TextColumn("X-Ray Opp", width="medium"),
                    "signal": st.column_config.TextColumn("Signal", width="small"),
                    "icebreaker": st.column_config.TextColumn("Icebreaker", width="large"),
                    "content_preview": st.column_config.TextColumn("Preview", width="medium"),
                    "source": st.column_config.TextColumn("Lead Source", width="small"),
                }
            )
            
            csv = df.to_csv(index=False).encode('utf-8')
            st.download_button("📥 Download Lead List (CSV)", csv, "leads.csv", "text/csv", type="primary")
        else:
            results_placeholder.info("No leads captured in this session.")

# --- 4. EXECUTION ENGINE ---
if st.session_state.is_running:
    
    def update_ui(msg):
        print(msg)
        st.session_state.logs.append(msg)
        
        # Update blocker status from logs
        if "Blocker Status:" in msg:
            blocker = msg.split("Blocker Status:")[1].strip()
            st.session_state.blocker_status = blocker
        elif "CAPTCHA" in msg or "Consent Block" in msg:
            st.session_state.blocker_status = "🔴 Blocked"
        elif "Consent Handled" in msg:
            st.session_state.blocker_status = "🟡 Consent"
        elif "No Results" in msg:
            st.session_state.blocker_status = "🟡 No Results"
        
        if "Discovered:" in msg or "Scraped:" in msg or "📢" in msg or "🛠️" in msg or "💡" in msg:
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
        
        # Batch Mode Execution
        batch_cycles = st.session_state.get('batch_cycles', 1)
        all_leads = []
        
        for cycle in range(batch_cycles):
            if batch_cycles > 1:
                update_ui(f"🔄 Starting Batch Cycle {cycle + 1}/{batch_cycles}")
            
            if mode == "Dual-Scan (Deep Hunt)":
                leads = asyncio.run(hunter.run_mission(keyword=st.session_state.target_query, update_callback=update_ui, enrich_with_xray=True))
            elif mode == "Google Maps (Local)":
                leads = asyncio.run(hunter.run_mission(keyword=st.session_state.target_query, update_callback=update_ui, enrich_with_xray=False))
            else:
                # LinkedIn X-Ray
                leads = asyncio.run(hunter.run_linkedin_mission(
                    keyword=st.session_state.target_query, 
                    update_callback=update_ui,
                    signal_mode=st.session_state.get('signal_mode', False)
                ))
            
            all_leads.extend(leads)
            
            # Cooldown between cycles (except after last cycle)
            if cycle < batch_cycles - 1:
                update_ui(f"⏳ Cooldown: 30s before next cycle...")
                time.sleep(30)
            
        st.session_state.results = all_leads
        st.session_state.is_running = False
        st.success("Mission Complete!")
        st.balloons()
        st.rerun()
        
    except Exception as e:
        update_ui(f"❌ Critical Error: {e}")
        st.session_state.is_running = False
        st.error(f"Error: {e}")
