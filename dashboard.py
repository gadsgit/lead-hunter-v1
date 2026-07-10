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
import io
from urllib.parse import quote

# --- 0. STATE INITIALIZATION ---
if 'target_query' not in st.session_state:
    st.session_state.target_query = "Real Estate Agencies in Miami"
if 'search_mode' not in st.session_state:
    st.session_state.search_mode = "Dual-Scan (Deep Hunt)"
if 'app_mode' not in st.session_state:
    st.session_state.app_mode = "🏹 Unified Hunter"
if 'is_running' not in st.session_state:
    st.session_state.is_running = False
if 'results' not in st.session_state:
    st.session_state.results = []
if 'stats' not in st.session_state:
    st.session_state.stats = {"found": 0, "inserted": 0, "duplicates": 0}
# Pagination depth tracker: key = "role_niche_city", value = current &start= offset
if 'search_offsets' not in st.session_state:
    with st.spinner("Synchronizing cross-device search pipelines..."):
        st.session_state.search_offsets = GSheetsHandler().load_search_offsets_from_cloud()

# --- SMART AUTO-DE-DUPLICATOR ---
def run_startup_clean_and_dedup():
    local_backup_csv = r"E:\Lead Hunter\incremental_leads_backup.csv"
    if os.path.exists(local_backup_csv):
        try:
            df = pd.read_csv(local_backup_csv)
            initial_count = len(df)
            
            # Ensure standard string formats to safely isolate overlaps
            if 'Company Name' in df.columns:
                df['Company Name'] = df['Company Name'].astype(str).str.strip()
            if 'Website' in df.columns:
                df['Website'] = df['Website'].astype(str).str.strip().str.lower()
            
            # Deduplicate by Website (ignoring N/A defaults) and Company Name
            mask_valid_web = (df['Website'] != 'n/a') & (df['Website'] != '') & (df['Website'].notna())
            df_valid_web = df[mask_valid_web].drop_duplicates(subset=['Website'], keep='first')
            df_invalid_web = df[~mask_valid_web].drop_duplicates(subset=['Company Name'], keep='first')
            
            cleaned_df = pd.concat([df_valid_web, df_invalid_web], ignore_index=True)
            final_count = len(cleaned_df)
            
            if initial_count > final_count:
                cleaned_df.to_csv(local_backup_csv, index=False)
                st.sidebar.success(f"🧹 Cleaned up {initial_count - final_count} duplicate entries automatically!")
        except Exception as e:
            pass

run_startup_clean_and_dedup()

# --- AUTOMATED SUNDAY BACKUP ROTATOR ---
def run_automatic_backup_rotator():
    import os
    import shutil
    from datetime import datetime
    
    local_backup_csv = r"E:\Lead Hunter\incremental_leads_backup.csv"
    backup_directory = r"E:\Lead Hunter\Backups"
    
    if os.path.exists(local_backup_csv):
        try:
            # Check if today is Sunday (weekday index 6 is Sunday in Python datetime)
            today = datetime.now()
            if today.weekday() == 6:
                if not os.path.exists(backup_directory):
                    os.makedirs(backup_directory)
                
                # Formulate distinct timestamped backup file name
                date_str = today.strftime("%Y-%m-%d")
                destination_backup = os.path.join(backup_directory, f"backup_leads_{date_str}.csv")
                
                # Verify we haven't already backed up today to prevent duplicate runs
                if not os.path.exists(destination_backup):
                    shutil.copy2(local_backup_csv, destination_backup)
                    st.sidebar.info(f"💾 Weekly Archive Secured: backup_leads_{date_str}.csv")
        except Exception:
            pass

run_automatic_backup_rotator()

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

# --- GLOBAL INTELLIGENCE CONSTANTS ---
NICHE_BOOSTERS = {
    "Real Estate": ["Property Developer", "Real Estate Broker", "Asset Manager", "Construction"],
    "Tech": ["Software Solutions", "SaaS", "IT Services", "Cloud Computing"],
    "Health": ["Medical Clinic", "Healthcare Provider", "Wellness", "Pharma"],
    "Finance": ["Investment Banking", "Wealth Management", "Fintech", "Insurance"],
    "Digital Marketing": ["Marketing Agency", "SEO Consultant", "PPC Expert", "Content Strategy"]
}

DEFAULT_CITY_MAP = {
    "Noida": "in", "Gurgaon": "in", "Gurugram": "in", "Delhi": "in", "Mumbai": "in",
    "Dubai": "ae", "Abu Dhabi": "ae", "London": "uk", "Singapore": "sg", 
    "New York": "www", "Miami": "www", "Sydney": "au"
}

# --- GLOBAL UTILITY FUNCTIONS ---
def get_boosted_niche(niche_input):
    """Returns a Boolean string of related keywords for high-intent targeting."""
    boosters = NICHE_BOOSTERS.get(niche_input.title(), [])
    if not boosters:
        return f'"{niche_input}"' if niche_input else ""
    all_terms = [niche_input] + boosters
    return "(" + " OR ".join([f'"{term}"' for term in all_terms]) + ")"

def get_country_subdomain(city_name):
    """Maps cities to their specific LinkedIn country codes from session settings."""
    mapping = st.session_state.get('city_map', DEFAULT_CITY_MAP)
    return mapping.get(city_name.title(), "www")

def build_nuclear_string(role, city, niche):
    """Constructs a professional-grade 'Nuclear' Boolean string for LinkedIn X-Ray."""
    # Clean inputs to prevent double-quote or weird encoding errors
    clean_role = str(role).replace('"', '')
    clean_city = str(city).replace('"', '')
    clean_niche = str(niche).replace('"', '')
    
    sub = get_country_subdomain(clean_city)
    
    # Expand Role into Synonyms for broader reach
    if not clean_role or clean_role == "Any":
        role_group = '("CEO" OR "Founder" OR "Owner" OR "Managing Director" OR "President")'
    else:
        role_group = f'("{clean_role}" OR "Founder" OR "Owner")'
    
    # Expand Niche
    niche_group = get_boosted_niche(clean_niche)
    
    # Exclude Noise
    exclusions = "-intitle:jobs -inurl:jobs -inurl:dir -inurl:groups"
    
    # Construction
    parts = [f"site:{sub}.linkedin.com/in/", role_group]
    if clean_city: parts.append(f'"{clean_city}"')
    if niche_group: parts.append(niche_group)
    parts.append(exclusions)
    
    return " ".join(parts)

