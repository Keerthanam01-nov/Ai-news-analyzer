"""
Daily News Buddy - AI News Analyzer for everyone (kids, students, aspirants, adults)

Features
- Live news from BBC, The Hindu, Al Jazeera, Guardian, NPR, NDTV, Indian Express, TOI, HT
  (last 24 hours first, up to 50 stories, search engines as a backup)
- Rolling live ticker, quick topic pills, daily mission, WhatsApp sharing
- Summary, sentiment, credibility hint, translation to Indian languages
- Story Studio: 2-min briefing, 8-scene cartoon, explain simply, quiz, hard words
- Newsie chatbot + dictionary, login (PBKDF2), guest mode, XP + streaks
- Privacy page, ratings, owner dashboard, backups, user data deletion

Optional Secrets: DATABASE_URL, GEMINI_API_KEY, ADMIN_EMAILS, APP_NAME,
CONTACT_EMAIL, GITHUB_URL, APP_URL, NEWSAPI_KEY
"""
import os
import re
import io
import base64
import json
import time
import html
import socket
import sqlite3
import hashlib
import hmac
import secrets
import ipaddress
import datetime as dt
from contextlib import closing
from email.utils import parsedate_to_datetime
from urllib.parse import quote_plus, urlparse, parse_qs
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor

import requests
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components


def cfg(name, default=""):
    """Read a setting from Streamlit secrets first, then environment variables."""
    try:
        v = st.secrets.get(name)
    except Exception:
        v = None
    return str(v) if v not in (None, "") else os.getenv(name, default)


# ----------------------------------------------------------------------------
# Config
# ----------------------------------------------------------------------------
APP_NAME = cfg("APP_NAME", "Daily News Buddy")  # change the name any time in Secrets: APP_NAME = "..."
DB_PATH = os.getenv("NEWSVERSE_DB", "data/newsverse.db")
UA = {"User-Agent": "Mozilla/5.0 (DailyNewsBuddy learning app)"}
esc = html.escape
BROWSER_UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
                            "Chrome/124.0 Safari/537.36",
              "Accept": "application/rss+xml, application/xml;q=0.9, text/xml;q=0.8, */*;q=0.5"}
IST = dt.timezone(dt.timedelta(hours=5, minutes=30))
MAX_STORIES = 50

LANGS = {
    "English": ("en", "en-IN"), "Hindi (हिन्दी)": ("hi", "hi-IN"),
    "Kannada (ಕನ್ನಡ)": ("kn", "kn-IN"), "Tamil (தமிழ்)": ("ta", "ta-IN"),
    "Telugu (తెలుగు)": ("te", "te-IN"), "Malayalam (മലയാളം)": ("ml", "ml-IN"),
    "Marathi (मराठी)": ("mr", "mr-IN"), "Bengali (বাংলা)": ("bn", "bn-IN"),
    "Gujarati (ગુજરાતી)": ("gu", "gu-IN"), "Punjabi (ਪੰਜਾਬੀ)": ("pa", "pa-IN"),
    "Urdu (اردو)": ("ur", "ur-IN"), "Odia (ଓଡ଼ିଆ)": ("or", "or-IN"),
    "Assamese (অসমীয়া)": ("as", "as-IN"), "Nepali (नेपाली)": ("ne", "ne-NP"),
}
CATEGORIES = {
    "Top stories": None, "India": "NATION", "Karnataka": None, "World": "WORLD", "Business": "BUSINESS",
    "Technology": "TECHNOLOGY", "Science": "SCIENCE", "Health": "HEALTH",
    "Sports": "SPORTS", "Entertainment": "ENTERTAINMENT",
}
KIDS_CATEGORIES = ["Top stories", "Science", "Technology", "Sports", "Entertainment", "World", "Health"]
CAT_COLOR = {"Top stories": "#FFC93C", "India": "#FF9F43", "Karnataka": "#FF6B6B", "World": "#4DABF7",
             "Business": "#3DDC97", "Technology": "#9B8CFF", "Science": "#22D3EE", "Health": "#F783AC",
             "Sports": "#FF8787", "Entertainment": "#E599F7"}
TOPICS = {"🏏 Cricket": "cricket", "🚀 Space": "ISRO space", "🎬 Movies": "movie film", "🔬 Science": "science",
          "🤖 AI & Tech": "artificial intelligence", "⚽ Football": "football", "📚 Exams": "exam results",
          "🌧️ Weather": "weather rain"}
LEVELS = [(0, "Cub Reporter", "🐣"), (50, "News Explorer", "🧭"), (150, "Story Detective", "🕵️"),
          (400, "Chief Editor", "👑"), (900, "News Legend", "🌟")]

KIDS_BLOCK = re.compile(
    r"\b(murder|murdered|rape|raped|sex|sexual|porn|suicide|kill|killed|killing|stabbed|shot dead|"
    r"terror|terrorist|blast|bomb|massacre|corpse|dead body|gang|molest|abuse|assault|beheaded|"
    r"drug|cocaine|heroin|casino|betting|gambling)\b", re.I)

TRUSTED_SOURCES = [
    "the hindu", "ndtv", "bbc", "reuters", "pti", "press trust", "indian express", "hindustan times",
    "times of india", "deccan herald", "livemint", "mint", "economic times", "business standard",
    "al jazeera", "associated press", "ap news", "bloomberg", "theprint", "the print", "scroll",
    "the wire", "firstpost", "india today", "news18", "dd news", "prasar bharati", "isro", "who",
    "bbc news", "npr", "the indian express", "nature", "science", "financial express", "the guardian",
    "new york times", "washington post",
]
CLICKBAIT = ["shocking", "you won't believe", "miracle", "secret", "exposed", "bombshell", "slams",
             "destroys", "goes viral", "must watch", "unbelievable", "100% cure", "what happens next",
             "will blow your mind", "banned", "leaked"]

EMOJI_HINTS = {
    "bus": "🚌", "dasara": "🎉", "dussehra": "🎉", "festival": "🎉", "cricket": "🏏", "rain": "🌧️",
    "flood": "🌊", "school": "🏫", "student": "🎒", "exam": "📝", "space": "🚀", "isro": "🚀",
    "moon": "🌙", "election": "🗳️", "vote": "🗳️", "tech": "💻", "ai ": "🤖", "robot": "🤖",
    "health": "🩺", "hospital": "🏥", "market": "📈", "sensex": "📈", "price": "💰", "budget": "💰",
    "train": "🚆", "metro": "🚇", "flight": "✈️", "airline": "✈️", "airbus": "✈️", "film": "🎬",
    "movie": "🎬", "tiger": "🐯", "elephant": "🐘", "temple": "🛕", "heat": "🔥", "fire": "🔥",
    "water": "💧", "farmer": "🌾", "crop": "🌾", "solar": "☀️", "electric": "⚡", "car": "🚗",
    "phone": "📱", "football": "⚽", "olympic": "🏅", "medal": "🏅", "tourist": "🧳", "tour": "🧳",
}
CAT_EMOJI = {"Top stories": "📰", "India": "🇮🇳", "Karnataka": "🏛️", "World": "🌍", "Business": "💼", "Technology": "💻",
             "Science": "🔬", "Health": "🩺", "Sports": "🏅", "Entertainment": "🎬"}

DEMO_ARTICLES = [
    {"title": "ISRO shares new images from its latest satellite mission", "source": "Sample story",
     "url": "https://www.isro.gov.in", "published": None, "image": "",
     "text": "India's space agency released fresh pictures taken from orbit. Scientists say the images will help study weather, farming and forests. Students across the country watched the live updates."},
    {"title": "City introduces free double-decker bus rides for tourists during festival week", "source": "Sample story",
     "url": "https://www.example.com", "published": None, "image": "",
     "text": "Officials launched special open-top bus tours so visitors can see the illuminated palace and local markets. Tickets are available online. The tours will run every evening for ten days."},
    {"title": "School children win national science fair with a low-cost water purifier", "source": "Sample story",
     "url": "https://www.example.com", "published": None, "image": "",
     "text": "A team of Class 9 students built a purifier using sand, charcoal and clay. Judges praised the design because it costs very little. The students plan to install it in nearby villages."},
]

st.set_page_config(page_title=f"{APP_NAME} - understand the news", page_icon="📰",
                   layout="wide", initial_sidebar_state="collapsed")


def embed_html(markup, height):
    """Render a self-contained HTML page (3D hero, cartoon). Uses st.iframe on new Streamlit."""
    if hasattr(st, "iframe"):
        st.iframe(markup, height=height)
    else:
        components.html(markup, height=height, scrolling=True)


def now():
    return dt.datetime.now(dt.timezone.utc)


def iso():
    return now().isoformat(timespec="seconds")


# ----------------------------------------------------------------------------
# Database (SQLite, parameterised queries only)
# ----------------------------------------------------------------------------
SCHEMA = """
CREATE TABLE IF NOT EXISTS users(
  id INTEGER PRIMARY KEY AUTOINCREMENT, email TEXT UNIQUE NOT NULL, name TEXT NOT NULL,
  salt TEXT NOT NULL, pw_hash TEXT NOT NULL, age_group TEXT, created TEXT, last_login TEXT,
  xp INTEGER DEFAULT 0, streak INTEGER DEFAULT 0, last_active TEXT,
  failed INTEGER DEFAULT 0, locked_until TEXT);
CREATE TABLE IF NOT EXISTS events(
  id INTEGER PRIMARY KEY AUTOINCREMENT, sid TEXT, user_id INTEGER, ts TEXT, kind TEXT, detail TEXT);
CREATE TABLE IF NOT EXISTS feedback(
  id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, ts TEXT, rating INTEGER,
  category TEXT, message TEXT, public INTEGER DEFAULT 0, display_name TEXT);
CREATE TABLE IF NOT EXISTS chats(
  id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, ts TEXT, question TEXT, answer TEXT);
CREATE TABLE IF NOT EXISTS saved(
  id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, ts TEXT, title TEXT, url TEXT, summary TEXT);
CREATE TABLE IF NOT EXISTS sessions(
  token_hash TEXT PRIMARY KEY, user_id INTEGER, expires TEXT);
CREATE INDEX IF NOT EXISTS idx_events_ts ON events(ts);
"""


def using_pg():
    return bool(cfg("DATABASE_URL"))


@st.cache_resource
def _pg_pool():
    from psycopg2.pool import ThreadedConnectionPool
    return ThreadedConnectionPool(1, 6, cfg("DATABASE_URL"), connect_timeout=10)


def _pg_run(sql, params=()):
    import psycopg2
    import psycopg2.extras
    pool = _pg_pool()
    for attempt in (1, 2):
        con = pool.getconn()
        try:
            with con.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(sql, params)
                rows = cur.fetchall() if cur.description else []
            con.commit()
            return rows
        except Exception as e:
            try:
                con.rollback()
            except Exception:
                pass
            if attempt == 2 or not isinstance(e, (psycopg2.OperationalError, psycopg2.InterfaceError)):
                raise
        finally:
            pool.putconn(con)


@st.cache_resource
def init_db():
    if using_pg():
        for stmt in [t.strip() for t in SCHEMA.split(";") if t.strip()]:
            _pg_run(stmt.replace("INTEGER PRIMARY KEY AUTOINCREMENT", "SERIAL PRIMARY KEY"))
        return True
    os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)
    with closing(sqlite3.connect(DB_PATH)) as con:
        con.execute("PRAGMA journal_mode=WAL")
        con.executescript(SCHEMA)
        con.commit()
    return True


def q(sql, params=()):
    if using_pg():
        return _pg_run(sql.replace("?", "%s"), params)
    with closing(sqlite3.connect(DB_PATH, timeout=15)) as con:
        con.row_factory = sqlite3.Row
        return con.execute(sql, params).fetchall()


def x(sql, params=()):
    if using_pg():
        s2 = sql.replace("?", "%s")
        ret = s2.lstrip().upper().startswith("INSERT INTO") and "INTO SESSIONS" not in s2.upper()
        rows = _pg_run(s2 + (" RETURNING id" if ret else ""), params)
        return rows[0]["id"] if ret and rows else None
    with closing(sqlite3.connect(DB_PATH, timeout=15)) as con:
        cur = con.execute(sql, params)
        con.commit()
        return cur.lastrowid


def df_query(sql, params=()):
    return pd.DataFrame([dict(r) for r in q(sql, params)])


# ----------------------------------------------------------------------------
# Auth
# ----------------------------------------------------------------------------
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def hash_pw(pw, salt_hex):
    return hashlib.pbkdf2_hmac("sha256", pw.encode(), bytes.fromhex(salt_hex), 240_000).hex()


def admin_emails():
    return {e.strip().lower() for e in cfg("ADMIN_EMAILS").split(",") if e.strip()}


def is_admin():
    u = st.session_state.get("user")
    return bool(u and u["email"] in admin_emails())


def signup(name, email, pw, age_group, consent):
    name, email = name.strip()[:40], email.strip().lower()
    if len(name) < 2:
        return False, "Please enter a nickname with at least 2 letters."
    if not EMAIL_RE.match(email) or len(email) > 120:
        return False, "That email doesn't look right. Check it and try again."
    if len(pw) < 8 or pw.isalpha() or pw.isdigit():
        return False, "Use a password with 8+ characters, mixing letters and numbers."
    if age_group != "18 or older" and not consent:
        return False, "Please tick the box to confirm a parent or guardian agrees."
    if q("SELECT 1 FROM users WHERE email=?", (email,)):
        return False, "This email is already registered. Log in instead."
    salt = secrets.token_hex(16)
    uid = x("INSERT INTO users(email,name,salt,pw_hash,age_group,created,last_login) VALUES(?,?,?,?,?,?,?)",
            (email, name, salt, hash_pw(pw, salt), age_group, iso(), iso()))
    return True, uid


def login(email, pw):
    email = email.strip().lower()
    bad = "Wrong email or password. New here? Use the Sign up tab first."
    rows = q("SELECT * FROM users WHERE email=?", (email,))
    if not rows:
        hash_pw(pw, "00" * 16)  # keep timing similar
        return False, bad
    u = rows[0]
    if u["locked_until"] and dt.datetime.fromisoformat(u["locked_until"]) > now():
        return False, "Too many wrong attempts. Please try again in 15 minutes."
    if not hmac.compare_digest(hash_pw(pw, u["salt"]), u["pw_hash"]):
        failed = (u["failed"] or 0) + 1
        lock = (now() + dt.timedelta(minutes=15)).isoformat(timespec="seconds") if failed >= 5 else None
        x("UPDATE users SET failed=?, locked_until=? WHERE id=?", (0 if lock else failed, lock, u["id"]))
        return False, bad
    x("UPDATE users SET failed=0, locked_until=NULL, last_login=? WHERE id=?", (iso(), u["id"]))
    return True, u


