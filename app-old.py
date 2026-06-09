import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
import html as html_lib
import re
from difflib import SequenceMatcher


st.set_page_config(page_title="Smart Recommender POC", layout="wide")

# ─────────────────────────────────────────────────────────────
# CUSTOM TOP HEADER & GLOBAL STYLING
# ─────────────────────────────────────────────────────────────
st.markdown("""
<style>
    /* 1. Force the entire app and sidebar to be clean white, killing the grey */
    .stApp, .main, [data-testid="stSidebar"] {
        background-color: #ffffff !important;
    }
    [data-testid="stSidebar"] {
        border-right: 1px solid #eaeaea !important;
        padding-top: 110px !important; /* Pushed further down to clear the yellow banner */
    }

/* 2. FIX THE SIDEBAR TOGGLE & TOP RIGHT ICONS */
    header[data-testid="stHeader"] { 
        background: transparent !important;
        box-shadow: none !important;
        z-index: 1000001 !important; 
        top: 24px !important; /* Pushes the toolbar down into the bright orange bar */
    }
    
    /* Target the text (like "Share") */
    header[data-testid="stHeader"] span {
        color: #ffffff !important;
    }
    
    /* Target the icons (Paths, Circles, etc) */
    header[data-testid="stHeader"] svg {
        fill: #ffffff !important;
        color: #ffffff !important;
    }
    
    /* 🟢 FIX: Prevent the 3-dots transparent bounding box from turning into a solid white square */
    header[data-testid="stHeader"] svg rect {
        fill: transparent !important;
    }

/* 3. Push the main content down so it doesn't hide under our new header */
    .appview-container .main .block-container { 
        padding-top: 300px !important; /* 🟢 FIX: Increased from 130px to 170px */
    }
    
    /* 4. The Fixed Header Wrapper - WIDTH BUG FIXED */
    .poc-header-wrapper {
        position: fixed;
        top: 0;
        left: 0;
        right: 0; /* FIX: Using right:0 instead of width:100% prevents the horizontal scrollbar gap */
        z-index: 999999;
        display: flex;
        flex-direction: column;
    }
    
    /* The Thin Dark Orange Bar */
    .poc-top-bar {
        background-color: #BF3C00;
        height: 24px;
        width: 100%;
    }
    
    /* The Thick Bright Orange Bar with Text */
    .poc-main-bar {
        background-color: #FE5900; 
        height: 60px;
        width: 100%;
        display: flex;
        align-items: center;
        padding: 0 40px 0 75px; 
    }
    
    /* The PoC Title Text */
    .poc-title {
        color: #ffffff;
        font-family: -apple-system, BlinkMacSystemFont, sans-serif;
        font-size: 22px;
        font-weight: 700;
        letter-spacing: -0.5px;
    }

    /* 🟢 NEW: The Yellow Promo Banner */
    .poc-promo-banner {
        background-color: #ffeb85;
        height: 36px;
        width: 100%;
        display: flex;
        align-items: center;
        justify-content: center;
        font-family: -apple-system, BlinkMacSystemFont, sans-serif;
        font-size: 14px;
        font-weight: 600;
        color: #000000;
        box-shadow: 0 2px 4px rgba(0,0,0,0.08);
    }

/* 5. The Vertical Orange Line for Titles */
    .public-header {
        font-family: -apple-system, BlinkMacSystemFont, sans-serif;
        font-size: 24px;
        font-weight: 700;
        color: #111111;
        margin-top: 80px !important; /* 🟢 FIX: Increased to push the title safely below the header */
        margin-bottom: 20px;
        display: flex;
        align-items: center;
    }
    .public-header::before {
        content: '';
        display: inline-block;
        width: 4px;
        height: 24px;
        background-color: #ff5e00;
        margin-right: 10px;
        border-radius: 2px;
    }
    
    /* Ensure any default streamlit alerts/infos are hidden if they try to render */
    [data-testid="stAlert"] {
        display: none !important;
    }
</style>

<div class="poc-header-wrapper">
    <div class="poc-top-bar"></div>
    <div class="poc-main-bar">
        <div class="poc-title">Recommendation PoC</div>
    </div>
    <div class="poc-promo-banner">
        🟢 Engine v7.4 — Rival Brand & Strict Fit Filtering
    </div>
</div>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────────────────────
SHEET_ID = "1PeLckGFNH-l9GrEvSs3ZQ0N0mXrEYwzA_JwO1wTzJWo"

CLUSTER_CONFIG = {
    "Smartphones": {"allow_siblings": False, "hierarchy_cap": 2},
    "Kids Books":  {"allow_siblings": True,  "hierarchy_cap": 10},
}
ACTIVE_CLUSTER = "Smartphones"

# 🟢 THE VIRTUAL SALES BUMP: 
# A brand match acts like 15 extra sales. Availability acts like 2 extra sales.
SMART_BOOST      = 15 
ECOSYSTEM_BOOST  = 100000  # 🟢 NEW: Massive lock-in for Watches & Earbuds
AVAIL_BOOST      = 2
HISTORY_BOOST    = 100000 
HISTORY_FREQ_MIN = 5

TECH_CATS = {"IT", "Telephony", "TV"}
APPL_CATS = {"MDA", "SDA", "Air Condition", "Personal Care"}
COMPAT_COLS = ["Συμβατό με", "Συμβατή συσκευή"]
CC = "_Compatible"

# 🟢 THE WALLED GARDEN LIST
ANDROID_OEMS = {"SAMSUNG", "XIAOMI", "HUAWEI", "MOTOROLA", "HONOR", "POCO", "REALME", "ONEPLUS", "NOTHING"}

# ─────────────────────────────────────────────────────────────
# ROLE → LOGIC KEY MAPPING
# The Slot_Matrix defines roles like "The Bodyguard (Primary Case)".
# We map role keywords to logic functions so slot numbers don't matter.
# ─────────────────────────────────────────────────────────────
def detect_logic_key(role: str) -> str:
    """Map a slot role string to a logic key based on spec:
    Spec Slot 1  → PRIMARY_CASE   (The Perfect Fit / Back Cover)
    Spec Slot 2  → SCREEN_GLASS   (The Screen Shield / Screen Protector)
    Spec Slot 3  → WALL_CHARGER   (The Power Source / Wall/Wireless Charger)
    Spec Slot 4  → EARBUDS        (The Audio Pivot / Handsfree/Earbuds)
    Spec Slot 5  → POWERBANK      (The Backup Power / Powerbank)
    Spec Slot 6  → CROSS_SELL     (The Lifestyle/Tech Feature / Misc Accessory)
    Spec Slot 7  → CAMERA_GLASS   (The Camera Shield / Camera Protector)
    Spec Slot 8  → SMARTWATCH     (The Wearable / Smartwatch)
    Spec Slot 9  → HOLDER         (The Commute / Car Holder)
    Spec Slot 10 → ALT_CASE       (The Alternative Case / Book Cover / Wallet)
    """
    r = role.lower()
    
    if "perfect fit" in r or "back cover" in r or "primary case" in r:
        return "PRIMARY_CASE"
    
    if "alternative" in r or "alt case" in r or "book cover" in r or "wallet" in r:
        return "ALT_CASE"
    
    if "screen" in r or "shield" in r:
        # Avoid catching 'Camera Shield' by ensuring 'camera' isn't in it
        if "camera" not in r:
            return "SCREEN_GLASS"
            
    if "camera" in r:
        return "CAMERA_GLASS"
        
    if "power source" in r or "wall" in r or "charger" in r:
        # Make sure we don't accidentally catch a car charger if you separate them later
        if "car" not in r:
            return "WALL_CHARGER"
            
    if "backup power" in r or "powerbank" in r or "power bank" in r:
        return "POWERBANK"
        
    if "wearable" in r or "smartwatch" in r:
        return "SMARTWATCH"
        
    if "audio" in r or "earbud" in r or "handsfree" in r:
        return "EARBUDS"
        
    if "commute" in r or "holder" in r or "drive" in r:
        return "HOLDER"
        
    if "lifestyle" in r or "misc" in r or "cross" in r:
        return "CROSS_SELL"
        
    return "UNKNOWN"

# ─────────────────────────────────────────────────────────────
# PORT & COLOR HELPERS
# ─────────────────────────────────────────────────────────────
def extract_base_port(raw):
    s = str(raw).strip().lower()
    if not s or s == 'nan': return ''
    if 'type-c' in s or 'type c' in s or 'usb-c' in s or 'usb c' in s: return 'Type-C'
    if 'lightning' in s: return 'Lightning'
    if 'micro usb' in s or 'micro-usb' in s: return 'Micro USB'
    if 'usb' in s: return 'USB'
    return re.sub(r'\s*\d+\.?\d*\s*(gen\s*\d+)?', '', str(raw).strip(), flags=re.IGNORECASE).strip() or str(raw).strip()

COLOR_MAP = {
    'black titanium': ['μαύρο', 'black', 'διάφανο'],
    'natural titanium': ['διάφανο', 'μπεζ', 'natural'],
    'white titanium': ['λευκό', 'white', 'διάφανο'],
    'blue titanium': ['μπλε', 'blue', 'διάφανο'],
    'deep purple': ['μωβ', 'purple', 'διάφανο'],
    'space black': ['μαύρο', 'black', 'διάφανο'],
    'silver': ['ασημί', 'silver', 'διάφανο'],
    'gold': ['χρυσό', 'gold', 'διάφανο'],
    'starlight': ['λευκό', 'μπεζ', 'διάφανο'],
    'midnight': ['μαύρο', 'black', 'διάφανο'],
    'red': ['κόκκινο', 'red', 'διάφανο'],
    'pink': ['ροζ', 'pink', 'διάφανο'],
    'green': ['πράσινο', 'green', 'διάφανο'],
    'blue': ['μπλε', 'blue', 'διάφανο'],
}
def get_case_colors(c):
    k = c.strip().lower()
    for mk, mv in COLOR_MAP.items():
        if mk in k or k in mk: return mv
    return [k, 'διάφανο']

# ─────────────────────────────────────────────────────────────
# GENERAL HELPERS
# ─────────────────────────────────────────────────────────────
def parse_euro_price(v):
    s = str(v).replace('€','').strip()
    if ',' in s and '.' in s: s = s.replace('.','')
    s = s.replace(',','.')
    try: return float(s)
    except: return 0.0

def price_ok(tp, np, l1):
    if np <= 0 or tp <= 0: return True
    if l1 in {"Books","Stationery","Toys","Music & Films","Gaming"}: return np <= tp*1.5
    elif tp <= 30: return np <= tp*1.5
    else: return np <= max(tp*0.40, 45)

def title_sim(a, b): return SequenceMatcher(None, a.lower(), b.lower()).ratio() * 100
def safe(v): return html_lib.escape(str(v))
def has_data(df, col, pct=0.05):
    if col not in df.columns: return False
    v = df[col].fillna('').astype(str).str.strip()
    return ((v!='').sum()/len(df)) >= pct if len(df)>0 else False
def sample(df, col, n=5):
    if col not in df.columns: return f"[NO COL '{col}']"
    v = df[col].dropna().astype(str).str.strip(); v = v[v!='']
    return v.head(n).tolist() if not v.empty else "[EMPTY]"

# ─────────────────────────────────────────────────────────────
# DATA
# ─────────────────────────────────────────────────────────────
@st.cache_data
def load_data():
    base = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/gviz/tq?tqx=out:csv&sheet="
    dp = pd.read_csv(base+"Products"); dp.columns = dp.columns.str.strip()
    dh = pd.read_csv(base+"History");  dh.columns = dh.columns.str.strip()
    ds = pd.read_csv(base+"Slot_Matrix"); ds.columns = ds.columns.str.strip()
    # Merge compat columns
    parts = [dp[c].fillna('').astype(str).str.strip() for c in COMPAT_COLS if c in dp.columns]
    found = [c for c in COMPAT_COLS if c in dp.columns]
    if parts:
        dp[CC] = parts[0]
        for p in parts[1:]:
            empty = dp[CC]==''
            dp.loc[empty, CC] = p[empty]
            dp.loc[~empty, CC] = dp.loc[~empty, CC] + ';' + p[~empty]
        dp[CC] = dp[CC].str.strip(';').str.replace(';;',';')
    else:
        dp[CC] = ''
    return dp, dh, ds, found

df_products, df_history, df_slots, compat_cols_found = load_data()

# ─────────────────────────────────────────────────────────────
# TRIGGER
# ─────────────────────────────────────────────────────────────
phones = df_products[(df_products['Level 2']=='Mobiles')&(df_products['Hierarchy']=='Smartphones')]

if phones.empty:
    phones = df_products[df_products['Level 2']=='Mobiles']
    st.sidebar.warning("⚠ Fallback to all Mobiles")

if phones.empty:
    st.error("🚨 CRITICAL: No phones found at all! Check your Google Sheet.")
    st.stop()

sel = st.sidebar.selectbox("Select a Smartphone:", phones['Title'].unique())

if sel:
    trigger = phones[phones['Title']==sel].iloc[0]
    
    # Use the custom CSS class to create the branded header
    st.markdown('<div class="public-header">Επιλογές για εσένα</div>', unsafe_allow_html=True)
    
    # Add a subtle text below it indicating what phone they are shopping for
    st.markdown(f"<p style='color: #555; font-size: 14px; margin-top: -15px; margin-bottom: 25px;'>Συμβατά αξεσουάρ για το <b>{sel}</b></p>", unsafe_allow_html=True)
    
    # Extract EXACT data from dataframe
    card_title = safe(str(trigger.get('Title', sel)))
    card_sku = safe(str(trigger.get('Material', 'N/A')))
    card_img = safe(str(trigger.get('Thumbnails', '')).strip())
    if not card_img or card_img == 'nan':
        card_img = "https://via.placeholder.com/150?text=No+Image"
        
    card_avail = safe(str(trigger.get('AVAILABILITY', 'Άμεσα Διαθέσιμο')))
    
    # Determine the color theme based on the exact availability text
    if card_avail in ["Κατόπιν Παραγγελίας", "Αναμένεται Σύντομα"]:
        avail_theme = "avail-blue"
    else:
        avail_theme = "avail-green"
    
    # Format the exact price from LIST PRICE
    try:
        raw_price = trigger.get('LIST PRICE', 0)
        t_price = parse_euro_price(raw_price)
    except:
        t_price = 0.0
        
    p_int = f"{int(t_price)}"
    p_dec = f"{t_price:.2f}".split('.')[1]

    # Create the HTML/CSS for the sidebar card
    sidebar_card_html = f"""
    <!DOCTYPE html>
    <html>
    <head>
    <style>
    body {{
        margin: 0;
        padding: 0;
        background-color: transparent;
        font-family: -apple-system, BlinkMacSystemFont, sans-serif;
    }}
    .sb-card {{
        border: 1px solid #eaeaea;
        border-radius: 12px;
        overflow: hidden;
        background: #fff;
        margin-top: 5px; /* Reduced margin */
    }}
    .sb-img-container {{
        padding: 20px;
        text-align: center;
        background: #fff;
    }}
    .sb-img {{
        max-width: 100%;
        max-height: 220px;
        object-fit: contain;
    }}
    .sb-details {{
        background: #f8f9fa;
        padding: 15px;
        border-top: 1px solid #eaeaea;
    }}
    .sb-title {{
        font-size: 14px;
        font-weight: 700;
        color: #222;
        margin-bottom: 6px;
        line-height: 1.3;
    }}
    .sb-sku {{
        font-size: 10px;
        color: #666;
        margin-bottom: 10px;
    }}
    
    /* 🟢 DYNAMIC AVAILABILITY BADGES */
    .sb-avail-badge {{
        display: inline-flex;
        align-items: center;
        gap: 6px;
        font-size: 12px;
        padding: 4px 8px;
        border-radius: 6px;
        font-weight: 700;
        margin-bottom: 15px;
    }}
    .avail-green {{
        background-color: #e5f3f0;
        color: #00897b;
    }}
    .avail-blue {{
        background-color: #e6f0f6;
        color: #2385aa;
    }}

    .sb-bottom-row {{
        display: flex;
        justify-content: space-between;
        align-items: center;
        border-top: 1px solid #eaeaea;
        padding-top: 15px;
    }}
    .sb-price-wrap {{
        color: #ff5e00;
        font-weight: 800;
        font-size: 24px;
        display: flex;
        align-items: flex-start;
        line-height: 1;
    }}
    .sb-price-dec {{
        font-size: 13px;
        font-weight: 700;
        margin-top: 2px;
    }}
    .sb-btn {{
        background: #ff5e00;
        color: #fff;
        border: none;
        border-radius: 8px;
        padding: 10px 16px;
        font-size: 14px;
        font-weight: 700;
        cursor: pointer;
        display: flex;
        align-items: center;
        gap: 6px;
        transition: background 0.2s;
    }}
    .sb-btn:hover {{
        background: #e65500;
    }}
    </style>
    </head>
    <body>
    <div class="sb-card">
        <div class="sb-img-container">
            <img class="sb-img" src="{card_img}" alt="Phone Image">
        </div>
        <div class="sb-details">
            <div class="sb-title">{card_title}</div>
            <div class="sb-sku">ΚΩΔΙΚΟΣ: {card_sku}</div>
            
            <div class="sb-avail-badge {avail_theme}">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round">
                    <polyline points="20 6 9 17 4 12"></polyline>
                </svg>
                {card_avail}
            </div>
            
            <div class="sb-bottom-row">
                <div class="sb-price-wrap">
                    {p_int}<span class="sb-price-dec">,{p_dec}€</span>
                </div>
                <button class="sb-btn">
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                        <circle cx="9" cy="21" r="1"></circle>
                        <circle cx="20" cy="21" r="1"></circle>
                        <path d="M1 1h4l2.68 13.39a2 2 0 0 0 2 1.61h9.72a2 2 0 0 0 2-1.61L23 6H6"></path>
                    </svg>
                    Προσθήκη
                </button>
            </div>
        </div>
    </div>
    </body>
    </html>
    """
    
    # 🟢 FIX: Use components.html instead of markdown, wrapped in the sidebar context
    with st.sidebar:
        components.html(sidebar_card_html, height=500, scrolling=False)

else:
    st.warning("Please select a phone from the sidebar.")
    st.stop()

# ─────────────────────────────────────────────────────────────
# ENGINE
# ─────────────────────────────────────────────────────────────
def run_engine(trigger, df_products, df_history, df_slots):
    diag, slot_diag, slot_notes = [], [], {}

    # Trigger attrs
    tm   = trigger['Material']
    tt   = str(trigger.get('Title',''))
    tb   = str(trigger.get('Κατασκευαστής','')).strip().upper()
    tmod = str(trigger.get('Μοντέλο','')).strip()
    tpr  = str(trigger.get('Θύρα USB','')).strip()
    tport= extract_base_port(tpr)
    tcol = str(trigger.get('Χρώμα','')).strip()
    tex  = str(trigger.get('Extra Χαρακτηριστικά','')).lower()
    tos  = str(trigger.get('Λειτουργικό σύστημα','')).lower()
    thier= str(trigger.get('Hierarchy',''))
    tl1  = str(trigger.get('Level 1',''))
    tprice=parse_euro_price(trigger.get('LIST PRICE',0))
    ccols= get_case_colors(tcol)

    # 🟢 FIX: Strict Regex Pattern using alphanumeric boundaries
    strict_tmod = ""
    if tmod:
        strict_tmod = rf"(?<![a-zA-Z0-9]){re.escape(tmod)}(?![a-zA-Z0-9])(?!\s*(Max|Plus|\+|Ultra|Pro))"

    # 🟢 NEW: RIVAL BRAND FILTER FOR STRICT FIT (Cases/Glass)
    brand_kws = {
        "SAMSUNG": ["samsung", "galaxy"],
        "APPLE": ["apple", "iphone", "ipad"],
        "XIAOMI": ["xiaomi", "redmi", "poco"],
        "OPPO": ["oppo"],
        "MOTOROLA": ["motorola", "moto"],
        "HUAWEI": ["huawei"],
        "HONOR": ["honor"],
        "REALME": ["realme"],
        "ONEPLUS": ["oneplus"],
        "VIVO": ["vivo"],
        "NOTHING": ["nothing", "cmf"]
    }
    rival_kws = []
    for k, v in brand_kws.items():
        if k != tb:
            rival_kws.extend(v)
    rival_regex = r"\b(" + "|".join(rival_kws) + r")\b" if rival_kws else ""

    c = df_products[df_products['Material']!=tm].copy()
    diag.append(("0. Start", len(c), ""))

    # 🟢 THE SALES SCORE (Primary Driver)
    if 'Sum of Sales' in c.columns:
        c['Sales_Tiebreaker'] = pd.to_numeric(c['Sum of Sales'], errors='coerce').fillna(0)
    else:
        c['Sales_Tiebreaker'] = 0

    # U2a: title dedup
    c = c[c['Title']!=tt]; diag.append(("1. U2a: title dedup", len(c), ""))

    # U2b: stock
    if 'CW Stock Units' in c.columns:
        st_col = pd.to_numeric(c['CW Stock Units'], errors='coerce')
        pct = (st_col>0).sum()/len(c) if len(c)>0 else 0
        if pct >= 0.10:
            c['CW Stock Units']=st_col.fillna(0); c=c[c['CW Stock Units']>0]
            diag.append(("2. U2b: stock", len(c), f"Applied ({pct:.0%})"))
        else: diag.append(("2. U2b: stock", len(c), f"⚠ SKIPPED ({pct:.0%})"))
    else: diag.append(("2. U2b: stock", len(c), "⚠ SKIPPED (no col)"))

    # U1: siblings
    mask = (c['Hierarchy']==thier) & (c['Κατασκευαστής'].fillna('').str.strip().str.upper()==tb)
    ns = mask.sum()
    if ns > 0:
        sims = c.loc[mask,'Title'].apply(lambda t: title_sim(tt,str(t)))
        dupes = sims[sims>=70].index; c=c.drop(dupes)
        diag.append(("3. U1: siblings", len(c), f"Checked {ns}, removed {len(dupes)}"))
    else: diag.append(("3. U1: siblings", len(c), "No siblings"))

    # U3: macro wall
    b4=len(c)
    if tl1 in TECH_CATS: c=c[~c['Level 1'].isin(APPL_CATS)]
    elif tl1 in APPL_CATS: c=c[~c['Level 1'].isin(TECH_CATS)]
    diag.append(("4a. U3: macro wall", len(c), f"Removed {b4-len(c)}"))

    # 🟢 U4: ECOSYSTEM WALLED GARDEN
    b4eco = len(c)
    if tb == "APPLE":
        # Ban Android brands from Apple triggers
        c = c[~c['Κατασκευαστής'].fillna('').str.strip().str.upper().isin(ANDROID_OEMS)]
    elif tb in ANDROID_OEMS:
        # Ban Apple accessories from Android triggers
        c = c[c['Κατασκευαστής'].fillna('').str.strip().str.upper() != "APPLE"]
    diag.append(("4b. U4: ecosystem wall", len(c), f"Removed {b4eco-len(c)} rival OEM items"))

    # Scoring
    tcust = df_history[df_history['Material']==tm]['customerEmail'].unique()
    bw = df_history[(df_history['customerEmail'].isin(tcust))&(df_history['Material']!=tm)]
    fdf = bw['Material'].value_counts().reset_index(); fdf.columns=['NID','Frequency']
    c = c.merge(fdf, left_on='Material', right_on='NID', how='left')
    c['Frequency']=c['Frequency'].fillna(0).astype(int)
    c['History_Score']=c['Frequency'].apply(lambda f: HISTORY_BOOST if f>=HISTORY_FREQ_MIN else 0)
    c['Next_Price']=c['LIST PRICE'].apply(parse_euro_price)

    hm=c['History_Score']>0
    if hm.any():
        ok=c.loc[hm].apply(lambda r: price_ok(tprice,r['Next_Price'],tl1), axis=1)
        c.loc[ok[~ok].index,'History_Score']=0

    c['Avail_Boost']=0; c.loc[c['AVAILABILITY']=='Άμεσα Διαθέσιμο','Avail_Boost']=AVAIL_BOOST
    c['Smart_Boost']=0
    
    if strict_tmod:
        c.loc[c['Μοντέλο'].fillna('').str.contains(strict_tmod, case=False, regex=True), 'Smart_Boost'] += SMART_BOOST
        
    c.loc[c['Κατασκευαστής'].fillna('').str.strip().str.upper()==tb,'Smart_Boost']+=SMART_BOOST
    
    # Final Score includes tiebreaker
    c['Final_Score'] = c['History_Score'] + c['Frequency'] + c['Avail_Boost'] + c['Smart_Boost'] + c['Sales_Tiebreaker']

    b4u5=len(c)
    nhm=c['History_Score']==0
    if nhm.any():
        ok2=c.loc[nhm].apply(lambda r: price_ok(tprice,r['Next_Price'],tl1), axis=1)
        c=c.drop(ok2[~ok2].index)
    diag.append(("5. U5: price ceiling", len(c), f"Removed {b4u5-len(c)} (ceil: €{max(tprice*0.40,45):.0f})"))

    # ── SLOT ASSIGNMENT ──
    all_slot = []
    for _, sr in df_slots.iterrows():
        sn = sr['Slot_Number']
        role = str(sr.get('Slot_Role',''))
        lk = detect_logic_key(role)
        ah = [h.strip() for h in str(sr['Allowed_Hierarchies']).split(",")]
        sc = c[c['Hierarchy'].isin(ah)].copy()
        afh = len(sc)
        notes = [f"Logic: {lk}"]

        if lk == "PRIMARY_CASE":
            if strict_tmod:
                b4 = len(sc)
                cv = sc[CC].fillna('').str.lower()
                m = sc[cv.str.contains(strict_tmod, case=False, regex=True)]
                
                # 🟢 NEW: Drop if it contains a rival brand name (e.g. Galaxy)
                if rival_regex and not m.empty:
                    m = m[~m[CC].fillna('').str.lower().str.contains(rival_regex, regex=True)]
                    m = m[~m['Title'].fillna('').str.lower().str.contains(rival_regex, regex=True)]
                    
                notes.append(f"Strict Model '{tmod}': {b4}→{len(m)}")
                sc = m  
            else:
                sc = sc.head(0) 

            if not sc.empty:
                b4=len(sc)
                f=sc[sc['Τύπος Θήκης'].fillna('').str.contains("Back Cover", case=False)]
                notes.append(f"Back Cover: {b4}→{len(f)}")
                sc = f  
                
            if not sc.empty and tcol:
                b4=len(sc)
                sc_color=sc[sc['Χρώμα'].fillna('').str.strip().str.lower().isin(ccols)]
                notes.append(f"Color {ccols[:3]}: {b4}→{len(sc_color)}")
                if not sc_color.empty: sc = sc_color 

        elif lk == "ALT_CASE":
            if strict_tmod:
                b4 = len(sc)
                cv = sc[CC].fillna('').str.lower()
                m = sc[cv.str.contains(strict_tmod, case=False, regex=True)]
                
                if rival_regex and not m.empty:
                    m = m[~m[CC].fillna('').str.lower().str.contains(rival_regex, regex=True)]
                    m = m[~m['Title'].fillna('').str.lower().str.contains(rival_regex, regex=True)]
                    
                notes.append(f"Strict Model '{tmod}': {b4}→{len(m)}")
                sc = m
            else:
                sc = sc.head(0)

            if not sc.empty:
                b4 = len(sc)
                is_book = sc['Τύπος Θήκης'].fillna('').str.contains("Book Cover|Wallet|360 Full Cover|Folio|Flip", case=False)
                
                if tcol:
                    is_back = sc['Τύπος Θήκης'].fillna('').str.contains("Back Cover", case=False)
                    is_diff_color = is_back & ~sc['Χρώμα'].fillna('').str.strip().str.lower().isin(ccols)
                    sc = sc[is_book | is_diff_color]
                    notes.append(f"Book OR Diff Color: {b4}→{len(sc)}")
                else:
                    sc = sc[is_book]
                    notes.append(f"Strict Book Cover (no phone color): {b4}→{len(sc)}")

        elif lk == "SCREEN_GLASS":
            if strict_tmod:
                b4 = len(sc)
                cv = sc[CC].fillna('').str.lower()
                m = sc[cv.str.contains(strict_tmod, case=False, regex=True)]
                
                if rival_regex and not m.empty:
                    m = m[~m[CC].fillna('').str.lower().str.contains(rival_regex, regex=True)]
                    m = m[~m['Title'].fillna('').str.lower().str.contains(rival_regex, regex=True)]
                    
                notes.append(f"Strict Model '{tmod}': {b4}→{len(m)}")
                sc = m
            else:
                sc = sc.head(0)

            if not sc.empty and has_data(sc, 'Τύπος προϊόντος'):
                b4=len(sc)
                f=sc[sc['Τύπος προϊόντος'].fillna('').str.contains("Προστατευτικό οθόνης|Προστατευτικό Οθόνης|Screen Protector", case=False)]
                notes.append(f"Screen Protector type: {b4}→{len(f)}")
                sc = f 

        elif lk == "CAMERA_GLASS":
            if strict_tmod:
                b4 = len(sc)
                cv = sc[CC].fillna('').str.lower()
                m = sc[cv.str.contains(strict_tmod, case=False, regex=True)]
                
                if rival_regex and not m.empty:
                    m = m[~m[CC].fillna('').str.lower().str.contains(rival_regex, regex=True)]
                    m = m[~m['Title'].fillna('').str.lower().str.contains(rival_regex, regex=True)]
                    
                notes.append(f"Strict Model '{tmod}': {b4}→{len(m)}")
                sc = m
            else:
                sc = sc.head(0)

            if not sc.empty and has_data(sc, 'Τύπος προϊόντος'):
                b4=len(sc)
                f=sc[sc['Τύπος προϊόντος'].fillna('').str.contains("Προστατευτικό καμερών|Camera", case=False)]
                notes.append(f"Camera type: {b4}→{len(f)}")
                sc = f 
            
            if sc.empty and tport:
                fb_h = ['CABLE-CHARGER', 'APPLE ORIGINAL IPHONE CABLE-ADAPTORS', 'ΚΑΛΩΔΙΑ ΔΕΔΟΜΕΝΩΝ', 'MOBILE CABLE-ADAPTORS', 'IPHONE CABLE-ADAPTORS']
                fb = c[c['Hierarchy'].isin(fb_h)].copy()
                if strict_tmod:
                    fb_model = fb[fb[CC].fillna('').str.contains(strict_tmod, case=False, regex=True)]
                    if not fb_model.empty: fb = fb_model
                fb_port = fb[fb[CC].fillna('').str.lower().str.contains(tport.lower(), regex=False) | fb['Title'].fillna('').str.lower().str.contains(tport.lower(), regex=False)]
                notes.append(f"Cable fallback ({tport}): {len(fb_port)}")
                if not fb_port.empty: sc = fb_port

        elif lk == "WALL_CHARGER":
            if not sc.empty:
                b4=len(sc)
                cv = sc[CC].fillna('').str.lower()
                keep = cv.str.contains("universal", regex=False) | (cv=='')
                if strict_tmod: 
                    keep = keep | cv.str.contains(strict_tmod, case=False, regex=True)
                if tport: 
                    keep = keep | cv.str.contains(tport.lower(), regex=False) | cv.str.contains("usb-c", regex=False)
                m=sc[keep]
                notes.append(f"Compat (model/universal/port): {b4}→{len(m)}")
                if not m.empty: sc=m

            if "γρήγορη φόρτιση" in tex and not sc.empty and has_data(sc, 'Ισχύς (Watt)'):
                b4=len(sc)
                f=sc[sc['Ισχύς (Watt)'].fillna('').str.contains("21 - 60|61 - 100|101", case=False)]
                notes.append(f"Fast charge watt: {b4}→{len(f)}")
                if not f.empty: sc=f

            if not sc.empty and has_data(sc, 'Τύπος3'):
                if "ασύρματη φόρτιση" in tex:
                    b4=len(sc)
                    f=sc[sc['Τύπος3'].fillna('').str.contains("Φορτιστής Πρίζας|Ασύρματος Φορτιστής|Σετ Φόρτισης", case=False)]
                    notes.append(f"Wireless charger types: {b4}→{len(f)}")
                    if not f.empty: sc=f
                    sc.loc[sc['Τύπος3'].fillna('').str.contains("Ασύρματος", case=False),'Final_Score']+=SMART_BOOST
                    if tb=="APPLE":
                        sc.loc[sc['Title'].fillna('').str.contains("MagSafe", case=False),'Final_Score']+=SMART_BOOST
                else:
                    b4=len(sc)
                    f=sc[sc['Τύπος3'].fillna('').str.contains("Φορτιστής Πρίζας|Σετ Φόρτισης", case=False)]
                    notes.append(f"Wall charger types: {b4}→{len(f)}")
                    if not f.empty: sc=f

        elif lk == "POWERBANK":
            if tport and not sc.empty:
                cv = sc[CC].fillna('').str.lower()
                ts = sc['Τύπος σύνδεσης'].fillna('').str.lower() if 'Τύπος σύνδεσης' in sc.columns else pd.Series('', index=sc.index)
                keep = cv.str.contains(tport.lower(), regex=False) | cv.str.contains("usb-c", regex=False) | cv.str.contains("universal", regex=False) | (cv=='')
                keep = keep | ts.str.contains(tport.lower(), regex=False) | ts.str.contains("usb-c", regex=False) | ts.str.contains("usb type-c", regex=False)
                b4=len(sc); m=sc[keep]
                notes.append(f"Port compat: {b4}→{len(m)}")
                if not m.empty: sc=m

            if "γρήγορη φόρτιση" in tex and not sc.empty and has_data(sc, 'Ισχύς (Watt)'):
                sc.loc[sc['Ισχύς (Watt)'].fillna('').str.contains("21 - 60|61 - 100|101|30|40|50", case=False),'Final_Score']+=SMART_BOOST
                notes.append("Fast charge boost")
            if "ασύρματη φόρτιση" in tex and not sc.empty:
                sc.loc[sc['Extra Χαρακτηριστικά'].fillna('').str.contains("Ασύρματη φόρτιση", case=False),'Final_Score']+=SMART_BOOST
                if tb=="APPLE":
                    sc.loc[sc['Extra Χαρακτηριστικά'].fillna('').str.contains("Magsafe", case=False),'Final_Score']+=SMART_BOOST
            if not sc.empty:
                sc.loc[sc['Κατασκευαστής'].fillna('').str.strip().str.upper()==tb,'Final_Score']+=SMART_BOOST

        elif lk == "SMARTWATCH":
            if not sc.empty and has_data(sc, CC):
                b4=len(sc)
                if "ios" in tos or tb=="APPLE":
                    f=sc[sc[CC].fillna('').str.contains("iOS|Apple", case=False)]
                elif "android" in tos or tb in ["SAMSUNG","XIAOMI","MOTOROLA"]:
                    f=sc[sc[CC].fillna('').str.contains("Android", case=False)]
                else:
                    f=sc
                notes.append(f"OS compat: {b4}→{len(f)}")
                if not f.empty: sc=f
                else: notes.append(f"  ⚠ kept all (sample: {sample(sc,CC,3)})")
            
            hw_boost = ECOSYSTEM_BOOST if tprice >= 700 else SMART_BOOST
            sc.loc[sc['Κατασκευαστής'].fillna('').str.strip().str.upper()==tb,'Final_Score'] += hw_boost

        elif lk == "EARBUDS":
            hw_boost = ECOSYSTEM_BOOST if tprice >= 700 else SMART_BOOST

            if "3.5mm jack" in tex:
                if has_data(sc, 'Τύπος σύνδεσης'):
                    sc.loc[sc['Τύπος σύνδεσης'].fillna('').str.contains("3.5mm|Jack", case=False),'Final_Score'] += SMART_BOOST
                    notes.append("3.5mm boost applied")
                sc.loc[sc['Κατασκευαστής'].fillna('').str.strip().str.upper()==tb,'Final_Score'] += hw_boost
            else:
                if has_data(sc, 'Τύπος σύνδεσης'):
                    b4=len(sc)
                    port_str = tport if tport else "USB-C"
                    search_str = f"Bluetooth|Ασύρματη|{port_str}"
                    keep_bt = (
                        sc['Τύπος σύνδεσης'].fillna('').str.contains(search_str, case=False, regex=True) |
                        sc['Hierarchy'].fillna('').str.contains("Bluetooth", case=False) |
                        sc['Title'].fillna('').str.contains(search_str, case=False, regex=True)
                    )
                    f=sc[keep_bt]
                    notes.append(f"BT/Wireless/{port_str}: {b4}→{len(f)}")
                    if not f.empty: sc=f
                    else: notes.append(f"  ⚠ kept all")
                else:
                    notes.append("Connection filter: SKIPPED (col empty)")
                
                sc.loc[sc['Κατασκευαστής'].fillna('').str.strip().str.upper()==tb,'Final_Score'] += hw_boost
                
                f = sc[keep_bt]
                notes.append(f"BT/Wireless/{port_str} (Safe Match): {b4}→{len(f)}")
                
                if not f.empty: sc=f
                else: notes.append(f"  ⚠ kept all")
                
                sc.loc[sc['Κατασκευαστής'].fillna('').str.strip().str.upper()==tb,'Final_Score']+=SMART_BOOST

        elif lk == "HOLDER":
            if tb=="APPLE" and "ασύρματη φόρτιση" in tex:
                sc.loc[sc['Τρόπος τοποθέτησης'].fillna('').str.contains("Μαγνητική|Magsafe", case=False),'Final_Score']+=SMART_BOOST
            notes.append(f"No hard filter, {len(sc)} remain")

        elif lk == "CROSS_SELL":
            b4=len(sc)
            if "με pen" in tex:
                f=sc[sc['Τύπος3'].fillna('').str.contains("Γραφίδα", case=False)]
                notes.append(f"Stylus: {b4}→{len(f)}")
                if not f.empty: sc=f
            elif tb=="APPLE":
                f=sc[
                    sc['Τύπος3'].fillna('').str.contains("AirTag|Air Tag|Smart Tag", case=False) |
                    sc['Title'].fillna('').str.contains("AirTag", case=False) |
                    sc['Hierarchy'].fillna('').str.contains("AIRTAG", case=False)
                ]
                notes.append(f"AirTag (Τύπος3/Title/Hierarchy): {b4}→{len(f)}")
                if not f.empty: sc=f
                else:
                    f2=sc[sc['Τύπος3'].fillna('').str.contains("Λουράκι|Αξεσουάρ|Μπρελόκ", case=False)]
                    notes.append(f"Apple acc fallback: {b4}→{len(f2)}")
                    if not f2.empty: sc=f2
            else:
                f=sc[sc['Τύπος3'].fillna('').str.contains(
                    "Λουράκι Λαιμού|Λουράκι Καρπού|Αξεσουάρ Smartphone|Αξεσουάρ Κάμερας|Αξεσουάρ Καθαρισμού|Μπρελόκ", case=False)]
                notes.append(f"Misc acc: {b4}→{len(f)}")
                if not f.empty: sc=f

        else:
            notes.append(f"⚠ UNKNOWN logic key '{lk}' — no filters applied")

        # ── Rank ──
        afa = len(sc)
        slot_diag.append((sn, role, lk, afh, afa))
        slot_notes[sn] = notes

        if not sc.empty:
            sc = sc.sort_values('Final_Score', ascending=False).copy()
            sc['Assigned_Slot']=sn; sc['Slot_Role']=role
            sc['Item_Rank']=range(1,len(sc)+1)
            sc['Draft_Score']=sc['Item_Rank']*100+sn
            all_slot.append(sc)

    if not all_slot:
        return pd.DataFrame(), diag, slot_diag, slot_notes, pd.DataFrame()

    full = pd.concat(all_slot, ignore_index=True).sort_values('Draft_Score').reset_index(drop=True)

    sel, hc, seen = [], {}, set()
    for _, r in full.iterrows():
        h, mat = r['Hierarchy'], r['Material']
        if mat in seen: continue
        if hc.get(h,0)>=2: continue
        sel.append(r); hc[h]=hc.get(h,0)+1; seen.add(mat)
        if len(sel)>=10: break

    diag.append(("6. Final", len(sel), f"Hierarchy cap=2"))
    return (pd.DataFrame(sel) if sel else pd.DataFrame()), diag, slot_diag, slot_notes, full


# ─────────────────────────────────────────────────────────────
# RUN & VISUALIZATION
# ─────────────────────────────────────────────────────────────
# Unpack the 5 variables from the engine
recs, diag, slot_diag, slot_notes, full_candidates = run_engine(trigger, df_products, df_history, df_slots)

# 🟢 NEW: AI-Style Marketing Copy for each Slot Logic Key (Optimized & Short)
MARKETING_COPY = {
    "PRIMARY_CASE": "Απόλυτη προστασία & τέλεια εφαρμογή.",
    "SCREEN_GLASS": "Αόρατη ασπίδα για την οθόνη σου.",
    "WALL_CHARGER": "Γρήγορη και απόλυτα ασφαλής φόρτιση.",
    "EARBUDS": "Κορυφαία, ασύρματη ακουστική εμπειρία.",
    "POWERBANK": "Ενέργεια on-the-go για να μη μένεις ποτέ.",
    "CROSS_SELL": "Smart gadget για το οικοσύστημά σου.",
    "CAMERA_GLASS": "Θωράκιση φακών για τέλειες λήψεις.",
    "SMARTWATCH": "Ο απόλυτος σύντροφος για τον καρπό σου.",
    "HOLDER": "Σταθερή τοποθέτηση για το αυτοκίνητο.",
    "ALT_CASE": "Premium προστασία και πρακτικότητα."
}

if not recs.empty:
    rts = recs.head(10)
    ch = ""
    for _, r in rts.iterrows():
        iu=safe(str(r.get('Thumbnails','')).strip())
        rp=parse_euro_price(r.get('LIST PRICE',0))
        np=f"{rp:.2f}".replace('.',','); op=f"{(rp*1.25):.2f}".replace('.',',')
        ti=safe(str(r.get('Title',''))); sn=int(r.get('Assigned_Slot',0))
        
        # Determine the marketing text based on the slot's logic key
        raw_role = str(r.get('Slot_Role',''))
        lk = detect_logic_key(raw_role)
        marketing_text = MARKETING_COPY.get(lk, "Ιδανική προσθήκη για να ολοκληρώσεις την αγορά σου.")
        
        ch+=f"""<div class="pc">
            <div class="sb">Slot {sn}</div>
            <img src="{iu}" alt="product">
            <div class="ti" title="{ti}">{ti}</div>
            <div class="sr">{marketing_text}</div>
            <div class="rv"><span class="sc">4.8</span> <span class="st">&#9733;&#9733;&#9733;&#9733;&#9733;</span> <span class="ct">(305)</span></div>
            <div class="op">&#928;.&#923;.&#932;. : {op}&#8364;</div>
            <div class="np">{np.split(',')[0]}<span class="dm">,{np.split(',')[1]}&#8364;</span></div>
            <button class="cb">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
                    <circle cx="9" cy="21" r="1"></circle>
                    <circle cx="20" cy="21" r="1"></circle>
                    <path d="M1 1h4l2.68 13.39a2 2 0 0 0 2 1.61h9.72a2 2 0 0 0 2-1.61L23 6H6"></path>
                </svg>
            </button>
        </div>"""

    # Base CSS tightly matched to the original screenshot
    css="""
    *{margin:0;padding:0;box-sizing:border-box}
    body{font-family:-apple-system,BlinkMacSystemFont,sans-serif;background:transparent}
    
    .desktop-wrapper { background-color: #f8f9fa; border-radius: 16px; padding: 30px; margin: 10px 0; position: relative; }
    .desktop-header { font-size: 24px; font-weight: 700; margin-bottom: 25px; color: #111; display:flex; align-items:center; }
    .desktop-header span { color: #ff5e00; margin-right: 10px; font-size: 26px; line-height: 1; font-weight: 900; }
    
    /* Hide the scrollbar but keep it scrollable */
    .car { display:flex; overflow-x:auto; gap:15px; padding-bottom:10px; scrollbar-width:none; scroll-behavior: smooth; }
    .car::-webkit-scrollbar { display: none; }
    
    .pc { background:#fff; border:1px solid #eaeaea; border-radius:12px; padding:15px 12px; display:flex; flex-direction:column; align-items:center; box-shadow:0 2px 5px rgba(0,0,0,.04); position:relative; flex-shrink:0; width:195px; min-width:195px; }
    .sb { position:absolute; top:8px; left:8px; background:#ff5e00; color:#fff; font-size:10px; font-weight:700; padding:3px 6px; border-radius:6px; z-index:10; }
    .pc img { height:110px; width:auto; object-fit:contain; margin-bottom:15px; margin-top:10px; }
    .ti { font-size:13px; color:#333; text-align:center; height:36px; overflow:hidden; display:-webkit-box; -webkit-line-clamp:2; -webkit-box-orient:vertical; margin-bottom:6px; line-height:1.3; padding:0 5px; }
    
    /* 🟢 UPDATED: Marketing Text Subtitle CSS */
    .sr { 
        font-size: 10px; 
        color: #777; 
        margin-bottom: 12px; 
        text-align: center; 
        height: 28px; /* Room for 2 lines */
        overflow: hidden; 
        display: -webkit-box;
        -webkit-line-clamp: 2;
        -webkit-box-orient: vertical;
        line-height: 1.35;
        width: 100%; 
        padding: 0 4px;
    }
    
    .rv { font-size:11px; margin-bottom:15px }
    .sc { color:#ff5e00; font-weight:700 }
    .st { color:#ff5e00; letter-spacing:-2px }
    .ct { color:#1a73e8 }
    .op { font-size:11px; color:#888; text-decoration:line-through; margin-bottom:2px }
    .np { font-size:18px; font-weight:700; color:#ff5e00; margin-bottom:15px }
    .dm { font-size:12px }
    .cb { background:#ff5e00; color:#fff; border:none; border-radius:8px; width:40px; height:35px; cursor:pointer; transition: background 0.2s; display: flex; justify-content: center; align-items: center; }
    .cb:hover { background:#e65500 }
    
    /* Smart Navigation Arrows */
    .nav-btn {
        position: absolute;
        top: 55%;
        transform: translateY(-50%);
        width: 44px;
        height: 44px;
        background-color: #fff;
        border: 1px solid #eaeaea;
        border-radius: 50%;
        box-shadow: 0 4px 10px rgba(0,0,0,0.1);
        display: flex;
        align-items: center;
        justify-content: center;
        cursor: pointer;
        z-index: 100;
        transition: transform 0.2s, box-shadow 0.2s, opacity 0.3s;
    }
    .nav-btn:hover {
        transform: translateY(-50%) scale(1.05);
        box-shadow: 0 6px 14px rgba(0,0,0,0.15);
    }
    
    .nav-left { left: 10px; opacity: 0; pointer-events: none; }
    .nav-right { right: 10px; }
    
    .nav-left::after {
        content: ''; width: 10px; height: 10px;
        border-top: 2px solid #555; border-left: 2px solid #555;
        transform: rotate(-45deg); margin-left: 4px;
    }
    .nav-right::after {
        content: ''; width: 10px; height: 10px;
        border-top: 2px solid #555; border-right: 2px solid #555;
        transform: rotate(45deg); margin-right: 4px;
    }
    """

    dp=f"""<!DOCTYPE html><html><head><meta charset="utf-8"><style>{css}</style></head>
    <body>
    <div class="desktop-wrapper">
        <div class="desktop-header"><span>|</span>Μαζί με αυτό, οι περισσότεροι αγοράζουν</div>
        <div class="nav-btn nav-left" id="btnLeft" onclick="scrollL()"></div>
        <div class="car" id="scrollContainer">{ch}</div>
        <div class="nav-btn nav-right" id="btnRight" onclick="scrollR()"></div>
    </div>

    <script>
        const container = document.getElementById('scrollContainer');
        const btnLeft = document.getElementById('btnLeft');
        const btnRight = document.getElementById('btnRight');
        const scrollAmount = 405; 

        function scrollL() {{ container.scrollBy({{ left: -scrollAmount, behavior: 'smooth' }}); }}
        function scrollR() {{ container.scrollBy({{ left: scrollAmount, behavior: 'smooth' }}); }}

        container.addEventListener('scroll', () => {{
            if (container.scrollLeft > 5) {{
                btnLeft.style.opacity = '1'; btnLeft.style.pointerEvents = 'auto';
            }} else {{
                btnLeft.style.opacity = '0'; btnLeft.style.pointerEvents = 'none';
            }}
            if (container.scrollLeft + container.clientWidth >= container.scrollWidth - 2) {{
                btnRight.style.opacity = '0'; btnRight.style.pointerEvents = 'none';
            }} else {{
                btnRight.style.opacity = '1'; btnRight.style.pointerEvents = 'auto';
            }}
        }});
        container.dispatchEvent(new Event('scroll'));
    </script>
    </body></html>"""

    # Render Layout
    components.html(dp, height=540, scrolling=False)

else:
    st.error("❌ No recommendations. Check diagnostics below.")


# ─────────────────────────────────────────────────────────────
# DIAGNOSTICS (HIDDEN AT BOTTOM)
# ─────────────────────────────────────────────────────────────
st.markdown("---")

# 🟢 FIX: Ultimate CSS Hack to mimic your Angular <cdk-accordion-item> and ic-chevron-down
st.markdown("""
<style>
/* 1. The Main Box (Matches the exact border and radius of your screenshot) */
[data-testid="stExpander"] {
    background-color: #ffffff !important;
    border: 1px solid #d9d9d9 !important;
    border-radius: 12px !important;
    box-shadow: none !important;
    margin-top: 20px;
}

/* 2. The Header Area (Matches .pbc-accordion-item-header) */
[data-testid="stExpander"] summary {
    padding: 24px 30px !important;
    display: flex !important;
    align-items: center !important;
}
[data-testid="stExpander"] summary:hover {
    background-color: transparent !important;
}

/* 3. The Typography (Matches .pbc-accordion-item-title) */
[data-testid="stExpander"] summary p {
    font-size: 18px !important;
    font-weight: 700 !important;
    color: #000000 !important;
    flex-grow: 1; /* Pushes the arrow to the far right */
}

/* 4. The Icon Hack (Killing Streamlit's default SVG and replacing it with your chevron) */
[data-testid="stExpander"] summary svg {
    display: none !important;
}
[data-testid="stExpander"] summary::after {
    content: '';
    display: inline-block;
    width: 12px;
    height: 12px;
    border-right: 2px solid #111;
    border-bottom: 2px solid #111;
    transform: rotate(45deg);
    transition: transform 0.2s ease;
    margin-top: -4px; /* Optical centering */
}

/* When the accordion is open, flip the arrow up */
[data-testid="stExpander"][open] summary::after {
    transform: rotate(225deg);
    margin-top: 6px;
}

/* 5. The Body Content (Matches your pbc-accordion-item-body padding) */
[data-testid="stExpanderDetails"] {
    padding: 10px 30px 30px 30px !important;
}
</style>
""", unsafe_allow_html=True)

# The actual expander
with st.expander("⚙️ System Diagnostics & Engine Math"):
    tpr = str(trigger.get('Θύρα USB','')).strip()
    tp2 = extract_base_port(tpr)
    tc2 = str(trigger.get('Χρώμα','')).strip()
    cc2 = get_case_colors(tc2)
    st.markdown(f"**Port:** `{tpr}` → **`{tp2}`** | **Color:** `{tc2}` → **{cc2}** | **Compat cols:** {compat_cols_found}")

    st.markdown("### Guardrail Funnel")
    st.dataframe(pd.DataFrame(diag, columns=["Step","Left","Note"]), use_container_width=True, hide_index=True)

    st.markdown("### Per-Slot Breakdown")
    st.dataframe(pd.DataFrame(slot_diag, columns=["Slot","Role","Logic","After Hierarchy","After Attributes"]), use_container_width=True, hide_index=True)

    st.markdown("### Slot Filter Details")
    for sn, notes in sorted(slot_notes.items()):
        if notes:
            st.markdown(f"**Slot {sn} — {' | '.join(notes[:2])}**")
            for n in notes: st.text(n)

    st.markdown("### 📋 Trigger")
    for col in ['Material','Title','Level 1','Level 2','Hierarchy','Κατασκευαστής','Μοντέλο',
                'Θύρα USB','Χρώμα','Λειτουργικό σύστημα','Extra Χαρακτηριστικά','LIST PRICE']:
        st.text(f"{col}: {trigger.get(col,'N/A')}")

    if not recs.empty:
        st.markdown("### 🏆 Top 3 Candidates per Slot")
        top3 = full_candidates[full_candidates['Item_Rank'] <= 3].copy()
        top3_cols = ['Assigned_Slot', 'Item_Rank', 'Title', 'Final_Score', 'Sales_Tiebreaker', 'Smart_Boost', 'Avail_Boost', 'Frequency', 'History_Score']
        avail_top3 = [c for c in top3_cols if c in top3.columns]
        st.dataframe(top3[avail_top3].sort_values(['Assigned_Slot', 'Item_Rank']), use_container_width=True, hide_index=True)

        st.markdown("### Score Breakdown (Final 10 Winners)")
        dc=['Title','Hierarchy','Assigned_Slot','Slot_Role','Item_Rank','History_Score','Frequency','Avail_Boost','Smart_Boost','Sales_Tiebreaker','Final_Score','Draft_Score']
        st.dataframe(recs[[c for c in dc if c in recs.columns]], use_container_width=True)
