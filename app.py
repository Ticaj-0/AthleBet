import streamlit as st
import psycopg2
import psycopg2.extras
import psycopg2.pool
from datetime import datetime
from contextlib import contextmanager

st.set_page_config(page_title="Athlé Bet", page_icon="🏃", layout="wide", initial_sidebar_state="collapsed")

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Bebas+Neue&family=DM+Sans:wght@400;500;600&display=swap');

/* ── RESET & BASE ── */
html, body, [class*="css"] {
    font-family: 'DM Sans', sans-serif;
    -webkit-tap-highlight-color: transparent;
    -webkit-text-size-adjust: 100%;
}
h1, h2, h3 { font-family: 'Bebas Neue', sans-serif; letter-spacing: 1px; }

/* ── HIDE STREAMLIT CHROME ON MOBILE ── */
#MainMenu, footer, header { display: none !important; }
.stDeployButton { display: none !important; }

/* ── MOBILE VIEWPORT FIX ── */
.block-container {
    padding: 1rem 0.75rem 5rem 0.75rem !important;   /* bottom padding for nav bar */
    max-width: 100% !important;
}

/* ── BOTTOM NAV BAR ── */
.mobile-nav {
    position: fixed;
    bottom: 0; left: 0; right: 0;
    background: #0f0f0f;
    display: flex;
    justify-content: space-around;
    align-items: stretch;
    height: 60px;
    z-index: 9999;
    border-top: 1px solid #2a2a2a;
    padding-bottom: env(safe-area-inset-bottom);
}
.mobile-nav a {
    flex: 1;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    color: #666;
    text-decoration: none;
    font-size: 9px;
    font-weight: 600;
    letter-spacing: 0.3px;
    gap: 3px;
    padding: 6px 2px;
    transition: color 0.15s;
}
.mobile-nav a .nav-icon { font-size: 20px; line-height: 1; }
.mobile-nav a.active { color: #e94560; }

/* ── TOUCH-FRIENDLY INPUTS ── */
input[type="text"], input[type="number"], input[type="email"],
.stTextInput > div > div > input,
.stNumberInput > div > div > input {
    font-size: 16px !important;  /* prevent iOS zoom */
    min-height: 48px !important;
    padding: 12px 14px !important;
    border-radius: 10px !important;
}

/* ── BUTTONS ── */
.stButton > button {
    min-height: 48px !important;
    border-radius: 10px !important;
    font-family: 'DM Sans', sans-serif;
    font-weight: 600;
    font-size: 15px !important;
    width: 100%;
    letter-spacing: 0.2px;
}
.stButton > button[kind="primary"],
.stButton > button[data-testid="baseButton-primary"] {
    background: #e94560 !important;
    border-color: #e94560 !important;
    color: white !important;
}

/* ── FORMS ── */
.stForm { border-radius: 12px !important; }
[data-testid="stForm"] { padding: 0 !important; }

/* ── SELECT & MULTISELECT ── */
.stSelectbox > div > div,
.stMultiSelect > div > div {
    min-height: 48px !important;
    font-size: 16px !important;
    border-radius: 10px !important;
}

/* ── NUMBER INPUT STEPPER ── */
.stNumberInput button {
    min-width: 44px !important;
    min-height: 44px !important;
}

/* ── METRICS ── */
[data-testid="metric-container"] {
    background: #1e293b;
    border-radius: 10px;
    padding: 12px 14px !important;
}

/* ── EXPANDERS ── */
.streamlit-expanderHeader {
    font-size: 15px !important;
    min-height: 52px !important;
    padding: 14px !important;
    border-radius: 10px !important;
}

/* ── SCORE BADGE ── */
.score-badge {
    background: #e94560; color: white;
    border-radius: 20px; padding: 3px 12px;
    font-size: 0.9em; font-weight: 700;
    display: inline-block;
}

/* ── CARD ── */
.athlete-card {
    background: #1e293b;
    border-radius: 12px;
    padding: 14px 16px;
    margin-bottom: 10px;
}

/* ── SIDEBAR override — keep it minimal on mobile ── */
section[data-testid="stSidebar"] {
    background: #0f0f0f;
    min-width: 260px !important;
    max-width: 280px !important;
}
section[data-testid="stSidebar"] * { color: white !important; }

/* ── DATE INPUT ── */
.stDateInput > div > div > input {
    font-size: 16px !important;
    min-height: 48px !important;
}

/* ── DIVIDER spacing ── */
hr { margin: 12px 0 !important; }

/* ── COLUMN GAPS ── */
[data-testid="column"] { padding: 0 4px !important; }

/* ── TOASTS / ALERTS ── */
.stAlert { border-radius: 10px !important; font-size: 14px !important; }

/* ── PAGE TITLE ── */
.page-header {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 6px 0 14px 0;
    margin-bottom: 4px;
}
.page-header h1 {
    font-size: 2em;
    margin: 0;
    line-height: 1;
}

/* ── LANDSCAPE: show sidebar radio on wider screens ── */
@media (min-width: 768px) {
    .mobile-nav { display: none !important; }
    .block-container { padding-bottom: 2rem !important; }
    section[data-testid="stSidebar"] { display: flex !important; }
}
@media (max-width: 767px) {
    /* collapse sidebar button */
    [data-testid="collapsedControl"] { display: none !important; }
}
</style>
""", unsafe_allow_html=True)

# ── CONNECTION POOL ──────────────────────────────────────────────────────────
@st.cache_resource
def get_pool():
    return psycopg2.pool.ThreadedConnectionPool(
        minconn=1, maxconn=5,
        dsn=st.secrets["supabase"]["url"],
        cursor_factory=psycopg2.extras.RealDictCursor
    )

@contextmanager
def db():
    pool = get_pool()
    conn = pool.getconn()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        pool.putconn(conn)

# ── DB INIT ──────────────────────────────────────────────────────────────────
def init_db():
    with db() as conn:
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS users (username TEXT PRIMARY KEY);
            CREATE TABLE IF NOT EXISTS athletes (id SERIAL PRIMARY KEY, first_name TEXT NOT NULL, last_name TEXT NOT NULL, age INTEGER);
            CREATE TABLE IF NOT EXISTS athlete_pbs (athlete_id INTEGER, discipline TEXT, pb REAL, PRIMARY KEY (athlete_id, discipline), FOREIGN KEY (athlete_id) REFERENCES athletes(id) ON DELETE CASCADE);
            CREATE TABLE IF NOT EXISTS competitions (id SERIAL PRIMARY KEY, name TEXT NOT NULL, date TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS competition_athletes (competition_id INTEGER, athlete_id INTEGER, discipline TEXT, PRIMARY KEY (competition_id, athlete_id), FOREIGN KEY (competition_id) REFERENCES competitions(id) ON DELETE CASCADE, FOREIGN KEY (athlete_id) REFERENCES athletes(id) ON DELETE CASCADE);
            CREATE TABLE IF NOT EXISTS predictions (username TEXT, competition_id INTEGER, athlete_id INTEGER, prediction REAL, PRIMARY KEY (username, competition_id, athlete_id), FOREIGN KEY (competition_id) REFERENCES competitions(id) ON DELETE CASCADE);
            CREATE TABLE IF NOT EXISTS results (competition_id INTEGER, athlete_id INTEGER, result REAL, PRIMARY KEY (competition_id, athlete_id), FOREIGN KEY (competition_id) REFERENCES competitions(id) ON DELETE CASCADE);
        """)
        cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name='competition_athletes' AND column_name='discipline'")
        if not cur.fetchone():
            cur.execute("ALTER TABLE competition_athletes ADD COLUMN discipline TEXT")

