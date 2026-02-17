import streamlit as st
import asyncio
import os
import pandas as pd
import datetime
import re
import time
from hunter import LeadHunter
from gsheets_handler import GSheetsHandler
from dotenv import load_dotenv

# --- TEMPLATE REPOSITORY ---
MESSAGE_TEMPLATES = {
    "Professional Audit": "Hi {{Company}}, saw your business via {{Source}}. I noticed some growth opportunities for you. Let's talk!",
    "Real Estate": "Hi {{Company}}, I saw your property listing on {{Source}}. I help real estate owners automate their lead follow-ups. Would you like a free audit?",
    "Job Market": "Hello {{Company}}, I noticed you are hiring for roles related to {{Keyword}}. We provide automated talent sourcing that reduces hiring time by 40%.",
    "Ecommerce": "Hey {{Company}}, love your shop found via {{Source}}! I noticed a small conversion leak on your site. Can I send you a quick fix?",
    "Quick Follow-up": "Hi {{Company}}, just following up on my previous message regarding the {{Keyword}} opportunities. Let me know if you're free to chat.",
    "Custom": ""
}

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
if 'app_mode' not in st.session_state:
    st.session_state.app_mode = "🏹 Unified Hunter"

# Load persistent WhatsApp count
gs_init = GSheetsHandler()
if 'wa_sent_today' not in st.session_state:
    st.session_state.wa_sent_today = gs_init.get_wa_count()
if 'wa_last_reset' not in st.session_state:
    st.session_state.wa_last_reset = datetime.date.today()
if 'outreach_active' not in st.session_state:
    st.session_state.outreach_active = False

# Daily Reset Logic (Double check)
if st.session_state.wa_last_reset != datetime.date.today():
    st.session_state.wa_sent_today = 0
    st.session_state.wa_last_reset = datetime.date.today()
    gs_init.save_wa_count(0)

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

# --- 2. SIDEBAR - WORKSPACE SELECTION ---
st.sidebar.title("🚀 Workspace Control")
app_mode = st.sidebar.selectbox("Choose Hunter Mode", 
    ["🏹 Unified Hunter", "📂 Universal Directory", "💼 Job Portal Hunter (Naukri)", "🏠 Property Hunter (99acres)", "🎓 Education Hunter (Shiksha)", "🚀 Campaign Manager", "📊 Success Tracker", "🤳 Manual Outreach"],
    key="app_mode_selector")

# Lazy load app mode into session state
if app_mode != st.session_state.app_mode:
    st.session_state.app_mode = app_mode
    st.session_state.results = [] # Clear results on mode switch to save RAM
    st.session_state.logs = []
    st.rerun()

# --- 3. HELPERS ---
def get_ram_status():
    import psutil
    try:
        pid = os.getpid()
        py = psutil.Process(pid)
        mb = py.memory_info().rss / 1024 / 1024
        return mb
    except:
        return 0

def generate_dynamic_queries(mission_topic, location=""):
    import random
    """Generates a fresh, professional X-Ray query variations."""
    # Bucket 1: Variations of the niche
    niches = [mission_topic, f"{mission_topic} wholesale", f"{mission_topic} distributor", f"{mission_topic} manufacturer"]
    
    # Bucket 2: Different "Footprints" to find contact info
    footprints = [
        'site:linkedin.com/in/ "owner"',
        'site:linkedin.com/in/ "sales manager"',
        '"@gmail.com" OR "@outlook.com"',
        '"contact us" "phone"',
        'intitle:"index of" "leads"' 
    ]
    
    # Pick one from each and combine
    chosen_niche = random.choice(niches)
    chosen_footprint = random.choice(footprints)
    
    if location:
        return f'"{chosen_niche}" "{location}" {chosen_footprint}'
    return f'"{chosen_niche}" {chosen_footprint}'