def set_user(row, kind="login"):
    st.session_state.user = {"id": row["id"], "name": row["name"], "email": row["email"],
                             "age_group": row["age_group"]}
    st.session_state.kids_set = row["age_group"] != "18 or older"
    log(kind)
    award(1, "login")


def _th(tok):
    return hashlib.sha256(tok.encode()).hexdigest()


def create_session(user_id):
    """Remember-me token (14 days). Only its hash is stored in the database."""
    tok = secrets.token_urlsafe(32)
    x("DELETE FROM sessions WHERE expires<?", (iso(),))
    x("INSERT INTO sessions(token_hash,user_id,expires) VALUES(?,?,?)",
      (_th(tok), user_id, (now() + dt.timedelta(days=14)).isoformat(timespec="seconds")))
    return tok


def restore_session():
    """After a refresh or the app waking up, log the person back in from the URL token."""
    if st.session_state.get("user") or st.session_state.get("guest"):
        return
    tok = st.query_params.get("s")
    if tok:
        rows = q("SELECT u.* FROM sessions s JOIN users u ON u.id=s.user_id WHERE s.token_hash=? AND s.expires>?",
                 (_th(tok), iso()))
        if rows:
            set_user(rows[0], "resume")
            return
        st.query_params.pop("s", None)
        st.session_state.ls_clear = True
    if st.query_params.get("g") == "1":
        st.session_state.guest = True
        st.session_state.kids_set = st.query_params.get("k") == "1"


def end_session():
    st.session_state.ls_clear = True
    st.session_state.pop("ls_saved", None)
    tok = st.query_params.get("s")
    if tok:
        x("DELETE FROM sessions WHERE token_hash=?", (_th(tok),))
    st.query_params.clear()


def delete_user_data(uid):
    for t in ("feedback", "chats", "saved", "sessions"):
        x(f"DELETE FROM {t} WHERE user_id=?", (uid,))
    x("UPDATE events SET user_id=NULL, detail='' WHERE user_id=?", (uid,))
    x("DELETE FROM users WHERE id=?", (uid,))


# ----------------------------------------------------------------------------
# Events, XP, limits
# ----------------------------------------------------------------------------
def uid():
    u = st.session_state.get("user")
    return u["id"] if u else None


def log(kind, detail=""):
    try:
        x("INSERT INTO events(sid,user_id,ts,kind,detail) VALUES(?,?,?,?,?)",
          (st.session_state.sid, uid(), iso(), kind, str(detail)[:200]))
    except Exception:
        pass


def level_of(xp):
    cur = LEVELS[0]
    nxt = None
    for i, lv in enumerate(LEVELS):
        if xp >= lv[0]:
            cur = lv
            nxt = LEVELS[i + 1] if i + 1 < len(LEVELS) else None
    return cur, nxt


def award(points, key):
    u = st.session_state.get("user")
    done = st.session_state.setdefault("awarded", set())
    if not u or key in done:
        return
    done.add(key)
    today = now().date().isoformat()
    row = q("SELECT streak,last_active FROM users WHERE id=?", (u["id"],))
    if not row:
        return
    streak = row[0]["streak"] or 0
    if row[0]["last_active"] != today:
        yday = (now().date() - dt.timedelta(days=1)).isoformat()
        streak = streak + 1 if row[0]["last_active"] == yday else 1
    x("UPDATE users SET xp=xp+?, streak=?, last_active=? WHERE id=?", (points, streak, today, u["id"]))
    if points > 1:
        st.toast(f"+{points} XP", icon="🌟")


def ai_allowed():
    if is_admin():
        return True
    today = now().date().isoformat()
    if uid():
        n = q("SELECT COUNT(*) c FROM events WHERE kind='ai' AND user_id=? AND substr(ts,1,10)=?", (uid(), today))[0]["c"]
        return n < int(cfg("AI_DAILY_LIMIT", "30"))
    n = q("SELECT COUNT(*) c FROM events WHERE kind='ai' AND sid=? AND substr(ts,1,10)=?",
          (st.session_state.sid, today))[0]["c"]
    return n < int(cfg("AI_GUEST_LIMIT", "5"))


# ----------------------------------------------------------------------------
# AI (Gemini or Anthropic) - results cached so repeat views cost nothing
# ----------------------------------------------------------------------------
SYSTEM_BASE = (
    "You are Newsie, a friendly, accurate news explainer for readers in India. "
    "Use only facts given in the provided text; never invent details. If the text is too thin, say so. "
    "Stay politically neutral and avoid graphic detail. Keep language simple and kind."
)


def ai_enabled():
    return bool(cfg("ANTHROPIC_API_KEY") or cfg("GEMINI_API_KEY"))


def ai_on():
    return ai_enabled()


def _api_error(r):
    try:
        e = r.json().get("error", {})
        msg = e.get("message") if isinstance(e, dict) else str(e)
    except Exception:
        msg = r.text[:120]
    return RuntimeError(f"HTTP {r.status_code}: {str(msg)[:140]}")


@st.cache_data(ttl=3600, show_spinner=False)
def gemini_models():
    """Ordered list of Gemini models to try. Model names are retired often, so we never rely on one name."""
    pinned = [m.strip() for m in cfg("GEMINI_MODEL").split(",") if m.strip()]
    found = []
    try:
        r = requests.get("https://generativelanguage.googleapis.com/v1beta/models",
                         headers={"x-goog-api-key": cfg("GEMINI_API_KEY")}, params={"pageSize": 200}, timeout=8)
        r.raise_for_status()
        names = [m["name"].split("/")[-1] for m in r.json().get("models", [])
                 if "generateContent" in m.get("supportedGenerationMethods", [])]
        bad = ("tts", "image", "live", "audio", "embedding", "robotics", "computer", "learnlm", "gemma",
               "exp", "thinking", "preview", "vision", "customtools")
        flash = [n for n in names if "flash" in n and not any(b_ in n for b_ in bad)]

        def ver(n):
            m = re.search(r"gemini-(\d+(?:\.\d+)?)", n)
            return (float(m.group(1)) if m else 0, "lite" not in n)
        found = sorted(flash, key=ver, reverse=True)
    except Exception:
        pass
    out = list(pinned)
    if "gemini-flash-latest" not in out:
        out.append("gemini-flash-latest")  # Google's always-current alias
    out += [n for n in found if n not in out][:4]
    return out


def _gemini_once(model, system, msgs, max_tokens, attempts):
    """One model, short timeout, automatic retry on timeouts and busy-server errors."""
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    headers = {"x-goog-api-key": cfg("GEMINI_API_KEY"), "content-type": "application/json"}
    body = {"systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user" if m["role"] == "user" else "model",
                          "parts": [{"text": m["content"]}]} for m in msgs],
            "generationConfig": {"maxOutputTokens": max_tokens * 2, "temperature": 0.7,
                                 "thinkingConfig": {"thinkingBudget": 0}}}
    last = None
    for i in range(attempts):
        try:
            r = requests.post(url, headers=headers, json=body, timeout=(5, 20))
            if r.status_code == 400 and "thinkingConfig" in body["generationConfig"]:
                body["generationConfig"].pop("thinkingConfig")  # model may not accept thinkingConfig
                r = requests.post(url, headers=headers, json=body, timeout=(5, 20))
            if r.status_code in (429, 500, 502, 503, 504):
                last = _api_error(r)
                time.sleep(1.2)
                continue
            if not r.ok:
                raise _api_error(r)
            cands = r.json().get("candidates", [])
            text = "".join(p.get("text", "") for p in (cands[0].get("content", {}).get("parts", []) if cands else []))
            if not text.strip():
                raise RuntimeError("Empty reply (the answer was blocked or filtered)")
            return text
        except (requests.Timeout, requests.ConnectionError) as e:
            last = e
    raise last or RuntimeError("AI service did not answer")


def _call_llm(system, msgs, max_tokens):
    if cfg("ANTHROPIC_API_KEY"):
        r = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={"x-api-key": cfg("ANTHROPIC_API_KEY"), "anthropic-version": "2023-06-01",
                     "content-type": "application/json"},
            json={"model": cfg("ANTHROPIC_MODEL", "claude-haiku-5-5"), "max_tokens": max_tokens,
                  "system": system, "messages": msgs}, timeout=30)
        if not r.ok:
            raise _api_error(r)
        return "".join(b.get("text", "") for b in r.json().get("content", []))
    last = None
    for i, model in enumerate(gemini_models()[:5]):
        try:
            return _gemini_once(model, system, msgs, max_tokens, 2 if i == 0 else 1)
        except Exception as e:  # retired model (404), blocked, busy... try the next one
            last = last or e
    raise last or RuntimeError("No Gemini model available")


@st.cache_data(ttl=6 * 3600, show_spinner=False, max_entries=500)
def _llm_cached(system, messages_json, max_tokens):
    return _call_llm(system, json.loads(messages_json), max_tokens)


def llm(system, messages, max_tokens=700):
    """Returns text, or None when AI is off / limit reached / call failed."""
    if not ai_on() or not ai_allowed():
        return None
    try:
        out = _llm_cached(system, json.dumps(messages), max_tokens).strip()
        log("ai")  # only successful calls count toward the daily limit
        st.session_state.pop("ai_err", None)
        return out
    except Exception as e:
        st.session_state.ai_err = str(e)[:150]
        return None


def ai_status():
    if not ai_on():
        return "The AI helper isn't set up yet. The site owner must add GEMINI_API_KEY in Streamlit Secrets."
    if not ai_allowed():
        return "You've used today's AI helpers. They refresh tomorrow."
    return f"The AI service didn't answer ({st.session_state.get('ai_err', 'unknown reason')}). Please try again in a minute."


def audience(kids):
    return "a curious 8-year-old child (very simple words, short sentences, fun tone)" if kids \
        else "a general reader at Class 10 level (clear, neutral, concise)"


# ----------------------------------------------------------------------------
# News fetching
# ----------------------------------------------------------------------------
def strip_tags(s):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", s or ""))).strip()


def parse_date(s):
    try:
        d = parsedate_to_datetime(s)
        return d if d.tzinfo else d.replace(tzinfo=dt.timezone.utc)
    except Exception:
        pass
    try:  # ISO dates used by some feeds
        d = dt.datetime.fromisoformat((s or "").strip().replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=dt.timezone.utc)
    except Exception:
        return None


B = "https://feeds.bbci.co.uk/news"
HINDU = "https://www.thehindu.com"
GUARD = "https://www.theguardian.com"
HT = "https://www.hindustantimes.com/feeds/rss"
IE = "https://indianexpress.com"
TOI = "https://timesofindia.indiatimes.com/rssfeeds"
OUTLETS = {
    "BBC News": {"region": "global", "feeds": {
        "Top stories": f"{B}/rss.xml", "World": f"{B}/world/rss.xml", "India": f"{B}/world/asia/india/rss.xml",
        "Business": f"{B}/business/rss.xml", "Technology": f"{B}/technology/rss.xml",
        "Science": f"{B}/science_and_environment/rss.xml", "Health": f"{B}/health/rss.xml",
        "Sports": "https://feeds.bbci.co.uk/sport/rss.xml", "Entertainment": f"{B}/entertainment_and_arts/rss.xml"}},
    "The Hindu": {"region": "india", "feeds": {
        "Top stories": f"{HINDU}/news/feeder/default.rss", "India": f"{HINDU}/news/national/feeder/default.rss",
        "World": f"{HINDU}/news/international/feeder/default.rss", "Karnataka": f"{HINDU}/news/national/karnataka/feeder/default.rss",
        "Business": f"{HINDU}/business/feeder/default.rss", "Technology": f"{HINDU}/sci-tech/technology/feeder/default.rss",
        "Science": f"{HINDU}/sci-tech/science/feeder/default.rss", "Sports": f"{HINDU}/sport/feeder/default.rss",
        "Entertainment": f"{HINDU}/entertainment/feeder/default.rss"}},
    "Al Jazeera": {"region": "global", "feeds": {
        "Top stories": "https://www.aljazeera.com/xml/rss/all.xml", "World": "https://www.aljazeera.com/xml/rss/all.xml"}},
    "The Guardian": {"region": "global", "feeds": {
        "Top stories": f"{GUARD}/international/rss", "World": f"{GUARD}/world/rss", "Business": f"{GUARD}/business/rss",
        "Technology": f"{GUARD}/technology/rss", "Science": f"{GUARD}/science/rss", "Sports": f"{GUARD}/sport/rss",
        "Entertainment": f"{GUARD}/culture/rss"}},
    "NPR": {"region": "global", "feeds": {
        "Top stories": "https://feeds.npr.org/1001/rss.xml", "World": "https://feeds.npr.org/1004/rss.xml",
        "Business": "https://feeds.npr.org/1006/rss.xml", "Science": "https://feeds.npr.org/1007/rss.xml",
        "Technology": "https://feeds.npr.org/1019/rss.xml", "Health": "https://feeds.npr.org/1128/rss.xml"}},
    "NDTV": {"region": "india", "feeds": {
        "Top stories": "https://feeds.feedburner.com/ndtvnews-top-stories", "India": "https://feeds.feedburner.com/ndtvnews-india-news",
        "World": "https://feeds.feedburner.com/ndtvnews-world-news", "Sports": "https://feeds.feedburner.com/ndtvsports-latest"}},
    "The Indian Express": {"region": "india", "feeds": {
        "Top stories": f"{IE}/feed/", "India": f"{IE}/section/india/feed/", "World": f"{IE}/section/world/feed/",
        "Business": f"{IE}/section/business/feed/", "Technology": f"{IE}/section/technology/feed/",
        "Sports": f"{IE}/section/sports/feed/", "Entertainment": f"{IE}/section/entertainment/feed/",
        "Health": f"{IE}/section/lifestyle/health/feed/"}},
    "Times of India": {"region": "india", "feeds": {
        "Top stories": "https://timesofindia.indiatimes.com/rssfeedstopstories.cms", "India": f"{TOI}/-2128936835.cms",
        "World": f"{TOI}/296589292.cms", "Business": f"{TOI}/1898055.cms", "Technology": f"{TOI}/66949542.cms",
        "Sports": f"{TOI}/4719148.cms", "Entertainment": f"{TOI}/1081479906.cms"}},
    "Hindustan Times": {"region": "india", "feeds": {
        "Top stories": f"{HT}/topnews/rssfeed.xml", "India": f"{HT}/india-news/rssfeed.xml", "World": f"{HT}/world-news/rssfeed.xml",
        "Business": f"{HT}/business/rssfeed.xml", "Sports": f"{HT}/sports/rssfeed.xml",
        "Entertainment": f"{HT}/entertainment/rssfeed.xml", "Technology": f"{HT}/technology/rssfeed.xml"}},
}
SOURCE_CHOICES = ["All trusted media", "Indian media", "Global media"]