if "db_initialized" not in st.session_state:
    init_db()
    st.session_state.db_initialized = True

# ── HELPERS ──────────────────────────────────────────────────────────────────
def fmt(d):
    try:
        return datetime.strptime(str(d), "%Y-%m-%d").strftime("%d/%m/%Y")
    except (ValueError, TypeError):
        return str(d) if d else ""

def score(p, r):
    d = abs(p - r)
    return 300 if d == 0 else max(0, int(150 - d * 4))

def rows_to_dicts(rows):
    return [dict(r) for r in rows] if rows else []

def invalidate_cache():
    st.cache_data.clear()

# ── CACHED QUERIES ────────────────────────────────────────────────────────────
@st.cache_data(ttl=30)
def get_all_athletes():
    with db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT * FROM athletes ORDER BY last_name, first_name")
        return rows_to_dicts(cur.fetchall())

@st.cache_data(ttl=30)
def get_all_competitions():
    with db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT * FROM competitions ORDER BY date DESC")
        return rows_to_dicts(cur.fetchall())

@st.cache_data(ttl=30)
def get_all_pbs():
    with db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT * FROM athlete_pbs ORDER BY athlete_id, discipline")
        rows = rows_to_dicts(cur.fetchall())
    pbs = {}
    for r in rows:
        pbs.setdefault(r["athlete_id"], []).append(r)
    return pbs

@st.cache_data(ttl=30)
def get_all_competition_athletes():
    with db() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT ca.competition_id, ca.discipline, a.id, a.first_name, a.last_name
            FROM competition_athletes ca
            JOIN athletes a ON a.id = ca.athlete_id
            ORDER BY ca.competition_id, a.last_name
        """)
        rows = rows_to_dicts(cur.fetchall())
    grouped = {}
    for r in rows:
        grouped.setdefault(r["competition_id"], []).append(r)
    return grouped

@st.cache_data(ttl=30)
def get_historique_data():
    with db() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT p.username, p.prediction, r.result, p.competition_id,
                   a.first_name, a.last_name, ca.discipline
            FROM predictions p
            JOIN results r ON p.competition_id = r.competition_id AND p.athlete_id = r.athlete_id
            JOIN athletes a ON a.id = p.athlete_id
            JOIN competition_athletes ca ON ca.competition_id = p.competition_id AND ca.athlete_id = p.athlete_id
            ORDER BY p.competition_id, a.last_name, p.username
        """)
        rows = rows_to_dicts(cur.fetchall())
    grouped = {}
    for r in rows:
        grouped.setdefault(r["competition_id"], []).append(r)
    return grouped

