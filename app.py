import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime
import uuid

st.set_page_config(page_title="Athlé Bet V7", layout="wide")

# =============================
# DATABASE
# =============================
conn = sqlite3.connect("app.db", check_same_thread=False)
c = conn.cursor()

c.execute("CREATE TABLE IF NOT EXISTS users (username TEXT PRIMARY KEY)")
c.execute("CREATE TABLE IF NOT EXISTS groups (id INTEGER PRIMARY KEY, name TEXT, code TEXT)")
c.execute("CREATE TABLE IF NOT EXISTS group_members (group_id INTEGER, username TEXT)")
c.execute("CREATE TABLE IF NOT EXISTS competitions (id INTEGER PRIMARY KEY, name TEXT, date TEXT, group_id INTEGER)")
c.execute("CREATE TABLE IF NOT EXISTS athletes (id INTEGER PRIMARY KEY, competition_id INTEGER, name TEXT, discipline TEXT, result REAL, pb REAL)")
c.execute("CREATE TABLE IF NOT EXISTS predictions (username TEXT, athlete_id INTEGER, prediction REAL, PRIMARY KEY(username, athlete_id))")
c.execute("CREATE TABLE IF NOT EXISTS chat (group_id INTEGER, username TEXT, message TEXT, time TEXT)")

try:
    c.execute("ALTER TABLE athletes ADD COLUMN pb REAL")
except:
    pass

conn.commit()

# =============================
# AUTH
# =============================
if "user" not in st.session_state:
    st.title("🏃 Athlé Bet")
    st.subheader("Entre ton pseudo pour commencer")

    user_input = st.text_input("Pseudo")

    if st.button("Entrer") and user_input:
        c.execute("INSERT OR IGNORE INTO users VALUES (?)", (user_input,))
        conn.commit()
        st.session_state.user = user_input
        st.rerun()

    st.stop()

user = st.session_state.user

# =============================
# NAV
# =============================
page = st.sidebar.radio(
    "Menu",
    ["🏠 Compétitions", "🏆 Classement", "➕ Ajouter", "🎯 Résultats", "👥 Groupes", "📜 Historique", "💬 Chat"]
)

# =============================
# SCORE
# =============================
def score(pred, actual):
    diff = abs(pred - actual)
    return 300 if diff == 0 else max(0, 150 - diff * 4)

# =============================
# COMP SET
# =============================
def set_comp(cid):
    st.session_state.comp = cid

# =============================
# GROUPES
# =============================
if page == "👥 Groupes":
    st.title("👥 Groupes")

    col1, col2 = st.columns(2)

    with col1:
        gname = st.text_input("Créer groupe")
        if st.button("Créer") and gname:
            code = str(uuid.uuid4())[:6]
            c.execute("INSERT INTO groups (name, code) VALUES (?,?)", (gname, code))
            conn.commit()
            st.success(f"Code: {code}")

    with col2:
        code = st.text_input("Rejoindre code")
        if st.button("Rejoindre") and code:
            g = c.execute("SELECT id FROM groups WHERE code=?", (code,)).fetchone()
            if g:
                c.execute("INSERT INTO group_members VALUES (?,?)", (g[0], user))
                conn.commit()
                st.success("Rejoint")

# =============================
# AJOUT
# =============================
elif page == "➕ Ajouter":
    st.title("➕ Compétition")

    name = st.text_input("Nom")
    date = st.date_input("Date")

    groups = c.execute("SELECT g.id,g.name FROM groups g JOIN group_members m ON g.id=m.group_id WHERE m.username=?", (user,)).fetchall()
    gdict = {g[1]: g[0] for g in groups}

    gsel = st.selectbox("Groupe", list(gdict.keys())) if gdict else None

    nb = st.slider("Nombre d'athlètes", 1, 15)

    athletes = []
    for i in range(nb):
        c1, c2, c3 = st.columns(3)
        with c1:
            n = st.text_input(f"Nom {i}")
        with c2:
            d = st.text_input(f"Disc {i}")
        with c3:
            pb = st.number_input(f"PB {i}", value=0.0)
        athletes.append((n, d, pb))

    if st.button("Créer") and gsel:
        gid = gdict[gsel]
        stored_date = date.strftime("%Y-%m-%d")

        c.execute("INSERT INTO competitions (name,date,group_id) VALUES (?,?,?)", (name, stored_date, gid))
        cid = c.lastrowid

        for n, d, pb in athletes:
            if n:
                c.execute("INSERT INTO athletes (competition_id,name,discipline,pb) VALUES (?,?,?,?)", (cid, n, d, pb))

        conn.commit()
        st.success("OK")