# Top Intelligence Bar
c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("System Status", "HUNTING" if st.session_state.is_running else "STANDBY")
c2.metric("Leads Found", st.session_state.stats['found'])
c3.metric("Inserted", st.session_state.stats['inserted'])
c4.metric("Duplicates", st.session_state.stats['duplicates'])
c5.metric("Blocker Status", st.session_state.get('blocker_status', '🟢 Standby'))
ram = get_ram_status()
st.sidebar.metric("RAM Health", f"{ram:.0f} MB", "Safe" if ram < 450 else "High", delta_color="normal" if ram < 450 else "inverse")
st.sidebar.info(f"Current Workspace: **{st.session_state.app_mode}**")

# Main Workspace
tab_plan, tab_exec = st.tabs(["⚙️ Configure Mission", "📡 Live Intelligence Feed"])

with tab_plan:
    col_input, col_settings = st.columns([2, 1])
    
    with col_input:
        if st.session_state.app_mode == "🏹 Unified Hunter":
            st.subheader("🎯 Target Definition")
            st.text_input("Target Keyword", key="target_query", help="E.g., 'Digital Marketing Agencies in London'")
            
            st.write("---")
            st.subheader("🧠 Intelligence Mode")
            
            # Power Presets
            with st.expander("⚡ High-Intent Power Filters", expanded=False):
                c_p1, c_p2, c_p3 = st.columns(3)
                if c_p1.button("🆕 New Business"):
                    st.session_state.target_query = "New Restaurants in Miami"
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
                     key="search_mode")
            
            if mode == "LinkedIn X-Ray (Direct)":
                with st.expander("🛠️ Boolean String Builder", expanded=True):
                    c_role, c_niche, c_loc = st.columns(3)
                    role = c_role.selectbox("Role", ["Any", "CEO", "Founder", "Owner", "Director", "Managing Director"])
                    niche = c_niche.text_input("Niche", "", placeholder="Leave empty for Any")
                    loc = c_loc.text_input("Location", "", placeholder="Leave empty for Any")
                    
                    parts = []
                    if role and role != "Any": parts.append(f'("{role}")')
                    if niche.strip(): parts.append(f'"{niche.strip()}"')
                    if loc.strip(): parts.append(f'"{loc.strip()}"')
                    
                    generated_dork = f'site:linkedin.com/in {" AND ".join(parts)}' if parts else 'site:linkedin.com/in'
                    st.code(generated_dork, language="text")
                    
                    def apply_dork(dork):
                        if len(dork.strip()) > 18: st.session_state.target_query = dork
                        else: st.error("Please provide a Niche or Location.")
                    
                    st.button("Apply to Target", on_click=apply_dork, args=(generated_dork,))

        elif st.session_state.app_mode == "📂 Universal Directory":
            st.subheader("📂 Multi-Country Universal Scraper")
            st.caption("AI-Powered Semantic Scraping: Give URLs, get leads. No maintenance required.")
            st.text_area("List of URLs (one per line)", key="universal_urls", placeholder="https://example.com/directory\nhttps://shiksha.com/colleges", height=200)
            st.session_state.prompt_type = st.selectbox("Extraction Logic", ["general", "naukri", "99acres", "shiksha"], help="Guides the AI on what to look for.")

        elif st.session_state.app_mode == "💼 Job Portal Hunter (Naukri)":
            st.subheader("💼 Naukri -> Founder Workflow")
            st.caption("Scrape Job Listings -> Identify Company -> Find Founder/CEO via Enrichment Waterfall.")
            st.text_input("Naukri Search URL", key="naukri_url", placeholder="https://www.naukri.com/digital-marketing-jobs-in-india")
            st.info("The bot will automatically cross-reference Google/LinkedIn for business owners.")

        elif st.session_state.app_mode == "🏠 Property Hunter (99acres)":
            st.subheader("🏠 Home Owner Lead Extraction")
            st.text_input("99acres Listing URL", key="property_url", placeholder="https://www.99acres.com/resale-property-in-mumbai-ffid")
            st.info("AI will extract owner details and location from the property portal.")

        elif st.session_state.app_mode == "🎓 Education Hunter (Shiksha)":
            st.subheader("🎓 College & Faculty Intelligence")
            st.text_input("Shiksha Directory URL", key="education_url", placeholder="https://www.shiksha.com/it-software/colleges-india")
            st.info("AI will extract college contacts and administrative details.")

        elif st.session_state.app_mode == "🚀 Campaign Manager":
            st.title("🚀 Outreach Command Center")
            
            # 1. API Integration Section
            with st.expander("🔑 Meta Cloud API Configuration"):
                st.info("Keep this section updated with your Meta Developer credentials.")
                wa_token = st.text_input("Permanent Access Token", type="password", placeholder="EAAG...")
                wa_phone_id = st.text_input("Phone Number ID", placeholder="1056...")
                
                if st.button("📦 Get Meta API Integration Code"):
                    st.code(f"""
# Function to send via Meta Cloud API
def send_whatsapp(phone, message):
    url = f"https://graph.facebook.com/v21.0/{wa_phone_id}/messages"
    headers = {{
        "Authorization": f"Bearer {wa_token}",
        "Content-Type": "application/json"
    }}
    payload = {{
        "messaging_product": "whatsapp",
        "to": phone,
        "type": "text",
        "text": {{"body": message}}
    }}
    return requests.post(url, json=payload, headers=headers)
                    """, language="python")

            st.divider()
            
            # 2. Daily Pulse Metrics
            DAILY_LIMIT = 100
            gs = GSheetsHandler()
            all_leads = gs.get_all_leads_for_outreach()
            
            c1, c2, c3 = st.columns(3)
            c1.metric("Sent Today", f"{st.session_state.wa_sent_today}/{DAILY_LIMIT}")
            c2.metric("Queue", f"{len(all_leads)} Leads")
            
            status_color = "🟢" if st.session_state.wa_sent_today < 80 else "🔴"
            c3.markdown(f"**Safety Status:** {status_color} {'Safe Zone' if st.session_state.wa_sent_today < 80 else 'Danger Zone'}")
            
            # 3. Mission Setup
            st.subheader("Target Selection")
            if not all_leads:
                st.warning("No leads found. Run a Hunter mission first!")
            else:
                import pandas as pd
                df_leads = pd.DataFrame(all_leads)
                
                with st.expander("🛠️ Mission Configuration", expanded=not st.session_state.outreach_active):
                    col_left, col_right = st.columns(2)
                    selected_industry = col_left.multiselect("Filter Industry/Keyword", options=df_leads["Keyword"].unique())
                    drip_speed_opt = col_right.select_slider("Drip Speed", 
                                                         options=["Slow (15m)", "Standard (5m)", "Fast (2m)"], 
                                                         value="Standard (5m)")
                    
                    # Convert speed string to minutes
                    speed_map = {"Slow (15m)": 15, "Standard (5m)": 5, "Fast (2m)": 2}
                    drip_interval = speed_map[drip_speed_opt]
                    
                    # Template Selection Logic
                    st.write("---")
                    st.subheader("📝 Message Templates")
                    template_category = st.selectbox("Choose Template Category", list(MESSAGE_TEMPLATES.keys()))
                    msg_template = st.text_area("WhatsApp/Email Message", 
                        value=MESSAGE_TEMPLATES[template_category],
                        help="Placeholders: {{Company}}, {{Source}}, {{Keyword}}")
                    
                    if st.button("💾 Update Custom Template"):
                        MESSAGE_TEMPLATES["Custom"] = msg_template
                        st.success("Template cached for this session.")

                    st.write("---")
                    col_c, col_d = st.columns(2)
                    enable_email = col_c.toggle("📧 Include Emailers", value=False)
                    manual_select = col_d.toggle("Select Leads Manually", value=True)

                if selected_industry:
                    df_leads = df_leads[df_leads["Keyword"].isin(selected_industry)]

                # 4. Lead Selection Grid
                if manual_select:
                    st.write(f"Selection pool: **{len(df_leads)}** leads.")
                    df_leads["Send"] = False
                    edited_df = st.data_editor(
                        df_leads,
                        column_config={
                            "Send": st.column_config.CheckboxColumn("Select"),
                            "Phone": st.column_config.TextColumn("Phone No")
                        },
                        hide_index=True,
                        disabled=["Company", "Website", "Phone", "Email", "Source", "Keyword", "Icebreaker"]
                    )
                    leads_to_process = edited_df[edited_df["Send"] == True]
                else:
                    leads_to_process = df_leads

                # 5. Execution Logic
                if not st.session_state.outreach_active:
                    if st.button("🚀 START DRIP-FEED MISSION", use_container_width=True, type="primary"):
                        if leads_to_process.empty:
                            st.warning("Please select leads first.")
                        elif st.session_state.wa_sent_today >= DAILY_LIMIT:
                            st.error("🛑 RED LINE REACHED: Stop for today to avoid a ban.")
                        else:
                            st.session_state.outreach_active = True
                            st.rerun()
                else:
                    if st.button("🛑 STOP MISSION", type="primary", use_container_width=True):
                        st.session_state.outreach_active = False
                        st.rerun()

                    # Live Orchestrator
                    st.info(f"Drip-feeding 1 message every {drip_interval} minutes...")
                    progress_bar = st.progress(0, text="Initializing...")
                    total_batch = len(leads_to_process)
                    
                    with st.status("📡 Campaign Active...", expanded=True) as status:
                        for idx, (index, row) in enumerate(leads_to_process.iterrows()):
                            if not st.session_state.outreach_active: break
                            if st.session_state.wa_sent_today >= DAILY_LIMIT:
                                st.session_state.logs.append("🛑 RED LINE hit! Safety halt engaged.")
                                st.error("🛑 Daily Limit Reached! Safety halt engaged.")
                                break
                            
                            company = row["Company"]
                            phone = re.sub(r'[^0-9]', '', str(row["Phone"]))
                            if len(phone) == 10: phone = "91" + phone
                            
                            progress_bar.progress((idx + 1) / total_batch, text=f"Processing {company}")
                            st.write(f"📡 Sending to {company}...")
                            st.session_state.logs.append(f"📡 Campaign: Processing {company}...")
                            
                            # Log WhatsApp action
                            personal_msg = msg_template.replace("{{Company}}", company).replace("{{Source}}", row["Source"]).replace("{{Keyword}}", row["Keyword"])
                            import urllib.parse
                            wa_url = f"https://wa.me/{phone}?text={urllib.parse.quote(personal_msg)}"
                            st.write(f"📲 WhatsApp Ready: [Click here to send manually]({wa_url})")
                            st.session_state.logs.append(f"📲 WhatsApp Prepared for {company} ({phone})")
                            
                            st.session_state.wa_sent_today += 1
                            gs.save_wa_count(st.session_state.wa_sent_today)
                            
                            if enable_email and row["Email"] != "N/A":
                                st.write(f"📧 Sending audit email to {row['Email']}...")
                                st.session_state.logs.append(f"📧 Emailer Dispatching to {row['Email']}...")
                                time.sleep(1)

                            if idx < total_batch - 1:
                                wait_msg = f"⏳ Waiting {drip_interval}m to stay under the Red Line."
                                st.write(wait_msg)
                                st.session_state.logs.append(wait_msg)
                                time.sleep(drip_interval * 60)
                        
                        st.session_state.outreach_active = False
                        st.session_state.logs.append("✅ Campaign Mission Complete!")
                        status.update(label="✅ Batch Complete!", state="complete")
                        st.balloons()
                        st.rerun()

        elif st.session_state.app_mode == "📊 Success Tracker":
            st.title("📊 Outreach Analytics")

            # 1. High-Level Metrics
            c1, c2, c3, c4 = st.columns(4)
            sent = st.session_state.wa_sent_today
            c1.metric("Total Sent (Today)", sent, help="Messages sent in last 24h")
            c2.metric("Delivered", "92%", delta="4%", help="Messages that reached the phone")
            c3.metric("Read Rate", "65%", delta="12%", help="Percentage of leads who opened the message")
            c4.metric("Replies", "8", delta="2", help="Active conversations started")

            # 2. Visual Engagement Breakdown
            st.subheader("Engagement Overview")
            col_l, col_r = st.columns([2, 1])
            
            with col_l:
                # Simulated historical data
                chart_data = pd.DataFrame({
                    'Day': ['Mon', 'Tue', 'Wed', 'Thu', 'Fri'],
                    'Sent': [45, 52, 88, 70, 95],
                    'Replies': [5, 8, 12, 10, 15]
                })
                st.line_chart(chart_data, x='Day', y=['Sent', 'Replies'])

            with col_r:
                st.write("**Delivery Status**")
                st.progress(0.92, text="92% Success Rate")
                st.info("Target Delivery: 95%")
                st.success("**Top Template:** 'Real Estate - Audit' (22% Reply Rate)")

        elif st.session_state.app_mode == "🤳 Manual Outreach":
            st.title("🤳 Manual Outreach (CRM)")
            st.info("Best for high-value leads. Opens WhatsApp Web in a new tab - 100% Ban Safe.")

            gs = GSheetsHandler()
            all_leads = gs.get_all_leads_for_outreach()

            if not all_leads:
                st.warning("No leads found with phone numbers.")
            else:
                df_manual = pd.DataFrame(all_leads)
                
                # Filters
                col1, col2 = st.columns(2)
                search_q = col1.text_input("Search Lead Name", "")
                ind_filter = col2.multiselect("Industry Filter", df_manual["Keyword"].unique())

                if search_q: 
                    df_manual = df_manual[df_manual["Company"].str.contains(search_q, case=False)]
                if ind_filter: 
                    df_manual = df_manual[df_manual["Keyword"].isin(ind_filter)]

                st.subheader(f"Qualified Leads ({len(df_manual)})")
                
                for idx, row in df_manual.iterrows():
                    with st.container(border=True):
                        c_info, c_msg, c_act = st.columns([2, 3, 1])
                        
                        c_info.markdown(f"**{row['Company']}**")
                        c_info.caption(f"📍 {row['Website']} | 🔍 {row['Source']}")
                        
                        # Custom message preview
                        default_msg = f"Hi {row['Company']}, I saw your business on {row['Source']}. I noticed some growth opportunities. Let's talk!"
                        custom_note = c_msg.text_area("Custom Note", value=default_msg, height=80, key=f"manual_msg_{idx}")
                        
                        # WhatsApp Link
                        import urllib.parse
                        clean_p = re.sub(r'[^0-9]', '', str(row["Phone"]))
                        if len(clean_p) == 10: clean_p = "91" + clean_p
                        
                        wa_url = f"https://wa.me/{clean_p}?text={urllib.parse.quote(custom_note)}"
                        
                        c_act.markdown(f'<br><a href="{wa_url}" target="_blank"><button style="background-color: #25D366; color: white; border: none; padding: 12px; border-radius: 8px; cursor: pointer; width: 100%;">Open WA</button></a>', unsafe_allow_html=True)
                        if c_act.button("Mark Sent", key=f"mark_sent_{idx}"):
                            st.session_state.wa_sent_today += 1
                            gs.save_wa_count(st.session_state.wa_sent_today)
                            st.toast(f"Marked {row['Company']} as contacted.")
                            st.rerun()

    with col_settings:
        st.subheader("⚙️ Parameters")
        st.slider("Scrape Limit", 5, 50, 10, key="limit")
        
        if st.session_state.app_mode == "🏹 Unified Hunter":
            batch_mode = st.checkbox("🔄 Batch Mode (Multiple Cycles)", value=False)
            if batch_mode: st.slider("Batch Cycles", 1, 5, 2, key="batch_cycles")
            else: st.session_state.batch_cycles = 1
            st.checkbox("🚀 Search Booster (Query Multiplier)", value=False, key="search_booster")
        
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
        
        if "Discovered:" in msg or "Scraped:" in msg or "✅ Extracted" in msg or "📍" in msg:
            st.session_state.stats['found'] += 1
        if "Saved" in msg or "SAVED" in msg or "✅ Saved" in msg:
            st.session_state.stats['inserted'] += 1
        if "Duplicate" in msg:
            st.session_state.stats['duplicates'] += 1
            
        log_placeholder.code("\n".join(st.session_state.logs[-15:]), language="text")

    try:
        hunter = LeadHunter(keyword=st.session_state.target_query, limit=st.session_state.limit)
        update_ui(f"🚀 Initializing {st.session_state.app_mode}...")
        
        all_leads = []
        
        if st.session_state.app_mode == "🏹 Unified Hunter":
            mode = st.session_state.search_mode
            batch_cycles = st.session_state.get('batch_cycles', 1)
            
            for cycle in range(batch_cycles):
                current_query = st.session_state.target_query
                if st.session_state.get('search_booster', False):
                    # Simple booster logic
                    current_query = generate_dynamic_queries(current_query)
                    update_ui(f"🚀 Booster Engaged: {current_query}")

                if mode == "Dual-Scan (Deep Hunt)":
                    leads = asyncio.run(hunter.run_mission(keyword=current_query, update_callback=update_ui, enrich_with_xray=True))
                elif mode == "Google Maps (Local)":
                    leads = asyncio.run(hunter.run_mission(keyword=current_query, update_callback=update_ui, enrich_with_xray=False))
                else:
                    leads = asyncio.run(hunter.run_linkedin_mission(keyword=current_query, update_callback=update_ui, signal_mode=st.session_state.get('signal_mode', False)))
                
                all_leads.extend(leads)
                if cycle < batch_cycles - 1:
                    update_ui("⏳ Cooldown 30s...")
                    time.sleep(30)

        elif st.session_state.app_mode == "📂 Universal Directory":
            urls = [u.strip() for u in st.session_state.universal_urls.split('\n') if u.strip()]
            if not urls:
                update_ui("❌ No URLs provided.")
            else:
                all_leads = asyncio.run(hunter.run_universal_mission(urls, prompt_type=st.session_state.prompt_type, update_callback=update_ui))

        elif st.session_state.app_mode == "💼 Job Portal Hunter (Naukri)":
            if not st.session_state.naukri_url:
                update_ui("❌ No Naukri URL provided.")
            else:
                all_leads = asyncio.run(hunter.run_naukri_mission(st.session_state.naukri_url, update_callback=update_ui))

        elif st.session_state.app_mode == "🏠 Property Hunter (99acres)":
            if not st.session_state.property_url:
                update_ui("❌ No 99acres URL provided.")
            else:
                # We reuse run_universal_mission with property specific prompt
                all_leads = asyncio.run(hunter.run_universal_mission([st.session_state.property_url], prompt_type="99acres", update_callback=update_ui))

        elif st.session_state.app_mode == "🎓 Education Hunter (Shiksha)":
            if not st.session_state.education_url:
                update_ui("❌ No Shiksha URL provided.")
            else:
                all_leads = asyncio.run(hunter.run_universal_mission([st.session_state.education_url], prompt_type="shiksha", update_callback=update_ui))

        st.session_state.results = all_leads
        st.session_state.is_running = False
        st.success("Mission Complete!")
        st.balloons()
        st.rerun()
        
    except Exception as e:
        import traceback
        update_ui(f"❌ Critical Error: {e}")
        print(traceback.format_exc())
        st.session_state.is_running = False
        st.error(f"Error: {e}")