@st.cache_data(ttl=30)
def get_classement_data():
    with db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT username FROM users")
        users = rows_to_dicts(cur.fetchall())
        cur.execute("""
            SELECT DISTINCT c.id, c.name, c.date FROM competitions c
            JOIN results r ON r.competition_id = c.id ORDER BY c.date ASC, c.id ASC
        """)
        comps = rows_to_dicts(cur.fetchall())
        cur.execute("""
            SELECT p.username, p.prediction, r.result, p.competition_id
            FROM predictions p
            JOIN results r ON p.competition_id = r.competition_id AND p.athlete_id = r.athlete_id
        """)
        scores = rows_to_dicts(cur.fetchall())
    return users, comps, scores

# ── AUTH ──────────────────────────────────────────────────────────────────────
if "user" not in st.session_state:
    saved_user = st.query_params.get("u", "")
    if saved_user:
        with db() as conn:
            cur = conn.cursor()
            cur.execute("SELECT 1 FROM users WHERE username = %s", (saved_user,))
            if cur.fetchone():
                st.session_state.user = saved_user
                st.rerun()

    st.markdown("""
<script>
(function() {
    var stored = localStorage.getItem('athle_bet_user');
    if (!stored) return;
    var params = new URLSearchParams(window.location.search);
    if (params.get('u') === stored) return;
    params.set('u', stored);
    window.location.search = params.toString();
})();
</script>
""", unsafe_allow_html=True)

    # ── PWA INSTALL POPUP ──
    st.markdown("""
<style>
#pwa-popup {
    display:none; position:fixed; bottom:24px; left:50%; transform:translateX(-50%);
    background:#1e293b; color:#f1f5f9; border:1.5px solid #e94560; border-radius:16px;
    padding:20px 22px; z-index:9999; box-shadow:0 8px 32px rgba(0,0,0,0.5);
    max-width:370px; width:92vw; font-family:'DM Sans',sans-serif;
    animation:slideUp 0.4s ease;
}
@keyframes slideUp {
    from{opacity:0;transform:translateX(-50%) translateY(30px)}
    to{opacity:1;transform:translateX(-50%) translateY(0)}
}
#pwa-popup .pwa-title { font-weight:700; font-size:1.05em; margin-bottom:6px; }
#pwa-popup .pwa-desc  { font-size:0.88em; color:#94a3b8; margin-bottom:12px; line-height:1.4; }
#pwa-popup .pwa-steps { font-size:0.83em; color:#cbd5e1; margin-bottom:14px; line-height:1.7; }
#pwa-popup .pwa-btn-row { display:flex; gap:10px; justify-content:flex-end; }
#pwa-popup button {
    border:none; border-radius:10px; padding:10px 18px;
    font-size:0.9em; font-weight:600; cursor:pointer;
    font-family:'DM Sans',sans-serif; min-height:44px;
}
#pwa-install-btn { background:#e94560; color:white; }
#pwa-dismiss-btn { background:#334155; color:#94a3b8; }
</style>
<div id="pwa-popup">
    <div class="pwa-title">📲 Installer Athlé Bet</div>
    <div class="pwa-desc">Accédez à l'app depuis votre écran d'accueil comme une vraie app mobile.</div>
    <div class="pwa-steps" id="pwa-steps-text"></div>
    <div class="pwa-btn-row">
        <button id="pwa-dismiss-btn" onclick="dismissPwa()">Plus tard</button>
        <button id="pwa-install-btn" onclick="triggerInstall()">Installer</button>
    </div>
</div>
<script>
(function() {
    if (localStorage.getItem('pwa_dismissed')) return;
    if (window.matchMedia('(display-mode: standalone)').matches) return;
    var popup=document.getElementById('pwa-popup'),stepsEl=document.getElementById('pwa-steps-text');
    var deferredPrompt=null,ua=navigator.userAgent;
    var isIOS=/iphone|ipad|ipod/i.test(ua),isSafari=/^((?!chrome|android).)*safari/i.test(ua);
    var isAndroid=/android/i.test(ua),isChrome=/chrome/i.test(ua)&&!(/edge/i.test(ua));
    if(isIOS&&isSafari){
        stepsEl.innerHTML='1. Appuyez sur <strong>Partager</strong> (⬆) dans Safari<br>2. Choisissez <strong>« Sur l\'écran d\'accueil »</strong><br>3. Confirmez avec <strong>Ajouter</strong>';
        document.getElementById('pwa-install-btn').style.display='none';
        popup.style.display='block';
    } else if(isAndroid&&isChrome){
        window.addEventListener('beforeinstallprompt',function(e){
            e.preventDefault();deferredPrompt=e;
            stepsEl.innerHTML='Appuyez sur <strong>Installer</strong> ci-dessous.';
            popup.style.display='block';
        });
    } else {
        stepsEl.innerHTML='Menu navigateur → <strong>« Installer l\'application »</strong>';
        popup.style.display='block';
    }
    window.triggerInstall=function(){
        if(deferredPrompt){deferredPrompt.prompt();deferredPrompt.userChoice.then(function(){deferredPrompt=null;popup.style.display='none';});}
        else{popup.style.display='none';}
    };
    window.dismissPwa=function(){popup.style.display='none';localStorage.setItem('pwa_dismissed','1');};
})();
</script>
""", unsafe_allow_html=True)

    # ── LOGIN SCREEN ──
    st.markdown("""
<div style='text-align:center;padding:32px 0 8px 0;'>
    <div style='font-family:"Bebas Neue",sans-serif;font-size:3.2em;letter-spacing:2px;line-height:1;'>🏃 ATHLÉ BET</div>
    <div style='color:#888;font-size:0.95em;margin-top:8px;'>Pronostique. Compète. Grimpe au classement.</div>
</div>
""", unsafe_allow_html=True)
    st.divider()
    u = st.text_input("Choisis ton pseudo", placeholder="Ex: SpeedDemon42", label_visibility="visible")
    if st.button("▶ Entrer dans l'arène", use_container_width=True, type="primary") and u.strip():
        with db() as conn:
            cur = conn.cursor()
            cur.execute("INSERT INTO users (username) VALUES (%s) ON CONFLICT (username) DO NOTHING", (u.strip(),))
        st.session_state.user = u.strip()
        st.query_params["u"] = u.strip()
        st.markdown(f"<script>localStorage.setItem('athle_bet_user','{u.strip()}');</script>", unsafe_allow_html=True)
        st.rerun()
    st.stop()