def clean_author(v):
    v = strip_tags(v or "")
    m = re.search(r"\(([^)]+)\)", v)
    if m:
        v = m.group(1)
    return "" if ("@" in v or len(v) > 60) else v.strip()


def parse_rss(text, provider, outlet=""):
    items = []
    for it in ET.fromstring(text).iter("item"):
        d = {}
        for ch in it:
            tag = ch.tag.split("}")[-1].lower()
            if tag in ("thumbnail", "content", "enclosure") and not d.get("img"):
                u = ch.get("url", "")
                if u.startswith("https://") and re.search(r"\.(jpe?g|png|webp)|image", u + ch.get("type", "") + ch.get("medium", ""), re.I):
                    d["img"] = u
            d.setdefault(tag, (ch.text or "").strip())
        title, link = strip_tags(d.get("title", "")), d.get("link", "")
        if provider == "bing":
            link = parse_qs(urlparse(link).query).get("url", [link])[0]
        source = d.get("source", "") or ""
        if provider == "google" and source and title.endswith(" - " + source):
            title = title[: -len(source) - 3]
        desc = strip_tags(d.get("description", ""))
        enc = strip_tags(d.get("encoded", ""))
        if len(enc) > len(desc):
            desc = enc
        if desc.lower().startswith(title.lower()[:40]) and len(desc) < len(title) + 40:
            desc = ""
        img = d.get("img") or d.get("image", "")
        items.append({"title": title, "source": outlet or source or provider.title(), "url": link,
                      "published": parse_date(d.get("pubdate", "") or d.get("date", "") or d.get("updated", "")),
                      "text": (desc or title)[:5000],
                      "author": clean_author(d.get("creator") or d.get("author", "")),
                      "image": img if img.startswith("https://") else ""})
    return items


def fetch_newsapi(query, cat, n):
    key = cfg("NEWSAPI_KEY")
    nc = {"Business": "business", "Technology": "technology", "Science": "science",
          "Health": "health", "Sports": "sports", "Entertainment": "entertainment"}
    if query or cat == "World":
        url = "https://newsapi.org/v2/everything"
        params = {"q": query or "world", "language": "en", "sortBy": "publishedAt", "pageSize": n}
    else:
        url = "https://newsapi.org/v2/top-headlines"
        params = {"country": "in", "pageSize": n}
        if cat in nc:
            params["category"] = nc[cat]
    r = requests.get(url, params=params, headers={"X-Api-Key": key}, timeout=15)
    r.raise_for_status()
    out = []
    for a in r.json().get("articles", []):
        txt = strip_tags(" ".join(filter(None, [a.get("description"), (a.get("content") or "").split("[+")[0]])))
        pub = None
        try:
            pub = dt.datetime.fromisoformat((a.get("publishedAt") or "").replace("Z", "+00:00"))
        except Exception:
            pass
        out.append({"title": strip_tags(a.get("title") or ""), "source": (a.get("source") or {}).get("name", ""),
                    "author": clean_author(a.get("author") or ""),
                    "url": a.get("url", ""), "published": pub, "text": txt or a.get("title", ""),
                    "image": (a.get("urlToImage") or "") if (a.get("urlToImage") or "").startswith("https://") else ""})
    return out


def _rss_bing(query, cat):
    qtxt = query or (f"{cat} news India" if cat not in (None, "Top stories") else "India top news")
    r = requests.get("https://www.bing.com/news/search", params={"q": qtxt, "format": "rss", "mkt": "en-IN"},
                     headers=UA, timeout=6)
    r.raise_for_status()
    return parse_rss(r.text, "bing")


def _rss_google(query, cat):
    base, tail = "https://news.google.com/rss", "hl=en-IN&gl=IN&ceid=IN:en"
    if query:
        url = f"{base}/search?q={quote_plus(query + ' when:1d')}&{tail}"
    elif CATEGORIES.get(cat):
        url = f"{base}/headlines/section/topic/{CATEGORIES[cat]}?{tail}"
    else:
        url = f"{base}?{tail}"
    r = requests.get(url, headers=UA, timeout=6)
    r.raise_for_status()
    return parse_rss(r.text, "google")


def fetch_rss(query, cat):
    """Ask Bing and Google at the same time; combine what comes back."""
    out = []
    with ThreadPoolExecutor(max_workers=2) as ex:
        futs = [ex.submit(_rss_bing, query, cat), ex.submit(_rss_google, query, cat)]
        for f in futs:
            try:
                out += f.result(timeout=9)
            except Exception:
                continue
    return out


def fetch_outlet(name, cat):
    url = OUTLETS[name]["feeds"].get(cat)
    if not url:
        return []
    r = requests.get(url, headers=BROWSER_UA, timeout=8)
    r.raise_for_status()
    return parse_rss(r.text, "direct", name)


def outlets_for(choice):
    if choice == "Indian media":
        return [k for k, v in OUTLETS.items() if v["region"] == "india"]
    if choice == "Global media":
        return [k for k, v in OUTLETS.items() if v["region"] == "global"]
    return [choice] if choice in OUTLETS else list(OUTLETS)


def interleave(lists):
    out, i = [], 0
    while any(i < len(l) for l in lists):
        for l in lists:
            if i < len(l):
                out.append(l[i])
        i += 1
    return out


def _gather(names, feed_cat, query):
    per = []
    with ThreadPoolExecutor(max_workers=9) as ex:
        futs = [ex.submit(fetch_outlet, nm, feed_cat) for nm in names]
        for f in futs:
            try:
                per.append(f.result(timeout=9)[:30])
            except Exception:
                per.append([])
    if query:
        words = re.findall(r"\w{3,}", query.lower())
        per = [[a for a in l if any(w in (a["title"] + " " + a["text"]).lower() for w in words)] for l in per]
    return interleave(per)


def _age_h(a):
    return (now() - a["published"]).total_seconds() / 3600


@st.cache_data(ttl=600, show_spinner=False)
def _fetch_live(query, cat, n, kids, source):
    """Publisher feeds first, then other outlets, then search engines. Newest first, last 24 hours preferred.
    Returns (articles, note). Raises if nothing at all was found."""
    want = n * 2 if kids else n
    sq = query or ("Karnataka" if cat == "Karnataka" else "")
    feed_cat = "Top stories" if query else cat
    items = _gather(outlets_for(source), feed_cat, query)
    if len(items) < want and source in OUTLETS:  # chosen outlet had too little: widen to the others
        items += _gather([k for k in OUTLETS if k != source], feed_cat, query)
    if len(items) < want:
        extra = []
        try:
            if cfg("NEWSAPI_KEY"):
                extra = fetch_newsapi(sq, cat, min(want, 100))
        except Exception:
            extra = []
        if not extra:
            extra = fetch_rss(sq or None, cat)
        items += extra
    if kids:
        items = [a for a in items if not KIDS_BLOCK.search(a["title"] + " " + a["text"])]
    seen, uniq = set(), []
    for a in items:
        k = a["title"].lower()[:60]
        if a["title"] and a["url"] and k not in seen:
            seen.add(k)
            uniq.append(a)
    if not uniq:
        raise RuntimeError("no stories")
    dated = sorted([a for a in uniq if a["published"]], key=lambda a: a["published"], reverse=True)
    undated = [a for a in uniq if not a["published"]]
    note = ""
    pick = [a for a in dated if _age_h(a) <= 24]
    if len(pick) < min(n, 8):
        pick = [a for a in dated if _age_h(a) <= 48]
        note = "Not many stories were published in the last 24 hours, so a few from yesterday are included."
        if len(pick) < 3:
            pick = dated + undated
            note = "Very few fresh stories were found, so some may be older."
    return pick[:n], note


def fetch_news(query, cat, n, kids, source="All trusted media"):
    """Returns (articles, note). Never raises."""
    try:
        return _fetch_live(query, cat, n, kids, source)
    except Exception:
        return DEMO_ARTICLES[:n], "Live news couldn't be loaded right now, so these are sample stories. Tap Get news to try again."


def public_url(url):
    try:
        p = urlparse(url)
        if p.scheme not in ("http", "https") or not p.hostname:
            return False
        for info in socket.getaddrinfo(p.hostname, None):
            ip = ipaddress.ip_address(info[4][0])
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
                return False
        return True
    except Exception:
        return False


JUNK = re.compile(r"(cookie|subscribe|sign up|newsletter|advertisement|all rights reserved|follow us|click here|"
                  r"read more:|also read|download the app|whatsapp channel|terms of use|privacy policy)", re.I)


def _extract(url):
    if not public_url(url):
        return ""
    r = requests.get(url, headers=UA, timeout=6, allow_redirects=True)
    if "text/html" not in r.headers.get("content-type", ""):
        return ""
    body = r.text[:900000]
    m = re.search(r"<article[^>]*>(.*?)</article>", body, flags=re.S | re.I)
    paras = [strip_tags(p) for p in re.findall(r"<p[^>]*>(.*?)</p>", m.group(1) if m else body, flags=re.S | re.I)]
    return " ".join(p for p in paras if len(p) > 60 and not JUNK.search(p))[:7000]


@st.cache_data(ttl=3600, show_spinner=False)
def extract_article(url):
    """Best-effort article body. Gives up after 7 seconds so the app never hangs."""
    ex = ThreadPoolExecutor(max_workers=1)
    try:
        return ex.submit(_extract, url).result(timeout=7)
    except Exception:
        return ""
    finally:
        ex.shutdown(wait=False)


# ----------------------------------------------------------------------------
# Analysis: summary, sentiment, credibility
# ----------------------------------------------------------------------------
def short_summary(a, limit=320):
    t = a["text"].strip()
    sents = re.split(r"(?<=[.!?])\s+", t)
    out = ""
    for s in sents:
        if len(out) + len(s) > limit and out:
            break
        out += (" " if out else "") + s
    return out[:limit + 80]


@st.cache_resource
def _vader():
    from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
    return SentimentIntensityAnalyzer()


def sentiment(text):
    try:
        c = _vader().polarity_scores(text)["compound"]
    except Exception:
        pos = len(re.findall(r"\b(win|wins|launch|rolls out|success|boost|growth|record|award|praise|safe)\b", text, re.I))
        neg = len(re.findall(r"\b(crash|fall|loss|attack|death|fail|crisis|glitch|ban|fire|flood)\b", text, re.I))
        c = 0.4 * (pos - neg)
    if c >= 0.2:
        return "Positive", "😊", "pos"
    if c <= -0.2:
        return "Negative", "😟", "neg"
    return "Neutral", "😐", "neu"


def credibility(a):
    """A transparent heuristic - NOT a fact-check."""
    score, why = 50, []
    src = (a["source"] or "").lower()
    if any(t in src for t in TRUSTED_SOURCES):
        score += 25
        why.append("Well-known news source")
    elif src and src != "sample story":
        why.append("Source not on our known list - cross-check it")
    hits = [w for w in CLICKBAIT if w in a["title"].lower()]
    if hits:
        score -= min(30, 10 * len(hits))
        why.append("Sensational wording: " + ", ".join(hits[:2]))
    letters = [c for c in a["title"] if c.isalpha()]
    if letters and sum(c.isupper() for c in letters) / len(letters) > 0.5 and len(letters) > 12:
        score -= 10
        why.append("Headline is mostly CAPITALS")
    if a["title"].count("!") >= 2:
        score -= 10
        why.append("Many exclamation marks")
    if len(a["text"]) > 150:
        score += 8
        why.append("Gives details, not only a headline")
    score = max(5, min(95, score))
    label = "Looks reliable" if score >= 70 else "Check other sources" if score >= 45 else "Be careful"
    color = "#3DDC97" if score >= 70 else "#FFC93C" if score >= 45 else "#FF6B6B"
    return score, label, color, why


def time_ago(d):
    if not d:
        return ""
    s = max(0, int((now() - d).total_seconds()))
    if s < 3600:
        return f"{max(1, s // 60)} min ago"
    if s < 86400:
        return f"{s // 3600} h ago"
    return d.astimezone(IST).strftime("%d %b %Y")


def guess_emoji(text, cat="Top stories"):
    t = " " + text.lower() + " "
    for k, e in EMOJI_HINTS.items():
        if k in t:
            return e
    return CAT_EMOJI.get(cat, "📰")


# ----------------------------------------------------------------------------
# Translation (chunked, retried, parallel, cached)
# ----------------------------------------------------------------------------
def _chunks(text, size=4000):
    parts, cur = [], ""
    for s in re.split(r"(?<=[.!?])\s+", text):
        if len(cur) + len(s) + 1 > size and cur:
            parts.append(cur)
            cur = ""
        cur += (" " if cur else "") + s
    if cur:
        parts.append(cur)
    return parts or [text]


def _gtx(text, code):
    out = []
    for c in _chunks(text, 1200):
        r = requests.get("https://translate.googleapis.com/translate_a/single", headers=UA, timeout=8,
                         params={"client": "gtx", "sl": "auto", "tl": code, "dt": "t", "q": c})
        r.raise_for_status()
        out.append("".join(seg[0] for seg in r.json()[0] if seg and seg[0]))
    return " ".join(out)


def _deep(text, code):
    from deep_translator import GoogleTranslator
    return " ".join(GoogleTranslator(source="auto", target=code).translate(c) for c in _chunks(text, 4000))


def _mymemory(text, code):
    out = []
    for c in _chunks(text, 450):
        r = requests.get("https://api.mymemory.translated.net/get", timeout=8,
                         params={"q": c, "langpair": f"en|{code}"})
        r.raise_for_status()
        j = r.json()
        t = html.unescape(j.get("responseData", {}).get("translatedText", ""))
        if str(j.get("responseStatus")) != "200" or not t:
            raise RuntimeError(str(j.get("responseDetails", "no result"))[:80])
        out.append(t)
    return " ".join(out)


def _tr(text, code):
    errs = []
    for name, fn in (("google", _gtx), ("google2", _deep), ("mymemory", _mymemory)):
        try:
            return fn(text, code)
        except Exception as e:
            errs.append(f"{name}: {type(e).__name__} {str(e)[:60]}")
    raise RuntimeError(" | ".join(errs))


@st.cache_data(ttl=86400, show_spinner=False)
def translate(text, code):
    if code == "en" or not text.strip():
        return text
    return _tr(text, code)


@st.cache_data(ttl=3600, show_spinner=False)
def translate_many(texts, code):
    if code == "en":
        return list(texts)

    def one(t):
        try:
            return _tr(t, code), None
        except Exception as e:
            return None, str(e)
    with ThreadPoolExecutor(max_workers=6) as ex:
        res = list(ex.map(one, texts))
    if texts and all(r[0] is None for r in res):
        raise RuntimeError(next((r[1] for r in res if r[1]), "translation failed"))
    return [r[0] if r[0] is not None else t for r, t in zip(res, texts)]