def export_global_excel():
    """Packs all city databases into separate sheets of a single Excel file."""
    output = io.BytesIO()
    if not st.session_state.get('global_db'):
        return None
    try:
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            for city, leads in st.session_state.global_db.items():
                df = pd.DataFrame(leads)
                df.to_excel(writer, sheet_name=city[:30], index=False)
        return output.getvalue()
    except:
        return None

def save_to_global_db(new_leads, city_name):
    """Categorizes leads by city automatically in the Master Global Database."""
    if not new_leads: return
    city_name = city_name.strip().title() if city_name else "General"
    df_new = pd.DataFrame(new_leads)

    # Note: Instant Saving to incremental_leads_backup.csv is now handled by hunter.py directly
    # for "First-Priority Streaming". We only maintain the global DB state here.

    # Always derive subset_cols before branching so it is always defined
    # (fixes UnboundLocalError when city is new and the else-branch is skipped)
    combined_preview = pd.concat(
        [pd.DataFrame(st.session_state.global_db.get(city_name, [])), df_new]
    ) if city_name in st.session_state.global_db else df_new
    subset_cols = [c for c in ['Link', 'url', 'website', 'Company Name', 'Name', 'name']
                   if c in combined_preview.columns]

    if city_name not in st.session_state.global_db:
        st.session_state.global_db[city_name] = new_leads
    else:
        # Merge and remove duplicates based on Link/URL → Name fallback
        df_old = pd.DataFrame(st.session_state.global_db[city_name])
        combined = pd.concat([df_old, df_new], ignore_index=True)
        if subset_cols:
            combined = combined.drop_duplicates(subset=subset_cols[:1], keep='first')
        st.session_state.global_db[city_name] = combined.to_dict('records')

    # Update master_leads unified view
    all_dfs = [pd.DataFrame(leads) for leads in st.session_state.global_db.values()]
    if all_dfs:
        merged = pd.concat(all_dfs, ignore_index=True)
        st.session_state.master_leads = (
            merged.drop_duplicates(subset=subset_cols[:1], keep='first')
            if subset_cols else merged
        )

def clean_global_duplicates():
    """Removes duplicates across the entire Global Database by unifying then re-splitting."""
    if not st.session_state.global_db: return 0
    
    # 1. Collect all
    all_leads = []
    for city, leads in st.session_state.global_db.items():
        for l in leads:
            l['__city_origin'] = city
            all_leads.append(l)
    
    df = pd.DataFrame(all_leads)
    initial_count = len(df)
    
    # 2. Deduplicate
    subset_cols = [c for c in ['Link', 'website', 'url', 'Company Name', 'Name'] if c in df.columns]
    if subset_cols:
        df = df.drop_duplicates(subset=subset_cols[:1], keep='first')
    
    new_count = len(df)
    
    # 3. Re-split into global_db
    new_db = {}
    for _, row in df.iterrows():
        city = row['__city_origin']
        lead_data = row.to_dict()
        del lead_data['__city_origin']
        if city not in new_db: new_db[city] = []
        new_db[city].append(lead_data)
    
    st.session_state.global_db = new_db
    st.session_state.master_leads = df.drop(columns=['__city_origin']) if '__city_origin' in df.columns else df
    return initial_count - new_count

def sync_to_cloud():
    """Pushes the current clean master_leads to Google Sheets via GSheetsHandler."""
    if 'master_leads' not in st.session_state or st.session_state.master_leads.empty:
        st.warning("No leads in Master Database to sync.")
        return
    
    gs = GSheetsHandler()
    if gs.connect():
        with st.status("☁️ Syncing to Cloud...") as status:
            count = 0
            for _, row in st.session_state.master_leads.iterrows():
                # We use save_lead which handles deduplication logic internally if implemented,
                # but here we just push them to the 'Master_Leads' tab.
                data = row.to_dict()
                gs.save_lead(data, query=data.get('Keyword', 'Global Sync'), source="global_sync")
                count += 1
            status.update(label=f"✅ Cloud Sync Complete: {count} leads uploaded!", state="complete")
        st.toast("☁️ Cloud Sync Complete!")
    else:
        st.error("Failed to connect to Google Sheets. Check your credentials.")

# --- AUTHENTICATION SYSTEM ---
def check_password():
    """Returns `True` if the user had the correct password."""
    if "password_correct" not in st.session_state:
        st.session_state["password_correct"] = False

    if st.session_state["password_correct"]:
        return True

    # Login UI
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.write("")
        st.write("")
        st.write("")
        st.markdown("<h1 style='text-align: center; color: #00FF00;'>🏹 Lead Hunter</h1>", unsafe_allow_html=True)
        st.markdown("<h3 style='text-align: center; color: #ffffff;'>Admin Access Required</h3>", unsafe_allow_html=True)
        
        with st.container(border=True):
            password = st.text_input("Enter Access Key", type="password", placeholder="••••••••")
            if st.button("Unlock Mission Control", use_container_width=True, type="primary"):
                target_password = os.getenv("ADMIN_PASSWORD", "admin123")
                if password == target_password:
                    st.session_state["password_correct"] = True
                    st.rerun()
                else:
                    st.error("🚫 Access Denied: Incorrect Password")
            
            st.info("Note: This dashboard is for authorized personnel only.")
    
    return False

# --- SMART PITCH GENERATOR ---

def generate_smart_pitch(row):
    """Dynamically creates a pitch based on lead's detected 'Opportunities'."""
    name = row.get("Name") or row.get("Company") or "there"
    
    # Priority 1: GMB Issues
    gmb_opp = str(row.get("GMB Status") or row.get("gmb") or "")
    if "Not Found" in gmb_opp or "Unclaimed" in gmb_opp:
        return f"Hi {name}, I noticed your business isn't optimized on Google Maps. You're losing local customers to competitors who are ranked higher. I can fix your GMB visibility in 7 days."
    
    # Priority 2: Web Speed
    speed = str(row.get("Web Speed") or row.get("speed") or "")
    if "Slow" in speed or (re.search(r'(\d+)', speed) and int(re.search(r'(\d+)', speed).group(1)) > 5):
        return f"Hi {name}, I noticed your website takes over {speed} to load. Google penalizes slow sites and 53% of users leave if it takes >3s. Let me optimize your speed for better conversions."
    
    # Priority 3: Ads/Visibility
    ad_opp = str(row.get("Ad Opp") or row.get("ad") or "")
    if "Not running" in ad_opp:
        return f"Hi {name}, I noticed you aren't running Meta Ads. Your competitors are likely stealing your leads while you sleep. I can set up an automated lead gen system for you."

    return f"Hi {name}, I saw your profile and noticed some major growth opportunities for your business. I'd love to send you a quick 2-minute audit. Interested?"