current_user = st.session_state.user

# ── PAGE STATE (bottom nav) ───────────────────────────────────────────────────
# Keep page in session state so the bottom nav JS can set it via query param
if "page" not in st.session_state:
    st.session_state.page = st.query_params.get("page", "pronostics")

# Sync from query param (set by bottom nav JS)
qp_page = st.query_params.get("page", None)
if qp_page and qp_page != st.session_state.page:
    st.session_state.page = qp_page

# ── SIDEBAR (desktop) ────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown(f"## 👋 {current_user}")
    st.divider()
    sidebar_choice = st.radio("Navigation", [
        "pronostics", "classement", "historique",
        "athletes", "competitions", "resultats",
    ], format_func=lambda x: {
        "pronostics": "🎯 Pronostics",
        "classement": "🏆 Classement",
        "historique": "📜 Historique",
        "athletes": "👤 Athlètes",
        "competitions": "🏟️ Compétitions",
        "resultats": "📊 Résultats",
    }[x], label_visibility="collapsed", key="sidebar_radio")
    st.divider()
    if st.button("🚪 Déconnexion", use_container_width=True):
        del st.session_state.user
        st.query_params.clear()
        st.markdown("<script>localStorage.removeItem('athle_bet_user');</script>", unsafe_allow_html=True)
        st.rerun()

# Sidebar takes priority when used
if sidebar_choice != st.session_state.get("_last_sidebar", st.session_state.page):
    st.session_state.page = sidebar_choice
st.session_state["_last_sidebar"] = sidebar_choice

page = st.session_state.page

# ── BOTTOM NAVIGATION BAR ────────────────────────────────────────────────────
nav_items = [
    ("pronostics",   "🎯", "Pronos"),
    ("classement",   "🏆", "Classmt"),
    ("historique",   "📜", "Historique"),
    ("athletes",     "👤", "Athlètes"),
    ("competitions", "🏟️", "Compét."),
    ("resultats",    "📊", "Résultats"),
]

nav_links = ""
for key, icon, label in nav_items:
    active_class = "active" if page == key else ""
    nav_links += f'<a href="?page={key}&u={current_user}" class="{active_class}"><span class="nav-icon">{icon}</span>{label}</a>'

st.markdown(f'<nav class="mobile-nav">{nav_links}</nav>', unsafe_allow_html=True)