def llm_translate(texts, code):
    """Backup: translate with the AI helper in one request. Returns list or None."""
    lang = next((k.split(" ")[0] for k, v in LANGS.items() if v[0] == code), code)
    numbered = "\n".join(f"{i + 1}. {' '.join(t.split())}" for i, t in enumerate(texts))
    out = llm("You are a precise translator.", [{"role": "user", "content":
              f"Translate each numbered line into {lang}. Keep the same numbering, one line per item, no extra text.\n{numbered}"}], 1500)
    if not out:
        return None
    res = {}
    for line in out.splitlines():
        m = re.match(r"\s*(\d+)[.)]\s*(.+)", line)
        if m:
            res[int(m.group(1))] = m.group(2).strip()
    return [res.get(i + 1) or texts[i] for i in range(len(texts))] if res else None


def tr_safe(text):
    """Translate to the user's chosen language; fall back to AI, then to English with the reason."""
    code = LANGS[st.session_state.lang][0]
    if code == "en":
        return text
    try:
        return translate(text, code)
    except Exception as e:
        alt = llm_translate([text], code)
        if alt:
            return alt[0]
        st.warning("Translation is not working right now, so this is shown in English.")
        st.caption(f"Details: {str(e)[:200]}")
        return text


# ----------------------------------------------------------------------------
# Dictionary
# ----------------------------------------------------------------------------
@st.cache_data(ttl=7 * 86400, show_spinner=False)
def define(word):
    try:
        r = requests.get(f"https://api.dictionaryapi.dev/api/v2/entries/en/{quote_plus(word.lower())}", timeout=8)
        if r.status_code != 200:
            return None
        e = r.json()[0]
        lines = [f"**{e.get('word', word)}**" + (f"  ·  _{e['phonetic']}_" if e.get("phonetic") else "")]
        for m in e.get("meanings", [])[:2]:
            d = m["definitions"][0]
            lines.append(f"- *{m.get('partOfSpeech', '')}*: {d['definition']}")
            if d.get("example"):
                lines.append(f"  - Example: “{d['example']}”")
        return "\n".join(lines)
    except Exception:
        return None


def hard_words(text, k=4):
    seen, out = set(), []
    for w in re.findall(r"[A-Za-z]{9,}", text):
        lw = w.lower()
        if lw not in seen:
            seen.add(lw)
            out.append(lw)
    return out[:k]


def dictionary_intent(msg):
    m = msg.strip().lower().rstrip("?.! ")
    pats = [r"^(?:define|meaning of|dictionary|word)\s*:?\s+([a-z][a-z\- ]{1,30})$",
            r"^what(?:'s| is)? the meaning of\s+([a-z][a-z\- ]{1,30})$",
            r"^what does\s+([a-z][a-z\- ]{1,30})\s+mean$", r"^([a-z][a-z\-]{2,24})$"]
    for p in pats:
        mt = re.match(p, m)
        if mt:
            return mt.group(1).strip()
    return None


# ----------------------------------------------------------------------------
# Story Studio content
# ----------------------------------------------------------------------------
STRICT = ("Use ONLY facts that appear in the provided text. Never add facts, numbers, names, dates, quotes or "
          "background that are not in the text. If something is not stated, say 'Not stated in the source'. "
          "Keep names and numbers exactly as written.")


def article_text(a, n=3000):
    return (a.get("full") or a["text"])[:n]


def explain_simply(a):
    kids = st.session_state.kids
    out = llm(SYSTEM_BASE, [{"role": "user", "content":
        f"Audience: {audience(kids)}.\nExplain this news in 4-5 short sentences, then one line starting "
        f"'Why it matters:'. Do not use bullet points. " + STRICT + f"\nTitle: {a['title']}\nText: {article_text(a, 4500)}"}], 450)
    if out:
        return out
    return short_summary(a, 260) + "\n\n(Tip: the AI helper gives a child-friendly explanation here.)"


def sentences(text, lo=30, hi=420):
    return [t.strip() for t in re.split(r"(?<=[.!?])\s+", text) if lo <= len(t.strip()) <= hi]


def make_briefing(a):
    """Point-wise briefing. Returns (markdown, written_by_ai, based_on_full_text)."""
    kids = st.session_state.kids
    full = len(a.get("full", "")) >= 500
    src = article_text(a, 6000) if full else a["text"]
    long_ok = len(src) > 1500
    out = llm(SYSTEM_BASE + " " + STRICT, [{"role": "user", "content":
        f"Write a point-wise news briefing for {audience(kids)}. Use exactly these Markdown headings, each followed by "
        "short bullet points ('- '):\n**📌 In one line**\n**🧾 What happened**\n**👥 Who and where**\n"
        "**🔢 Key facts and numbers**\n**💡 Why it matters**\n**⏭️ What to watch next** (only if the text says; "
        "otherwise write 'Not stated in the source').\n"
        + ("Aim for about 350-450 words in total.\n" if long_ok else
           "The text is short, so write fewer bullets instead of guessing.\n")
        + f"Title: {a['title']}\nSource: {a['source']}\nText: {src}"}], 1300)
    if out:
        return out, True, full
    pts = sentences(src)[: 10 if full else 5] or [a["title"]]
    md = ("**📌 In one line**\n- " + a["title"] + "\n\n**🧾 Key points from the article**\n"
          + "\n".join("- " + p for p in pts))
    return md, False, full


def translate_markdown(md, code):
    """Translate a Markdown briefing line by line so bullets and headings survive."""
    if code == "en":
        return md
    rows = []
    for line in md.splitlines():
        m = re.match(r"^(\s*(?:[-*•]\s+|#+\s+)?)(\*\*)?(.*?)(\*\*)?\s*$", line)
        rows.append((m.group(1), bool(m.group(2)), m.group(3)) if m and m.group(3) else None)
    bodies = tuple(r[2] for r in rows if r)
    try:
        tr = list(translate_many(bodies, code))
    except Exception:
        tr = llm_translate(list(bodies), code)
        if not tr:
            st.warning("Translation is not working right now, so this is shown in English.")
            return md
    it, out = iter(tr), []
    for r in rows:
        if r is None:
            out.append("")
        else:
            t = next(it)
            out.append(f"{r[0]}**{t}**" if r[1] else f"{r[0]}{t}")
    return "\n".join(out)


ACTIONS = {"wave", "jump", "point", "think", "cheer", "surprise"}
MOTIONS = {"float", "drive", "fly", "spin", "shake", "zoom"}
MOTION_HINT = {"🚌": "drive", "🚆": "drive", "🚗": "drive", "🚇": "drive", "✈️": "fly", "🚀": "fly", "🌍": "spin",
               "🔥": "shake", "⚡": "shake", "🏏": "zoom", "⚽": "zoom", "📈": "zoom"}
DEFAULT_ACTIONS = ["wave", "point", "think", "jump", "point", "surprise", "cheer", "wave"]
OUTRO = (f"That's your {APP_NAME} update! Always open the source link to double-check the facts. "
         "Stay curious, and see you next time. Bye bye!")


def _finish_panels(panels, em):
    for i, p in enumerate(panels):
        if p.get("action") not in ACTIONS:
            p["action"] = DEFAULT_ACTIONS[i % len(DEFAULT_ACTIONS)]
        first = p["emoji"].strip()[:2] if p.get("emoji") else em
        p["motion"] = p.get("motion") if p.get("motion") in MOTIONS else MOTION_HINT.get(first, "float")
    return panels


def cartoon_script(a):
    """8-panel comic (about 45-60 seconds). Facts come only from the article text."""
    kids = st.session_state.kids
    em = guess_emoji(a["title"] + " " + a["text"])
    out = llm(SYSTEM_BASE + " " + STRICT, [{"role": "user", "content":
        "Write an animated 7-panel comic script explaining this news, starring Newsie the owl (explains) and Kiki the "
        f"tiger cub (asks questions). Audience: {audience(kids)}. Flow: 1 hook, 2 what happened, 3 who and where, "
        "4 an important fact, 5 another fact or number, 6 why it matters, 7 a recap of the 3 things to remember. "
        "Each text must be 15-30 words. Reply with ONLY a JSON array of 7 objects: "
        '{"speaker":"Newsie" or "Kiki","emoji":"1-3 emojis for the scene","text":"...",'
        '"action":"wave|jump|point|think|cheer|surprise","motion":"float|drive|fly|spin|shake|zoom"}.\n'
        f"Title: {a['title']}\nText: {article_text(a, 4500)}"}], 1500)
    if out:
        try:
            arr = json.loads(out[out.index("["): out.rindex("]") + 1])
            panels = [{"speaker": "Kiki" if str(p.get("speaker", "")).lower().startswith("k") else "Newsie",
                       "emoji": str(p.get("emoji", em))[:12], "text": str(p.get("text", ""))[:260],
                       "action": str(p.get("action", "")).lower(), "motion": str(p.get("motion", "")).lower()}
                      for p in arr[:7] if p.get("text")]
            if len(panels) >= 5:
                panels.append({"speaker": "Newsie", "emoji": "👋🎉", "text": OUTRO, "action": "wave", "motion": "zoom"})
                return _finish_panels(panels, em), True
        except Exception:
            pass
    facts = sentences(article_text(a, 4000), 30, 230)
    first = facts[0] if facts else a["title"]
    rest = facts[1:5]
    base = [("Newsie", em, f"Hello friends! Here is today's news: {a['title'][:150]}"),
            ("Kiki", "🤔", "Ooh! Tell me more, Newsie. What exactly happened?"),
            ("Newsie", em, first)]
    for i, f in enumerate(rest):
        base.append(("Kiki" if i % 2 == 0 else "Newsie", "📌" if i % 2 == 0 else em, f))
    base.append(("Kiki", "🧠", "So the big thing to remember is: " + a["title"][:140]))
    base.append(("Newsie", "👋🎉", OUTRO))
    panels = [{"speaker": sp, "emoji": e, "text": t} for sp, e, t in base]
    return _finish_panels(panels, em), False


