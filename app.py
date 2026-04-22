import streamlit as st
import sqlite3
from datetime import datetime
from contextlib import contextmanager

st.set_page_config(page_title="Athlé Bet", page_icon="🏃", layout="wide")

# =========================
# STYLES
# =========================
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Bebas+Neue&family=DM+Sans:wght@400;500;600&display=swap');

html, body, [class*="css"] {
    font-family: 'DM Sans', sans-serif;
}

h1, h2, h3 {
    font-family: 'Bebas Neue', sans-serif;
    letter-spacing: 1px;
}

section[data-testid="stSidebar"] {
    background: #0f0f0f;
    color: white;
}

section[data-testid="stSidebar"] * {
    color: white !important;
}

.metric-card {
    background: #1a1a2e;
    border-left: 4px solid #e94560;
    border-radius: 8px;
    padding: 16px 20px;
    margin-bottom: 10px;
}

.athlete-card {
    background: #f8f9fa;
    border-radius: 10px;
    padding: 16px;
    margin-bottom: 12px;
    border: 1px solid #e0e0e0;
}

.podium-1 { color: #FFD700; font-weight: 700; font-size: 1.1em; }
.podium-2 { color: #C0C0C0; font-weight: 700; }
.podium-3 { color: #CD7F32; font-weight: 700; }

.score-badge {
    background: #e94560;
    color: white;
    border-radius: 20px;
    padding: 2px 10px;
    font-size: 0.85em;
    font-weight: 600;
}

.stButton > button {
    border-radius: 6px;
    font-family: 'DM Sans', sans-serif;
    font-weight: 500;
}
</style>
""", unsafe_allow_html=True)

# =========================
# DB
# =========================
DB = "app.db"

@contextmanager
def db():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

def init_db():
    with db() as conn:
        conn.execute("PRAGMA foreign_keys = ON")

        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                username TEXT PRIMARY KEY
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS athletes (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                first_name TEXT NOT NULL,
                last_name  TEXT NOT NULL,
                age        INTEGER
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS athlete_pbs (
                athlete_id INTEGER,
                discipline TEXT,
                pb         REAL,
                PRIMARY KEY (athlete_id, discipline),
                FOREIGN KEY (athlete_id) REFERENCES athletes(id) ON DELETE CASCADE
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS competitions (
                id   INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                date TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS predictions (
                username       TEXT,
                competition_id INTEGER,
                athlete_id     INTEGER,
                prediction     REAL,
                PRIMARY KEY (username, competition_id, athlete_id),
                FOREIGN KEY (competition_id) REFERENCES competitions(id) ON DELETE CASCADE
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS results (
                competition_id INTEGER,
                athlete_id     INTEGER,
                result         REAL,
                PRIMARY KEY (competition_id, athlete_id),
                FOREIGN KEY (competition_id) REFERENCES competitions(id) ON DELETE CASCADE
            )
        """)

        cols = {
            row[1] for row in
            conn.execute("PRAGMA table_info(competition_athletes)").fetchall()
        }

        if "competition_id" not in cols:
            conn.execute("""
                CREATE TABLE competition_athletes (
                    competition_id INTEGER,
                    athlete_id     INTEGER,
                    discipline     TEXT,
                    PRIMARY KEY (competition_id, athlete_id),
                    FOREIGN KEY (competition_id) REFERENCES competitions(id) ON DELETE CASCADE,
                    FOREIGN KEY (athlete_id)     REFERENCES athletes(id)     ON DELETE CASCADE
                )
            """)
        elif "discipline" not in cols:
            conn.execute("""
                CREATE TABLE competition_athletes_new (
                    competition_id INTEGER,
                    athlete_id     INTEGER,
                    discipline     TEXT,
                    PRIMARY KEY (competition_id, athlete_id),
                    FOREIGN KEY (competition_id) REFERENCES competitions(id) ON DELETE CASCADE,
                    FOREIGN KEY (athlete_id)     REFERENCES athletes(id)     ON DELETE CASCADE
                )
            """)
            conn.execute("""
                INSERT OR IGNORE INTO competition_athletes_new (competition_id, athlete_id, discipline)
                SELECT competition_id, athlete_id, NULL FROM competition_athletes
            """)
            conn.execute("DROP TABLE competition_athletes")
            conn.execute("ALTER TABLE competition_athletes_new RENAME TO competition_athletes")

init_db()

# =========================
# UTILS
# =========================
def fmt(d):
    try:
        return datetime.strptime(d, "%Y-%m-%d").strftime("%d/%m/%Y")
    except ValueError:
        return d

def score(p, r):
    d = abs(p - r)
    if d == 0:
        return 300
    return max(0, int(150 - d * 4))

def get_all_athletes():
    with db() as conn:
        return conn.execute("SELECT * FROM athletes ORDER BY last_name, first_name").fetchall()

def get_all_competitions():
    with db() as conn:
        return conn.execute("SELECT * FROM competitions ORDER BY date DESC").fetchall()

# =========================
# AUTH + PERSISTANCE SESSION
# =========================
if "user" not in st.session_state:

    saved_user = st.query_params.get("u", "")
    if saved_user:
        with db() as conn:
            exists = conn.execute(
                "SELECT 1 FROM users WHERE username = :username",
                {"username": saved_user}
            ).fetchone()
        if exists:
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

    # --- Popup PWA install ---
    st.markdown("""
<style>
#pwa-popup {
    display: none;
    position: fixed;
    bottom: 28px;
    left: 50%;
    transform: translateX(-50%);
    background: #1e293b;
    color: #f1f5f9;
    border: 1.5px solid #e94560;
    border-radius: 16px;
    padding: 18px 24px;
    z-index: 9999;
    box-shadow: 0 8px 32px rgba(0,0,0,0.4);
    max-width: 370px;
    width: 90vw;
    font-family: 'DM Sans', sans-serif;
    animation: slideUp 0.4s ease;
}
@keyframes slideUp {
    from { opacity:0; transform: translateX(-50%) translateY(30px); }
    to   { opacity:1; transform: translateX(-50%) translateY(0); }
}
#pwa-popup .pwa-title { font-weight:700; font-size:1.05em; margin-bottom:6px; display:flex; align-items:center; gap:8px; }
#pwa-popup .pwa-desc  { font-size:0.88em; color:#94a3b8; margin-bottom:14px; line-height:1.4; }
#pwa-popup .pwa-steps { font-size:0.83em; color:#cbd5e1; margin-bottom:14px; line-height:1.7; }
#pwa-popup .pwa-btn-row { display:flex; gap:10px; justify-content:flex-end; }
#pwa-popup button { border:none; border-radius:8px; padding:7px 16px; font-size:0.88em; font-weight:600; cursor:pointer; font-family:'DM Sans',sans-serif; }
#pwa-install-btn  { background:#e94560; color:white; }
#pwa-dismiss-btn  { background:#334155; color:#94a3b8; }
</style>

<div id="pwa-popup">
    <div class="pwa-title">📲 Installer Athlé Bet</div>
    <div class="pwa-desc">Ajoutez l'app sur votre écran d'accueil pour y accéder comme une vraie application mobile.</div>
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

    var popup   = document.getElementById('pwa-popup');
    var stepsEl = document.getElementById('pwa-steps-text');
    var deferredPrompt = null;
    var ua       = navigator.userAgent;
    var isIOS    = /iphone|ipad|ipod/i.test(ua);
    var isSafari = /^((?!chrome|android).)*safari/i.test(ua);
    var isAndroid = /android/i.test(ua);
    var isChrome  = /chrome/i.test(ua) && !(/edge/i.test(ua));

    if (isIOS && isSafari) {
        stepsEl.innerHTML = '1. Appuyez sur <strong>Partager</strong> (&#9633;↑) dans Safari<br>2. Choisissez <strong>« Sur l\'écran d\'accueil »</strong><br>3. Confirmez avec <strong>Ajouter</strong>';
        document.getElementById('pwa-install-btn').style.display = 'none';
        popup.style.display = 'block';
    } else if (isAndroid && isChrome) {
        window.addEventListener('beforeinstallprompt', function(e) {
            e.preventDefault();
            deferredPrompt = e;
            stepsEl.innerHTML = 'Appuyez sur <strong>Installer</strong> ci-dessous.';
            popup.style.display = 'block';
        });
    } else {
        stepsEl.innerHTML = 'Dans votre navigateur, cherchez l\'icône <strong>⊕</strong> dans la barre d\'adresse ou le menu → <strong>« Installer l\'application »</strong>.';
        popup.style.display = 'block';
    }

    window.triggerInstall = function() {
        if (deferredPrompt) {
            deferredPrompt.prompt();
            deferredPrompt.userChoice.then(function() { deferredPrompt = null; popup.style.display = 'none'; });
        } else { popup.style.display = 'none'; }
    };
    window.dismissPwa = function() {
        popup.style.display = 'none';
        localStorage.setItem('pwa_dismissed', '1');
    };
})();
</script>
""", unsafe_allow_html=True)

    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown("<h1 style='text-align:center; font-size:3em;'>🏃 ATHLÉ BET</h1>", unsafe_allow_html=True)
        st.markdown("<p style='text-align:center; color:#666;'>Pronostique. Compète. Grimpe au classement.</p>", unsafe_allow_html=True)
        st.divider()
        u = st.text_input("Choisis ton pseudo", placeholder="Ex: SpeedDemon42")
        if st.button("▶ Entrer dans l'arène", use_container_width=True) and u.strip():
            with db() as conn:
                conn.execute("INSERT OR IGNORE INTO users VALUES (:username)", {"username": u.strip()})
            st.session_state.user = u.strip()
            st.query_params["u"] = u.strip()
            st.markdown(f"""
<script>localStorage.setItem('athle_bet_user', '{u.strip()}');</script>
""", unsafe_allow_html=True)
            st.rerun()
        if not u and st.session_state.get("_tried"):
            st.warning("Merci d'entrer un pseudo.")
    st.stop()

current_user = st.session_state.user

# =========================
# SIDEBAR
# =========================
with st.sidebar:
    st.markdown(f"## 👋 {current_user}")
    st.divider()

    page = st.radio("Navigation", [
        "🎯 Pronostics",
        "🏆 Classement",
        "📜 Historique",
        "👤 Athlètes",
        "🏟️ Compétitions",
        "📊 Résultats",
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

    with st.expander("➕ Ajouter un athlète", expanded=False):
        with st.form("add_athlete"):
            c1, c2, c3 = st.columns(3)
            fn = c1.text_input("Prénom")
            ln = c2.text_input("Nom")
            age = c3.number_input("Âge", 10, 100, 20)
            submitted = st.form_submit_button("Créer l'athlète", use_container_width=True)
            if submitted:
                if fn.strip() and ln.strip():
                    with db() as conn:
                        conn.execute(
                            "INSERT INTO athletes VALUES (NULL, :fn, :ln, :age)",
                            {"fn": fn.strip(), "ln": ln.strip(), "age": age}
                        )
                    st.success(f"✅ {fn} {ln} ajouté(e) !")
                    st.rerun()
                else:
                    st.error("Prénom et nom requis.")

    st.divider()

    athletes = get_all_athletes()

    if not athletes:
        st.info("Aucun athlète pour l'instant. Ajoutez-en un ci-dessus !")
    else:
        st.markdown(f"**{len(athletes)} athlète(s) enregistré(s)**")

        for a in athletes:
            with st.container():
                col_info, col_btn = st.columns([5, 1])
                with col_info:
                    st.markdown(f"### {a['first_name']} {a['last_name']}  `{a['age']} ans`")

                with col_btn:
                    if st.button("🗑️", key=f"del_{a['id']}", help="Supprimer cet athlète"):
                        st.session_state[f"confirm_del_{a['id']}"] = True

                if st.session_state.get(f"confirm_del_{a['id']}"):
                    st.warning(f"⚠️ Supprimer **{a['first_name']} {a['last_name']}** ? Cette action est irréversible.")
                    cc1, cc2 = st.columns(2)
                    if cc1.button("✅ Confirmer", key=f"yes_{a['id']}"):
                        with db() as conn:
                            conn.execute("PRAGMA foreign_keys = ON")
                            conn.execute("DELETE FROM athletes WHERE id = :id", {"id": a['id']})
                        st.rerun()
                    if cc2.button("❌ Annuler", key=f"no_{a['id']}"):
                        st.session_state[f"confirm_del_{a['id']}"] = False
                        st.rerun()

                with db() as conn:
                    pbs = conn.execute(
                        "SELECT * FROM athlete_pbs WHERE athlete_id = :aid ORDER BY discipline",
                        {"aid": a["id"]}
                    ).fetchall()

                if pbs:
                    pb_cols = st.columns(min(len(pbs), 4))
                    for i, pb in enumerate(pbs):
                        pb_cols[i % 4].metric(pb["discipline"], pb["pb"])

                if st.button("✏️ Gérer les PBs", key=f"edit_{a['id']}"):
                    st.session_state[f"show_pb_{a['id']}"] = not st.session_state.get(f"show_pb_{a['id']}", False)

                if st.session_state.get(f"show_pb_{a['id']}"):
                    with st.form(f"pb_form_{a['id']}"):
                        st.markdown("**PBs existants**")
                        inputs = []
                        to_delete = []
                        for i, pb in enumerate(pbs):
                            c1, c2, c3 = st.columns([3, 2, 1])
                            d = c1.text_input("Discipline", pb["discipline"], key=f"d_{a['id']}_{i}")
                            v = c2.number_input("PB", value=float(pb["pb"]), key=f"v_{a['id']}_{i}")
                            delete = c3.checkbox("🗑️", key=f"del_pb_{a['id']}_{i}", help="Supprimer ce PB")
                            inputs.append((d, v, pb["discipline"]))
                            if delete:
                                to_delete.append(pb["discipline"])

                        st.markdown("**Nouveau PB**")
                        nc1, nc2 = st.columns(2)
                        new_d = nc1.text_input("Discipline", key=f"nd_{a['id']}")
                        new_v = nc2.number_input("PB", 0.0, key=f"nv_{a['id']}")

                        if st.form_submit_button("💾 Sauvegarder"):
                            with db() as conn:
                                for orig_discipline in to_delete:
                                    conn.execute(
                                        "DELETE FROM athlete_pbs WHERE athlete_id = :aid AND discipline = :disc",
                                        {"aid": a["id"], "disc": orig_discipline}
                                    )
                                for d, v, orig_d in inputs:
                                    if orig_d not in to_delete and d.strip():
                                        conn.execute(
                                            "INSERT OR REPLACE INTO athlete_pbs VALUES (:aid, :disc, :pb)",
                                            {"aid": a["id"], "disc": d.strip(), "pb": v}
                                        )
                                if new_d.strip():
                                    conn.execute(
                                        "INSERT OR REPLACE INTO athlete_pbs VALUES (:aid, :disc, :pb)",
                                        {"aid": a["id"], "disc": new_d.strip(), "pb": new_v}
                                    )
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
        st.warning("Ajoutez d'abord des athlètes avant de créer une compétition.")
    else:
        with st.expander("➕ Nouvelle compétition", expanded=True):
            name = st.text_input("Nom de la compétition")
            date = st.date_input("Date")

            options = {f"{a['first_name']} {a['last_name']}": a["id"] for a in athletes}
            selected = st.multiselect("Athlètes participants", list(options.keys()))

            athlete_disciplines = {}
            if selected:
                st.markdown("**Discipline par athlète :**")
                for s in selected:
                    aid = options[s]
                    with db() as conn:
                        pbs = conn.execute(
                            "SELECT discipline FROM athlete_pbs WHERE athlete_id = :aid ORDER BY discipline",
                            {"aid": aid}
                        ).fetchall()
                    disc_list = [pb["discipline"] for pb in pbs]

                    col_name, col_disc = st.columns([2, 3])
                    col_name.markdown(f"**{s}**")
                    if disc_list:
                        disc_list_with_other = disc_list + ["✏️ Autre..."]
                        chosen = col_disc.selectbox(
                            "Discipline", disc_list_with_other,
                            key=f"disc_{aid}"
                        )
                        if chosen == "✏️ Autre...":
                            athlete_disciplines[aid] = st.text_input(
                                f"Discipline personnalisée pour {s}",
                                key=f"disc_custom_{aid}"
                            )
                        else:
                            athlete_disciplines[aid] = chosen
                    else:
                        athlete_disciplines[aid] = col_disc.text_input(
                            "Discipline (aucun PB enregistré)",
                            key=f"disc_free_{aid}"
                        )

            if st.button("🏟️ Créer la compétition") and name.strip() and selected:
                all_filled = all(athlete_disciplines.get(options[s], "").strip() for s in selected)
                if not all_filled:
                    st.error("⚠️ Veuillez renseigner une discipline pour chaque athlète.")
                else:
                    with db() as conn:
                        cur = conn.cursor()
                        cur.execute(
                            "INSERT INTO competitions VALUES (NULL, :name, :date)",
                            {"name": name.strip(), "date": date.strftime("%Y-%m-%d")}
                        )
                        cid = cur.lastrowid
                        for s in selected:
                            aid = options[s]
                            disc = athlete_disciplines[aid].strip()
                            cur.execute(
                                "INSERT OR IGNORE INTO competition_athletes (competition_id, athlete_id, discipline) VALUES (:cid, :aid, :disc)",
                                {"cid": cid, "aid": aid, "disc": disc}
                            )
                    st.success(f"✅ Compétition **{name}** créée avec {len(selected)} athlète(s) !")
                    st.rerun()

    st.divider()
    comps = get_all_competitions()

    if not comps:
        st.info("Aucune compétition créée.")
    else:
        st.markdown(f"**{len(comps)} compétition(s)**")
        for c in comps:
            with db() as conn:
                ca_rows = conn.execute("""
                    SELECT a.first_name, a.last_name, ca.discipline
                    FROM competition_athletes ca
                    JOIN athletes a ON a.id = ca.athlete_id
                    WHERE ca.competition_id = :cid
                    ORDER BY a.last_name
                """, {"cid": c["id"]}).fetchall()

            col1, col2 = st.columns([5, 1])
            col1.markdown(f"**{c['name']}** — {fmt(c['date'])}  `{len(ca_rows)} athlète(s)`")
            if col2.button("🗑️", key=f"delcomp_{c['id']}", help="Supprimer"):
                st.session_state[f"confirm_delcomp_{c['id']}"] = True

            if ca_rows:
                detail = "  ".join([
                    f"{r['first_name']} {r['last_name']} `{r['discipline'] or '—'}`"
                    for r in ca_rows
                ])
                st.caption(detail)

            if st.session_state.get(f"confirm_delcomp_{c['id']}"):
                st.warning(f"⚠️ Supprimer **{c['name']}** et tous ses pronostics/résultats ?")
                cc1, cc2 = st.columns(2)
                if cc1.button("✅ Confirmer", key=f"yescomp_{c['id']}"):
                    with db() as conn:
                        conn.execute("PRAGMA foreign_keys = ON")
                        conn.execute("DELETE FROM competitions WHERE id = :id", {"id": c["id"]})
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
                    # FIX : paramètres nommés — :cid utilisé 2 fois sans ambiguïté
                    ath = conn.execute("""
                        SELECT a.id, a.first_name, a.last_name,
                               ca.discipline,
                               p.prediction,
                               pb.pb
                        FROM competition_athletes ca
                        JOIN athletes a ON a.id = ca.athlete_id
                        LEFT JOIN predictions p
                            ON p.athlete_id = a.id
                            AND p.competition_id = :cid
                            AND p.username = :user
                        LEFT JOIN athlete_pbs pb
                            ON pb.athlete_id = a.id
                            AND pb.discipline = ca.discipline
                        WHERE ca.competition_id = :cid
                    """, {"cid": c["id"], "user": current_user}).fetchall()

                if not ath:
                    st.warning("Aucun athlète dans cette compétition.")
                    continue

                with st.form(f"prono_{c['id']}"):
                    st.markdown("**Entrez vos pronostics :**")
                    predictions = {}
                    for a in ath:
                        val = float(a["prediction"]) if a["prediction"] is not None else 0.0
                        disc = a["discipline"] or "—"
                        pb_val = a["pb"]

                        col_name, col_disc, col_pb, col_input = st.columns([3, 2, 2, 2])
                        col_name.markdown(f"**{a['first_name']} {a['last_name']}**")
                        col_disc.markdown(f"🏅 `{disc}`")
                        if pb_val is not None:
                            col_pb.metric("PB", f"{pb_val:.2f}", delta=None)
                        else:
                            col_pb.caption("Pas de PB")

                        predictions[a["id"]] = col_input.number_input(
                            "Prono",
                            value=val,
                            min_value=0.0,
                            step=0.01,
                            key=f"prono_{c['id']}_{a['id']}"
                        )

                    if st.form_submit_button("💾 Sauvegarder tous mes pronostics", use_container_width=True):
                        with db() as conn:
                            for aid, pred in predictions.items():
                                conn.execute(
                                    "INSERT OR REPLACE INTO predictions VALUES (:user, :cid, :aid, :pred)",
                                    {"user": current_user, "cid": c["id"], "aid": aid, "pred": pred}
                                )
                        st.success("✅ Pronostics enregistrés !")
                        st.rerun()

# =========================
# RÉSULTATS
# =========================
elif page == "📊 Résultats":
    st.title("📊 Saisie des Résultats")
    st.caption("Entrez les résultats officiels des compétitions.")

    comps = get_all_competitions()

    if not comps:
        st.info("Aucune compétition disponible.")
    else:
        for c in comps:
            with st.expander(f"🏟️ {c['name']} — {fmt(c['date'])}"):
                with db() as conn:
                    # FIX : paramètres nommés — :cid utilisé 2 fois sans ambiguïté
                    ath = conn.execute("""
                        SELECT a.id, a.first_name, a.last_name, ca.discipline, r.result
                        FROM competition_athletes ca
                        JOIN athletes a ON a.id = ca.athlete_id
                        LEFT JOIN results r
                            ON r.athlete_id = a.id
                            AND r.competition_id = :cid
                        WHERE ca.competition_id = :cid
                        ORDER BY a.last_name
                    """, {"cid": c["id"]}).fetchall()

                if not ath:
                    st.warning("Aucun athlète dans cette compétition.")
                    continue

                with st.form(f"result_{c['id']}"):
                    st.markdown("**Résultats officiels :**")
                    results = {}
                    for a in ath:
                        val = float(a["result"]) if a["result"] is not None else 0.0
                        disc = a["discipline"] or "—"
                        label = f"{a['first_name']} {a['last_name']}  [{disc}]"
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
                        with db() as conn:
                            for aid, res in results.items():
                                if res > 0:
                                    conn.execute(
                                        "INSERT OR REPLACE INTO results VALUES (:cid, :aid, :res)",
                                        {"cid": c["id"], "aid": aid, "res": res}
                                    )
                        st.success("✅ Résultats enregistrés !")
                        st.rerun()

# =========================
# HISTORIQUE
# =========================
elif page == "📜 Historique":
    st.title("📜 Historique")

    comps = get_all_competitions()

    if not comps:
        st.info("Aucune compétition disponible.")
    else:
        for c in comps:
            with st.expander(f"🏟️ {c['name']} — {fmt(c['date'])}"):
                with db() as conn:
                    rows = conn.execute("""
                        SELECT p.username, p.prediction, r.result,
                               a.first_name, a.last_name, ca.discipline
                        FROM predictions p
                        JOIN results r
                            ON p.competition_id = r.competition_id
                            AND p.athlete_id = r.athlete_id
                        JOIN athletes a ON a.id = p.athlete_id
                        JOIN competition_athletes ca
                            ON ca.competition_id = p.competition_id
                            AND ca.athlete_id = p.athlete_id
                        WHERE p.competition_id = :cid
                        ORDER BY a.last_name, p.username
                    """, {"cid": c["id"]}).fetchall()

                if not rows:
                    st.info("Aucun résultat disponible pour cette compétition.")
                    continue

                headers = st.columns([2, 2, 2, 1, 1, 1])
                headers[0].markdown("**Utilisateur**")
                headers[1].markdown("**Athlète**")
                headers[2].markdown("**Discipline**")
                headers[3].markdown("**Prono**")
                headers[4].markdown("**Résultat**")
                headers[5].markdown("**Points**")
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
elif page == "🏆 Classement Général":
    st.title("🏆 Classement Général")

    with db() as conn:
        all_users = conn.execute("SELECT username FROM users").fetchall()

        comps_with_results = conn.execute("""
            SELECT DISTINCT c.id, c.name, c.date
            FROM competitions c
            JOIN results r ON r.competition_id = c.id
            ORDER BY c.date ASC, c.id ASC
        """).fetchall()

        all_scored_rows = conn.execute("""
            SELECT p.username, p.prediction, r.result, p.competition_id
            FROM predictions p
            JOIN results r
                ON p.competition_id = r.competition_id
                AND p.athlete_id = r.athlete_id
        """).fetchall()

    usernames = [u_row["username"] for u_row in all_users]

    def compute_scores(rows, exclude_comp_id=None):
        s = {u: 0 for u in usernames}
        for row in rows:
            if exclude_comp_id and row["competition_id"] == exclude_comp_id:
                continue
            s[row["username"]] += score(row["prediction"], row["result"])
        return s

    def ranked(scores_map):
        sorted_list = sorted(scores_map.items(), key=lambda x: -x[1])
        ranks = {}
        for i, (u, _) in enumerate(sorted_list, 1):
            ranks[u] = i
        return ranks

    scores_now = compute_scores(all_scored_rows)
    ranks_now = ranked(scores_now)
    sorted_scores = sorted(scores_now.items(), key=lambda x: -x[1])

    last_comp = comps_with_results[-1] if comps_with_results else None
    if last_comp and len(comps_with_results) > 1:
        scores_before = compute_scores(all_scored_rows, exclude_comp_id=last_comp["id"])
        ranks_before = ranked(scores_before)
        delta_label = f"vs avant « {last_comp['name']} »"
    elif last_comp and len(comps_with_results) == 1:
        ranks_before = {u: 1 for u in usernames}
        delta_label = f"vs avant « {last_comp['name']} »"
    else:
        ranks_before = None
        delta_label = None

    if not any(s > 0 for _, s in sorted_scores):
        st.info("Aucun score encore calculé. Ajoutez des résultats dans **📊 Résultats**.")

    if delta_label:
        st.caption(f"📊 Évolution {delta_label}")

    medals = {1: "🥇", 2: "🥈", 3: "🥉"}

    for i, (username, total_score) in enumerate(sorted_scores, 1):
        is_me = username == current_user

        if i == 1:
            bg = "linear-gradient(135deg, #F9D423 0%, #F7971E 100%)"
            border = "#E6A817"
            text_color = "#3d2000"
            rank_label = "🥇"
        elif i == 2:
            bg = "linear-gradient(135deg, #e0e0e0 0%, #9e9e9e 100%)"
            border = "#757575"
            text_color = "#1a1a1a"
            rank_label = "🥈"
        elif i == 3:
            bg = "linear-gradient(135deg, #cd9b5a 0%, #8B5e2a 100%)"
            border = "#7a4f22"
            text_color = "#fff0e0"
            rank_label = "🥉"
        else:
            bg = "#1e293b"
            border = "#FFD700" if is_me else "#334155"
            text_color = "#f1f5f9"
            rank_label = f"#{i}"

        if is_me and i > 3:
            bg = "#2d3f5e"
            border = "#FFD700"

        me_badge = f"<span style='font-size:0.72em; color:{'#5a3a00' if i==1 else ('#444' if i==2 else ('#c8a07a' if i==3 else '#94a3b8'))}; margin-left:6px;'>(vous)</span>" if is_me else ""

        if ranks_before is not None:
            prev_rank = ranks_before.get(username, len(usernames))
            delta = prev_rank - i
            if delta > 0:
                delta_html = f"<span style='color:#22c55e; font-size:0.88em; font-weight:700; background:rgba(34,197,94,0.15); padding:1px 6px; border-radius:10px;'>▲ +{delta}</span>"
            elif delta < 0:
                delta_html = f"<span style='color:#ef4444; font-size:0.88em; font-weight:700; background:rgba(239,68,68,0.15); padding:1px 6px; border-radius:10px;'>▼ {delta}</span>"
            else:
                delta_html = "<span style='color:#94a3b8; font-size:0.88em; padding:1px 6px;'>—</span>"
        else:
            delta_html = ""

        pts_color = "#3d2000" if i == 1 else ("#1a1a1a" if i == 2 else ("#fff0e0" if i == 3 else "#e94560"))

        st.markdown(f"""
        <div style="background:{bg}; border:2px solid {border}; border-radius:12px;
                    padding:14px 22px; margin-bottom:10px; display:flex;
                    justify-content:space-between; align-items:center;
                    box-shadow: 0 2px 8px rgba(0,0,0,0.18);">
            <span style="font-size:1.18em; color:{text_color}; display:flex; align-items:center; gap:10px;">
                <span style="font-size:1.3em;">{rank_label}</span>
                <strong>{username}</strong>{me_badge}
                {delta_html}
            </span>
            <span style="font-size:1.25em; font-weight:800; color:{pts_color};">{total_score} pts</span>
        </div>
        """, unsafe_allow_html=True)

    if last_comp:
        st.divider()
        with st.expander(f"📋 Détail « {last_comp['name']} » — {fmt(last_comp['date'])}"):
            with db() as conn:
                last_rows = conn.execute("""
                    SELECT p.username, SUM(CASE
                        WHEN ABS(p.prediction - r.result) = 0 THEN 300
                        ELSE MAX(0, CAST(150 - ABS(p.prediction - r.result) * 4 AS INTEGER))
                    END) as pts
                    FROM predictions p
                    JOIN results r
                        ON p.competition_id = r.competition_id
                        AND p.athlete_id = r.athlete_id
                    WHERE p.competition_id = :cid
                    GROUP BY p.username
                    ORDER BY pts DESC
                """, {"cid": last_comp["id"]}).fetchall()

            if last_rows:
                for j, row in enumerate(last_rows, 1):
                    m = medals.get(j, f"#{j}")
                    st.write(f"{m} **{row['username']}** — {row['pts']} pts sur cette compétition")