# ── PAGE: ATHLÈTES ───────────────────────────────────────────────────────────
if page == "athletes":
    st.markdown("<div class='page-header'><h1>👤 Athlètes</h1></div>", unsafe_allow_html=True)

    with st.expander("➕ Ajouter un athlète", expanded=False):
        with st.form("add_athlete"):
            fn  = st.text_input("Prénom")
            ln  = st.text_input("Nom")
            age = st.number_input("Âge", 10, 100, 20)
            if st.form_submit_button("✅ Créer l'athlète", use_container_width=True):
                if fn.strip() and ln.strip():
                    with db() as conn:
                        cur = conn.cursor()
                        cur.execute("INSERT INTO athletes (first_name, last_name, age) VALUES (%s,%s,%s)", (fn.strip(), ln.strip(), age))
                    invalidate_cache()
                    st.success(f"✅ {fn} {ln} ajouté(e) !")
                    st.rerun()
                else:
                    st.error("Prénom et nom requis.")

    st.divider()
    athletes = get_all_athletes()
    all_pbs  = get_all_pbs()

    if not athletes:
        st.info("Aucun athlète pour l'instant.")
    else:
        st.caption(f"{len(athletes)} athlète(s) enregistré(s)")
        for a in athletes:
            with st.container():
                col_info, col_btn = st.columns([5, 1])
                col_info.markdown(f"**{a['first_name']} {a['last_name']}** · {a['age']} ans")
                if col_btn.button("🗑️", key=f"del_{a['id']}", help="Supprimer"):
                    st.session_state[f"confirm_del_{a['id']}"] = True

                if st.session_state.get(f"confirm_del_{a['id']}"):
                    st.warning(f"Supprimer **{a['first_name']} {a['last_name']}** ?")
                    cc1, cc2 = st.columns(2)
                    if cc1.button("✅ Confirmer", key=f"yes_{a['id']}"):
                        with db() as conn:
                            cur = conn.cursor()
                            cur.execute("DELETE FROM athletes WHERE id=%s", (a['id'],))
                        invalidate_cache()
                        st.rerun()
                    if cc2.button("❌ Annuler", key=f"no_{a['id']}"):
                        st.session_state[f"confirm_del_{a['id']}"] = False
                        st.rerun()

                pbs = all_pbs.get(a["id"], [])
                if pbs:
                    # Responsive: 2 cols on mobile instead of 4
                    pb_cols = st.columns(min(len(pbs), 2))
                    for i, pb in enumerate(pbs):
                        pb_cols[i % 2].metric(pb["discipline"], pb["pb"])

                if st.button("✏️ Gérer les PBs", key=f"edit_{a['id']}", use_container_width=True):
                    st.session_state[f"show_pb_{a['id']}"] = not st.session_state.get(f"show_pb_{a['id']}", False)

                if st.session_state.get(f"show_pb_{a['id']}"):
                    with st.form(f"pb_form_{a['id']}"):
                        st.markdown("**PBs existants**")
                        inputs, to_delete = [], []
                        for i, pb in enumerate(pbs):
                            # Stack vertically on mobile (better touch targets)
                            st.markdown(f"**{pb['discipline']}**")
                            c1, c2 = st.columns([3, 1])
                            v = c1.number_input("Valeur", value=float(pb["pb"]), key=f"v_{a['id']}_{i}")
                            if c2.checkbox("🗑️", key=f"del_pb_{a['id']}_{i}"):
                                to_delete.append(pb["discipline"])
                            inputs.append((pb["discipline"], v, pb["discipline"]))
                        st.markdown("**Nouveau PB**")
                        new_d = st.text_input("Discipline", key=f"nd_{a['id']}")
                        new_v = st.number_input("Valeur", 0.0, key=f"nv_{a['id']}")
                        if st.form_submit_button("💾 Sauvegarder", use_container_width=True):
                            with db() as conn:
                                cur = conn.cursor()
                                for orig_d in to_delete:
                                    cur.execute("DELETE FROM athlete_pbs WHERE athlete_id=%s AND discipline=%s", (a["id"], orig_d))
                                for d, v, orig_d in inputs:
                                    if orig_d not in to_delete and d.strip():
                                        cur.execute("INSERT INTO athlete_pbs (athlete_id,discipline,pb) VALUES (%s,%s,%s) ON CONFLICT (athlete_id,discipline) DO UPDATE SET pb=EXCLUDED.pb", (a["id"], d.strip(), v))
                                if new_d.strip():
                                    cur.execute("INSERT INTO athlete_pbs (athlete_id,discipline,pb) VALUES (%s,%s,%s) ON CONFLICT (athlete_id,discipline) DO UPDATE SET pb=EXCLUDED.pb", (a["id"], new_d.strip(), new_v))
                            invalidate_cache()
                            st.session_state[f"show_pb_{a['id']}"] = False
                            st.success("PBs mis à jour !")
                            st.rerun()
            st.divider()