CARTOON_TEMPLATE = r"""<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<link href="https://fonts.googleapis.com/css2?family=Baloo+2:wght@700;800&family=Nunito:wght@700;800&display=swap" rel="stylesheet">
<style>
*{box-sizing:border-box}html,body{margin:0;font-family:Nunito,system-ui,sans-serif;color:#1c1650;background:transparent}
.stage{background:linear-gradient(180deg,#7fd6ff 0%,#c9f0ff 55%,#9be08f 55%,#6cc56a 100%);border:4px solid #1c1650;border-radius:22px;
 box-shadow:6px 6px 0 #1c1650;padding:12px 12px 14px;position:relative;overflow:hidden}
.title{font:800 15px 'Baloo 2';color:#1c1650;background:#FFC93C;display:inline-block;padding:3px 12px;border-radius:99px;max-width:100%;
 white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.scene{font-size:64px;text-align:center;height:84px;line-height:84px;margin-top:4px}
.scene.pop{animation:pop .5s ease-out}
.chars{display:flex;justify-content:center;gap:18px;align-items:flex-end;min-height:150px}
.char{width:118px;opacity:.55;transform:scale(.82);transform-origin:bottom center;transition:transform .3s,opacity .3s}
.char.active{opacity:1;transform:scale(1.08)}
.char svg{width:100%;height:auto;display:block;overflow:visible}
.eyes{animation:blink 4.2s infinite;transform-box:fill-box;transform-origin:center}
.char.active.talk .beak,.char.active.talk .mouth{animation:chomp .24s infinite}
.beak,.mouth{transform-box:fill-box;transform-origin:50% 0}
.char.active.talk{animation:bob .5s ease-in-out infinite}
.char.active.talk .wl{animation:flapl .5s ease-in-out infinite}.char.active.talk .wr{animation:flapr .5s ease-in-out infinite}
.wl,.wr{transform-box:fill-box}.wl{transform-origin:100% 20%}.wr{transform-origin:0% 20%}
.bubble{background:#fff;border:4px solid #1c1650;border-radius:18px;padding:10px 14px;margin-top:10px;min-height:86px;font-weight:800;font-size:16px;line-height:1.4;position:relative}
.bubble:before{content:"";position:absolute;top:-14px;left:50%;margin-left:-12px;border:12px solid transparent;border-bottom-color:#1c1650;border-top:0}
.bubble b{display:block;font:800 13px 'Baloo 2';color:#7a3cff}
.dots{display:flex;gap:6px;justify-content:center;margin:10px 0 2px}.dots i{width:10px;height:10px;border-radius:50%;background:#fff;border:2px solid #1c1650}.dots i.on{background:#FF6B6B}
.ctl{display:flex;gap:10px;justify-content:center;flex-wrap:wrap;margin-top:8px}
button{font:800 16px Nunito;background:#FFC93C;color:#1c1650;border:3px solid #1c1650;border-radius:14px;padding:10px 18px;min-height:46px;cursor:pointer;box-shadow:0 4px 0 #1c1650}
button:active{transform:translateY(3px);box-shadow:none}button:focus-visible{outline:3px solid #fff;outline-offset:2px}
.hint{font-size:12px;color:#1c1650;text-align:center;margin-top:8px;opacity:.8}
.stage>*{position:relative;z-index:1}
.stage:before,.stage:after{content:"☁️";position:absolute;top:28px;left:-70px;font-size:42px;opacity:.85;animation:cloud 26s linear infinite;z-index:0}
.stage:after{top:78px;font-size:30px;animation-duration:38s;animation-delay:-14s}
.scene{display:block}
.m-float{animation:pop .5s ease-out,bob 2.6s .5s ease-in-out infinite}
.m-drive{animation:pop .5s ease-out,drive 2.6s .5s ease-in-out infinite alternate}
.m-fly{animation:pop .5s ease-out,fly 2s .5s ease-in-out infinite alternate}
.m-spin{animation:pop .5s ease-out,spin 4s .5s linear infinite}
.m-shake{animation:pop .5s ease-out,shake .3s .5s linear infinite}
.m-zoom{animation:pop .5s ease-out,zoom 1.4s .5s ease-in-out infinite alternate}
.char svg{transform-origin:50% 100%}
.char.act-jump svg{animation:jump .7s ease-in-out infinite}
.char.act-wave svg{animation:wave .7s ease-in-out infinite}
.char.act-point svg{animation:point .9s ease-in-out infinite}
.char.act-think svg{animation:think 1.6s ease-in-out infinite}
.char.act-cheer svg{animation:cheer .55s ease-in-out infinite}
.char.act-surprise svg{animation:surprise .4s ease-in-out infinite}
.cf{position:absolute;top:-20px;font-size:22px;animation:fall 2.8s linear forwards;z-index:5;pointer-events:none}
@keyframes cloud{to{left:110%}}
@keyframes drive{from{transform:translateX(-120px) scaleX(1)}to{transform:translateX(120px)}}
@keyframes fly{from{transform:translateY(8px) rotate(-8deg)}to{transform:translateY(-18px) rotate(8deg)}}
@keyframes spin{to{transform:rotate(360deg)}}
@keyframes shake{25%{transform:translateX(-5px)}75%{transform:translateX(5px)}}
@keyframes zoom{from{transform:scale(.9)}to{transform:scale(1.22)}}
@keyframes jump{50%{transform:translateY(-18px) scale(1.04)}}
@keyframes wave{50%{transform:rotate(7deg)}0%,100%{transform:rotate(-7deg)}}
@keyframes point{50%{transform:translateX(12px) rotate(5deg)}}
@keyframes think{50%{transform:rotate(-9deg) translateY(-3px)}}
@keyframes cheer{50%{transform:translateY(-14px) rotate(9deg)}0%,100%{transform:rotate(-9deg)}}
@keyframes surprise{50%{transform:scale(1.12)}}
@keyframes fall{to{transform:translateY(560px) rotate(540deg);opacity:.9}}
@keyframes blink{0%,94%,100%{transform:scaleY(1)}97%{transform:scaleY(.08)}}
@keyframes chomp{50%{transform:scaleY(1.7)}}
@keyframes bob{50%{translate:0 -6px}}
@keyframes flapl{50%{transform:rotate(-24deg)}}@keyframes flapr{50%{transform:rotate(24deg)}}
@keyframes pop{0%{transform:scale(.3) rotate(-12deg);opacity:0}70%{transform:scale(1.15)}100%{transform:none;opacity:1}}
@media (prefers-reduced-motion:reduce){*{animation:none!important}}
</style></head><body>
<div class="stage" id="stage">
 <span class="title">__TITLE__</span>
 <div class="scene" id="scene">📰</div>
 <div class="chars">
  <div class="char active" id="Newsie" aria-label="Newsie the owl">
   <svg viewBox="0 0 120 140"><g class="wl"><ellipse cx="14" cy="92" rx="13" ry="32" fill="#6D3FD1"/></g><g class="wr"><ellipse cx="106" cy="92" rx="13" ry="32" fill="#6D3FD1"/></g>
    <ellipse cx="60" cy="88" rx="42" ry="48" fill="#8B5CF6"/><ellipse cx="60" cy="102" rx="27" ry="30" fill="#EDE4FF"/>
    <path d="M24 52 L30 20 L50 40Z" fill="#6D3FD1"/><path d="M96 52 L90 20 L70 40Z" fill="#6D3FD1"/>
    <g class="eyes"><circle cx="43" cy="63" r="19" fill="#fff" stroke="#1c1650" stroke-width="3"/><circle cx="77" cy="63" r="19" fill="#fff" stroke="#1c1650" stroke-width="3"/>
     <circle cx="45" cy="65" r="8" fill="#1c1650"/><circle cx="75" cy="65" r="8" fill="#1c1650"/><circle cx="48" cy="62" r="3" fill="#fff"/><circle cx="78" cy="62" r="3" fill="#fff"/></g>
    <g class="beak"><path d="M51 78 L69 78 L60 98Z" fill="#FFB020" stroke="#1c1650" stroke-width="2.5" stroke-linejoin="round"/></g>
    <path d="M45 134 l-5 8 M52 134 l-2 9 M68 134 l2 9 M75 134 l5 8" stroke="#FFB020" stroke-width="4" stroke-linecap="round"/>
    <rect x="30" y="2" width="60" height="14" rx="4" fill="#1c1650"/><rect x="54" y="-4" width="12" height="8" fill="#1c1650"/></svg></div>
  <div class="char" id="Kiki" aria-label="Kiki the tiger cub">
   <svg viewBox="0 0 120 140"><ellipse cx="60" cy="118" rx="34" ry="28" fill="#FF9F43" stroke="#1c1650" stroke-width="3"/><ellipse cx="60" cy="126" rx="20" ry="18" fill="#FFE3BF"/>
    <circle cx="28" cy="38" r="15" fill="#FF9F43" stroke="#1c1650" stroke-width="3"/><circle cx="92" cy="38" r="15" fill="#FF9F43" stroke="#1c1650" stroke-width="3"/>
    <circle cx="28" cy="38" r="7" fill="#FFB3C1"/><circle cx="92" cy="38" r="7" fill="#FFB3C1"/>
    <circle cx="60" cy="68" r="44" fill="#FF9F43" stroke="#1c1650" stroke-width="3"/>
    <path d="M60 25 v14 M44 28 l4 12 M76 28 l-4 12 M18 62 h12 M18 76 h12 M102 62 h-12 M102 76 h-12" stroke="#1c1650" stroke-width="5" stroke-linecap="round"/>
    <ellipse cx="60" cy="86" rx="22" ry="16" fill="#FFE3BF"/>
    <g class="eyes"><circle cx="42" cy="62" r="11" fill="#fff" stroke="#1c1650" stroke-width="3"/><circle cx="78" cy="62" r="11" fill="#fff" stroke="#1c1650" stroke-width="3"/>
     <circle cx="44" cy="64" r="5.5" fill="#1c1650"/><circle cx="76" cy="64" r="5.5" fill="#1c1650"/><circle cx="46" cy="62" r="2" fill="#fff"/><circle cx="78" cy="62" r="2" fill="#fff"/></g>
    <path d="M52 78 h16 l-8 8z" fill="#FF6B8A" stroke="#1c1650" stroke-width="2" stroke-linejoin="round"/>
    <g class="mouth"><path d="M48 90 q12 14 24 0 z" fill="#8f1d2c" stroke="#1c1650" stroke-width="2.5" stroke-linejoin="round"/></g></svg></div>
 </div>
 <div class="bubble" aria-live="polite"><b id="who"></b><span id="txt"></span></div>
 <div class="dots" id="dots"></div>
 <div class="ctl"><button id="play">▶ Play the story</button><button id="next">⏭ Next</button></div>
 <div class="hint" id="hint">🔊 Turn your volume up and press Play.</div>
</div>
<script>
(function(){
const P=__PANELS__,LANG="__LANG__",$=id=>document.getElementById(id);
const scene=$('scene'),who=$('who'),txt=$('txt'),dots=$('dots'),play=$('play'),next=$('next'),hint=$('hint');
let idx=0,playing=false,tok=0,typer=null,voices=[];
dots.innerHTML=P.map(()=>'<i></i>').join('');
const synth=window.speechSynthesis,au=new Audio();window._keep=[];
function loadV(){voices=synth?synth.getVoices():[];}
if(synth){loadV();synth.onvoiceschanged=loadV;}
function pickVoice(){const l=LANG.toLowerCase(),pl=l.split('-')[0];
 const exact=voices.filter(v=>v.lang.toLowerCase().replace('_','-')===l);
 const same=voices.filter(v=>v.lang.toLowerCase().replace('_','-').startsWith(pl));
 const pool=exact.length?exact:same;if(!pool.length)return null;
 return pool.find(v=>/natural|google|online/i.test(v.name))||pool[0];}
function confetti(){const e=['\ud83c\udf89','\u2b50','\ud83c\udf88','\u2728'];for(let k=0;k<26;k++){const c=document.createElement('span');c.className='cf';c.textContent=e[k%4];c.style.left=Math.random()*95+'%';c.style.animationDelay=Math.random()*1.2+'s';$('stage').appendChild(c);setTimeout(()=>c.remove(),4500);}}
function talk(on){['Newsie','Kiki'].forEach(n=>$(n).classList.toggle('talk',on));}
function chunks(t){const s=t.match(/[^.!?\u0964]+[.!?\u0964]*\s*/g)||[t],out=[];let cur='';
 s.forEach(x=>{if((cur+x).length>150&&cur){out.push(cur);cur='';}cur+=x;});if(cur)out.push(cur);return out;}
function say(p,done,my){
 if(p.audio){au.pause();au.src='data:audio/mpeg;base64,'+p.audio;const k=p.speaker==='Kiki';
  au.preservesPitch=!k;au.webkitPreservesPitch=!k;au.playbackRate=k?1.15:1;au.onended=done;au.onerror=done;
  const pr=au.play();if(pr&&pr.catch)pr.catch(done);return;}
 const wait=()=>setTimeout(done,Math.max(2500,p.text.length*75));
 if(!synth){wait();return;}
 const v=pickVoice();
 if(!v&&!LANG.startsWith('en')){hint.textContent='\u26a0\ufe0f This device has no '+LANG+' voice. Turn on "Clear voice" above, or install that language voice in your device settings.';wait();return;}
 const parts=chunks(p.text);let n=0;
 const go=()=>{if(my!==tok)return;if(n>=parts.length){done();return;}
  const u=new SpeechSynthesisUtterance(parts[n++]);u.lang=LANG;if(v)u.voice=v;u.rate=.92;u.pitch=p.speaker==='Kiki'?1.4:1;
  u.onend=go;u.onerror=e=>{if(e.error==='canceled'||e.error==='interrupted')return;go();};
  window._keep.push(u);synth.speak(u);};
 setTimeout(go,150);
}
function show(i,speak){
 idx=i;const p=P[i],my=++tok;clearInterval(typer);if(synth)synth.cancel();au.pause();
 scene.textContent=p.emoji;scene.className='scene';void scene.offsetWidth;scene.className='scene m-'+(p.motion||'float');
 who.textContent=p.speaker;txt.textContent='';
 ['Newsie','Kiki'].forEach(n=>{const c=$(n);c.className=c.className.replace(/\bact-\w+/g,'').trim();c.classList.toggle('active',n===p.speaker);});$(p.speaker).classList.add('act-'+(p.action||'wave'));
 [...dots.children].forEach((d,k)=>d.classList.toggle('on',k===i));
 let k=0;typer=setInterval(()=>{txt.textContent=p.text.slice(0,++k);if(k>=p.text.length)clearInterval(typer);},speak?32:12);
 if(!speak){talk(false);return;}
 talk(true);let fin=false;
 const done=()=>{if(fin||my!==tok)return;fin=true;talk(false);
  if(playing&&i+1<P.length)setTimeout(()=>{if(my===tok)show(i+1,true);},400);
  else if(i+1>=P.length){playing=false;play.textContent='\ud83d\udd01 Play again';hint.textContent='\ud83c\udf89 The End! Try the Briefing or Quiz for more.';confetti();}};
 say(p,done,my);
 setTimeout(done,9000+p.text.length*120);
}
play.onclick=()=>{playing=true;play.textContent='\u23f8 Restart';show(0,true);};
next.onclick=()=>{playing=true;show(Math.min(idx+1,P.length-1),true);};
show(0,false);
})();
</script></body></html>"""


def cartoon_html(panels, voice_lang, title):
    data = json.dumps(
        [{"speaker": p["speaker"], "emoji": p["emoji"], "text": p["text"], "audio": p.get("audio", ""),
          "action": p.get("action", "wave"), "motion": p.get("motion", "float")} for p in panels],
        ensure_ascii=False).replace("</", "<\\/")
    return (CARTOON_TEMPLATE.replace("__PANELS__", data)
            .replace("__LANG__", esc(voice_lang)).replace("__TITLE__", esc(title[:80])))


@st.cache_data(ttl=86400, show_spinner=False, max_entries=300)
def tts_b64(text, code, who):
    """Clear server voice that works for every language on every device."""
    from gtts import gTTS
    kw = {"tld": "co.in" if who == "Newsie" else "com.au"} if code == "en" else {}
    buf = io.BytesIO()
    gTTS(text=text, lang=code, **kw).write_to_fp(buf)
    return base64.b64encode(buf.getvalue()).decode()


def make_quiz(a):
    kids = st.session_state.kids
    out = llm(SYSTEM_BASE, [{"role": "user", "content":
        f"Make 3 multiple-choice questions for {audience(kids)} based ONLY on this news. Reply with ONLY a JSON "
        'array of objects: {"q":"...","options":["A","B","C"],"answer":0-based index,"why":"short reason"}.\n'
        f"Title: {a['title']}\nText: {article_text(a)}"}], 700)
    if not out:
        return None
    try:
        arr = json.loads(out[out.index("["): out.rindex("]") + 1])
        good = [z for z in arr if isinstance(z.get("options"), list) and len(z["options"]) >= 2
                and isinstance(z.get("answer"), int) and 0 <= z["answer"] < len(z["options"])]
        return good[:3] or None
    except Exception:
        return None