# =============================
# COMPETITIONS (PB INLINE)
# =============================
elif page == "🏠 Compétitions":
    st.title("🏠 Compétitions")

    comps = c.execute("SELECT * FROM competitions").fetchall()

    for cid, name, date, gid in comps:
        display_date = date
        try:
            display_date = datetime.strptime(date, "%Y-%m-%d").strftime("%d-%m-%Y")
        except:
            pass

        label = f"🏁 {name} | 📅 {display_date}"
        st.button(label, key=f"c{cid}", on_click=set_comp, args=(cid,))

    if "comp" in st.session_state:
        athletes = c.execute("SELECT * FROM athletes WHERE competition_id=?", (st.session_state.comp,)).fetchall()

        st.subheader("🏃 Athlètes & Pronostics")

        for i in range(0, len(athletes), 2):
            cols = st.columns(2)

            for j in range(2):
                if i + j < len(athletes):
                    aid, _, n, d, r, pb = athletes[i + j]

                    with cols[j]:
                        pb_txt = f" — PB: {pb}" if pb else ""
                        st.markdown(f"**{n} ({d}){pb_txt}**")

                        existing = c.execute("SELECT prediction FROM predictions WHERE username=? AND athlete_id=?", (user, aid)).fetchone()
                        val = existing[0] if existing else 0.0

                        p = st.number_input("⏱", value=float(val), key=f"p{aid}", label_visibility="collapsed")

                        if st.button("💾", key=f"s{aid}"):
                            c.execute("REPLACE INTO predictions VALUES (?,?,?)", (user, aid, p))
                            conn.commit()
                            st.toast("Sauvegardé")

# =============================
# RESULTATS
# =============================
elif page == "🎯 Résultats":
    st.title("🎯 Résultats")

    comps = c.execute("SELECT * FROM competitions").fetchall()

    for cid, name, date, gid in comps:
        display_date = date
        try:
            display_date = datetime.strptime(date, "%Y-%m-%d").strftime("%d-%m-%Y")
        except:
            pass

        with st.expander(f"🏁 {name} — 📅 {display_date}"):
            athletes = c.execute("SELECT * FROM athletes WHERE competition_id=?", (cid,)).fetchall()

            for aid, _, n, _, r, pb in athletes:
                res = st.number_input(n, value=float(r or 0), key=f"r{aid}")

                if st.button("Valider", key=f"vr{aid}"):
                    c.execute("UPDATE athletes SET result=? WHERE id=?", (res, aid))
                    conn.commit()

# =============================
# CLASSEMENT
# =============================
elif page == "🏆 Classement":
    st.title("🏆 Classement")

    users = c.execute("SELECT username FROM users").fetchall()
    scores = {u[0]: 0 for u in users}

    preds = c.execute("SELECT username, athlete_id, prediction FROM predictions").fetchall()

    for u, aid, p in preds:
        r = c.execute("SELECT result FROM athletes WHERE id=?", (aid,)).fetchone()[0]
        if r is not None:
            scores[u] += score(p, r)

    df = pd.DataFrame(list(scores.items()), columns=["Joueur", "Points"]).sort_values(by="Points", ascending=False)

    for i, row in enumerate(df.itertuples(index=False), 1):
        medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else ""
        st.write(f"{medal} {i}. {row.Joueur} — {row.Points} pts")

# =============================
# HISTORIQUE (COMPACT)
# =============================
elif page == "📜 Historique":
    st.title("📜 Historique")

    users = c.execute("SELECT username FROM users").fetchall()

    for u, in users:
        st.markdown(f"### 👤 {u}")

        comps = c.execute("SELECT * FROM competitions").fetchall()

        for cid, cname, cdate, gid in comps:
            athletes = c.execute("SELECT id,result FROM athletes WHERE competition_id=?", (cid,)).fetchall()

            rows = []
            total = 0

            for aid, res in athletes:
                pred = c.execute("SELECT prediction FROM predictions WHERE username=? AND athlete_id=?", (u, aid)).fetchone()

                if pred and res is not None:
                    diff = abs(pred[0] - res)
                    pts = score(pred[0], res)
                    total += pts
                    rows.append((aid, pred[0], res, diff, pts))

            if rows:
                st.markdown(f"**🏁 {cname} — Total {total} pts**")

                for r in rows:
                    st.write(f"{r[0]} | 🎯 {r[1]} | 🏁 {r[2]} | 📏 {r[3]} | ⭐ {r[4]}")

# =============================
# CHAT
# =============================
elif page == "💬 Chat":
    st.title("💬 Chat")

    groups = c.execute("SELECT g.id,g.name FROM groups g JOIN group_members m ON g.id=m.group_id WHERE m.username=?", (user,)).fetchall()
    gdict = {g[1]: g[0] for g in groups}

    gsel = st.selectbox("Groupe", list(gdict.keys())) if gdict else None

    if gsel:
        gid = gdict[gsel]

        msg = st.text_input("Message")
        if st.button("Envoyer") and msg:
            c.execute("INSERT INTO chat VALUES (?,?,?,?)", (gid, user, msg, str(datetime.now())))
            conn.commit()

        msgs = c.execute("SELECT username,message FROM chat WHERE group_id=? ORDER BY time DESC", (gid,)).fetchall()

        for m in msgs:
            st.write(f"{m[0]}: {m[1]}")

st.sidebar.success("V7 FINAL UX 🚀")