# ── PAGE: COMPÉTITIONS ───────────────────────────────────────────────────────
elif page == "competitions":
    st.markdown("<div class='page-header'><h1>🏟️ Compétitions</h1></div>", unsafe_allow_html=True)

    athletes = get_all_athletes()
    if not athletes:
        st.warning("Ajoutez d'abord des athlètes.")
    else:
        with st.expander("➕ Nouvelle compétition", expanded=True):
            name     = st.text_input("Nom de la compétition")
            date     = st.date_input("Date")
            options  = {f"{a['first_name']} {a['last_name']}": a["id"] for a in athletes}
            selected = st.multiselect("Athlètes participants", list(options.keys()))
            all_pbs  = get_all_pbs()

            athlete_disciplines = {}
            if selected:
                st.markdown("**Discipline par athlète :**")
                for s in selected:
                    aid = options[s]
                    disc_list = [pb["discipline"] for pb in all_pbs.get(aid, [])]
                    st.markdown(f"**{s}**")
                    if disc_list:
                        chosen = st.selectbox("Discipline", disc_list + ["✏️ Autre..."], key=f"disc_{aid}")
                        if chosen == "✏️ Autre...":
                            athlete_disciplines[aid] = st.text_input(f"Discipline pour {s}", key=f"disc_custom_{aid}")
                        else:
                            athlete_disciplines[aid] = chosen
                    else:
                        athlete_disciplines[aid] = st.text_input("Discipline (aucun PB)", key=f"disc_free_{aid}")

            if st.button("🏟️ Créer la compétition", use_container_width=True, type="primary") and name.strip() and selected:
                if not all(athlete_disciplines.get(options[s], "").strip() for s in selected):
                    st.error("⚠️ Renseignez une discipline pour chaque athlète.")
                else:
                    with db() as conn:
                        cur = conn.cursor()
                        cur.execute("INSERT INTO competitions (name,date) VALUES (%s,%s) RETURNING id", (name.strip(), date.strftime("%Y-%m-%d")))
                        cid = cur.fetchone()["id"]
                        cur.executemany(
                            "INSERT INTO competition_athletes (competition_id,athlete_id,discipline) VALUES (%s,%s,%s) ON CONFLICT DO NOTHING",
                            [(cid, options[s], athlete_disciplines[options[s]].strip()) for s in selected]
                        )
                    invalidate_cache()
                    st.success(f"✅ Compétition **{name}** créée !")
                    st.rerun()

    st.divider()
    comps         = get_all_competitions()
    comp_athletes = get_all_competition_athletes()

    if not comps:
        st.info("Aucune compétition créée.")
    else:
        st.caption(f"{len(comps)} compétition(s)")
        for c in comps:
            ca_rows = comp_athletes.get(c["id"], [])
            col1, col2 = st.columns([5, 1])
            col1.markdown(f"**{c['name']}** · {fmt(c['date'])}")
            col1.caption(f"{len(ca_rows)} athlète(s)")
            if col2.button("🗑️", key=f"delcomp_{c['id']}", help="Supprimer"):
                st.session_state[f"confirm_delcomp_{c['id']}"] = True
            if ca_rows:
                st.caption("  ".join([f"{r['first_name']} {r['last_name']} `{r['discipline'] or '—'}`" for r in ca_rows]))
            if st.session_state.get(f"confirm_delcomp_{c['id']}"):
                st.warning(f"Supprimer **{c['name']}** et toutes ses données ?")
                cc1, cc2 = st.columns(2)
                if cc1.button("✅ Confirmer", key=f"yescomp_{c['id']}"):
                    with db() as conn:
                        cur = conn.cursor()
                        cur.execute("DELETE FROM competitions WHERE id=%s", (c["id"],))
                    invalidate_cache()
                    st.rerun()
                if cc2.button("❌ Annuler", key=f"nocomp_{c['id']}"):
                    st.session_state[f"confirm_delcomp_{c['id']}"] = False
                    st.rerun()
            st.divider()

# ── PAGE: PRONOSTICS ─────────────────────────────────────────────────────────
elif page == "pronostics":
    st.markdown("<div class='page-header'><h1>🎯 Pronostics</h1></div>", unsafe_allow_html=True)
    st.caption(f"Connecté : **{current_user}**")

    comps = get_all_competitions()
    if not comps:
        st.info("Aucune compétition disponible.")
    else:
        for c in comps:
            with st.expander(f"🏟️ {c['name']} — {fmt(c['date'])}"):
                with db() as conn:
                    cur = conn.cursor()
                    cur.execute("""
                        SELECT a.id, a.first_name, a.last_name, ca.discipline, p.prediction, pb.pb
                        FROM competition_athletes ca
                        JOIN athletes a ON a.id = ca.athlete_id
                        LEFT JOIN predictions p ON p.athlete_id=a.id AND p.competition_id=%s AND p.username=%s
                        LEFT JOIN athlete_pbs pb ON pb.athlete_id=a.id AND pb.discipline=ca.discipline
                        WHERE ca.competition_id=%s
                    """, (c["id"], current_user, c["id"]))
                    ath = rows_to_dicts(cur.fetchall())

                if not ath:
                    st.warning("Aucun athlète dans cette compétition.")
                    continue

                with st.form(f"prono_{c['id']}"):
                    predictions = {}
                    for a in ath:
                        val = float(a["prediction"]) if a["prediction"] is not None else 0.0
                        # Mobile layout: athlete name + discipline on top, then PB + input side by side
                        st.markdown(f"**{a['first_name']} {a['last_name']}** · 🏅 `{a['discipline'] or '—'}`")
                        col_pb, col_input = st.columns(2)
                        if a["pb"] is not None:
                            col_pb.metric("PB", f"{a['pb']:.2f}")
                        else:
                            col_pb.caption("Pas de PB")
                        predictions[a["id"]] = col_input.number_input(
                            "Pronostic", value=val, min_value=0.0, step=0.01,
                            key=f"prono_{c['id']}_{a['id']}"
                        )
                        st.divider()

                    if st.form_submit_button("💾 Sauvegarder mes pronostics", use_container_width=True):
                        with db() as conn:
                            cur = conn.cursor()
                            cur.executemany("""
                                INSERT INTO predictions (username,competition_id,athlete_id,prediction)
                                VALUES (%s,%s,%s,%s)
                                ON CONFLICT (username,competition_id,athlete_id) DO UPDATE SET prediction=EXCLUDED.prediction
                            """, [(current_user, c["id"], aid, pred) for aid, pred in predictions.items()])
                        invalidate_cache()
                        st.success("✅ Pronostics enregistrés !")
                        st.rerun()

