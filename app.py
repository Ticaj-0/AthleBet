import streamlit as st
import psycopg2
import psycopg2.extras
import psycopg2.pool
from datetime import datetime
from contextlib import contextmanager
import requests

st.set_page_config(page_title="Athlé Bet", page_icon="🏃", layout="wide")

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Bebas+Neue&family=DM+Sans:wght@400;500;600&display=swap');
html, body, [class*="css"] { font-family: 'DM Sans', sans-serif; }
h1, h2, h3 { font-family: 'Bebas Neue', sans-serif; letter-spacing: 1px; }
section[data-testid="stSidebar"] { background: #0f0f0f; color: white; }
section[data-testid="stSidebar"] * { color: white !important; }
.score-badge { background: #e94560; color: white; border-radius: 20px; padding: 2px 10px; font-size: 0.85em; font-weight: 600; }
.stButton > button { border-radius: 6px; font-family: 'DM Sans', sans-serif; font-weight: 500; }
</style>
""", unsafe_allow_html=True)

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
            CREATE TABLE IF NOT EXISTS competition_notifications (competition_id INTEGER PRIMARY KEY,sent_at TIMESTAMP DEFAULT NOW());
        """)
        cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name='competition_athletes' AND column_name='discipline'")
        if not cur.fetchone():
            cur.execute("ALTER TABLE competition_athletes ADD COLUMN discipline TEXT")

if "db_initialized" not in st.session_state:
    init_db()
    st.session_state.db_initialized = True

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

def send_onesignal_notification(title, message):
    url = "https://onesignal.com/api/v1/notifications"

    payload = {
        "app_id": st.secrets["onesignal"]["app_id"],
        "included_segments": ["All"],
        "headings": {"en": title},
        "contents": {"en": message}
    }

    headers = {
        "Authorization": f"Basic {st.secrets['onesignal']['api_key']}",
        "Content-Type": "application/json"
    }

    requests.post(url, json=payload, headers=headers)
    
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


# ─────────────────────────────────────────────────────────────────────────────
# PB AUTO-UPDATE HELPER
# ─────────────────────────────────────────────────────────────────────────────
HIGHER_IS_BETTER_KEYWORDS = [
    "saut", "hauteur", "longueur", "perche", "triple", "lancer",
    "poids", "disque", "marteau", "javelot", "throw", "jump", "vault"
]

def is_higher_better(discipline: str) -> bool:
    d = discipline.lower()
    return any(kw in d for kw in HIGHER_IS_BETTER_KEYWORDS)

def maybe_update_pb(cur, athlete_id: int, discipline: str, new_result: float):
    """Update the PB if new_result is better than the existing one."""
    cur.execute(
        "SELECT pb FROM athlete_pbs WHERE athlete_id=%s AND discipline=%s",
        (athlete_id, discipline)
    )
    row = cur.fetchone()
    higher = is_higher_better(discipline)

    if row is None:
        cur.execute(
            "INSERT INTO athlete_pbs (athlete_id, discipline, pb) VALUES (%s, %s, %s)",
            (athlete_id, discipline, new_result)
        )
        return True, None, new_result
    else:
        old_pb = float(row["pb"])
        is_better = (new_result > old_pb) if higher else (new_result < old_pb)
        if is_better:
            cur.execute(
                "UPDATE athlete_pbs SET pb=%s WHERE athlete_id=%s AND discipline=%s",
                (new_result, athlete_id, discipline)
            )
            return True, old_pb, new_result
        return False, old_pb, old_pb


# =========================
# AUTH — bloc clean
# =========================
if "user" not in st.session_state:

    # -------------------------
    # Query param login
    # -------------------------
    saved_user = st.query_params.get("u", "")

    if saved_user:
        with db() as conn:
            cur = conn.cursor()
            cur.execute("SELECT 1 FROM users WHERE username = %s", (saved_user,))
            if cur.fetchone():
                st.session_state.user = saved_user
                st.rerun()

    # -------------------------
    # Auto-login via localStorage
    # -------------------------
    st.markdown("""
    <script>
    (function () {
        try {
            var stored = localStorage.getItem('athle_bet_user');
            if (!stored) return;
            var params = new URLSearchParams(window.location.search);
            if (params.get('u') === stored) return;
            params.set('u', stored);
            window.location.search = params.toString();
        } catch (e) {}
    })();
    </script>
    """, unsafe_allow_html=True)

    # =========================
    # CSS GLOBAL (UN SEUL BLOC)
    # =========================
    st.markdown("""
    <style>

    /* INSTALL BANNER */
    .install-banner {
        background: linear-gradient(135deg, #0f172a 0%, #1e1b4b 100%);
        border: 1px solid rgba(99,102,241,0.4);
        border-radius: 16px;
        padding: 18px;
        margin-bottom: 20px;
        color: #e2e8f0;
    }
    .install-title {
        font-size: 1.1em;
        font-weight: 700;
        margin-bottom: 6px;
    }
    .install-sub {
        font-size: 0.85em;
        color: #94a3b8;
        margin-bottom: 14px;
    }
    .step {
        background: rgba(255,255,255,0.05);
        border-radius: 10px;
        padding: 10px;
        margin-bottom: 8px;
        font-size: 0.85em;
    }
    .step strong {
        color: #a5b4fc;
    }

    /* LOGIN */
    .login-container {
        max-width: 520px;
        margin: 40px auto;
        padding: 28px;
        background: linear-gradient(145deg, #0f172a, #111827);
        border: 1px solid #1f2937;
        border-radius: 18px;
        box-shadow: 0 20px 60px rgba(0,0,0,0.4);
    }
    .login-title {
        text-align:center;
        font-size:3em;
        margin-bottom: 0;
        color: #f8fafc;
    }
    .login-subtitle {
        text-align:center;
        color:#94a3b8;
        margin-top: 8px;
        margin-bottom: 24px;
    }
    div.stButton > button {
        background: linear-gradient(135deg, #e94560, #ff2e63);
        color: white;
        border: none;
        border-radius: 12px;
        padding: 12px 16px;
        font-size: 1em;
        font-weight: 600;
        transition: 0.2s ease;
    }
    div.stButton > button:hover {
        transform: translateY(-1px);
        opacity: 0.95;
    }

    </style>
    """, unsafe_allow_html=True)

    # =========================
    # LOGIN CARD
    # =========================
    st.markdown("<h1 class='login-title'>🏃 ATHLÉ BET</h1>", unsafe_allow_html=True)
    st.markdown("<p class='login-subtitle'>Pronostique. Compète. Grimpe au classement.</p>", unsafe_allow_html=True)

    # =========================
    # INSTALL (VERSION EXPANDER)
    # =========================
    with st.expander("📲 Installer Athlé Bet", expanded=False):
        st.markdown("Ajoute l'app à ton écran d'accueil pour un accès rapide")
    
        st.markdown("### 🍎 iPhone / iPad")
        st.write("Bouton Partager ⬆ → Sur l'écran d'accueil → Ajouter")
    
        st.markdown("### 🤖 Android")
        st.write("Menu ⋮ → Ajouter à l'écran d'accueil")
    
        st.markdown("### 💻 PC / Mac")
        st.write("Icône d'installation dans la barre d'adresse Chrome / Edge")
        
    u = st.text_input("Ton pseudo", placeholder="Ex: Ticaj")

    if st.button("▶ Entrer dans l'arène", use_container_width=True):
        if u.strip():
            with db() as conn:
                cur = conn.cursor()
                cur.execute(
                    "INSERT INTO users (username) VALUES (%s) ON CONFLICT DO NOTHING",
                    (u.strip(),)
                )

            st.session_state.user = u.strip()
            st.query_params["u"] = u.strip()

            st.markdown(
                f"<script>localStorage.setItem('athle_bet_user','{u.strip()}');</script>",
                unsafe_allow_html=True
            )

            st.rerun()
        else:
            st.warning("Entre un pseudo")

    st.markdown("</div>", unsafe_allow_html=True)

    st.stop()

current_user = st.session_state.user

# =========================
# SIDEBAR
# =========================
with st.sidebar:
    st.markdown(f"## 👋 {current_user}")
    st.divider()
    page = st.radio("Navigation", [
        "🎯 Pronostics", "🏆 Classement", "📜 Historique",
        "👤 Athlètes", "🏟️ Compétitions", "📊 Résultats",
    ], label_visibility="collapsed")
    st.divider()
    if st.button("🚪 Déconnexion", use_container_width=True):
        del st.session_state.user
        st.query_params.clear()
        st.markdown("<script>localStorage.removeItem('athle_bet_user');</script>", unsafe_allow_html=True)
        st.rerun()

# =========================
# ATHLÈTES
# =========================
if page == "👤 Athlètes":
    st.title("👤 Athlètes")

    # ➕ AJOUT
    with st.expander("➕ Ajouter un athlète", expanded=False):
        with st.form("add_athlete"):
            c1, c2, c3 = st.columns(3)
            fn = c1.text_input("Prénom")
            ln = c2.text_input("Nom")
            age = c3.number_input("Âge", 10, 100, 20)

            if st.form_submit_button("Créer l'athlète", use_container_width=True):
                if fn.strip() and ln.strip():
                    with db() as conn:
                        cur = conn.cursor()
                        cur.execute(
                            "INSERT INTO athletes (first_name, last_name, age) VALUES (%s,%s,%s)",
                            (fn.strip(), ln.strip(), age)
                        )
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
        st.markdown(f"**{len(athletes)} athlète(s) enregistré(s)**")

        for a in athletes:
            with st.container():

                # HEADER
                col_info, col_actions = st.columns([5, 2])
                
                col_info.markdown(f"### {a['first_name']} {a['last_name']}  `{a['age']} ans`")
                
                btn_edit, btn_delete = col_actions.columns(2)
                
                # ✏️ EDIT AGE
                if btn_edit.button("✏️", key=f"edit_age_{a['id']}"):
                    st.session_state[f"edit_age_{a['id']}"] = not st.session_state.get(f"edit_age_{a['id']}", False)
                
                # 🗑️ DELETE
                if btn_delete.button("🗑️", key=f"del_{a['id']}"):
                    st.session_state[f"confirm_del_{a['id']}"] = True

                if st.session_state.get(f"confirm_del_{a['id']}"):
                    st.warning(f"⚠️ Supprimer **{a['first_name']} {a['last_name']}** ?")
                    c1, c2 = st.columns(2)

                    if c1.button("✅ Confirmer", key=f"yes_{a['id']}"):
                        with db() as conn:
                            cur = conn.cursor()
                            cur.execute("DELETE FROM athletes WHERE id=%s", (a['id'],))
                        invalidate_cache()
                        st.rerun()

                    if c2.button("❌ Annuler", key=f"no_{a['id']}"):
                        st.session_state[f"confirm_del_{a['id']}"] = False
                        st.rerun()

                # ✏️ EDIT AGE
                if st.button("✏️ Modifier l'âge", key=f"edit_age_{a['id']}"):
                    st.session_state[f"edit_age_{a['id']}"] = not st.session_state.get(f"edit_age_{a['id']}", False)

                if st.session_state.get(f"edit_age_{a['id']}"):
                    with st.form(f"age_form_{a['id']}"):
                        new_age = st.number_input(
                            "Nouvel âge",
                            min_value=10,
                            max_value=100,
                            value=int(a["age"]),
                            key=f"age_input_{a['id']}"
                        )

                        if st.form_submit_button("💾 Enregistrer"):
                            with db() as conn:
                                cur = conn.cursor()
                                cur.execute(
                                    "UPDATE athletes SET age=%s WHERE id=%s",
                                    (new_age, a["id"])
                                )

                            invalidate_cache()
                            st.session_state[f"edit_age_{a['id']}"] = False
                            st.success("Âge mis à jour !")
                            st.rerun()

                # PB DISPLAY
                pbs = all_pbs.get(a["id"], [])
                if pbs:
                    pb_cols = st.columns(min(len(pbs), 4))
                    for i, pb in enumerate(pbs):
                        pb_cols[i % 4].metric(pb["discipline"], pb["pb"])

                # ✏️ EDIT PB
                if st.button("✏️ Gérer les PBs", key=f"edit_pb_{a['id']}"):
                    st.session_state[f"show_pb_{a['id']}"] = not st.session_state.get(f"show_pb_{a['id']}", False)

                if st.session_state.get(f"show_pb_{a['id']}"):
                    with st.form(f"pb_form_{a['id']}"):

                        st.markdown("**PBs existants**")

                        inputs = []
                        to_delete = []

                        for i, pb in enumerate(pbs):
                            c1, c2, c3 = st.columns([3, 2, 1])

                            d = c1.text_input(
                                "Discipline",
                                pb["discipline"],
                                key=f"d_{a['id']}_{i}"
                            )

                            v = c2.number_input(
                                "PB",
                                value=float(pb["pb"]),
                                key=f"v_{a['id']}_{i}"
                            )

                            if c3.checkbox("🗑️", key=f"del_pb_{a['id']}_{i}"):
                                to_delete.append(pb["discipline"])

                            inputs.append((d, v, pb["discipline"]))

                        st.markdown("**Nouveau PB**")
                        nc1, nc2 = st.columns(2)

                        new_d = nc1.text_input("Discipline", key=f"nd_{a['id']}")
                        new_v = nc2.number_input("PB", 0.0, key=f"nv_{a['id']}")

                        if st.form_submit_button("💾 Sauvegarder"):
                            with db() as conn:
                                cur = conn.cursor()

                                # delete
                                for orig_d in to_delete:
                                    cur.execute(
                                        "DELETE FROM athlete_pbs WHERE athlete_id=%s AND discipline=%s",
                                        (a["id"], orig_d)
                                    )

                                # update
                                for d, v, orig_d in inputs:
                                    if orig_d not in to_delete and d.strip():
                                        cur.execute("""
                                            INSERT INTO athlete_pbs (athlete_id,discipline,pb)
                                            VALUES (%s,%s,%s)
                                            ON CONFLICT (athlete_id,discipline)
                                            DO UPDATE SET pb=EXCLUDED.pb
                                        """, (a["id"], d.strip(), v))

                                # new
                                if new_d.strip():
                                    cur.execute("""
                                        INSERT INTO athlete_pbs (athlete_id,discipline,pb)
                                        VALUES (%s,%s,%s)
                                        ON CONFLICT (athlete_id,discipline)
                                        DO UPDATE SET pb=EXCLUDED.pb
                                    """, (a["id"], new_d.strip(), new_v))

                            invalidate_cache()
                            st.session_state[f"show_pb_{a['id']}"] = False
                            st.success("PBs mis à jour !")
                            st.rerun()

                st.divider()
# =========================
# COMPÉTITIONS
# =========================
elif page == "🏟️ Compétitions":
    st.title("🏟️ Compétitions")

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
                    col_name, col_disc = st.columns([2, 3])
                    col_name.markdown(f"**{s}**")
                    if disc_list:
                        chosen = col_disc.selectbox("Discipline", disc_list + ["✏️ Autre..."], key=f"disc_{aid}")
                        if chosen == "✏️ Autre...":
                            athlete_disciplines[aid] = st.text_input(f"Discipline personnalisée pour {s}", key=f"disc_custom_{aid}")
                        else:
                            athlete_disciplines[aid] = chosen
                    else:
                        athlete_disciplines[aid] = col_disc.text_input("Discipline (aucun PB)", key=f"disc_free_{aid}")

            if st.button("🏟️ Créer la compétition") and name.strip() and selected:
                if not all(athlete_disciplines.get(options[s], "").strip() for s in selected):
                    st.error("⚠️ Veuillez renseigner une discipline pour chaque athlète.")
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
        st.markdown(f"**{len(comps)} compétition(s)**")
        for c in comps:
            ca_rows = comp_athletes.get(c["id"], [])
            col1, col2 = st.columns([5, 1])
            col1.markdown(f"**{c['name']}** — {fmt(c['date'])}  `{len(ca_rows)} athlète(s)`")
            if col2.button("🗑️", key=f"delcomp_{c['id']}", help="Supprimer"):
                st.session_state[f"confirm_delcomp_{c['id']}"] = True
            if ca_rows:
                st.caption("  ".join([f"{r['first_name']} {r['last_name']} `{r['discipline'] or '—'}`" for r in ca_rows]))
            if st.session_state.get(f"confirm_delcomp_{c['id']}"):
                st.warning(f"⚠️ Supprimer **{c['name']}** et tous ses données ?")
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

# =========================
# PRONOSTICS
# =========================
elif page == "🎯 Pronostics":
    st.title("🎯 Mes Pronostics")
    st.caption(f"Connecté en tant que **{current_user}**")

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
                    st.markdown("**Entrez vos pronostics :**")
                    predictions = {}
                    for a in ath:
                        val = float(a["prediction"]) if a["prediction"] is not None else 0.0
                        col_name, col_disc, col_pb, col_input = st.columns([3, 2, 2, 2])
                        col_name.markdown(f"**{a['first_name']} {a['last_name']}**")
                        col_disc.markdown(f"🏅 `{a['discipline'] or '—'}`")
                        if a["pb"] is not None:
                            col_pb.metric("PB", f"{a['pb']:.2f}", delta=None)
                        else:
                            col_pb.caption("Pas de PB")
                        predictions[a["id"]] = col_input.number_input("Prono", value=val, min_value=0.0, step=0.01, key=f"prono_{c['id']}_{a['id']}")

                    if st.form_submit_button("💾 Sauvegarder tous mes pronostics", use_container_width=True):
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

# =========================
# RÉSULTATS (with auto PB update)
# =========================
elif page == "📊 Résultats":
    st.title("📊 Saisie des Résultats")

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
                    st.markdown("**Résultats officiels :**")
                    results = {}
                
                    for a in ath:
                        val = float(a["result"]) if a["result"] is not None else 0.0
                        label = f"{a['first_name']} {a['last_name']}  [{a['discipline'] or '—'}]"
                        if a["result"] is not None:
                            label += f"  ✅ (actuel: {a['result']})"
                
                        results[a["id"]] = st.number_input(
                            label,
                            value=val,
                            min_value=0.0,
                            step=0.01,
                            key=f"res_{c['id']}_{a['id']}"
                        )
                
                    if st.form_submit_button("💾 Enregistrer les résultats", use_container_width=True):
                        pb_updates = []
                        should_notify = False
                
                        with db() as conn:
                            cur = conn.cursor()
                
                            # 1. INSERT / UPDATE résultats
                            cur.executemany("""
                                INSERT INTO results (competition_id, athlete_id, result)
                                VALUES (%s, %s, %s)
                                ON CONFLICT (competition_id, athlete_id)
                                DO UPDATE SET result = EXCLUDED.result
                            """, [
                                (c["id"], aid, res)
                                for aid, res in results.items()
                                if res > 0
                            ])
                
                            # 2. PB update
                            for a in ath:
                                res_val = results.get(a["id"], 0.0)
                
                                if res_val <= 0 or not a["discipline"]:
                                    continue
                
                                updated, old_pb, new_pb = maybe_update_pb(
                                    cur, a["id"], a["discipline"], res_val
                                )
                
                                if updated:
                                    name_str = f"{a['first_name']} {a['last_name']}"
                                    if old_pb is None:
                                        pb_updates.append(
                                            f"🆕 **{name_str}** — Premier PB en {a['discipline']} : **{new_pb:.2f}**"
                                        )
                                    else:
                                        pb_updates.append(
                                            f"🏅 **{name_str}** — Nouveau PB en {a['discipline']} : {old_pb:.2f} → **{new_pb:.2f}**"
                                        )
                
                            # 3. ONE SIGNAL (SAFE + ONCE ONLY)
                            cur.execute("""
                                SELECT 1 FROM competition_notifications WHERE competition_id=%s
                            """, (c["id"],))
                
                            already_sent = cur.fetchone()
                
                            if not already_sent:
                                should_notify = True
                
                                cur.execute("""
                                    INSERT INTO competition_notifications (competition_id)
                                    VALUES (%s)
                                """, (c["id"],))
                
                        # OUTSIDE DB (API call propre)
                        if should_notify:
                            send_onesignal_notification(
                                title="🏟️ Résultats disponibles",
                                message=f"Les résultats de la compétition « {c['name']} » sont maintenant disponibles !"
                            )
                
                        invalidate_cache()
                        st.success("✅ Résultats enregistrés !")
                
                        if pb_updates:
                            st.balloons()
                            st.markdown("### 🎉 Nouveaux PBs !")
                            for msg in pb_updates:
                                st.markdown(msg)
                
                        st.rerun()

# =========================
# HISTORIQUE
# =========================
elif page == "📜 Historique":
    st.title("📜 Historique")

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
                headers = st.columns([2, 2, 2, 1, 1, 1])
                for h, label in zip(headers, ["**Utilisateur**","**Athlète**","**Discipline**","**Prono**","**Résultat**","**Points**"]):
                    h.markdown(label)
                st.divider()
                for row in rows:
                    pts = score(row["prediction"], row["result"])
                    cols = st.columns([2, 2, 2, 1, 1, 1])
                    cols[0].write(row["username"])
                    cols[1].write(f"{row['first_name']} {row['last_name']}")
                    cols[2].write(row["discipline"] or "—")
                    cols[3].write(f"{row['prediction']:.2f}")
                    cols[4].write(f"{row['result']:.2f}")
                    cols[5].markdown(f"<span class='score-badge'>{pts} pts</span>", unsafe_allow_html=True)

# =========================
# CLASSEMENT
# =========================
elif page == "🏆 Classement":
    st.title("🏆 Classement Général")

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
        '<div style="background:{bg};border:2px solid {border};border-radius:12px;'
        'padding:14px 22px;margin-bottom:10px;display:flex;justify-content:space-between;'
        'align-items:center;box-shadow:0 2px 8px rgba(0,0,0,0.18);">'
        '<div style="display:flex;align-items:center;gap:10px;color:{text_color};font-size:1.18em;">'
        '<span style="font-size:1.3em;">{rank_label}</span>'
        '<strong>{username}</strong>{me_badge}{delta_html}'
        '</div>'
        '<div style="font-size:1.25em;font-weight:800;color:{pts_color};">{total_score} pts</div>'
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
                delta_html = '<span style="color:#22c55e;font-size:0.88em;font-weight:700;background:rgba(34,197,94,0.15);padding:1px 6px;border-radius:10px;">▲ +{d}</span>'.format(d=delta)
            elif delta < 0:
                delta_html = '<span style="color:#ef4444;font-size:0.88em;font-weight:700;background:rgba(239,68,68,0.15);padding:1px 6px;border-radius:10px;">▼ {d}</span>'.format(d=delta)
            else:
                delta_html = '<span style="color:#94a3b8;font-size:0.88em;padding:1px 6px;">—</span>'
        else:
            delta_html = ""

        st.markdown(CARD_TPL.format(
            bg=bg, border=border, text_color=text_color, rank_label=rank_label,
            username=username, me_badge=me_badge, delta_html=delta_html,
            pts_color=pts_color, total_score=total_score,
        ), unsafe_allow_html=True)

    if last_comp:
        st.divider()
        with st.expander(f"📋 Détail « {last_comp['name']} » — {fmt(last_comp['date'])}"):
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
                st.write(f"{medals.get(j,'#'+str(j))} **{row['username']}** — {row['pts']} pts sur cette compétition")