# ----------------------------------------------------------------------------
# UI: styling and 3D hero
# ----------------------------------------------------------------------------
def inject_css(kids=False):
    accent = "#FF9F1C" if kids else "#FFC93C"
    st.markdown("""
<link href="https://fonts.googleapis.com/css2?family=Baloo+2:wght@500;700;800&family=Nunito:wght@400;600;800&display=swap" rel="stylesheet">
<style>
:root{--ink:#0F1230;--panel:#1A1E4A;--panel2:#242a63;--sun:__ACCENT__;--coral:#FF6B6B;--mint:#3DDC97;--lilac:#9B8CFF;--txt:#F6F4FF}
html,body,[class*="css"],.stMarkdown,p,li,label{font-family:'Nunito',system-ui,sans-serif!important}
h1,h2,h3,h4,.nv-h{font-family:'Baloo 2',system-ui,sans-serif!important;letter-spacing:.2px}
.block-container{max-width:1100px;padding:1rem 1rem 4rem}
[data-testid="stHeader"]{background:transparent}
.stButton>button,.stFormSubmitButton>button,.stDownloadButton>button{border-radius:14px;min-height:44px;font-weight:800;
 border:2px solid rgba(255,255,255,.16);transition:transform .15s ease}
.stButton>button:hover{transform:translateY(-2px) scale(1.02)}
.stButton>button[kind="primary"],.stFormSubmitButton>button[kind="primary"]{background:var(--sun);color:#1c1650;border-color:var(--sun)}
.stButton>button:focus-visible{outline:3px solid #fff;outline-offset:2px}
.nv-card{background:linear-gradient(160deg,var(--panel),#161a40);border:1px solid rgba(255,255,255,.10);border-top:6px solid var(--cc,#FFC93C);border-radius:20px;
 padding:16px 18px;margin-bottom:6px;transition:transform .25s ease,box-shadow .25s ease;transform-style:preserve-3d}
@media (hover:hover) and (prefers-reduced-motion:no-preference){.nv-card:hover{transform:perspective(900px) rotateX(2deg) translateY(-3px);box-shadow:0 18px 40px rgba(0,0,0,.4)}}
.nv-card h4{margin:0 0 6px;font-size:1.18rem;line-height:1.3;color:#fff}
.nv-meta{color:#b9b6e6;font-size:.85rem;margin-bottom:8px}
.nv-sum{color:#e9e6ff;line-height:1.55;font-size:.98rem}
.chip{display:inline-block;padding:3px 11px;border-radius:99px;font-size:.78rem;font-weight:800;margin:0 6px 6px 0}
.chip.pos{background:rgba(61,220,151,.18);color:#3DDC97}.chip.neu{background:rgba(155,140,255,.2);color:#C9C0FF}
.chip.neg{background:rgba(255,107,107,.2);color:#FF9A9A}.chip.cat{background:rgba(255,201,60,.16);color:#FFC93C}.chip.ok{background:rgba(61,220,151,.14);color:#3DDC97}
.chip.new{background:#FF6B6B;color:#fff;animation:nvpulse 1.6s ease-in-out infinite}
@keyframes nvpulse{50%{transform:scale(1.08)}}
.nv-sum ul{margin:6px 0 0 18px;padding:0}.nv-sum li{margin-bottom:5px}
.trust{height:7px;border-radius:9px;background:rgba(255,255,255,.1);overflow:hidden;margin:2px 0 4px}
.trust>i{display:block;height:100%;border-radius:9px}
.nv-thumb{width:100%;max-height:150px;object-fit:cover;border-radius:14px;margin-bottom:10px}
.nv-stat{background:var(--panel);border-radius:18px;padding:14px 16px;border:1px solid rgba(255,255,255,.08);color:#F6F4FF}
.nv-stat b{font-family:'Baloo 2';font-size:1.8rem;color:var(--sun);display:block;line-height:1.1}
.nv-note{background:rgba(155,140,255,.12);border-left:4px solid var(--lilac);border-radius:10px;padding:10px 14px;color:#dcd8ff;font-size:.92rem}
.nv-tick{display:flex;align-items:center;gap:10px;background:linear-gradient(90deg,#ff5e62,#ff9966);border-radius:14px;padding:7px 10px;margin:2px 0 6px;overflow:hidden}
.nv-tick b{background:#fff;color:#d62828;padding:2px 10px;border-radius:99px;font-size:.8rem;white-space:nowrap}
.nv-track{overflow:hidden;flex:1}
.nv-run{display:inline-block;white-space:nowrap;animation:nvrun 160s linear infinite;color:#fff;font-weight:800}
.nv-run:hover{animation-play-state:paused}
.nv-run span{margin-right:56px}
@keyframes nvrun{to{transform:translateX(-50%)}}
@media (prefers-reduced-motion:reduce){.nv-run{animation:none}.nv-track{overflow-x:auto}.nv-card:hover{transform:none}}
.nv-mission{background:linear-gradient(135deg,rgba(255,201,60,.18),rgba(255,107,107,.15));border:2px dashed rgba(255,201,60,.55);
 border-radius:16px;padding:10px 14px;margin:6px 0 4px;font-weight:700}
.nv-foot{text-align:center;margin-top:34px;padding:18px 10px 6px;border-top:1px solid rgba(128,128,128,.35);font-size:.92rem;line-height:1.7}
.nv-foot a{font-weight:800;text-decoration:none;margin:0 6px}
@media (max-width:640px){.block-container{padding:.6rem .6rem 4rem}.nv-card h4{font-size:1.05rem}}
</style>""".replace("__ACCENT__", accent), unsafe_allow_html=True)


HERO_HTML = """<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<link href="https://fonts.googleapis.com/css2?family=Baloo+2:wght@700;800&family=Nunito:wght@600&display=swap" rel="stylesheet">
<style>
html,body{margin:0;height:100%;background:radial-gradient(120% 120% at 70% 40%,#2a2f7a 0%,#12153e 55%,#0b0d28 100%);overflow:hidden;font-family:Nunito,sans-serif}
canvas{position:absolute;inset:0;width:100%;height:100%;touch-action:pan-y}
.t{position:absolute;left:22px;top:18px;right:22px;pointer-events:none;color:#F6F4FF}
.t h1{font:800 clamp(26px,5.5vw,46px)/1.05 'Baloo 2',sans-serif;margin:0;text-shadow:0 4px 0 #5b3cff}
.t p{margin:6px 0 0;font-size:clamp(13px,2.4vw,17px);color:#cfcaff;max-width:30ch}
.nogl .t{position:static;padding:30px}
</style></head><body>
<canvas id="c" aria-hidden="true"></canvas>
<div class="t"><h1>__APPNAME__ 📰</h1><p>Fresh news, explained for everyone.</p></div>
<script src="https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js"></script>
<script>
(function(){
const heads=__HEADS__;
if(!window.THREE){document.body.classList.add('nogl');return;}
const el=document.getElementById('c');let r;
try{r=new THREE.WebGLRenderer({canvas:el,antialias:true,alpha:true});}catch(e){document.body.classList.add('nogl');return;}
r.setPixelRatio(Math.min(devicePixelRatio,2));
const scene=new THREE.Scene(),cam=new THREE.PerspectiveCamera(50,1,.1,100);cam.position.set(0,0,8);
const N=1700,pos=new Float32Array(N*3),col=new Float32Array(N*3),ga=Math.PI*(3-Math.sqrt(5));
for(let i=0;i<N;i++){const y=1-i/(N-1)*2,rad=Math.sqrt(1-y*y),th=ga*i;
pos.set([Math.cos(th)*rad*2,y*2,Math.sin(th)*rad*2],i*3);
const hot=Math.random()<.14;col.set(hot?[1,.79,.24]:[.24,.86,.59],i*3);}
const g=new THREE.BufferGeometry();g.setAttribute('position',new THREE.BufferAttribute(pos,3));g.setAttribute('color',new THREE.BufferAttribute(col,3));
const globe=new THREE.Points(g,new THREE.PointsMaterial({size:.055,vertexColors:true}));
const core=new THREE.Mesh(new THREE.SphereGeometry(1.92,32,32),new THREE.MeshBasicMaterial({color:0x151a5c}));
scene.add(core,globe);
const sp=new Float32Array(500*3);for(let i=0;i<500*3;i++)sp[i]=(Math.random()-.5)*40;
const sg=new THREE.BufferGeometry();sg.setAttribute('position',new THREE.BufferAttribute(sp,3));
scene.add(new THREE.Points(sg,new THREE.PointsMaterial({size:.05,color:0xffffff})));
const grp=new THREE.Group();scene.add(grp);const emo=['📰','🚀','🌍','🏏','💡','🔬','🎬','🌦️'];
heads.slice(0,7).forEach((h,i)=>{const c=document.createElement('canvas');c.width=512;c.height=256;const x=c.getContext('2d');
x.fillStyle='#FFF3C4';x.beginPath();x.roundRect?x.roundRect(6,6,500,244,26):x.rect(6,6,500,244);x.fill();x.lineWidth=8;x.strokeStyle='#1c1650';x.stroke();
x.font='56px serif';x.fillText(emo[i%emo.length],26,76);x.fillStyle='#1c1650';x.font='800 30px Nunito,sans-serif';
let words=h.split(' '),line='',y=122,n=0;for(const w of words){const t=line+w+' ';if(x.measureText(t).width>440){x.fillText(line,26,y);line=w+' ';y+=36;n++;if(n>=3)break;}else line=t;}
if(n<3)x.fillText(line,26,y);
const m=new THREE.Mesh(new THREE.PlaneGeometry(2.3,1.15),new THREE.MeshBasicMaterial({map:new THREE.CanvasTexture(c),transparent:true,side:THREE.DoubleSide}));
const a=i/Math.min(heads.length,7)*Math.PI*2;m.position.set(Math.cos(a)*3.9,Math.sin(i*1.7)*1.2,Math.sin(a)*3.9);grp.add(m);});
function size(){const w=el.clientWidth,h=el.clientHeight;r.setSize(w,h,false);cam.aspect=w/h;cam.position.z=w<520?10.5:8;cam.position.x=w<520?0:-1.6;cam.updateProjectionMatrix();}
addEventListener('resize',size);size();
let tx=0,ty=0;addEventListener('pointermove',e=>{tx=(e.clientX/innerWidth-.5)*.6;ty=(e.clientY/innerHeight-.5)*.4;});
const still=matchMedia('(prefers-reduced-motion: reduce)').matches;
function frame(){if(!still){globe.rotation.y+=.0035;core.rotation.y=globe.rotation.y;grp.rotation.y-=.0028;}
globe.rotation.x+=(ty-globe.rotation.x)*.04;grp.children.forEach(m=>m.lookAt(cam.position));r.render(scene,cam);if(!still)requestAnimationFrame(frame);}
frame();
})();
</script></body></html>"""


def hero():
    arts = st.session_state.get("articles") or DEMO_ARTICLES
    heads = [a["title"][:70] for a in arts[:7]]
    payload = json.dumps(heads).replace("</", "<\\/")
    embed_html(HERO_HTML.replace("__HEADS__", payload).replace("__APPNAME__", esc(APP_NAME)), 300)


def ticker_html(arts):
    items = "".join(f"<span>{guess_emoji(a['title'])} {esc(a['title'][:110])}</span>" for a in arts[:20])
    return f'<div class="nv-tick"><b>🔴 LIVE</b><div class="nv-track"><div class="nv-run">{items}{items}</div></div></div>'


def mission_card():
    """Daily mission: 3 small goals that keep kids (and adults) coming back."""
    today = now().astimezone(IST).date().isoformat()
    m = st.session_state.get("mission")
    if not m or m.get("day") != today:
        m = st.session_state.mission = {"day": today, "read": set(), "cartoon": False, "quiz": False}
    parts = [len(m["read"]) >= 3, m["cartoon"], m["quiz"]]
    n = sum(parts)
    tick = lambda ok: "✅" if ok else "⬜"
    st.markdown(f'<div class="nv-mission">🎯 <b>Today\'s mission</b> ({n}/3) &nbsp; '
                f'{tick(parts[0])} Open 3 stories ({min(3, len(m["read"]))}/3) &nbsp; '
                f'{tick(parts[1])} Watch a cartoon &nbsp; {tick(parts[2])} Finish a quiz</div>', unsafe_allow_html=True)
    if n == 3 and not st.session_state.get("mission_done") == today:
        st.session_state.mission_done = today
        st.balloons()
        award(10, "mission_" + today)
        st.success("🏆 Mission complete! Come back tomorrow to keep your streak.")


def contact_email():
    return cfg("CONTACT_EMAIL", "factdive28@gmail.com")


def footer():
    mail, gh = contact_email(), cfg("GITHUB_URL")
    links = []
    if gh.startswith("https://"):
        links.append(f'<a href="{esc(gh, True)}" target="_blank" rel="noopener noreferrer">💻 GitHub</a>')
    if mail:
        links.append(f'<a href="mailto:{esc(mail, True)}">✉️ {esc(mail)}</a>')
    st.markdown(
        f'<div class="nv-foot"><b>{esc(APP_NAME)}</b> · Made with ❤️ in India<br>'
        f'🔒 We never sell your data. Open the <b>Privacy</b> page to see what we keep and why.<br>'
        f'{" · ".join(links)}<br><small>Summaries link to the original publishers. AI can make mistakes, '
        f'so always check the source.</small></div>', unsafe_allow_html=True)


def privacy_md():
    mail = contact_email()
    contact = f"Write to **{mail}**." if mail else "Use the Rate us page to contact the site owner."
    return f"""
**Short answer:** we keep as little as possible, we never sell it, and you can delete it yourself any time.

#### What we store
- Your **nickname, email and age group** (so you can log in and so we know whether Kids Mode is right).
- Your **password only as a salted hash** (PBKDF2). Nobody, including the owner, can read your real password.
- Your **XP, streak, saved stories, questions you ask Newsie, and ratings** you send.
- **Simple usage events** such as "opened a story", with a random visitor ID. We do **not** store your IP address, phone number, address or location.

#### Where it is stored and who can see it
- In a **PostgreSQL database on Neon**, reached over an encrypted connection. The app itself runs on Streamlit Community Cloud.
- Only the **site owner** can open the Owner page, which shows nicknames, emails, questions and feedback. This is used to run and improve the app.
- Publicly, only your **nickname and XP** appear on the leaderboard, and a review appears only if you tick "show publicly".
- We **do not sell, rent or share** your data and there are **no ads**.

#### Services that receive some text to do their job
- **Google Gemini** (AI helper): the article text or the question you type to Newsie.
- **Google Translate and Google text-to-speech**: the text being translated or read aloud.
- **News publishers** (BBC, The Hindu and others): we only read their public feeds. Nothing about you is sent.
- **Free dictionary service**: the word you look up.

Please **never type personal details** (full name, school, phone, address) into Ask Newsie.

#### Kids and families
- Under 18? A parent or guardian must agree when you sign up. Use a nickname, not your full name.
- Kids Mode hides violent and adult stories and uses simple words. No filter is perfect, so parents should stay nearby.

#### "Keep me logged in"
- This saves a random token in your browser for 14 days. Only its hash is kept on our side.
- **Do not share your address bar link after logging in**, because it contains that token. Log out on shared devices.

#### Your control
- **My Space → Privacy and account deletion** removes your profile, saved stories, chats, ratings and login tokens. Usage events are made anonymous.
- {contact}

No website can promise perfect security, but we use hashed passwords, parameterised database queries and a locked-down owner page to keep your data safe.
"""


def page_privacy():
    st.markdown("### 🔒 Privacy and data safety")
    st.markdown(privacy_md())


# ----------------------------------------------------------------------------
# Pages
# ----------------------------------------------------------------------------
def auth_screen():
    st.markdown(f"### Join {esc(APP_NAME)}")
    st.caption("Log in to save stories, earn XP and keep your streak. Guests can explore with fewer AI helpers.")
    t1, t2, t3 = st.tabs(["Log in", "Sign up", "Just explore"])
    with t1:
        with st.form("login_form"):
            e = st.text_input("Email", key="li_e")
            p = st.text_input("Password", type="password", key="li_p")
            keep = st.checkbox("Keep me logged in on this device", value=True, key="li_keep")
            if st.form_submit_button("Log in", type="primary", width="stretch"):
                ok, res = login(e, p)
                if ok:
                    set_user(res)
                    if keep:
                        st.query_params["s"] = create_session(res["id"])
                    st.rerun()
                else:
                    st.error(res)
    with t2:
        with st.form("signup_form"):
            n = st.text_input("Nickname (no full names please)", max_chars=40)
            e = st.text_input("Email (use a parent's email if you're under 18)")
            p = st.text_input("Password (8+ characters, letters and numbers)", type="password")
            ag = st.selectbox("Age group", ["Under 13", "13 to 17", "18 or older"], index=2)
            c = st.checkbox("A parent or guardian knows about this account and agrees (needed if under 18)")
            keep = st.checkbox("Keep me logged in on this device", value=True, key="su_keep")
            st.caption("We store your nickname, email, XP and what you save or ask, only to run the app. "
                       "You can delete everything from My Space at any time. We never sell your data.")
            if st.form_submit_button("Create my account", type="primary", width="stretch"):
                ok, res = signup(n, e, p, ag, c)
                if ok:
                    set_user(q("SELECT * FROM users WHERE id=?", (res,))[0])
                    if keep:
                        st.query_params["s"] = create_session(res)
                    st.rerun()
                else:
                    st.error(res)
    with t3:
        st.write("No account needed. You can read news, see sentiment and credibility hints, and try 5 AI helpers a day.")
        kid = st.toggle("I'm a kid (turn on Kids Mode)", value=False, key="guest_kid")
        if st.button("Start exploring", type="primary", width="stretch"):
            st.session_state.guest = True
            st.session_state.kids_set = kid
            st.query_params["g"] = "1"
            st.query_params["k"] = "1" if kid else "0"
            log("guest_start")
            st.rerun()
    with st.expander("🔒 Is my data safe? Where is it stored?"):
        st.markdown(privacy_md())