# ── PAGE: RÉSULTATS ──────────────────────────────────────────────────────────
elif page == "resultats":
    st.markdown("<div class='page-header'><h1>📊 Résultats</h1></div>", unsafe_allow_html=True)

    comps = get_all_competitions()
    if not comps:
        st.info("Aucune compétition disponible.")
    else:
        for c in comps:
            with st.expander(f"🏟️ {c['name']} — {fmt(c['date'])}"):
                with db() as conn:
                    cur = conn.cursor()
                    cur.execute("""
                        SELECT a.id, a.first_name, a.last_name, ca.discipline, r.result
                        FROM competition_athletes ca
                        JOIN athletes a ON a.id=ca.athlete_id
                        LEFT JOIN results r ON r.athlete_id=a.id AND r.competition_id=%s
                        WHERE ca.competition_id=%s ORDER BY a.last_name
                    """, (c["id"], c["id"]))
                    ath = rows_to_dicts(cur.fetchall())

                if not ath:
                    st.warning("Aucun athlète dans cette compétition.")
                    continue

                with st.form(f"result_{c['id']}"):
                    results = {}
                    for a in ath:
                        val = float(a["result"]) if a["result"] is not None else 0.0
                        status = f" ✅ ({a['result']})" if a["result"] is not None else ""
                        st.markdown(f"**{a['first_name']} {a['last_name']}** · `{a['discipline'] or '—'}`{status}")
                        results[a["id"]] = st.number_input(
                            "Résultat", value=val, min_value=0.0, step=0.01,
                            key=f"res_{c['id']}_{a['id']}"
                        )

                    if st.form_submit_button("💾 Enregistrer les résultats", use_container_width=True):
                        with db() as conn:
                            cur = conn.cursor()
                            cur.executemany("""
                                INSERT INTO results (competition_id,athlete_id,result)
                                VALUES (%s,%s,%s)
                                ON CONFLICT (competition_id,athlete_id) DO UPDATE SET result=EXCLUDED.result
                            """, [(c["id"], aid, res) for aid, res in results.items() if res > 0])
                        invalidate_cache()
                        st.success("✅ Résultats enregistrés !")
                        st.rerun()

# ── PAGE: HISTORIQUE ─────────────────────────────────────────────────────────
elif page == "historique":
    st.markdown("<div class='page-header'><h1>📜 Historique</h1></div>", unsafe_allow_html=True)

    comps = get_all_competitions()
    hist  = get_historique_data()

    if not comps:
        st.info("Aucune compétition disponible.")
    else:
        for c in comps:
            with st.expander(f"🏟️ {c['name']} — {fmt(c['date'])}"):
                rows = hist.get(c["id"], [])
                if not rows:
                    st.info("Aucun résultat disponible.")
                    continue
                # Mobile: card-style rows instead of 6-column table
                for row in rows:
                    pts = score(row["prediction"], row["result"])
                    st.markdown(
                        f"**{row['username']}** · {row['first_name']} {row['last_name']} · `{row['discipline'] or '—'}`  \n"
                        f"Prono: `{row['prediction']:.2f}` · Résultat: `{row['result']:.2f}` · "
                        f"<span class='score-badge'>{pts} pts</span>",
                        unsafe_allow_html=True
                    )
                    st.divider()