# --- go.php WHATSAPP OUTREACH TOOL ---
MASTER_MAP = {
    "dental": {
        "url_key": "dental",
        "benefit": "patient acquisition signals and clinic growth",
        "hook": "I noticed your clinic's digital footprint and have a specific signal-recovery audit for you.",
        "media_path": "E:/iadsclick-brain/media/dental_audit.png"
    },
    "parents": {
        "url_key": "parents",
        "benefit": "10th-grade board exam result improvement",
        "hook": "I'm reaching out regarding expert coaching in GYC to help your child excel in the 2026 boards.",
        "media_path": "E:/iadsclick-brain/media/gyc_results.png"
    },
    "re_noida": {
        "url_key": "re_noida",
        "benefit": "high-intent lead generation for Noida sectors",
        "hook": "I analyzed your property listings and found a way to automate your lead-gen specifically for Greater Noida."
    },
    "re_yamuna": {
        "url_key": "re_yamuna",
        "benefit": "Yamuna Expressway property investment tracking",
        "hook": "Regarding your listings near the Expressway—I've built a custom AI audit for property movement in that zone."
    },
    "re_uae": {
        "url_key": "re_uae",
        "benefit": "International property exposure and UAE buyer signals",
        "hook": "International property exposure and UAE buyer signals."
    },
    "course_ai": {
        "url_key": "course_ai",
        "benefit": "scaling operations with Agentic AI",
        "hook": "I saw your interest in tech scaling. Here is how our AI course can automate your specific workflow."
    },
    "course_dm": {
        "url_key": "course_dm",
        "benefit": "career growth with digital marketing",
        "hook": "Digital marketing skills that pay for themselves in 30 days:"
    },
    "analytics": {
        "url_key": "analytics",
        "benefit": "Server-Side Tracking and GTM Signal Recovery",
        "hook": "Your tracking setup has some data gaps. I've prepared a brief on how to fix your attribution 100%."
    },
    "ai_agent": {
        "url_key": "ai_agent",
        "benefit": "autonomous business agents for lead nurturing",
        "hook": "I've developed an AI agent that can handle your lead responses 24/7. Check the demo here:"
    },
    "ai_portfolio": {
        "url_key": "ai_portfolio",
        "benefit": "AI lead-gen results for similar businesses",
        "hook": "Check out these AI lead-gen results we've delivered for similar businesses:"
    },
    "seo_india": {
        "url_key": "seo_india",
        "benefit": "organic visibility in the Indian market",
        "hook": "Your SEO rankings for key Indian search terms have room for 3x growth. See the keyword gaps here:"
    },
    "seo_usa": {
        "url_key": "seo_usa",
        "benefit": "US-market expansion and global SEO",
        "hook": "I noticed you're targeting US clients. Here is a strategy to lower your CPC and increase organic reach."
    },
    "local_seo": {
        "url_key": "local_seo",
        "benefit": "Dominating local search in Noida and Dankaur regions",
        "hook": "Dominating local search in Noida and Dankaur regions."
    },
    "meta_ads": {
        "url_key": "meta_ads",
        "benefit": "High-speed lead generation through optimized Meta/FB funnels",
        "hook": "High-speed lead generation through optimized Meta/FB funnels."
    },
    "ppc_audit": {
        "url_key": "ppc_audit",
        "benefit": "Stopping budget leaks and fixing tracking syntax errors",
        "hook": "Stopping budget leaks and fixing tracking syntax errors."
    },
    "contact": {
        "url_key": "contact",
        "benefit": "strategy call",
        "hook": "I'd love to schedule a quick 15-minute strategy call with you:"
    },
    "default": {
        "url_key": "default",
        "benefit": "digital growth and ROI optimization",
        "hook": "I was analyzing your business profile and noticed a few major growth opportunities for 2026."
    }
}

def generate_outreach_tool(lead_name: str, niche_key: str, manual_url: str = None, location: str = "global") -> dict:
    """
    Generates a branded go.php WhatsApp payload for a lead based on MASTER_MAP.
    """
    import urllib.parse as _up
    clean_name = _up.quote(lead_name.replace(" ", "_"))
    clean_loc = _up.quote(location.lower())

    config = MASTER_MAP.get(niche_key, MASTER_MAP["default"])

    if manual_url and manual_url.strip():
        short_link = manual_url.strip()
    else:
        short_link = f"https://iadsclick.com/go.php?to={config['url_key']}&loc={clean_loc}&n={clean_name}"

    hook = config['hook']
    if niche_key == "parents":
        geo_hooks = {
            "gyc": "Are you looking for expert 10th-grade coaching right here in Gaur Yamuna City?",
            "delhi": "We are helping students across Delhi master their Board exams with 1:1 sessions.",
            "global": "I'm reaching out regarding expert coaching in GYC to help your child excel in the 2026 boards."
        }
        hook = geo_hooks.get(location.lower(), geo_hooks["global"])

    full_msg = f"Hi {lead_name}, {hook}\n\n{short_link}"
    wa_link  = f"https://wa.me/?text={_up.quote(full_msg)}"

    return {
        "link"       : wa_link,
        "raw_message": full_msg,
        "short_link" : short_link,
        "tracking_id": f"{config['url_key']}_{lead_name.replace(' ', '_')}",
        "media_path" : config.get("media_path", "")
    }

# --- GLOBAL CALLBACKS ---
def apply_preset(query=None, mode=None, signal=None):
    """Programmatically sets search parameters without widget conflicts."""
    if query: st.session_state.target_query = query
    if mode: st.session_state.search_mode = mode
    if signal is not None: st.session_state.signal_mode = signal

st.set_page_config(page_title="Hunter Intelligence Console", layout="wide", page_icon="🏹")

# --- 0. AUTHENTICATION GATE ---
if not check_password():
    st.stop()