def sidebar():
    u = st.session_state.get("user")
    with st.sidebar:
        st.markdown(f"## 📰 {esc(APP_NAME)}")
        if u:
            row = q("SELECT xp,streak FROM users WHERE id=?", (u["id"],))[0]
            (lo, name, icon), nxt = level_of(row["xp"])
            st.markdown(f"**Hi {esc(u['name'])}!** {icon} {name}")
            if nxt:
                st.progress(min(1.0, (row["xp"] - lo) / (nxt[0] - lo)), text=f"{row['xp']} / {nxt[0]} XP")
            else:
                st.caption(f"{row['xp']} XP · top level!")
            st.caption(f"🔥 {row['streak']}-day streak")
        elif st.session_state.get("guest"):
            st.caption("Exploring as guest")
        st.toggle("🧸 Kids Mode (safe stories, simple words)", key="kids")
        st.selectbox("🌐 Translate summaries to", list(LANGS), key="lang")
        if u or st.session_state.get("guest"):
            if st.button("Log out" if u else "Leave guest mode", width="stretch"):
                end_session()
                for k in ("user", "guest", "articles", "chat", "awarded", "kids_prev", "mission"):
                    st.session_state.pop(k, None)
                st.rerun()
        with st.expander("🔧 Check connections"):
            st.caption("Shows which parts (news, translation, AI, voice) are working.")
            if st.button("Run check", key="hc_btn"):
                with st.spinner("Checking..."):
                    st.session_state.hc = health_check()
            for name, ok, detail in st.session_state.get("hc", []):
                st.markdown(f"{ok} **{name}**  \n<small>{esc(detail)}</small>", unsafe_allow_html=True)
        st.divider()
        st.caption("Credibility and sentiment are quick hints, not facts. Always open the source.")


def bullets(text, k=3):
    parts = [p.strip() for p in re.split(r"(?<=[.!?\u0964])\s+", text) if len(p.strip()) > 15]
    return (parts or [text])[:k]


def card_html(a, summary, cat):
    s_label, s_emoji, s_cls = sentiment(a["title"] + ". " + a["text"])
    score, label, color, why = credibility(a)
    img = f'<img class="nv-thumb" src="{esc(a["image"], True)}" alt="" loading="lazy">' if a.get("image") else ""
    by = f' · ✍️ {esc(a["author"])}' if a.get("author") else ""
    est = '<span class="chip ok">✅ Established outlet</span>' if a["source"] in OUTLETS or any(t in a["source"].lower() for t in TRUSTED_SOURCES) else ""
    fresh = '<span class="chip new">🆕 Fresh</span>' if a.get("published") and 0 <= (now() - a["published"]).total_seconds() < 10800 else ""
    lis = "".join(f"<li>{esc(b)}</li>" for b in bullets(summary))
    return (f'<div class="nv-card" style="--cc:{CAT_COLOR.get(cat, "#FFC93C")}">{img}<h4>{esc(a["title"])}</h4>'
            f'<div class="nv-meta">{esc(a["source"])}{by} · {esc(time_ago(a["published"]))}</div>'
            f'{fresh}<span class="chip cat">{esc(cat)}</span><span class="chip {s_cls}">{s_emoji} {s_label}</span>{est}'
            f'<div class="nv-sum"><ul>{lis}</ul></div>'
            f'<div class="nv-meta" style="margin-top:10px">Credibility hint: <b style="color:{color}">{label} ({score}/100)</b></div>'
            f'<div class="trust"><i style="width:{score}%;background:{color}"></i></div>'
            f'<div class="nv-meta">{esc("; ".join(why[:2]))}</div></div>')


def wa_url(a):
    text = f"{a['title']}\n{a['url']}\n- via {APP_NAME}" + (f" {cfg('APP_URL')}" if cfg("APP_URL") else "")
    return "https://wa.me/?text=" + quote_plus(text)


@st.dialog("Story Studio", width="large")
def studio(a):
    st.markdown(f"#### {esc(a['title'])}")
    st.caption(f"{a['source']}" + (f" · by {a['author']}" if a.get("author") else "") + f" · {time_ago(a['published'])}")
    if "full" not in a:
        with st.spinner("Reading the full story..."):
            a["full"] = extract_article(a["url"])
    full = len(a["full"]) >= 500
    if full:
        st.success("✅ Based on the full article text from the publisher.")
    else:
        st.warning("⚠️ Only the headline and a short snippet were available, so explanations stay brief instead of guessing. "
                   "Open the original for the full story.")
    log("studio", a["title"][:80])
    award(3, "read_" + a["url"])
    st.session_state.get("mission", {}).get("read", set()).add(a["url"])
    modes = ["📋 2-min briefing", "🎨 Cartoon", "🧒 Explain simply", "🧠 Quiz", "📚 Hard words"]
    mode = st.radio("What would you like?", modes, horizontal=True, key="studio_mode")
    code, voice = LANGS[st.session_state.lang]
    if mode == modes[0]:
        with st.spinner("Writing your briefing..."):
            md, ai, _ = make_briefing(a)
        if code != "en":
            with st.spinner("Translating..."):
                md = translate_markdown(md, code)
        words = len(re.findall(r"\w+", md))
        st.caption(f"⏱ About {max(1, round(words / 180))} min read · "
                   + ("AI-written strictly from the article text" if ai else "Key sentences taken from the article"))
        st.markdown(md)
        if st.button("🔊 Listen to this briefing", key="listen_btn"):
            plain = re.sub(r"[*#_`]", "", md)[:2500]
            try:
                st.audio(base64.b64decode(tts_b64(plain, code, "Newsie")), format="audio/mp3")
            except Exception as e:
                st.info(f"Audio isn't available for this language right now ({type(e).__name__}).")
        st.caption("AI can make mistakes. Check the original link for exact details.")
        award(4, "brief_" + a["url"])
    elif mode == modes[1]:
        srv = st.toggle("🔊 Clear voice (works for every language)", value=True, key="srv_voice")
        with st.spinner("Drawing your comic..."):
            panels, ai = cartoon_script(a)
            if code != "en":
                try:
                    for p in panels:
                        p["text"] = translate(p["text"], code)
                except Exception:
                    alt = llm_translate([p["text"] for p in panels], code)
                    if alt:
                        for p, t in zip(panels, alt):
                            p["text"] = t
                    else:
                        st.warning("Translation is not working right now, so the comic is in English.")
            if srv:
                try:
                    for p in panels:
                        p["audio"] = tts_b64(p["text"], code, p["speaker"])
                except Exception as e:
                    for p in panels:
                        p.pop("audio", None)
                    st.caption(f"Clear voice isn't available for this language right now ({type(e).__name__}). "
                               "Using your device's voice instead.")
        embed_html(cartoon_html(panels, voice, a["title"]), 640)
        award(10, "cartoon_" + a["url"])
        if "mission" in st.session_state:
            st.session_state.mission["cartoon"] = True
        st.caption("The comic only uses facts from the article text." + ("" if ai or ai_on() else " Add GEMINI_API_KEY in Secrets for richer comics."))
    elif mode == modes[2]:
        with st.spinner("Newsie is thinking..."):
            txt = explain_simply(a)
        st.write(tr_safe(txt))
    elif mode == modes[3]:
        qk = "quiz_" + hashlib.sha1(a["url"].encode()).hexdigest()[:8]
        if qk not in st.session_state or not st.session_state[qk]:
            with st.spinner("Making questions..."):
                st.session_state[qk] = make_quiz(a) or []
        quiz = st.session_state[qk]
        if not quiz:
            st.info(ai_status() + " You can still try the briefing, cartoon or hard words.")
        else:
            picks = []
            for i, z in enumerate(quiz):
                picks.append(st.radio(f"{i+1}. {z['q']}", z["options"], index=None, key=f"{qk}_{i}"))
            if st.button("Check my answers", type="primary", key=qk + "_go"):
                score = 0
                for z, p in zip(quiz, picks):
                    right = z["options"][z["answer"]]
                    if p == right:
                        score += 1
                        st.success(f"✅ {right}. {z.get('why', '')}")
                    else:
                        st.error(f"The answer is: {right}. {z.get('why', '')}")
                award(5 * score, qk + "_xp")
                if "mission" in st.session_state:
                    st.session_state.mission["quiz"] = True
                log("quiz", f"{score}/{len(quiz)}")
                st.markdown(f"**You scored {score} out of {len(quiz)}!**")
    else:
        shown = 0
        for w in hard_words(a["title"] + " " + article_text(a)):
            d = define(w)
            if d:
                st.markdown(d)
                shown += 1
        if not shown:
            st.info("No tricky words found here, or the dictionary is busy. Try the Ask Newsie page.")
    st.link_button(f"🔗 Read the original at {a['source']}", a["url"], width="stretch")


def page_news():
    kids = st.session_state.kids
    cats = KIDS_CATEGORIES if kids else list(CATEGORIES)
    tick_ph = st.container()
    mission_card()
    topic = st.pills("⚡ Quick topics", list(TOPICS), key="topic_pill", label_visibility="collapsed")
    with st.form("news_form"):
        query = st.text_input("Search a topic", placeholder="e.g. ISRO, Mysuru Dasara, cricket", max_chars=80)
        c2, c3, c4 = st.columns(3)
        cat = c2.selectbox("Category", cats)
        source = c3.selectbox("News from", SOURCE_CHOICES + list(OUTLETS))
        n = c4.slider("Stories", 10, MAX_STORIES, 30)
        go = st.form_submit_button("🔎 Get fresh news", type="primary", width="stretch")
    topic_changed = topic != st.session_state.get("last_topic")
    st.session_state.last_topic = topic
    first = "articles" not in st.session_state
    if go or first or topic_changed or st.session_state.get("kids_prev") != kids:
        eff = query.strip() if go else (TOPICS.get(topic, "") if topic else query.strip())
        with st.spinner("Fetching fresh stories..."):
            arts, note = fetch_news(eff, cat, n, kids, source)
        st.session_state.articles, st.session_state.note = arts, note
        st.session_state.cat = cat
        st.session_state.kids_prev = kids
        st.session_state.shown = 12
        st.session_state.fetched_at = now()
        if go or topic_changed:
            log("search", f"{cat}|{eff}"[:100])
    arts = st.session_state.get("articles", [])
    live = bool(arts) and arts[0]["source"] != "Sample story"
    if live:
        with tick_ph:
            st.markdown(ticker_html(arts), unsafe_allow_html=True)
            fa = st.session_state.get("fetched_at")
            st.caption(f"🕒 Updated {fa.astimezone(IST).strftime('%I:%M %p')} IST · {len(arts)} stories, newest first" if fa else "")
    if st.session_state.get("note"):
        (st.info if live else st.warning)(st.session_state.note)
    if kids:
        st.markdown('<div class="nv-note">🧸 Kids Mode is on: gentle stories only, simple explanations and comics.</div>',
                    unsafe_allow_html=True)
    code = LANGS[st.session_state.lang][0]
    shown = st.session_state.setdefault("shown", 12)
    view = arts[:shown]
    summaries = [short_summary(a) for a in view]
    if code != "en":
        with st.spinner("Translating..."):
            try:
                summaries = translate_many(tuple(summaries), code)
            except Exception as e:
                st.warning("Translation is busy right now, so summaries are in English. Please try again shortly.")
                st.caption(f"Technical detail: {str(e)[:160]}")
    cols = st.columns(2) if len(view) > 1 else [st.container()]
    for i, (a, s) in enumerate(zip(view, summaries)):
        aid = hashlib.sha1((a["url"] + a["title"]).encode()).hexdigest()[:8]
        with cols[i % len(cols)]:
            st.markdown(card_html(a, s, st.session_state.get("cat", "Top stories")), unsafe_allow_html=True)
            b1, b2, b3 = st.columns(3)
            if b1.button("✨ Studio", key=f"st_{aid}", width="stretch", type="primary"):
                studio(a)
            if b2.button("🔖 Save", key=f"sv_{aid}", width="stretch"):
                if uid():
                    if not q("SELECT 1 FROM saved WHERE user_id=? AND url=?", (uid(), a["url"])):
                        x("INSERT INTO saved(user_id,ts,title,url,summary) VALUES(?,?,?,?,?)",
                          (uid(), iso(), a["title"], a["url"], short_summary(a, 200)))
                        log("save")
                        award(2, "save_" + aid)
                    st.toast("Saved to My Space", icon="🔖")
                else:
                    st.toast("Log in to save stories", icon="🔒")
            b3.link_button("🔗 Source", a["url"], width="stretch")
            d1, d2 = st.columns(2)
            d1.link_button("🔍 Cross-check", f"https://www.google.com/search?q={quote_plus(a['title'])}&tbm=nws", width="stretch")
            d2.link_button("📲 Share", wa_url(a), width="stretch")
    if shown < len(arts):
        if st.button(f"⬇️ Show more stories ({len(arts) - shown} more)", key="more_btn", width="stretch"):
            st.session_state.shown = shown + 12
            st.rerun()


def keyword_answer(question):
    words = {w for w in re.findall(r"[a-z]{4,}", question.lower())}
    best, score = None, 0
    for a in st.session_state.get("articles", []):
        sc = len(words & set(re.findall(r"[a-z]{4,}", (a["title"] + " " + a["text"]).lower())))
        if sc > score:
            best, score = a, sc
    if best:
        return (f"I found this in today's stories:\n\n**{best['title']}**\n\n{short_summary(best, 300)}\n\n"
                "_(Add an AI key in settings and I can answer in more detail.)_")
    return ("I can look up word meanings (try: *define inflation*). " + ai_status())


