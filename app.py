import streamlit as st
import psycopg2
import psycopg2.extras
import psycopg2.pool
from datetime import datetime, date
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

        # ── Tables de base (création initiale) ──────────────────────────────
        cur.execute("""
            CREATE TABLE IF NOT EXISTS users (username TEXT PRIMARY KEY);

            CREATE TABLE IF NOT EXISTS athletes (
                id SERIAL PRIMARY KEY,
                first_name TEXT NOT NULL,
                last_name  TEXT NOT NULL,
                age        INTEGER
            );

            CREATE TABLE IF NOT EXISTS athlete_pbs (
                athlete_id INTEGER,
                discipline TEXT,
                pb         REAL,
                PRIMARY KEY (athlete_id, discipline),
                FOREIGN KEY (athlete_id) REFERENCES athletes(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS competitions (
                id   SERIAL PRIMARY KEY,
                name TEXT NOT NULL,
                date TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS competition_notifications (
                competition_id INTEGER PRIMARY KEY,
                sent_at        TIMESTAMP DEFAULT NOW()
            );
        """)

        # ── Migration 1 : ancienne competition_athletes sans colonne discipline ──
        # On crée la table si elle n'existe pas encore du tout (premier boot propre)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS competition_athletes (
                competition_id INTEGER NOT NULL,
                athlete_id     INTEGER NOT NULL,
                discipline     TEXT,
                PRIMARY KEY (competition_id, athlete_id),
                FOREIGN KEY (competition_id) REFERENCES competitions(id) ON DELETE CASCADE,
                FOREIGN KEY (athlete_id)     REFERENCES athletes(id)     ON DELETE CASCADE
            )
        """)

        # Ajout colonne discipline si absente (très ancienne version)
        cur.execute("""
            SELECT column_name FROM information_schema.columns
            WHERE table_name='competition_athletes' AND column_name='discipline'
        """)
        if not cur.fetchone():
            cur.execute("ALTER TABLE competition_athletes ADD COLUMN discipline TEXT")

        # ── Migration 2 : refonte competition_athletes → multi-discipline ────
        # On détecte si la table a déjà une colonne id SERIAL (nouvelle structure)
        cur.execute("""
            SELECT column_name FROM information_schema.columns
            WHERE table_name='competition_athletes' AND column_name='id'
        """)
        if not cur.fetchone():
            # Nouvelle table avec id SERIAL + UNIQUE (comp, athlete, discipline)
            cur.execute("""
                CREATE TABLE competition_athletes_new (
                    id             SERIAL PRIMARY KEY,
                    competition_id INTEGER NOT NULL,
                    athlete_id     INTEGER NOT NULL,
                    discipline     TEXT,
                    UNIQUE (competition_id, athlete_id, discipline),
                    FOREIGN KEY (competition_id) REFERENCES competitions(id) ON DELETE CASCADE,
                    FOREIGN KEY (athlete_id)     REFERENCES athletes(id)     ON DELETE CASCADE
                )
            """)
            # Copie des données existantes (conserve tout)
            cur.execute("""
                INSERT INTO competition_athletes_new (competition_id, athlete_id, discipline)
                SELECT competition_id, athlete_id, discipline
                FROM competition_athletes
                ON CONFLICT DO NOTHING
            """)
            cur.execute("DROP TABLE competition_athletes")
            cur.execute("ALTER TABLE competition_athletes_new RENAME TO competition_athletes")

        # ── Migration 3 : predictions → ajout colonne discipline ─────────────
        cur.execute("""
            SELECT column_name FROM information_schema.columns
            WHERE table_name='predictions' AND column_name='discipline'
        """)
        if not cur.fetchone():
            # La table n'a pas encore discipline : on la recrée proprement
            cur.execute("""
                CREATE TABLE IF NOT EXISTS predictions (
                    username       TEXT,
                    competition_id INTEGER,
                    athlete_id     INTEGER,
                    prediction     REAL,
                    PRIMARY KEY (username, competition_id, athlete_id),
                    FOREIGN KEY (competition_id) REFERENCES competitions(id) ON DELETE CASCADE
                )
            """)
            cur.execute("ALTER TABLE predictions ADD COLUMN discipline TEXT")
            # Peupler discipline depuis competition_athletes pour les lignes existantes
            cur.execute("""
                UPDATE predictions p
                SET discipline = ca.discipline
                FROM competition_athletes ca
                WHERE ca.competition_id = p.competition_id
                  AND ca.athlete_id     = p.athlete_id
            """)
            # Reconstruire la PK avec discipline
            cur.execute("ALTER TABLE predictions DROP CONSTRAINT IF EXISTS predictions_pkey")
            cur.execute("""
                ALTER TABLE predictions
                ADD PRIMARY KEY (username, competition_id, athlete_id, discipline)
            """)
        else:
            # Table déjà migrée : s'assurer qu'elle existe (premier boot propre)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS predictions (
                    username       TEXT,
                    competition_id INTEGER,
                    athlete_id     INTEGER,
                    discipline     TEXT,
                    prediction     REAL,
                    PRIMARY KEY (username, competition_id, athlete_id, discipline),
                    FOREIGN KEY (competition_id) REFERENCES competitions(id) ON DELETE CASCADE
                )
            """)

        # ── Migration 4 : results → ajout colonne discipline ─────────────────
        cur.execute("""
            SELECT column_name FROM information_schema.columns
            WHERE table_name='results' AND column_name='discipline'
        """)
        if not cur.fetchone():
            cur.execute("""
                CREATE TABLE IF NOT EXISTS results (
                    competition_id INTEGER,
                    athlete_id     INTEGER,
                    result         REAL,
                    PRIMARY KEY (competition_id, athlete_id),
                    FOREIGN KEY (competition_id) REFERENCES competitions(id) ON DELETE CASCADE
                )
            """)
            cur.execute("ALTER TABLE results ADD COLUMN discipline TEXT")
            cur.execute("""
                UPDATE results r
                SET discipline = ca.discipline
                FROM competition_athletes ca
                WHERE ca.competition_id = r.competition_id
                  AND ca.athlete_id     = r.athlete_id
            """)
            cur.execute("ALTER TABLE results DROP CONSTRAINT IF EXISTS results_pkey")
            cur.execute("""
                ALTER TABLE results
                ADD PRIMARY KEY (competition_id, athlete_id, discipline)
            """)
        else:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS results (
                    competition_id INTEGER,
                    athlete_id     INTEGER,
                    discipline     TEXT,
                    result         REAL,
                    PRIMARY KEY (competition_id, athlete_id, discipline),
                    FOREIGN KEY (competition_id) REFERENCES competitions(id) ON DELETE CASCADE
                )
            """)


if "db_initialized" not in st.session_state:
    init_db()
    st.session_state.db_initialized = True


def fmt(d):
    try:
        return datetime.strptime(str(d), "%Y-%m-%d").strftime("%d/%m/%Y")
    except (ValueError, TypeError):
        return str(d) if d else ""


# =========================
# SYSTÈME DE POINTS
# =========================
def score(p, r):
    d = abs(p - r)
    BREAKPOINTS = [
        (0.0,   500),
        (0.01,  250),
        (0.10,  200),
        (0.50,  150),
        (1.00,  100),
        (2.00,   60),
        (10.0,    0),
    ]
    if d <= 0:
        return 500
    for i in range(1, len(BREAKPOINTS)):
        d0, p0 = BREAKPOINTS[i - 1]
        d1, p1 = BREAKPOINTS[i]
        if d <= d1:
            t = (d - d0) / (d1 - d0)
            return max(0, round(p0 + t * (p1 - p0)))
    return 0


def score_label(p, r):
    d = abs(p - r)
    if d == 0:
        return "🎯 PARFAIT !", "#FFD700"
    elif d < 0.01:
        return "⚡ Au centième", "#a78bfa"
    elif d < 0.10:
        return "🔥 Au dixième", "#fb923c"
    elif d < 0.50:
        return "✨ À 0.5s", "#34d399"
    elif d < 1.00:
        return "👍 À 1s", "#60a5fa"
    elif d < 2.00:
        return "📍 À 2s", "#94a3b8"
    else:
        return "💨 Raté", "#475569"


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


# =========================
# CACHE DATA
# =========================
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
    """
    Retourne un dict competition_id -> list[row]
    Chaque row = (competition_id, discipline, id, first_name, last_name)
    Un athlète peut apparaître plusieurs fois si plusieurs disciplines.
    """
    with db() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT ca.competition_id, ca.discipline, a.id, a.first_name, a.last_name
            FROM competition_athletes ca
            JOIN athletes a ON a.id = ca.athlete_id
            ORDER BY ca.competition_id, a.last_name, ca.discipline
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
                   a.first_name, a.last_name, p.discipline,
                   pb.pb AS athlete_pb
            FROM predictions p
            JOIN results r ON  p.competition_id = r.competition_id
                           AND p.athlete_id     = r.athlete_id
                           AND p.discipline     = r.discipline
            JOIN athletes a ON a.id = p.athlete_id
            LEFT JOIN athlete_pbs pb ON pb.athlete_id = p.athlete_id
                                     AND pb.discipline = p.discipline
            ORDER BY p.competition_id, a.last_name, p.discipline, p.username
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
            JOIN results r ON r.competition_id = c.id
            ORDER BY c.date ASC, c.id ASC
        """)
        comps = rows_to_dicts(cur.fetchall())
        cur.execute("""
            SELECT p.username, p.prediction, r.result, p.competition_id
            FROM predictions p
            JOIN results r ON  p.competition_id = r.competition_id
                           AND p.athlete_id     = r.athlete_id
                           AND p.discipline     = r.discipline
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
# AUTH
# =========================
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

    st.markdown("""
    <style>
    .login-title { text-align:center; font-size:3em; margin-bottom:0; color:#f8fafc; }
    .login-subtitle { text-align:center; color:#94a3b8; margin-top:8px; margin-bottom:24px; }
    div.stButton > button {
        background: linear-gradient(135deg, #e94560, #ff2e63);
        color: white; border: none; border-radius: 12px;
        padding: 12px 16px; font-size: 1em; font-weight: 600;
    }
    </style>
    """, unsafe_allow_html=True)

    st.markdown("<h1 class='login-title'>🏃 ATHLÉ BET</h1>", unsafe_allow_html=True)
    st.markdown("<p class='login-subtitle'>Pronostique. Compète. Grimpe au classement.</p>", unsafe_allow_html=True)

    with st.expander("📲 Installer Athlé Bet", expanded=False):
        st.markdown("Ajoute l'app à ton écran d'accueil pour un accès rapide")
        st.markdown("### 🍎 iPhone / iPad")
        st.write("Bouton Partager ⬆ → Sur l'écran d'accueil → Ajouter")
        st.markdown("### 🤖 Android")
        st.write("Menu ⋮ → Ajouter à l'écran d'accueil")
        st.markdown("### 💻 PC / Mac")
        st.write("Icône d'installation dans la barre d'adresse Chrome / Edge")

    u = st.text_input("Ton pseudo", placeholder="Ex: Ticaj (Définitif)")

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

DISCIPLINE_ORDER = ["100m", "200m", "300m", "300mH", "400m", "400mH", "600m"]


def sort_pbs(pbs):
    def sort_key(pb):
        try:
            return DISCIPLINE_ORDER.index(pb["discipline"])
        except ValueError:
            return len(DISCIPLINE_ORDER)
    return sorted(pbs, key=sort_key)


# =========================
# ATHLÈTES
# =========================
if page == "👤 Athlètes":
    st.title("👤 Athlètes")

    with st.expander("➕ Ajouter un athlète", expanded=False):
        with st.form("add_athlete"):
            c1, c2, c3 = st.columns(3)
            fn  = c1.text_input("Prénom")
            ln  = c2.text_input("Nom")
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
                col_info, col_btn = st.columns([8, 1])
                col_info.markdown(f"### {a['first_name']} {a['last_name']}  `{a['age']} ans`")

                if col_btn.button("⚙️", key=f"options_{a['id']}"):
                    current = st.session_state.get(f"panel_{a['id']}", False)
                    st.session_state[f"panel_{a['id']}"] = not current

                if st.session_state.get(f"panel_{a['id']}"):
                    with st.container():
                        st.markdown("""
                        <div style="background:#1e293b;border:1px solid #334155;border-radius:12px;padding:16px 20px;margin-bottom:12px;">
                        """, unsafe_allow_html=True)

                        with st.form(f"edit_form_{a['id']}"):
                            st.markdown("##### ✏️ Modifier l'athlète")
                            ef1, ef2, ef3 = st.columns(3)
                            new_fn  = ef1.text_input("Prénom", value=a["first_name"])
                            new_ln  = ef2.text_input("Nom",    value=a["last_name"])
                            new_age = ef3.number_input("Âge", min_value=10, max_value=100, value=int(a["age"]))
                            st.markdown("---")
                            s1, s2, s3 = st.columns([2, 2, 1])
                            saved   = s1.form_submit_button("💾 Enregistrer", use_container_width=True)
                            closed  = s2.form_submit_button("✖ Fermer",       use_container_width=True)
                            deleted = s3.form_submit_button("🗑️",             use_container_width=True)

                            if saved:
                                if new_fn.strip() and new_ln.strip():
                                    with db() as conn:
                                        cur = conn.cursor()
                                        cur.execute(
                                            "UPDATE athletes SET first_name=%s, last_name=%s, age=%s WHERE id=%s",
                                            (new_fn.strip(), new_ln.strip(), new_age, a["id"])
                                        )
                                    invalidate_cache()
                                    st.session_state[f"panel_{a['id']}"] = False
                                    st.success("✅ Athlète mis à jour !")
                                    st.rerun()
                                else:
                                    st.error("Prénom et nom requis.")
                            if closed:
                                st.session_state[f"panel_{a['id']}"] = False
                                st.rerun()
                            if deleted:
                                st.session_state[f"confirm_del_{a['id']}"] = True

                        st.markdown("</div>", unsafe_allow_html=True)

                    if st.session_state.get(f"confirm_del_{a['id']}"):
                        st.warning(f"⚠️ Supprimer **{a['first_name']} {a['last_name']}** ? Cette action est irréversible.")
                        cd1, cd2 = st.columns(2)
                        if cd1.button("✅ Oui, supprimer", key=f"yes_{a['id']}", use_container_width=True):
                            with db() as conn:
                                cur = conn.cursor()
                                cur.execute("DELETE FROM athletes WHERE id=%s", (a["id"],))
                            invalidate_cache()
                            st.session_state.pop(f"panel_{a['id']}", None)
                            st.session_state.pop(f"confirm_del_{a['id']}", None)
                            st.rerun()
                        if cd2.button("❌ Annuler", key=f"no_{a['id']}", use_container_width=True):
                            st.session_state[f"confirm_del_{a['id']}"] = False
                            st.rerun()

                pbs = sort_pbs(all_pbs.get(a["id"], []))
                if pbs:
                    pb_cols = st.columns(min(len(pbs), 4))
                    for i, pb in enumerate(pbs):
                        pb_cols[i % 4].metric(pb["discipline"], pb["pb"])

                if st.button("✏️ Gérer les PBs", key=f"edit_pb_{a['id']}"):
                    st.session_state[f"show_pb_{a['id']}"] = not st.session_state.get(f"show_pb_{a['id']}", False)

                if st.session_state.get(f"show_pb_{a['id']}"):
                    with st.form(f"pb_form_{a['id']}"):
                        st.markdown("**PBs existants**")
                        inputs    = []
                        to_delete = []

                        for i, pb in enumerate(pbs):
                            c1, c2, c3 = st.columns([3, 2, 1])
                            d = c1.text_input("Discipline", pb["discipline"], key=f"d_{a['id']}_{i}")
                            v = c2.number_input("PB", value=float(pb["pb"]),  key=f"v_{a['id']}_{i}")
                            if c3.checkbox("🗑️", key=f"del_pb_{a['id']}_{i}"):
                                to_delete.append(pb["discipline"])
                            inputs.append((d, v, pb["discipline"]))

                        st.markdown("**Nouveau PB**")
                        nc1, nc2 = st.columns(2)
                        new_d = nc1.text_input("Discipline", key=f"nd_{a['id']}")
                        new_v = nc2.number_input("PB", 0.0,  key=f"nv_{a['id']}")

                        if st.form_submit_button("💾 Sauvegarder"):
                            with db() as conn:
                                cur = conn.cursor()
                                for orig_d in to_delete:
                                    cur.execute(
                                        "DELETE FROM athlete_pbs WHERE athlete_id=%s AND discipline=%s",
                                        (a["id"], orig_d)
                                    )
                                for d, v, orig_d in inputs:
                                    if orig_d not in to_delete and d.strip():
                                        cur.execute("""
                                            INSERT INTO athlete_pbs (athlete_id,discipline,pb)
                                            VALUES (%s,%s,%s)
                                            ON CONFLICT (athlete_id,discipline)
                                            DO UPDATE SET pb=EXCLUDED.pb
                                        """, (a["id"], d.strip(), v))
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
            date_val = st.date_input("Date")
            options  = {f"{a['first_name']} {a['last_name']}": a["id"] for a in athletes}
            selected = st.multiselect("Athlètes participants", list(options.keys()))
            all_pbs  = get_all_pbs()

            # athlete_disciplines : aid -> list[str]
            athlete_disciplines = {}

            if selected:
                st.markdown("**Disciplines par athlète :**")
                for s in selected:
                    aid = options[s]
                    disc_list = [pb["discipline"] for pb in all_pbs.get(aid, [])]
                    st.markdown(f"**{s}**")

                    if disc_list:
                        chosen_discs = st.multiselect(
                            "Disciplines", disc_list,
                            key=f"disc_multi_{aid}"
                        )
                        add_custom = st.checkbox("➕ Discipline libre", key=f"add_custom_{aid}")
                        if add_custom:
                            custom_disc = st.text_input(
                                f"Discipline libre pour {s}", key=f"disc_custom_{aid}"
                            )
                            if custom_disc.strip():
                                chosen_discs = chosen_discs + [custom_disc.strip()]
                        athlete_disciplines[aid] = chosen_discs
                    else:
                        free = st.text_input("Discipline (aucun PB)", key=f"disc_free_{aid}")
                        athlete_disciplines[aid] = [free.strip()] if free.strip() else []

            if st.button("🏟️ Créer la compétition") and name.strip() and selected:
                if not all(athlete_disciplines.get(options[s]) for s in selected):
                    st.error("⚠️ Veuillez renseigner au moins une discipline pour chaque athlète.")
                else:
                    with db() as conn:
                        cur = conn.cursor()
                        cur.execute(
                            "INSERT INTO competitions (name,date) VALUES (%s,%s) RETURNING id",
                            (name.strip(), date_val.strftime("%Y-%m-%d"))
                        )
                        cid = cur.fetchone()["id"]
                        rows_to_insert = []
                        for s in selected:
                            aid = options[s]
                            for disc in athlete_disciplines[aid]:
                                rows_to_insert.append((cid, aid, disc))
                        cur.executemany(
                            """INSERT INTO competition_athletes (competition_id,athlete_id,discipline)
                               VALUES (%s,%s,%s)
                               ON CONFLICT (competition_id,athlete_id,discipline) DO NOTHING""",
                            rows_to_insert
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
        # Compter les athlètes uniques (pas les lignes discipline)
        def count_unique_athletes(ca_rows):
            return len(set(r["id"] for r in ca_rows))

        st.markdown(f"**{len(comps)} compétition(s)**")
        for c in comps:
            ca_rows = comp_athletes.get(c["id"], [])
            n_athletes = count_unique_athletes(ca_rows)
            col1, col2 = st.columns([5, 1])
            col1.markdown(f"**{c['name']}** — {fmt(c['date'])}  `{n_athletes} athlète(s)`")
            if col2.button("🗑️", key=f"delcomp_{c['id']}", help="Supprimer"):
                st.session_state[f"confirm_delcomp_{c['id']}"] = True

            # Bouton édition
            if st.button("⚙️", key=f"editcomp_{c['id']}"):
                st.session_state[f"show_editcomp_{c['id']}"] = not st.session_state.get(
                    f"show_editcomp_{c['id']}", False
                )

            if st.session_state.get(f"show_editcomp_{c['id']}"):
                all_athletes_list = get_all_athletes()
                all_pbs = get_all_pbs()

                # Reconstruire : aid -> list[discipline] depuis ca_rows
                existing_disc_by_aid = {}
                for r in ca_rows:
                    existing_disc_by_aid.setdefault(r["id"], [])
                    if r["discipline"]:
                        existing_disc_by_aid[r["id"]].append(r["discipline"])

                athlete_map = {
                    f"{a['first_name']} {a['last_name']}": a["id"]
                    for a in all_athletes_list
                }

                # Athlètes déjà dans la compétition (dédupliqués)
                existing_names = list(dict.fromkeys(
                    f"{r['first_name']} {r['last_name']}" for r in ca_rows
                ))

                with st.form(f"edit_comp_form_{c['id']}"):
                    st.markdown("### ✏️ Modifier les participants")

                    selected_athletes = st.multiselect(
                        "Athlètes participants",
                        options=list(athlete_map.keys()),
                        default=existing_names,
                        key=f"multi_edit_{c['id']}"
                    )

                    disciplines = {}  # aid -> list[str]

                    if selected_athletes:
                        st.markdown("### 🏅 Disciplines")
                        for athlete_name in selected_athletes:
                            aid = athlete_map[athlete_name]
                            current_discs = existing_disc_by_aid.get(aid, [])
                            pb_disciplines = [pb["discipline"] for pb in all_pbs.get(aid, [])]

                            st.markdown(f"**{athlete_name}**")

                            if pb_disciplines:
                                chosen = st.multiselect(
                                    "Disciplines",
                                    pb_disciplines + ["✏️ Discipline libre"],
                                    default=[
                                        d for d in current_discs
                                        if d in pb_disciplines
                                    ],
                                    key=f"edit_disc_{c['id']}_{aid}"
                                )
                                
                                final_discs = []
                                
                                for d in chosen:
                                
                                    if d == "✏️ Discipline libre":
                                
                                        custom_val = st.text_input(
                                            f"Discipline libre pour {athlete_name}",
                                            value=next(
                                                (
                                                    x for x in current_discs
                                                    if x not in pb_disciplines
                                                ),
                                                ""
                                            ),
                                            key=f"custom_disc_{c['id']}_{aid}"
                                        )
                                
                                        if custom_val.strip():
                                            final_discs.append(custom_val.strip())
                                
                                    else:
                                        final_discs.append(d)
                                
                                disciplines[aid] = final_discs
                            else:
                                free_val = ", ".join(current_discs)
                                free = st.text_input(
                                    "Discipline(s) (séparées par virgule)",
                                    value=free_val,
                                    key=f"free_disc_{c['id']}_{aid}"
                                )
                                disciplines[aid] = [d.strip() for d in free.split(",") if d.strip()]

                    save_changes = st.form_submit_button(
                        "💾 Sauvegarder les modifications", use_container_width=True
                    )

                    if save_changes:
                    
                        missing_custom = False
                    
                        for athlete_name in selected_athletes:
                    
                            aid = athlete_map[athlete_name]
                    
                            selected_discs = st.session_state.get(
                                f"edit_disc_{c['id']}_{aid}",
                                []
                            )
                    
                            if "✏️ Discipline libre" in selected_discs:
                    
                                custom_val = st.session_state.get(
                                    f"custom_disc_{c['id']}_{aid}",
                                    ""
                                )
                    
                                if not custom_val.strip():
                                    missing_custom = True
                    
                        if missing_custom:
                            st.warning(
                                "⚠️ Une discipline libre a été sélectionnée. "
                                "Le champ est maintenant affiché : remplissez-le puis cliquez à nouveau sur sauvegarder."
                            )
                            st.stop()
                    
                        rows_to_insert = []
                    
                        for name_str in selected_athletes:
                    
                            aid = athlete_map[name_str]
                    
                            for disc in disciplines.get(aid, []):
                    
                                rows_to_insert.append((c["id"], aid, disc))
                    
                        with db() as conn:
                            cur = conn.cursor()
                    
                            cur.execute(
                                "DELETE FROM competition_athletes WHERE competition_id=%s",
                                (c["id"],)
                            )
                    
                            if rows_to_insert:
                                cur.executemany("""
                                    INSERT INTO competition_athletes
                                        (competition_id, athlete_id, discipline)
                                    VALUES (%s, %s, %s)
                                    ON CONFLICT
                                    (competition_id, athlete_id, discipline)
                                    DO NOTHING
                                """, rows_to_insert)
                    
                        invalidate_cache()
                    
                        st.success("✅ Compétition mise à jour !")
                    
                        st.session_state[f"show_editcomp_{c['id']}"] = False
                    
                        st.rerun()
                        for name_str in selected_athletes:
                            aid = athlete_map[name_str]
                            for disc in disciplines.get(aid, []):
                                rows_to_insert.append((c["id"], aid, disc))

                        with db() as conn:
                            cur = conn.cursor()
                            cur.execute(
                                "DELETE FROM competition_athletes WHERE competition_id=%s",
                                (c["id"],)
                            )
                            if rows_to_insert:
                                cur.executemany("""
                                    INSERT INTO competition_athletes
                                        (competition_id, athlete_id, discipline)
                                    VALUES (%s, %s, %s)
                                    ON CONFLICT (competition_id, athlete_id, discipline) DO NOTHING
                                """, rows_to_insert)

                        invalidate_cache()
                        st.success("✅ Compétition mise à jour !")
                        st.session_state[f"show_editcomp_{c['id']}"] = False
                        st.rerun()

            # Résumé des participants avec disciplines
            if ca_rows:
                # Regrouper par athlète pour affichage compact
                athlete_summary = {}
                for r in ca_rows:
                    key = f"{r['first_name']} {r['last_name']}"
                    athlete_summary.setdefault(key, [])
                    if r["discipline"]:
                        athlete_summary[key].append(r["discipline"])
                summary_parts = []
                for name_str, discs in athlete_summary.items():
                    discs_str = " · ".join(f"`{d}`" for d in discs) if discs else "`—`"
                    summary_parts.append(f"{name_str} {discs_str}")
                st.caption("  ".join(summary_parts))

            if st.session_state.get(f"confirm_delcomp_{c['id']}"):
                st.warning(f"⚠️ Supprimer **{c['name']}** et toutes ses données ?")
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

    with st.expander("📐 Système de points", expanded=False):
        st.markdown("""
        | Précision | Points |
        |-----------|--------|
        | 🎯 Chrono exacte | **500 pts** |
        | ⚡ Au centième (< 0.01s) | **250 pts** |
        | 🔥 Au dixième (< 0.10s) | **200 pts** |
        | ✨ À la demi-seconde (< 0.50s) | **150 pts** |
        | 👍 À la seconde (< 1.00s) | **100 pts** |
        | 📍 Dans les 2 secondes (< 2.00s) | **60 pts** |
        | 💨 Au-delà | **0–40 pts** (dégressif) |
        """)

    comps = get_all_competitions()
    today = date.today()

    if not comps:
        st.info("Aucune compétition disponible.")
    else:
        for c in comps:
            try:
                comp_date = datetime.strptime(str(c["date"]), "%Y-%m-%d").date()
            except (ValueError, TypeError):
                comp_date = None

            is_locked = comp_date is not None and comp_date < today

            with st.expander(
                f"🏟️ {c['name']} — {fmt(c['date'])}" + (" 🔒" if is_locked else "")
            ):
                if is_locked:
                    if comp_date == today:
                        st.markdown("""
                        <div style="background:linear-gradient(135deg,#7c2d12,#991b1b);
                            border:1px solid #dc2626;border-radius:10px;padding:14px 18px;margin-bottom:14px;">
                            <span style="font-size:1.1em;font-weight:700;color:#fca5a5;">
                                🔒 Pronostics fermés — La compétition a lieu aujourd'hui !
                            </span><br>
                            <span style="color:#fecaca;font-size:0.9em;">
                                Les pronostics sont verrouillés le jour de la compétition.
                            </span>
                        </div>
                        """, unsafe_allow_html=True)
                    else:
                        st.markdown("""
                        <div style="background:linear-gradient(135deg,#1e1b4b,#312e81);
                            border:1px solid #4338ca;border-radius:10px;padding:14px 18px;margin-bottom:14px;">
                            <span style="font-size:1.1em;font-weight:700;color:#a5b4fc;">
                                🔒 Compétition terminée — Pronostics clôturés
                            </span>
                        </div>
                        """, unsafe_allow_html=True)

                # Une ligne par (athlète, discipline)
                with db() as conn:
                    cur = conn.cursor()
                    cur.execute("""
                        SELECT a.id, a.first_name, a.last_name, ca.discipline,
                               p.prediction, pb.pb
                        FROM competition_athletes ca
                        JOIN athletes a ON a.id = ca.athlete_id
                        LEFT JOIN predictions p
                            ON  p.athlete_id     = a.id
                            AND p.competition_id = %s
                            AND p.username       = %s
                            AND p.discipline     = ca.discipline
                        LEFT JOIN athlete_pbs pb
                            ON  pb.athlete_id  = a.id
                            AND pb.discipline  = ca.discipline
                        WHERE ca.competition_id = %s
                        ORDER BY a.last_name, ca.discipline
                    """, (c["id"], current_user, c["id"]))
                    ath = rows_to_dicts(cur.fetchall())

                if not ath:
                    st.warning("Aucun athlète dans cette compétition.")
                    continue

                if is_locked:
                    st.markdown("**Tes pronostics enregistrés :**")
                    for a in ath:
                        col_name, col_disc, col_pb, col_pred = st.columns([3, 2, 2, 2])
                        col_name.markdown(f"**{a['first_name']} {a['last_name']}**")
                        col_disc.markdown(f"🏅 `{a['discipline'] or '—'}`")
                        if a["pb"] is not None:
                            col_pb.metric("PB", f"{a['pb']:.2f}")
                        else:
                            col_pb.caption("Pas de PB")
                        if a["prediction"] is not None:
                            col_pred.metric("Mon prono", f"{a['prediction']:.2f}")
                        else:
                            col_pred.caption("Pas de prono")
                else:
                    with st.form(f"prono_{c['id']}"):
                        st.markdown("**Entrez vos pronostics :**")
                        # predictions : (aid, discipline) -> float
                        predictions = {}
                        for a in ath:
                            val = float(a["prediction"]) if a["prediction"] is not None else 0.0
                            col_name, col_disc, col_pb, col_input = st.columns([3, 2, 2, 2])
                            col_name.markdown(f"**{a['first_name']} {a['last_name']}**")
                            col_disc.markdown(f"🏅 `{a['discipline'] or '—'}`")
                            if a["pb"] is not None:
                                col_pb.metric("PB", f"{a['pb']:.2f}")
                            else:
                                col_pb.caption("Pas de PB")
                            key = (a["id"], a["discipline"] or "")
                            predictions[key] = col_input.number_input(
                                "Prono", value=val, min_value=0.0, step=0.01,
                                key=f"prono_{c['id']}_{a['id']}_{a['discipline']}"
                            )

                        if st.form_submit_button(
                            "💾 Sauvegarder tous mes pronostics", use_container_width=True
                        ):
                            with db() as conn:
                                cur = conn.cursor()
                                cur.executemany("""
                                    INSERT INTO predictions
                                        (username, competition_id, athlete_id, discipline, prediction)
                                    VALUES (%s, %s, %s, %s, %s)
                                    ON CONFLICT (username, competition_id, athlete_id, discipline)
                                    DO UPDATE SET prediction = EXCLUDED.prediction
                                """, [
                                    (current_user, c["id"], aid, disc, pred)
                                    for (aid, disc), pred in predictions.items()
                                ])
                            invalidate_cache()
                            st.success("✅ Pronostics enregistrés !")
                            st.rerun()


# =========================
# RÉSULTATS
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
                        JOIN athletes a ON a.id = ca.athlete_id
                        LEFT JOIN results r
                            ON  r.athlete_id     = a.id
                            AND r.competition_id = %s
                            AND r.discipline     = ca.discipline
                        WHERE ca.competition_id = %s
                        ORDER BY a.last_name, ca.discipline
                    """, (c["id"], c["id"]))
                    ath = rows_to_dicts(cur.fetchall())

                if not ath:
                    st.warning("Aucun athlète dans cette compétition.")
                    continue

                with st.form(f"result_{c['id']}"):
                    st.markdown("**Résultats officiels :**")
                    results = {}  # (aid, discipline) -> float

                    for a in ath:
                        val = float(a["result"]) if a["result"] is not None else 0.0
                        label = f"{a['first_name']} {a['last_name']}  [{a['discipline'] or '—'}]"
                        if a["result"] is not None:
                            label += f"  ✅ (actuel: {a['result']})"

                        key = (a["id"], a["discipline"] or "")
                        results[key] = st.number_input(
                            label, value=val, min_value=0.0, step=0.01,
                            key=f"res_{c['id']}_{a['id']}_{a['discipline']}"
                        )

                    if st.form_submit_button(
                        "💾 Enregistrer les résultats", use_container_width=True
                    ):
                        pb_updates = []
                        should_notify = False

                        with db() as conn:
                            cur = conn.cursor()

                            cur.executemany("""
                                INSERT INTO results
                                    (competition_id, athlete_id, discipline, result)
                                VALUES (%s, %s, %s, %s)
                                ON CONFLICT (competition_id, athlete_id, discipline)
                                DO UPDATE SET result = EXCLUDED.result
                            """, [
                                (c["id"], aid, disc, res)
                                for (aid, disc), res in results.items()
                                if res > 0
                            ])

                            for a in ath:
                                disc = a["discipline"] or ""
                                res_val = results.get((a["id"], disc), 0.0)
                                if res_val <= 0 or not disc:
                                    continue
                                updated, old_pb, new_pb = maybe_update_pb(
                                    cur, a["id"], disc, res_val
                                )
                                if updated:
                                    name_str = f"{a['first_name']} {a['last_name']}"
                                    if old_pb is None:
                                        pb_updates.append(
                                            f"🆕 **{name_str}** — Premier PB en {disc} : **{new_pb:.2f}**"
                                        )
                                    else:
                                        pb_updates.append(
                                            f"🏅 **{name_str}** — Nouveau PB en {disc} : {old_pb:.2f} → **{new_pb:.2f}**"
                                        )

                            cur.execute(
                                "SELECT 1 FROM competition_notifications WHERE competition_id=%s",
                                (c["id"],)
                            )
                            already_sent = cur.fetchone()
                            if not already_sent:
                                should_notify = True
                                cur.execute(
                                    "INSERT INTO competition_notifications (competition_id) VALUES (%s)",
                                    (c["id"],)
                                )

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

    st.markdown("""
    <style>
    .hist-athlete-block {
        background: #0f172a; border: 1px solid #1e293b;
        border-radius: 14px; padding: 16px 20px; margin-bottom: 14px;
    }
    .hist-athlete-name {
        font-size: 1.05em; font-weight: 700; color: #f1f5f9; margin-bottom: 10px;
    }
    .hist-discipline-tag {
        background: #1e293b; color: #94a3b8; border-radius: 6px;
        padding: 2px 8px; font-size: 0.8em; margin-left: 8px; font-weight: 500;
    }
    </style>
    """, unsafe_allow_html=True)

    comps = get_all_competitions()
    hist  = get_historique_data()

    if not comps:
        st.info("Aucune compétition disponible.")
    else:
        for c in comps:
            with st.expander(f"🏟️ {c['name']} — {fmt(c['date'])}"):
                rows = hist.get(c["id"], [])
                if not rows:
                    st.info("Aucun résultat disponible pour cette compétition.")
                    continue

                # Regrouper par (athlète, discipline, résultat)
                athletes_data = {}
                for row in rows:
                    key = (row["first_name"], row["last_name"], row["discipline"], row["result"])
                    if key not in athletes_data:
                        athletes_data[key] = {
                            "result":     row["result"],
                            "discipline": row["discipline"],
                            "first_name": row["first_name"],
                            "last_name":  row["last_name"],
                            "athlete_pb": row.get("athlete_pb"),
                            "pronos": []
                        }
                    athletes_data[key]["pronos"].append({
                        "username":   row["username"],
                        "prediction": row["prediction"]
                    })

                # Stats globales
                all_scores_comp = [score(r["prediction"], r["result"]) for r in rows]
                total_pronos  = len(rows)
                perfect_count = sum(1 for r in rows if abs(r["prediction"] - r["result"]) == 0)
                avg_pts       = sum(all_scores_comp) / len(all_scores_comp) if all_scores_comp else 0

                stat_cols = st.columns(3)
                stat_cols[0].metric("🎽 Pronostics", total_pronos)
                stat_cols[1].metric("🎯 Exactitudes", perfect_count)
                stat_cols[2].metric("📊 Moy. pts", f"{avg_pts:.0f}")
                st.markdown("---")

                for (fn, ln, disc, result), data in athletes_data.items():
                    athlete_pb = data.get("athlete_pb")
                    higher = is_higher_better(disc or "")
                    is_pb  = False
                    if athlete_pb is not None:
                        is_pb = (result >= float(athlete_pb)) if higher else (result <= float(athlete_pb))

                    result_color = "#22c55e" if is_pb else "#e94560"
                    pb_badge = ""
                    if is_pb:
                        pb_badge = "<span style='background:#14532d;color:#86efac;border-radius:8px;padding:2px 10px;font-size:0.78em;font-weight:700;margin-left:10px;'>🏅 PB</span>"
                    elif athlete_pb is not None:
                        diff_from_pb = abs(result - float(athlete_pb))
                        sign = "+" if (
                            (not higher and result > float(athlete_pb)) or
                            (higher and result < float(athlete_pb))
                        ) else "-" if diff_from_pb > 0 else ""
                        pb_badge = f"<span style='background:#1e293b;color:#64748b;border-radius:8px;padding:2px 10px;font-size:0.78em;font-weight:600;margin-left:10px;'>{sign}{diff_from_pb:.2f}s du PB ({float(athlete_pb):.2f})</span>"

                    st.markdown(f"""
                    <div class='hist-athlete-block'>
                        <div class='hist-athlete-name'>
                            🏃 {fn} {ln}
                            <span class='hist-discipline-tag'>{disc or '—'}</span>
                        </div>
                        <div style='margin-bottom:10px;'>
                            <span style='color:#94a3b8;font-size:0.85em;'>RÉSULTAT OFFICIEL</span><br>
                            <span style='font-family:"Bebas Neue",sans-serif;font-size:2em;color:{result_color};letter-spacing:1px;'>{result:.2f}</span>
                            <span style='color:#64748b;font-size:0.85em;'>s</span>
                            {pb_badge}
                        </div>
                    </div>
                    """, unsafe_allow_html=True)

                    pronos_sorted = sorted(
                        data["pronos"],
                        key=lambda x: score(x["prediction"], result),
                        reverse=True
                    )

                    for i, prono in enumerate(pronos_sorted):
                        pts  = score(prono["prediction"], result)
                        diff = abs(prono["prediction"] - result)
                        lbl, lbl_color = score_label(prono["prediction"], result)

                        if pts >= 250:
                            pts_bg, pts_color = "linear-gradient(135deg,#854d0e,#ca8a04)", "#fef08a"
                        elif pts >= 150:
                            pts_bg, pts_color = "linear-gradient(135deg,#065f46,#059669)", "#d1fae5"
                        elif pts >= 60:
                            pts_bg, pts_color = "linear-gradient(135deg,#1e3a5f,#2563eb)", "#bfdbfe"
                        else:
                            pts_bg, pts_color = "linear-gradient(135deg,#1e293b,#334155)", "#94a3b8"

                        rank_icon = ["🥇", "🥈", "🥉"][i] if i < 3 else f"#{i+1}"

                        st.markdown(f"""
                        <div style='background:#1e293b;border-radius:10px;padding:10px 14px;
                                    margin-bottom:8px;display:flex;justify-content:space-between;
                                    align-items:center;border:1px solid #334155;'>
                            <div style='display:flex;align-items:center;gap:10px;'>
                                <span style='font-size:1.2em;'>{rank_icon}</span>
                                <div>
                                    <span style='font-weight:700;color:#f1f5f9;font-size:1em;'>{prono['username']}</span>
                                    <br>
                                    <span style='color:#94a3b8;font-size:0.82em;'>Prono : </span>
                                    <span style='color:#60a5fa;font-weight:700;font-size:0.95em;'>{prono['prediction']:.2f}s</span>
                                    <span style='color:#475569;font-size:0.8em;'> · écart : {diff:.2f}s</span>
                                    <span style='background:{lbl_color}22;color:{lbl_color};border-radius:6px;
                                               padding:1px 8px;font-size:0.78em;font-weight:600;margin-left:6px;'>
                                        {lbl}
                                    </span>
                                </div>
                            </div>
                            <div style='text-align:right;'>
                                <div style='background:{pts_bg};color:{pts_color};border-radius:16px;
                                           padding:5px 16px;font-weight:800;font-size:1.05em;white-space:nowrap;'>
                                    {pts} pts
                                </div>
                            </div>
                        </div>
                        """, unsafe_allow_html=True)

                    st.markdown("<br>", unsafe_allow_html=True)


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
        return {
            u: i for i, (u, _) in enumerate(
                sorted(scores_map.items(), key=lambda x: -x[1]), 1
            )
        }

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
            bg,border,text_color,rank_label,badge_col = (
                "linear-gradient(135deg,#F9D423 0%,#F7971E 100%)",
                "#E6A817","#3d2000","🥇","#5a3a00"
            )
        elif i == 2:
            bg,border,text_color,rank_label,badge_col = (
                "linear-gradient(135deg,#e0e0e0 0%,#9e9e9e 100%)",
                "#757575","#1a1a1a","🥈","#444444"
            )
        elif i == 3:
            bg,border,text_color,rank_label,badge_col = (
                "linear-gradient(135deg,#cd9b5a 0%,#8B5e2a 100%)",
                "#7a4f22","#fff0e0","🥉","#c8a07a"
            )
        else:
            bg         = "#2d3f5e" if is_me else "#1e293b"
            border     = "#FFD700" if is_me else "#334155"
            text_color = "#f1f5f9"
            rank_label = "#" + str(i)
            badge_col  = "#94a3b8"

        pts_color = "#3d2000" if i==1 else "#1a1a1a" if i==2 else "#fff0e0" if i==3 else "#e94560"
        me_badge  = (
            f'<span style="font-size:0.72em;color:{badge_col};margin-left:6px;">(vous)</span>'
            if is_me else ""
        )

        if ranks_before is not None:
            prev_rank = ranks_before.get(username, len(usernames))
            delta = prev_rank - i
            if delta > 0:
                delta_html = f'<span style="color:#22c55e;font-size:0.88em;font-weight:700;background:rgba(34,197,94,0.15);padding:1px 6px;border-radius:10px;">▲ +{delta}</span>'
            elif delta < 0:
                delta_html = f'<span style="color:#ef4444;font-size:0.88em;font-weight:700;background:rgba(239,68,68,0.15);padding:1px 6px;border-radius:10px;">▼ {delta}</span>'
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
                    SELECT p.username, p.prediction, r.result
                    FROM predictions p
                    JOIN results r ON  p.competition_id = r.competition_id
                                   AND p.athlete_id     = r.athlete_id
                                   AND p.discipline     = r.discipline
                    WHERE p.competition_id = %s
                """, (last_comp["id"],))
                last_raw = rows_to_dicts(cur.fetchall())

            user_pts = {}
            for row in last_raw:
                u = row["username"]
                user_pts[u] = user_pts.get(u, 0) + score(row["prediction"], row["result"])

            last_rows_sorted = sorted(user_pts.items(), key=lambda x: -x[1])
            for j, (uname, pts) in enumerate(last_rows_sorted, 1):
                st.write(f"{medals.get(j,'#'+str(j))} **{uname}** — {pts} pts sur cette compétition")