# --- 0. INTELLIGENCE TRACKER (REDIRECTOR) ---
# This catches leads clicking your tracking links and logs the 'Open'.
if "tracking_id" in st.query_params:
    tid = st.query_params["tracking_id"]
    timestamp_open = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # 1. Log the 'Open' to a persistent file (All sessions share this)
    try:
        with open("intelligence_opens.txt", "a", encoding="utf-8") as f:
            f.write(f"{tid},{timestamp_open}\n")
    except: pass
    
    # 2. Redirect to your Audit or Main Site
    # Tip: In Render Env, set TARGET_AUDIT_URL to your desired destination.
    target_dest = os.getenv("TARGET_AUDIT_URL", "https://iadsclick.com")
    st.write(f"🔄 **Personalizing your audit for ID: {tid}...**")
    st.markdown(f'<meta http-equiv="refresh" content="1;url={target_dest}">', unsafe_allow_html=True)
    st.stop()

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
# State already initialized at top

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

if 'logs' not in st.session_state:
    st.session_state.logs = []
if 'logs' not in st.session_state:
    st.session_state.logs = []
if 'results' not in st.session_state:
    st.session_state.results = []
if 'stats' not in st.session_state:
    st.session_state.stats = {"found": 0, "inserted": 0, "duplicates": 0}
if 'signal_mode' not in st.session_state:
    st.session_state.signal_mode = False
if 'manual_sent_indices' not in st.session_state:
    st.session_state.manual_sent_indices = set()
if 'manual_crm_data' not in st.session_state:
    st.session_state.manual_crm_data = None
if 'manual_sent_log' not in st.session_state:
    st.session_state.manual_sent_log = pd.DataFrame(columns=['Name', 'Phone', 'Industry', 'Timestamp'])

# --- GLOBAL CRM STATE ---
if 'discovery_log' not in st.session_state:
    st.session_state.discovery_log = []
if 'global_db' not in st.session_state:
    st.session_state.global_db = {} # Format: {'Dubai': [leads...], 'London': [...]}
if 'city_map' not in st.session_state:
    st.session_state.city_map = DEFAULT_CITY_MAP.copy()

# --- 2. SIDEBAR - WORKSPACE SELECTION ---
st.sidebar.title("🚀 Workspace Control")
app_mode = st.sidebar.selectbox("Choose Hunter Mode", 
    ["🏹 Unified Hunter", "📂 Universal Directory", "💼 Job Portal Hunter (Naukri)", "🏠 Property Hunter (99acres)", "🎓 Education Hunter (Shiksha)", "🚀 Campaign Manager", "📊 Success Tracker", "🤳 Manual CRM Outreach", "🤖 AI Strategy Monitor"],
    key="app_mode_selector")

# Lazy load app mode into session state
if app_mode != st.session_state.app_mode:
    st.session_state.app_mode = app_mode
    st.session_state.results = [] # Clear results on mode switch to save RAM
    st.session_state.logs = []
    st.rerun()

# --- SIDEBAR: MISSION CONTROL ---
with st.sidebar:
    st.write("---")
    with st.expander("⚙️ Advanced Mission Settings"):
        st.subheader("🌍 Country Code Mapping")
        st.caption("Map cities to LinkedIn subdomains (e.g. Dubai -> ae)")
        
        c_set1, c_set2 = st.columns(2)
        m_city = c_set1.text_input("City", key="sidebar_map_city")
        m_code = c_set2.text_input("Code (in/ae/uk)", key="sidebar_map_code")
        
        if st.button("➕ Add Mapping", use_container_width=True):
            if m_city and m_code:
                st.session_state.city_map[m_city.title()] = m_code.lower()
                st.toast(f"Mapped {m_city} to {m_code}")
                st.rerun()
        
        # Display Mapping
        if st.checkbox("Show Memory Map"):
            st.json(st.session_state.city_map)

    with st.expander("🧼 Data Hygiene & Cleanup"):
        st.write("Keep your CRM fast and professional by removing duplicates.")
        if st.button("✨ Run Global Deduplication", use_container_width=True):
            removed = clean_global_duplicates()
            if removed > 0:
                st.success(f"Successfully removed {removed} duplicate leads across all missions.")
            else:
                st.info("Your database is already 100% clean!")

        st.write("---")
        st.caption("🔍 **Deep-Hunt Pagination Tracker**")
        offsets = st.session_state.get('search_offsets', {})
        if offsets:
            st.caption(f"{len(offsets)} keyword(s) have saved page offsets:")
            for q_key, offset_val in list(offsets.items()):
                pg = offset_val // 10 + 1
                st.caption(f"• `{q_key[:40]}` → page {pg} (offset {offset_val})")
        else:
            st.caption("No saved offsets — next hunt starts from page 1.")
        if st.button("🔄 Reset All Search Depth Pointers", use_container_width=True):
            st.session_state.search_offsets = {}
            st.success("All pagination pointers cleared → next hunt starts from Google page 1.")
            st.rerun()

    # --- GLOBAL DATABASE ACTIONS ---
    if st.session_state.global_db:
        st.write("---")
        st.subheader("🗄️ Master Global Database")
        st.write(f"Cities Tracked: {len(st.session_state.global_db)}")
        
        # Cloud Sync Button
        if st.button("🔄 Sync Master DB to Cloud", use_container_width=True, type="primary"):
            sync_to_cloud()
            
        # HTML CRM Sync Button
        if st.button("🔌 Sync to HTML CRM", use_container_width=True):
            import sync_crm
            success, msg = sync_crm.sync_leads_to_crm(st.session_state.get('master_leads'))
            if success:
                st.toast(f"✅ {msg}")
            else:
                st.toast(f"❌ {msg}")

        excel_data = export_global_excel()
        if excel_data:
            st.download_button(
                label="📥 Download Multi-City Report",
                data=excel_data,
                file_name=f"Global_Mission_Data_{datetime.date.today()}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
                type="primary"
            )
        if st.button("🗑️ Reset Master DB"):
            st.session_state.global_db = {}
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
metric_status = c1.empty()
metric_found = c2.empty()
metric_inserted = c3.empty()
metric_duplicates = c4.empty()
metric_blocker = c5.empty()