def newsie_reply(question):
    kids = st.session_state.kids
    word = dictionary_intent(question)
    if word:
        d = define(word)
        if d:
            return d
    if not ai_enabled():
        return keyword_answer(question)
    if not ai_allowed():
        return "You've used all your AI helpers for today. They refresh tomorrow. Meanwhile, try word meanings like *define economy*."
    heads = "\n".join("- " + a["title"] for a in st.session_state.get("articles", [])[:8])
    system = (SYSTEM_BASE + f" You are chatting with {audience(kids)}. You can explain words and news topics. "
              "You cannot browse the internet; today's headlines on screen are listed below. If unsure, say so and "
              "suggest checking trusted sources. Never ask for personal details. Politely steer away from adult or "
              "harmful topics. Keep answers under 120 words.\nHeadlines:\n" + heads)
    hist = [m for m in st.session_state.chat[-8:]] + [{"role": "user", "content": question}]
    out = llm(system, hist, 450)
    return out or keyword_answer(question)


def page_ask():
    st.markdown("### 💬 Ask Newsie")
    st.caption("Ask about any news word, topic or doubt. Type just a word to get its meaning.")
    st.session_state.setdefault("chat", [])
    sug = ["define inflation", "Why do prices go up?", "What is GDP?", "Explain climate change simply"]
    cols = st.columns(len(sug))
    for c, s in zip(cols, sug):
        if c.button(s, key="sg_" + s, width="stretch"):
            st.session_state.pending = s
    for m in st.session_state.chat:
        with st.chat_message(m["role"], avatar="🦉" if m["role"] == "assistant" else None):
            st.markdown(m["content"])
    msg = st.chat_input("Ask a doubt or type a word...", max_chars=400) or st.session_state.pop("pending", None)
    if msg:
        st.session_state.chat.append({"role": "user", "content": msg})
        with st.chat_message("user"):
            st.markdown(msg)
        with st.chat_message("assistant", avatar="🦉"):
            with st.spinner("Newsie is thinking..."):
                ans = newsie_reply(msg)
            if LANGS[st.session_state.lang][0] != "en":
                ans = tr_safe(ans)
            st.markdown(ans)
        st.session_state.chat.append({"role": "assistant", "content": ans})
        x("INSERT INTO chats(user_id,ts,question,answer) VALUES(?,?,?,?)", (uid(), iso(), msg[:400], ans[:1500]))
        log("chat")
        award(1, "chat_" + str(len(st.session_state.chat)))
    st.caption(f"Questions you ask are saved to help improve {APP_NAME} and are sent to Google's AI to get an answer. "
               "Please don't share personal details.")


def page_space():
    u = st.session_state.get("user")
    st.markdown("### 🧭 My Space")
    if not u:
        st.info("Log in to save stories, earn XP and join the leaderboard.")
        return
    row = q("SELECT xp,streak,created FROM users WHERE id=?", (u["id"],))[0]
    (lo, name, icon), _ = level_of(row["xp"])
    c1, c2, c3 = st.columns(3)
    c1.markdown(f'<div class="nv-stat"><b>{row["xp"]}</b>XP earned</div>', unsafe_allow_html=True)
    c2.markdown(f'<div class="nv-stat"><b>{row["streak"]} 🔥</b>day streak</div>', unsafe_allow_html=True)
    c3.markdown(f'<div class="nv-stat"><b>{icon}</b>{name}</div>', unsafe_allow_html=True)
    st.markdown("#### 🔖 Saved stories")
    saved = q("SELECT id,title,url,summary FROM saved WHERE user_id=? ORDER BY id DESC LIMIT 50", (u["id"],))
    if not saved:
        st.caption("Nothing saved yet. Tap Save on any story.")
    for s in saved:
        with st.container(border=True):
            st.markdown(f"**{esc(s['title'])}**")
            st.caption(s["summary"])
            a, b = st.columns([1, 1])
            a.link_button("Open source", s["url"], width="stretch")
            if b.button("Remove", key=f"rm_{s['id']}", width="stretch"):
                x("DELETE FROM saved WHERE id=? AND user_id=?", (s["id"], u["id"]))
                st.rerun()
    st.markdown("#### 🏆 Leaderboard")
    top = q("SELECT name,xp FROM users ORDER BY xp DESC LIMIT 10")
    st.dataframe(pd.DataFrame([{"Rank": i + 1, "Nickname": t["name"], "XP": t["xp"]} for i, t in enumerate(top)]),
                 hide_index=True, width="stretch")
    with st.expander("Privacy and account deletion"):
        st.write("Your password is stored only as a salted hash. We never sell your data. "
                 "Deleting your account removes your profile, saved stories, chats, feedback and login tokens.")
        ok = st.checkbox("I understand this cannot be undone", key="del_ok")
        if st.button("Delete my account and data", disabled=not ok):
            delete_user_data(u["id"])
            st.query_params.clear()
            for k in ("user", "guest", "chat", "awarded"):
                st.session_state.pop(k, None)
            st.rerun()


def page_feedback():
    st.markdown(f"### ⭐ Rate {esc(APP_NAME)}")
    u = st.session_state.get("user")
    with st.form("fb_form", clear_on_submit=True):
        stars = st.feedback("stars")
        cat = st.selectbox("What is this about?", ["Overall app", "News quality", "Cartoons", "Chatbot", "Translation", "Bug", "Idea"])
        msg = st.text_area("Tell us more (optional)", max_chars=800)
        pub = st.checkbox("Show my review publicly with my nickname")
        if st.form_submit_button("Send feedback", type="primary", width="stretch"):
            if stars is None:
                st.error("Please pick a star rating first.")
            else:
                x("INSERT INTO feedback(user_id,ts,rating,category,message,public,display_name) VALUES(?,?,?,?,?,?,?)",
                  (uid(), iso(), stars + 1, cat, msg.strip(), 1 if (pub and u and msg.strip()) else 0,
                   u["name"] if u else "Guest"))
                log("feedback", stars + 1)
                award(5, "fb_" + iso())
                st.success("Thank you! Your feedback helps us improve.")
    avg = q("SELECT AVG(rating) a, COUNT(*) c FROM feedback")[0]
    if avg["c"]:
        st.markdown(f"**Community rating: {avg['a']:.1f} / 5** from {avg['c']} reviews")
    for r in q("SELECT display_name,rating,message FROM feedback WHERE public=1 ORDER BY id DESC LIMIT 5"):
        st.markdown(f"{'⭐' * r['rating']} **{esc(r['display_name'])}**: {esc(r['message'])}")


def page_admin():
    if not is_admin():
        st.error("This page is for the site owner only.")
        return
    st.markdown("### 🛡️ Owner dashboard")
    today = now().date().isoformat()
    users = q("SELECT COUNT(*) c FROM users")[0]["c"]
    guests = q("SELECT COUNT(DISTINCT sid) c FROM events WHERE user_id IS NULL")[0]["c"]
    dau = q("SELECT COUNT(DISTINCT COALESCE(CAST(user_id AS TEXT), sid)) c FROM events WHERE substr(ts,1,10)=?", (today,))[0]["c"]
    ai_n = q("SELECT COUNT(*) c FROM events WHERE kind='ai' AND substr(ts,1,10)=?", (today,))[0]["c"]
    fb = q("SELECT AVG(rating) a, COUNT(*) c FROM feedback")[0]
    cols = st.columns(5)
    for c, (v, l) in zip(cols, [(users, "registered users"), (guests, "guest visitors"), (dau, "active today"),
                                (ai_n, "AI calls today"), (f"{(fb['a'] or 0):.1f}★", f"{fb['c']} ratings")]):
        c.markdown(f'<div class="nv-stat"><b>{v}</b>{l}</div>', unsafe_allow_html=True)
    since = (now() - dt.timedelta(days=14)).isoformat()
    act = df_query("SELECT substr(ts,1,10) AS day, COUNT(DISTINCT COALESCE(CAST(user_id AS TEXT), sid)) AS users "
                   "FROM events WHERE ts>=? GROUP BY day ORDER BY day", (since,))
    st.markdown("#### Daily active people (last 14 days)")
    if not act.empty:
        st.line_chart(act.set_index("day"))
    kinds = df_query("SELECT kind, COUNT(*) n FROM events GROUP BY kind ORDER BY n DESC")
    st.markdown("#### What people use")
    if not kinds.empty:
        st.bar_chart(kinds.set_index("kind"))
    t1, t2, t3, t4 = st.tabs(["Feedback", "Doubts asked", "Users", "Backup and privacy"])
    with t1:
        f = df_query("SELECT f.ts, COALESCE(u.name,'Guest') AS name, f.rating, f.category, f.message FROM feedback f "
                     "LEFT JOIN users u ON u.id=f.user_id ORDER BY f.id DESC LIMIT 500")
        st.dataframe(f, hide_index=True, width="stretch")
        st.download_button("Download feedback CSV", f.to_csv(index=False).encode(), "feedback.csv", "text/csv")
    with t2:
        c = df_query("SELECT c.ts, COALESCE(u.name,'Guest') AS name, c.question, c.answer FROM chats c "
                     "LEFT JOIN users u ON u.id=c.user_id ORDER BY c.id DESC LIMIT 500")
        st.dataframe(c, hide_index=True, width="stretch")
        st.download_button("Download doubts CSV", c.to_csv(index=False).encode(), "doubts.csv", "text/csv")
    with t3:
        us = df_query("SELECT id,name,email,age_group,created,last_login,xp,streak FROM users ORDER BY id DESC")
        st.dataframe(us, hide_index=True, width="stretch")
        st.download_button("Download users CSV", us.to_csv(index=False).encode(), "users.csv", "text/csv")
    with t4:
        if using_pg():
            st.success("✅ Your data is stored in a permanent PostgreSQL database. It survives restarts and redeploys.")
        else:
            st.warning("⚠️ Temporary database: Streamlit Cloud erases it on restart. Add DATABASE_URL in Secrets "
                       "(free Neon database) and download a backup below until then.")
            if os.path.exists(DB_PATH):
                with open(DB_PATH, "rb") as fh:
                    st.download_button("Download full database backup", fh.read(), "app_backup.db")
        if not cfg("GITHUB_URL"):
            st.info("Footer tip: add GITHUB_URL = \"https://github.com/yourname/yourrepo\" in Secrets to show your GitHub link.")
        em = st.text_input("Delete a user's data by email (for privacy requests)")
        if em and st.button("Delete this user's data"):
            r = q("SELECT id FROM users WHERE email=?", (em.strip().lower(),))
            if r:
                delete_user_data(r[0]["id"])
                st.success("Deleted.")
            else:
                st.warning("No such user.")


# ----------------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------------
def ls_helper(action, token=""):
    """Best effort: remember the login token in this browser so the person stays logged in next visit."""
    js = {"save": f"P.localStorage.setItem('nv_s',{json.dumps(token)});",
          "clear": "P.localStorage.removeItem('nv_s');",
          "restore": "const t=P.localStorage.getItem('nv_s'),u=new URL(P.location.href);"
                     "if(t&&!u.searchParams.get('s')&&P.sessionStorage.getItem('nv_try')!==t)"
                     "{P.sessionStorage.setItem('nv_try',t);u.searchParams.set('s',t);P.location.replace(u.toString());}"}[action]
    markup = f"<script>try{{const P=window.parent;{js}}}catch(e){{}}</script>"
    try:
        components.html(markup, height=0)
    except Exception:
        embed_html(markup, 1)


def health_check():
    rows = []

    def t(name, fn):
        try:
            rows.append((name, "✅", str(fn())[:110]))
        except Exception as e:
            rows.append((name, "❌", f"{type(e).__name__}: {str(e)[:140]}"))

    def ai_test():
        if not ai_on():
            raise RuntimeError("No GEMINI_API_KEY / ANTHROPIC_API_KEY found in Secrets")
        return "replied: " + _call_llm("Reply with one word.", [{"role": "user", "content": "Say OK"}], 20).strip()[:20]

    def voice_test():
        from gtts import gTTS
        gTTS(text="hello", lang="en").write_to_fp(io.BytesIO())
        return "server voice works"

    def outlets_test():
        ok, bad = [], []
        with ThreadPoolExecutor(max_workers=9) as ex:
            futs = {nm: ex.submit(fetch_outlet, nm, "Top stories") for nm in OUTLETS}
            for nm, f in futs.items():
                try:
                    (ok if f.result(timeout=10) else bad).append(nm)
                except Exception:
                    bad.append(nm)
        return f"{len(ok)}/{len(OUTLETS)} outlets reachable" + (f" · down: {', '.join(bad)}" if bad else "")

    def db_test():
        q("SELECT 1 AS ok")
        return "PostgreSQL (permanent)" if using_pg() else "SQLite (temporary: erased when the app restarts)"

    t("Database", db_test)
    t("News outlets", outlets_test)
    t("Translation (Hindi)", lambda: _tr("Good morning friends", "hi"))
    t("Dictionary", lambda: (define("economy") or "no result").split("\n")[0])
    t("AI helper", ai_test)
    t("Clear voice (gTTS)", voice_test)
    return rows


def main():
    try:
        init_db()
    except Exception as e:
        st.error("The database could not be reached. Check DATABASE_URL in Secrets.")
        st.caption(f"{type(e).__name__}: {str(e)[:200]}")
        st.stop()
    st.session_state.setdefault("sid", secrets.token_hex(6))
    st.session_state.setdefault("kids", False)
    st.session_state.setdefault("lang", "English")
    restore_session()
    if "kids_set" in st.session_state:
        st.session_state.kids = st.session_state.pop("kids_set")
    inject_css(st.session_state.kids)
    if "visit_logged" not in st.session_state:
        st.session_state.visit_logged = True
        log("visit")
    sidebar()
    hero()
    user, guest = st.session_state.get("user"), st.session_state.get("guest")
    tok = st.query_params.get("s")
    if user and tok and not st.session_state.get("ls_saved"):
        ls_helper("save", tok)
        st.session_state.ls_saved = True
    if not user and not guest:
        if st.session_state.pop("ls_clear", False):
            ls_helper("clear")
        elif not tok:
            ls_helper("restore")
        auth_screen()
        footer()
        return
    pages = ["📰 News", "💬 Ask Newsie", "🧭 My Space", "⭐ Rate us", "🔒 Privacy"] + (["🛡️ Owner"] if is_admin() else [])
    choice = st.segmented_control("Menu", pages, default=pages[0], key="nav", label_visibility="collapsed") or pages[0]
    fn = {"📰 News": page_news, "💬 Ask Newsie": page_ask, "🧭 My Space": page_space,
          "⭐ Rate us": page_feedback, "🔒 Privacy": page_privacy, "🛡️ Owner": page_admin}[choice]
    try:
        fn()
    except Exception as e:  # never show a blank crash screen
        st.error("Something went wrong on this page. Tap the menu to try again.")
        st.caption(f"{type(e).__name__}: {str(e)[:160]}")
    footer()


main()