# ── PAGE: CLASSEMENT ─────────────────────────────────────────────────────────
elif page == "classement":
    st.markdown("<div class='page-header'><h1>🏆 Classement</h1></div>", unsafe_allow_html=True)

    all_users, comps_with_results, all_scored_rows = get_classement_data()
    usernames = [u["username"] for u in all_users]

    def compute_scores(rows, exclude_comp_id=None):
        s = {u: 0 for u in usernames}
        for row in rows:
            if exclude_comp_id and row["competition_id"] == exclude_comp_id:
                continue
            s[row["username"]] += score(row["prediction"], row["result"])
        return s

    def ranked(scores_map):
        return {u: i for i, (u, _) in enumerate(sorted(scores_map.items(), key=lambda x: -x[1]), 1)}

    scores_now    = compute_scores(all_scored_rows)
    sorted_scores = sorted(scores_now.items(), key=lambda x: -x[1])
    last_comp     = comps_with_results[-1] if comps_with_results else None

    if last_comp and len(comps_with_results) > 1:
        ranks_before = ranked(compute_scores(all_scored_rows, exclude_comp_id=last_comp["id"]))
        delta_label  = f"vs avant « {last_comp['name']} »"
    elif last_comp:
        ranks_before = {u: 1 for u in usernames}
        delta_label  = f"vs avant « {last_comp['name']} »"
    else:
        ranks_before = None
        delta_label  = None

    if not any(s > 0 for _, s in sorted_scores):
        st.info("Aucun score encore calculé.")
    if delta_label:
        st.caption(f"📊 Évolution {delta_label}")

    CARD_TPL = (
        '<div style="background:{bg};border:2px solid {border};border-radius:14px;'
        'padding:14px 18px;margin-bottom:10px;display:flex;justify-content:space-between;'
        'align-items:center;">'
        '<div style="display:flex;align-items:center;gap:10px;color:{text_color};font-size:1.1em;">'
        '<span style="font-size:1.4em;">{rank_label}</span>'
        '<div><strong style="font-size:1em;">{username}</strong>{me_badge}<br>{delta_html}</div>'
        '</div>'
        '<div style="font-size:1.3em;font-weight:800;color:{pts_color};">{total_score}<br>'
        '<span style="font-size:0.55em;font-weight:500;opacity:0.8;">pts</span></div>'
        '</div>'
    )
    medals = {1: "🥇", 2: "🥈", 3: "🥉"}

    for i, (username, total_score) in enumerate(sorted_scores, 1):
        is_me = username == current_user
        if i == 1:
            bg,border,text_color,rank_label,badge_col = "linear-gradient(135deg,#F9D423 0%,#F7971E 100%)","#E6A817","#3d2000","🥇","#5a3a00"
        elif i == 2:
            bg,border,text_color,rank_label,badge_col = "linear-gradient(135deg,#e0e0e0 0%,#9e9e9e 100%)","#757575","#1a1a1a","🥈","#444444"
        elif i == 3:
            bg,border,text_color,rank_label,badge_col = "linear-gradient(135deg,#cd9b5a 0%,#8B5e2a 100%)","#7a4f22","#fff0e0","🥉","#c8a07a"
        else:
            bg         = "#2d3f5e" if is_me else "#1e293b"
            border     = "#FFD700" if is_me else "#334155"
            text_color = "#f1f5f9"
            rank_label = "#" + str(i)
            badge_col  = "#94a3b8"

        pts_color  = "#3d2000" if i==1 else "#1a1a1a" if i==2 else "#fff0e0" if i==3 else "#e94560"
        me_badge   = '<span style="font-size:0.72em;color:{c};margin-left:6px;">(vous)</span>'.format(c=badge_col) if is_me else ""

        if ranks_before is not None:
            prev_rank = ranks_before.get(username, len(usernames))
            delta = prev_rank - i
            if delta > 0:
                delta_html = '<span style="color:#22c55e;font-size:0.82em;font-weight:700;">▲ +{d}</span>'.format(d=delta)
            elif delta < 0:
                delta_html = '<span style="color:#ef4444;font-size:0.82em;font-weight:700;">▼ {d}</span>'.format(d=delta)
            else:
                delta_html = '<span style="color:#94a3b8;font-size:0.82em;">—</span>'
        else:
            delta_html = ""

        st.markdown(CARD_TPL.format(
            bg=bg, border=border, text_color=text_color, rank_label=rank_label,
            username=username, me_badge=me_badge, delta_html=delta_html,
            pts_color=pts_color, total_score=total_score,
        ), unsafe_allow_html=True)

    if last_comp:
        st.divider()
        with st.expander(f"📋 Détail « {last_comp['name']} »"):
            with db() as conn:
                cur = conn.cursor()
                cur.execute("""
                    SELECT p.username,
                           SUM(CASE WHEN ABS(p.prediction-r.result)=0 THEN 300
                               ELSE GREATEST(0,FLOOR(150-ABS(p.prediction-r.result)*4)::int) END) as pts
                    FROM predictions p
                    JOIN results r ON p.competition_id=r.competition_id AND p.athlete_id=r.athlete_id
                    WHERE p.competition_id=%s GROUP BY p.username ORDER BY pts DESC
                """, (last_comp["id"],))
                last_rows = rows_to_dicts(cur.fetchall())
            for j, row in enumerate(last_rows, 1):
                st.write(f"{medals.get(j,'#'+str(j))} **{row['username']}** — {row['pts']} pts")