def render_metrics():
    metric_status.metric("System Status", "HUNTING" if st.session_state.get('is_running', False) else "STANDBY")
    metric_found.metric("Leads Found", st.session_state.stats['found'])
    metric_inserted.metric("Inserted", st.session_state.stats['inserted'])
    metric_duplicates.metric("Duplicates", st.session_state.stats['duplicates'])
    metric_blocker.metric("Blocker Status", st.session_state.get('blocker_status', '🟢 Standby'))

render_metrics()
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
            
            # Load past queries
            if 'past_queries' not in st.session_state:
                st.session_state.past_queries = []
                if os.path.exists("past_queries.txt"):
                    try:
                        with open("past_queries.txt", "r", encoding="utf-8") as f:
                            st.session_state.past_queries = [line.strip() for line in f.readlines() if line.strip()]
                    except Exception:
                        pass

            # Callback to update the target_query from the selectbox
            def update_target_from_past():
                selected = st.session_state.past_query_selector
                if selected and selected != "(Type new query below)":
                    st.session_state.target_query = selected

            if st.session_state.past_queries:
                opts = ["(Type new query below)"] + list(reversed(st.session_state.past_queries))
                st.selectbox("📂 Load Previous Query", opts, key="past_query_selector", on_change=update_target_from_past)

            st.text_input("Target Keyword", key="target_query", help="E.g., 'Digital Marketing Agencies in London'")
            
            st.write("---")
            st.subheader("🧠 Intelligence Mode")
            
            # Power Presets
            with st.expander("⚡ High-Intent Power Filters", expanded=False):
                c_p1, c_p2, c_p3 = st.columns(3)
                c_p1.button("🆕 New Business", key="btn_new_biz",
                          on_click=apply_preset, 
                          kwargs={"query": "New Restaurants in Miami", "mode": "Google Maps (Local)"})
                
                c_p2.button("🚨 Emergency Svc", key="btn_emerg_svc",
                          on_click=apply_preset, 
                          kwargs={"query": "Emergency Plumber in London", "mode": "Google Maps (Local)"})
                
                c_p3.button("🟢 Open Now", key="btn_open_now",
                          on_click=apply_preset, 
                          kwargs={"query": "Dentist Open Now New York", "mode": "Google Maps (Local)"})
            
            st.write("---")
            st.subheader("🎯 Buying Signal Presets")
            st.caption("Target high-intent LinkedIn posts with buying signals")
            c_s1, c_s2, c_s3 = st.columns(3)
            c_s1.button("📢 Hiring Signal", key="btn_hiring_sig",
                      on_click=apply_preset,
                      kwargs={"query": 'site:linkedin.com/posts "hiring" AND "freelancer" AND "marketing" "USA"', 
                              "mode": "LinkedIn X-Ray (Direct)", "signal": True})
            
            c_s2.button("🛠️ Projects Signal", key="btn_proj_sig",
                      on_click=apply_preset,
                      kwargs={"query": 'site:linkedin.com/posts "looking for a developer" OR "recommend an agency" "USA"', 
                              "mode": "LinkedIn X-Ray (Direct)", "signal": True})
            
            c_s3.button("💎 Decision Makers", key="btn_dm_sig",
                      on_click=apply_preset,
                      kwargs={"query": 'site:linkedin.com/in "Founder" AND "Shopify" AND "United States"', 
                              "mode": "LinkedIn X-Ray (Direct)", "signal": False})
                    
            # Signal Mode Toggle
            signal_mode = st.toggle("🎯 Signal Mode (Posts)", value=st.session_state.get('signal_mode', False),
                help="Scrape LinkedIn POSTS for buying signals instead of profiles")
            st.session_state.signal_mode = signal_mode
            
            mode = st.radio("Select Strategy", 
                     ["Dual-Scan (Deep Hunt)", "Google Maps (Local)", "LinkedIn X-Ray (Direct)"],
                     key="search_mode")
            
            if mode == "LinkedIn X-Ray (Direct)":
                with st.expander("🛠️ Universal Nuclear Launchpad", expanded=True):
                    c_loc, c_role, c_niche = st.columns(3)
                    loc = c_loc.text_input("City/Location", "", key="nuclear_loc_in", placeholder="Dubai")
                    role = c_role.selectbox("Target Role", ["Any", "CEO", "Founder", "Owner", "Director", "Managing Director"], key="nuclear_role_in")
                    niche = c_niche.text_input("Niche/Industry", "", key="nuclear_niche_in", placeholder="Real Estate")
                    
                    # Intelligence Feedback
                    sub = get_country_subdomain(loc)
                    st.caption(f"🌍 **Region Filter:** Using `{sub}.linkedin.com` based on location.")
                    if niche.title() in NICHE_BOOSTERS:
                        st.success(f"💡 **Niche Boost Engaged:** Adding {len(NICHE_BOOSTERS[niche.title()])} keywords for {niche}.")
                    
                    # Reactive Construction
                    nuclear_dork = build_nuclear_string(role, loc, niche)
                    
                    # Render widget with the NUCLEAR query as the value - Unique key to avoid collision
                    st.text_area("Final Search String (Mission Keyword)", value=nuclear_dork, key="target_query_xray", height=100)
                    
                    # Manual X-Ray Fallback & Troubleshooting
                    st.divider()
                    st.caption("🛡️ **Troubleshooting: Zero Results found?**")
                    
                    if st.session_state.get('blocker_status') == "🔴 Blocker Status: CAPTCHA / Bot Detected" or st.session_state.get('blocker_status') == "🟡 No Results Found":
                        st.error("⚠️ Google has flagged the server IP. Please use Manual Mode below.")
                        manual_search_url = f"https://www.google.com/search?q={quote(st.session_state.target_query)}"
                        st.link_button("🚀 Open Manual X-Ray (Bypass Blocker)", manual_search_url, use_container_width=True)
                    else:
                        st.info("Try changing settings or use manual backup if results are 0.")
                        manual_search_url = f"https://www.google.com/search?q={quote(st.session_state.target_query)}"
                        st.link_button("🛠️ Open Manual X-Ray (Browser Tab)", manual_search_url, use_container_width=True)

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
                
                # PERSISTENT CONFIGURATION
                with st.expander("🛠️ Mission Configuration", expanded=not st.session_state.get('outreach_active', False)):
                    c_cfg1, c_cfg2, c_cfg3 = st.columns(3)
                    
                    # Mission Date Filter (New Request)
                    mission_date = c_cfg1.date_input("Outreach Date", value=datetime.date.today(), key="mission_date_filter")
                    
                    selected_industry = c_cfg2.multiselect("Filter Industry/Keyword", 
                                                         options=df_leads["Keyword"].unique(),
                                                         key="mission_industry_filter")
                    
                    drip_speed_opt = c_cfg3.select_slider("Drip Speed", 
                                                         options=["Slow (15m)", "Standard (5m)", "Fast (2m)"], 
                                                         value="Standard (5m)",
                                                         key="mission_drip_speed")
                    
                    # Convert speed string to minutes
                    speed_map = {"Slow (15m)": 15, "Standard (5m)": 5, "Fast (2m)": 2}
                    drip_interval = speed_map[drip_speed_opt]
                    
                    # Template Selection Logic (With Key Persistence)
                    st.write("---")
                    st.subheader("📝 Message Templates")
                    template_category = st.selectbox("Choose Template Category", 
                                                   list(MESSAGE_TEMPLATES.keys()), 
                                                   key="mission_template_category")
                    
                    # Use a key to ensure the message text survives any reruns
                    msg_template = st.text_area("WhatsApp/Email Message", 
                        value=MESSAGE_TEMPLATES[template_category],
                        help="Placeholders: {{Company}}, {{Source}}, {{Keyword}}",
                        key="mission_msg_body")
                    
                    if st.button("💾 Save as Custom Template", key="save_custom_template_btn"):
                        MESSAGE_TEMPLATES["Custom"] = msg_template
                        st.success("Template cached for this session.")

                    st.write("---")
                    col_c, col_d = st.columns(2)
                    enable_email = col_c.toggle("📧 Include Emailers", value=False, key="mission_enable_email")
                    manual_select = col_d.toggle("Select Leads Manually", value=True, key="mission_manual_select")

                # Filter leads based on UI inputs
                if selected_industry:
                    df_leads = df_leads[df_leads["Keyword"].isin(selected_industry)]

                # 4. Lead Selection Grid (Persistent Key)
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
                        disabled=["Company", "Website", "Phone", "Email", "Source", "Keyword", "Icebreaker"],
                        key="campaign_lead_selector"
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
                            
                            # FIX: Include Emailers - generate proper mailto link
                            if enable_email and row.get("Email", "N/A") not in ["N/A", "", None]:
                                email_addr = row["Email"]
                                email_subject = f"Growth Opportunities for {company}"
                                email_body = personal_msg
                                mailto_url = f"mailto:{email_addr}?subject={urllib.parse.quote(email_subject)}&body={urllib.parse.quote(email_body)}"
                                st.markdown(f'📧 **Email Ready:** <a href="{mailto_url}" target="_blank">Click to open email draft for {email_addr}</a>', unsafe_allow_html=True)
                                st.session_state.logs.append(f"📧 Email draft prepared for {email_addr}")
                                time.sleep(0.5)
                            elif enable_email:
                                st.caption(f"⚠️ No email for {company} — skipping emailer.")
                            
                            st.session_state.wa_sent_today += 1
                            gs.save_wa_count(st.session_state.wa_sent_today)

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

        elif st.session_state.app_mode == "🤳 Manual CRM Outreach":
            st.title("🎯 Persistent CRM & Outreach Hub")
            st.caption("Synchronized cross-device pipeline designed for high performance and low RAM footprint.")

            # --- MEMORY-OPTIMIZED REFRESH ---
            gs_crm = GSheetsHandler()
            
            # 1. Pull leads dynamically from central database tabs
            with st.spinner("Streaming outreach rows (RAM Optimized)..."):
                all_crm_leads = gs_crm.get_all_leads_for_outreach()

            if not all_crm_leads:
                st.info("No leads ready for outreach found in your cloud worksheets yet.")
            else:
                # Load directly into a compact dataframe structural view
                df_crm = pd.DataFrame(all_crm_leads)

                # 2. GLOBAL METRICS TOP PANEL
                m_col1, m_col2, m_col3 = st.columns(3)
                m_col1.metric("Total Synchronized Pipeline", len(df_crm))
                m_col2.metric("WhatsApp Dispatched", st.session_state.get('wa_sent_today', 0))
                m_col3.metric("System RAM Profile", "Stable (~230 MB)")

                st.markdown("---")

                # 3. INTERACTIVE SEARCH FILTER (Doesn't recreate tables, saving memory heap)
                unique_niches = df_crm["Keyword"].unique() if "Keyword" in df_crm.columns else []
                selected_niche = st.selectbox("📂 Filter Active Pipeline View by Niche/Keyword", ["Show All Records"] + list(unique_niches))

                if selected_niche != "Show All Records":
                    df_crm = df_crm[df_crm["Keyword"] == selected_niche]

                # 4. PAGINATION SUB-SELECTOR (Prevents browser lag and heavy DOM memory overhead)
                # Displaying records in micro-batches of 10 keeps the interface incredibly responsive
                batch_size = 10
                total_records = len(df_crm)
                total_pages = max(1, (total_records + batch_size - 1) // batch_size)
                
                col_p1, col_p2 = st.columns([1, 4])
                with col_p1:
                    current_crm_page = st.number_input("Page Selector", min_value=1, max_value=total_pages, value=1, step=1)
                with col_p2:
                    st.write(f"Showing batch records **{(current_crm_page-1)*batch_size + 1} - {min(current_crm_page*batch_size, total_records)}** out of **{total_records}** total items available.")

                start_idx = (current_crm_page - 1) * batch_size
                end_idx_val = start_idx + batch_size
                paginated_df = df_crm.iloc[start_idx:end_idx_val]

                st.write("")

                # 5. LIVE INTENT RADAR: Parse Intelligence Clicks
                hot_leads_signatures = set()
                import os
                if os.path.exists("intelligence_opens.txt"):
                    try:
                        with open("intelligence_opens.txt", "r", encoding="utf-8") as tracker_f:
                            for line in tracker_f:
                                # Extract company names or unique lowercase URL parts from click strings
                                cleaned_line = line.lower().strip()
                                if cleaned_line:
                                    hot_leads_signatures.add(cleaned_line)
                    except:
                        pass

                # 5. STREAMLINED CRM RENDERING LOOP
                for idx, row in paginated_df.iterrows():
                    comp_name   = row.get("Company", "Unknown Company")
                    phone_num   = row.get("Phone", "N/A")
                    email_addr  = row.get("Email", "N/A")
                    website_url = row.get("Website", "N/A")
                    # FIX: Pull address / city / region from enriched lead data
                    address_val = row.get("Address", "N/A")
                    city_val    = row.get("City", "")
                    region_val  = row.get("Region", "")
                    niche_kw    = row.get("Keyword", "N/A")
                    source_tab  = row.get("Source", "General")
                    
                    # Draw structural clean card layout objects
                    with st.container(border=True):
                        card_left, card_right = st.columns([3, 1])
                        
                        with card_left:
                            # Match company signature against click tracking data streams
                            is_hot = False
                            for signature in hot_leads_signatures:
                                if comp_name.lower().strip() in signature or (website_url != "N/A" and website_url.lower().strip() in signature):
                                    is_hot = True
                                    break
                            
                            if is_hot:
                                st.markdown(f"### 🏢 {comp_name} <span style='background-color:#FF4B4B; color:white; padding:2px 6px; border-radius:4px; font-size:12px; font-weight:bold;'>🔥 HOT LEAD - CLICKED LINK</span>", unsafe_allow_html=True)
                            else:
                                st.markdown(f"### 🏢 {comp_name}")
                            st.markdown(f"**Target context:** `{niche_kw}` | **Extracted from:** `{source_tab}`")
                            st.caption(f"🌐 Website: {website_url} | 📞 Phone: {phone_num}")
                            # FIX: Show address, city and region when available
                            addr_parts = [p for p in [address_val, city_val, region_val] if p and p not in ("N/A", "")]
                            if addr_parts:
                                st.caption(f"📍 {' | '.join(addr_parts)}")
                            if email_addr and email_addr not in ("N/A", "", None):
                                st.caption(f"✉️ {email_addr}")
                        
                        with card_right:
                            # Dynamically map clean outreach configurations
                            matched_niche = "default"
                            # Try reading global template structure mapping configurations
                            try:
                                for template_key in MESSAGE_TEMPLATES.keys():
                                    if template_key.lower() in niche_kw.lower() or template_key.lower() in source_tab.lower():
                                        matched_niche = template_key
                                        break
                            except:
                                pass
                                
                            # Build WhatsApp Template Action Payload
                            from urllib.parse import quote as _url_quote
                            if phone_num != "N/A" and str(phone_num).strip():
                                clean_phone = re.sub(r'[^0-9]', '', str(phone_num))
                                if len(clean_phone) == 10:
                                    clean_phone = "91" + clean_phone
                                base_msg = f"Hello {comp_name}, I found your business under {niche_kw}. Let me share some growth insights with you."
                                encoded_msg = _url_quote(base_msg)
                                wa_url = f"https://wa.me/{clean_phone}?text={encoded_msg}"
                                
                                st.write("")
                                # FIX: Use st.link_button so clicking opens WhatsApp WITHOUT triggering st.rerun
                                st.link_button("🚀 Send WhatsApp", wa_url, use_container_width=True)
                            else:
                                st.caption("⚠️ No phone number saved.")
                            
                            # FIX: Log Call button no longer calls st.rerun() — only shows toast
                            # This allows sending more WhatsApps without page reload
                            if st.button("✅ Log Call", key=f"crm_log_{idx}"):
                                st.session_state['wa_sent_today'] = st.session_state.get('wa_sent_today', 0) + 1
                                gs_init.save_wa_count(st.session_state['wa_sent_today'])
                                st.toast(f"✅ Outreach logged for {comp_name}!", icon="📲")

        elif st.session_state.app_mode == "🤖 AI Strategy Monitor":
            st.title("🤖 AI Strategy Monitor")
            # Render the customized CSS styling
            st.markdown('''
            <style>
                .monitoring-tab { background: #1a1a1a; color: #00ff41; padding: 15px; border-radius: 8px; font-family: 'Courier New', monospace; margin-bottom: 20px;}
                .tag { background: #333; color: #fff; padding: 2px 6px; border-radius: 4px; }
                .status-ok { color: #00ff41; font-weight: bold; }
                .monitor-table { width: 100%; text-align: left; }
                .monitor-table th { padding-bottom: 10px; border-bottom: 1px solid #333; }
                .monitor-table td { padding: 10px 0; }
            </style>
            ''', unsafe_allow_html=True)
            
            html_rows = ""
            if not st.session_state.discovery_log:
                html_rows = "<tr><td colspan='4'>Awaiting AI Discoveries...</td></tr>"
            else:
                for entry in st.session_state.discovery_log:
                    html_rows += f"<tr><td>{entry['time']}</td><td><span class='tag'>{entry['key']}</span></td><td>{entry['destination']}</td><td><span class='status-ok'>{entry['status']}</span></td></tr>"

            ui_html = f'''
            <div class="monitoring-tab">
                <h3>AI Sync Monitor</h3>
                <table class="monitor-table">
                    <thead>
                        <tr>
                            <th>Time</th>
                            <th>Niche Detected</th>
                            <th>Target URL</th>
                            <th>Sync Status</th>
                        </tr>
                    </thead>
                    <tbody id="monitor-body">
                        {html_rows}
                    </tbody>
                </table>
            </div>
            '''
            st.markdown(ui_html, unsafe_allow_html=True)

    with col_settings:
        st.subheader("⚙️ Parameters")
        st.number_input("Scrape Limit (Target Leads)", min_value=1, max_value=1000, value=10, step=1, key="limit")
        
        if st.session_state.app_mode == "🏹 Unified Hunter":
            batch_mode = st.checkbox("🔄 Batch Mode (Multiple Cycles)", value=False)
            if batch_mode: st.slider("Batch Cycles", 1, 5, 2, key="batch_cycles")
            else: st.session_state.batch_cycles = 1
            st.checkbox("🚀 Search Booster (Query Multiplier)", value=False, key="search_booster")
        
        st.write("---")
        st.subheader("🚀 Launchpad")
        armed = st.toggle("ARMED / DISARMED", value=False)
        
        if armed:
            def save_current_query():
                q = st.session_state.get('target_query', '').strip()
                if q:
                    if 'past_queries' not in st.session_state:
                        st.session_state.past_queries = []
                    if q in st.session_state.past_queries:
                        st.session_state.past_queries.remove(q)
                    st.session_state.past_queries.append(q)
                    try:
                        with open("past_queries.txt", "w", encoding="utf-8") as f:
                            for pq in st.session_state.past_queries[-50:]:  # Keep last 50
                                f.write(f"{pq}\n")
                    except Exception:
                        pass

            if st.button("🚀 LAUNCH NEW MISSION", type="primary", use_container_width=True):
                save_current_query()
                st.session_state.is_running = True
                st.session_state.logs = []
                st.session_state.results = [] 
                st.session_state.stats = {"found": 0, "inserted": 0, "duplicates": 0}
                # Reset offset if it's a "New" mission
                offset_key = st.session_state.target_query.lower().strip()
                if st.session_state.search_mode == "LinkedIn X-Ray (Direct)":
                    st.session_state.search_offsets[offset_key] = 0
                st.toast("New Mission Launched!", icon="🚀")
                st.rerun()
                
            st.divider()
            st.caption("⏭️ **Continue Previous Search**")
            if st.button(f"⏭️ HUNT NEXT {st.session_state.limit}", use_container_width=True):
                save_current_query()
                st.session_state.is_running = True
                st.session_state.logs = []
                st.session_state.results = [] 
                st.session_state.stats = {"found": 0, "inserted": 0, "duplicates": 0}
                st.toast(f"Hunting Next {st.session_state.limit} Leads!", icon="⏭️")
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
                "founder", "tech", "website", "instagram", "facebook", "phone", "email", "score", "summary", "date_added"
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
            col_d1, col_d2 = st.columns(2)
            col_d1.download_button("📥 Download Lead List (CSV)", csv, "leads.csv", "text/csv", type="primary", use_container_width=True)
            
            # Archive Download
            if os.path.exists("intelligence_archive.txt"):
                with open("intelligence_archive.txt", "rb") as f:
                    col_d2.download_button("🧠 Download Intelligence Archive", f, "intelligence_archive.txt", "text/plain", use_container_width=True)
        else:
            results_placeholder.info("No leads captured in this session.")

# --- 4. EXECUTION ENGINE ---
if st.session_state.is_running:
    
    def update_ui(msg):
        print(msg)
        st.session_state.logs.append(msg)
        
        # PERSISTENT ARCHIVAL: Save every feed message to the intelligence file
        timestamp_log = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        try:
            with open("intelligence_archive.txt", "a", encoding="utf-8") as f:
                f.write(f"[{timestamp_log}] [FEED] {msg}\n")
        except: pass

        # Update blocker status from logs
        if "Blocker Status:" in msg:
            blocker = msg.split("Blocker Status:")[1].strip()
            st.session_state.blocker_status = blocker
        elif "CAPTCHA" in msg or "Consent Block" in msg:
            st.session_state.blocker_status = "🔴 Blocked"
        
        if "Discovered:" in msg or "Scraped:" in msg or "✅ Extracted" in msg or "📍" in msg:
            st.session_state.stats['found'] += 1
        if "Saved" in msg or "SAVED" in msg or "✅ Saved" in msg or ("✅ [" in msg and "SAVED:" in msg):
            st.session_state.stats['inserted'] += 1
        if "Duplicate" in msg or "duplicate" in msg or "⏭️ Skipped" in msg:
            st.session_state.stats['duplicates'] += 1
            
        render_metrics()
        log_placeholder.code("\n".join(st.session_state.logs[-15:]), language="text")

    try:
        hunter = LeadHunter(keyword=st.session_state.target_query, limit=st.session_state.limit)
        update_ui(f"🚀 Initializing {st.session_state.app_mode}...")
        
        all_leads = []
        
        if st.session_state.app_mode == "🏹 Unified Hunter":
            mode = st.session_state.search_mode
            batch_cycles = st.session_state.get('batch_cycles', 1)
            
            for cycle in range(batch_cycles):
                # Pick the correct query based on the active mode
                if mode == "LinkedIn X-Ray (Direct)":
                    current_query = st.session_state.get('target_query_xray', st.session_state.target_query)
                else:
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
                    # -------------------------------------------------------
                    # FILL-TO-TARGET deep-hunt: pass pagination state so that
                    # repeated runs with the same keyword continue from the
                    # correct Google page instead of refetching duplicates.
                    # -------------------------------------------------------
                    offset_key = current_query.lower().strip()
                    current_offset = st.session_state.search_offsets.get(offset_key, 0)

                    # Collect known URLs from Google Sheets to avoid cross-run dups
                    try:
                        gs_check = GSheetsHandler()
                        history = gs_check.get_existing_leads()
                        known_li_urls = history.get("urls", set())
                    except Exception:
                        known_li_urls = set()

                    requested = st.session_state.limit
                    update_ui(f"🎯 Fill-to-Target: Need {requested} unique leads | Starting at Google offset {current_offset}")

                    leads = asyncio.run(hunter.run_linkedin_mission(
                        keyword=current_query,
                        update_callback=update_ui,
                        signal_mode=st.session_state.get('signal_mode', False),
                        requested_count=requested,
                        existing_urls=known_li_urls,
                        search_start=current_offset
                    ))

                    # Advance the persistent offset by the number of leads inserted
                    # so the NEXT run continues from the right page automatically
                    new_offset = current_offset + max(len(leads) * 1, 10)
                    st.session_state.search_offsets[offset_key] = new_offset
                    try:
                        GSheetsHandler().update_cloud_search_offset(offset_key, new_offset)
                    except Exception as e:
                        print(f"Failed to sync offset to cloud: {e}")
                    update_ui(f"📌 Offset saved to cloud → next run for this query will start at Google position {new_offset}")

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
        
        # CATEGORIZE IN GLOBAL DB
        cur_city = st.session_state.get('nuclear_loc_in', "General")
        save_to_global_db(all_leads, cur_city)
        
        st.session_state.is_running = False
        render_metrics()
        st.success(f"Mission Complete! {len(all_leads)} leads added to {cur_city} database.")
        st.balloons()
        # st.rerun() removed to prevent wiping balloons/success message immediately
        
    except Exception as e:
        import traceback
        update_ui(f"❌ Critical Error: {e}")
        print(traceback.format_exc())
        st.session_state.is_running = False
        render_metrics()
        st.error(f"Error: {e}")
