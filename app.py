"""
NewsVerse - AI News Analyzer for everyone (kids, students, aspirants, adults)

Features
- Live news (NewsAPI if key set, otherwise free Bing / Google News RSS)
- Summary, sentiment, credibility hint, translation to 11 Indian languages
- Story Studio: explain simply, 4-panel cartoon, quiz, hard-words dictionary
- Newsie chatbot + dictionary
- Login / sign-up (PBKDF2 hashed passwords), guest mode, XP + streaks
- Ratings & feedback, admin dashboard, backups, user data deletion
"""
import os
import re
import io
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

# ----------------------------------------------------------------------------
# Config
# ----------------------------------------------------------------------------
APP_NAME = "NewsVerse"
DB_PATH = os.getenv("NEWSVERSE_DB", "data/newsverse.db")
UA = {"User-Agent": "Mozilla/5.0 (NewsVerse learning app)"}
esc = html.escape

LANGS = {
    "English": ("en", "en-IN"), "Hindi (हिन्दी)": ("hi", "hi-IN"),
    "Kannada (ಕನ್ನಡ)": ("kn", "kn-IN"), "Tamil (தமிழ்)": ("ta", "ta-IN"),
    "Telugu (తెలుగు)": ("te", "te-IN"), "Malayalam (മലയാളം)": ("ml", "ml-IN"),
    "Marathi (मराठी)": ("mr", "mr-IN"), "Bengali (বাংলা)": ("bn", "bn-IN"),
    "Gujarati (ગુજરાતી)": ("gu", "gu-IN"), "Punjabi (ਪੰਜਾਬੀ)": ("pa", "pa-IN"),
    "Urdu (اردو)": ("ur", "ur-IN"),
}
CATEGORIES = {
    "Top stories": None, "India": "NATION", "World": "WORLD", "Business": "BUSINESS",
    "Technology": "TECHNOLOGY", "Science": "SCIENCE", "Health": "HEALTH",
    "Sports": "SPORTS", "Entertainment": "ENTERTAINMENT",
}
KIDS_CATEGORIES = ["Top stories", "Science", "Technology", "Sports", "Entertainment", "World", "Health"]
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
    "nature", "science", "financial express", "the guardian", "new york times", "washington post",
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
CAT_EMOJI = {"Top stories": "📰", "India": "🇮🇳", "World": "🌍", "Business": "💼", "Technology": "💻",
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

st.set_page_config(page_title=f"{APP_NAME} - understand the news", page_icon="🪐",
                   layout="wide", initial_sidebar_state="collapsed")


def embed_html(markup, height):
    """Render a self-contained HTML page (3D hero, cartoon). Uses st.iframe on new Streamlit."""
    if hasattr(st, "iframe"):
        st.iframe(markup, height=height)
    else:
        components.html(markup, height=height, scrolling=True)


def cfg(name, default=""):
    """Read a setting from Streamlit secrets first, then environment variables."""
    try:
        v = st.secrets.get(name)
    except Exception:
        v = None
    return str(v) if v not in (None, "") else os.getenv(name, default)


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
CREATE INDEX IF NOT EXISTS idx_events_ts ON events(ts);
"""


@st.cache_resource
def init_db():
    os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)
    with closing(sqlite3.connect(DB_PATH)) as con:
        con.execute("PRAGMA journal_mode=WAL")
        con.executescript(SCHEMA)
        con.commit()
    return True


def q(sql, params=()):
    with closing(sqlite3.connect(DB_PATH, timeout=15)) as con:
        con.row_factory = sqlite3.Row
        return con.execute(sql, params).fetchall()


def x(sql, params=()):
    with closing(sqlite3.connect(DB_PATH, timeout=15)) as con:
        cur = con.execute(sql, params)
        con.commit()
        return cur.lastrowid


def df_query(sql, params=()):
    with closing(sqlite3.connect(DB_PATH, timeout=15)) as con:
        return pd.read_sql_query(sql, con, params=params)


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
    bad = "Wrong email or password."
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


def set_user(row):
    st.session_state.user = {"id": row["id"], "name": row["name"], "email": row["email"],
                             "age_group": row["age_group"]}
    st.session_state.kids_set = row["age_group"] != "18 or older"
    log("login")
    award(1, "login")


def delete_user_data(uid):
    for t in ("feedback", "chats", "saved"):
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
# AI (Anthropic API, optional) - results cached so repeat views cost nothing
# ----------------------------------------------------------------------------
SYSTEM_BASE = (
    "You are Newsie, a friendly, accurate news explainer for readers in India. "
    "Use only facts given in the provided text; never invent details. If the text is too thin, say so. "
    "Stay politically neutral and avoid graphic detail. Keep language simple and kind."
)


@st.cache_data(ttl=6 * 3600, show_spinner=False, max_entries=500)
def _llm_cached(system, messages_json, max_tokens):
    key = cfg("ANTHROPIC_API_KEY")
    r = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers={"x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
        json={"model": cfg("ANTHROPIC_MODEL", "claude-haiku-5-5"), "max_tokens": max_tokens,
              "system": system, "messages": json.loads(messages_json)}, timeout=45)
    r.raise_for_status()
    return "".join(b.get("text", "") for b in r.json().get("content", []))


def llm(system, messages, max_tokens=700):
    """Returns text, or None when AI is off / limit reached / call failed."""
    if not cfg("ANTHROPIC_API_KEY") or not ai_allowed():
        return None
    log("ai")
    try:
        return _llm_cached(system, json.dumps(messages), max_tokens).strip()
    except Exception:
        return None


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
        return None


def parse_rss(text, provider):
    items = []
    for it in ET.fromstring(text).iter("item"):
        d = {}
        for ch in it:
            d.setdefault(ch.tag.split("}")[-1].lower(), (ch.text or "").strip())
        title, link = strip_tags(d.get("title", "")), d.get("link", "")
        if provider == "bing":
            link = parse_qs(urlparse(link).query).get("url", [link])[0]
        source = d.get("source", "") or ""
        if provider == "google" and source and title.endswith(" - " + source):
            title = title[: -len(source) - 3]
        desc = strip_tags(d.get("description", ""))
        if desc.lower().startswith(title.lower()[:40]):
            desc = ""
        items.append({"title": title, "source": source or provider.title(), "url": link,
                      "published": parse_date(d.get("pubdate", "")), "text": desc or title,
                      "image": d.get("image", "") if d.get("image", "").startswith("https://") else ""})
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
                    "url": a.get("url", ""), "published": pub, "text": txt or a.get("title", ""),
                    "image": (a.get("urlToImage") or "") if (a.get("urlToImage") or "").startswith("https://") else ""})
    return out


def fetch_rss(query, cat):
    qtxt = query or (f"{cat} news India" if cat not in (None, "Top stories") else "India top news")
    try:
        r = requests.get("https://www.bing.com/news/search", params={"q": qtxt, "format": "rss", "mkt": "en-IN"},
                         headers=UA, timeout=12)
        r.raise_for_status()
        items = parse_rss(r.text, "bing")
        if items:
            return items
    except Exception:
        pass
    base = "https://news.google.com/rss"
    tail = "hl=en-IN&gl=IN&ceid=IN:en"
    if query:
        url = f"{base}/search?q={quote_plus(query)}&{tail}"
    elif CATEGORIES.get(cat):
        url = f"{base}/headlines/section/topic/{CATEGORIES[cat]}?{tail}"
    else:
        url = f"{base}?{tail}"
    r = requests.get(url, headers=UA, timeout=12)
    r.raise_for_status()
    return parse_rss(r.text, "google")


@st.cache_data(ttl=600, show_spinner=False)
def fetch_news(query, cat, n, kids):
    """Returns (articles, note). Never raises."""
    want = n * 2 if kids else n
    items, note = [], ""
    try:
        if cfg("NEWSAPI_KEY"):
            items = fetch_newsapi(query, cat, min(want, 50))
    except Exception:
        items = []
    if not items:
        try:
            items = fetch_rss(query, cat)
        except Exception:
            items = []
    if kids:
        items = [a for a in items if not KIDS_BLOCK.search(a["title"] + " " + a["text"])]
    seen, uniq = set(), []
    for a in items:
        k = a["title"].lower()[:60]
        if a["title"] and a["url"] and k not in seen:
            seen.add(k)
            uniq.append(a)
    if not uniq:
        return DEMO_ARTICLES[:n], "Live news couldn't be loaded right now, so these are sample stories. Try again in a minute."
    return uniq[:n], note


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


@st.cache_data(ttl=3600, show_spinner=False)
def extract_article(url):
    """Best-effort article body (first paragraphs). Returns '' on any problem."""
    if not public_url(url):
        return ""
    try:
        r = requests.get(url, headers=UA, timeout=8, allow_redirects=True)
        if "text/html" not in r.headers.get("content-type", ""):
            return ""
        paras = [strip_tags(p) for p in re.findall(r"<p[^>]*>(.*?)</p>", r.text[:600000], flags=re.S | re.I)]
        return " ".join(p for p in paras if len(p) > 60)[:3500]
    except Exception:
        return ""


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


def sentiment(text):
    try:
        from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
        c = SentimentIntensityAnalyzer().polarity_scores(text)["compound"]
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
    s = int((now() - d).total_seconds())
    if s < 3600:
        return f"{max(1, s // 60)} min ago"
    if s < 86400:
        return f"{s // 3600} h ago"
    return d.astimezone(dt.timezone(dt.timedelta(hours=5, minutes=30))).strftime("%d %b %Y")


def guess_emoji(text, cat="Top stories"):
    t = " " + text.lower() + " "
    for k, e in EMOJI_HINTS.items():
        if k in t:
            return e
    return CAT_EMOJI.get(cat, "📰")


# ----------------------------------------------------------------------------
# Translation (chunked, retried, parallel, cached) - fixes the old translate errors
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


def _tr(text, code):
    from deep_translator import GoogleTranslator
    out = []
    for c in _chunks(text):
        for attempt in range(3):
            try:
                out.append(GoogleTranslator(source="auto", target=code).translate(c))
                break
            except Exception:
                if attempt == 2:
                    raise
                time.sleep(0.7 * (attempt + 1))
    return " ".join(out)


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
            return _tr(t, code)
        except Exception:
            return None
    with ThreadPoolExecutor(max_workers=6) as ex:
        res = list(ex.map(one, texts))
    if texts and all(r is None for r in res):
        raise RuntimeError("translation failed")
    return [r if r is not None else t for r, t in zip(res, texts)]


def tr_safe(text):
    """Translate to the user's chosen language; fall back to English with a notice."""
    code = LANGS[st.session_state.lang][0]
    try:
        return translate(text, code)
    except Exception:
        st.warning("Translation is busy right now, so this is shown in English. Please try again in a moment.")
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
def article_text(a):
    return (a.get("full") or a["text"])[:3000]


def explain_simply(a):
    kids = st.session_state.kids
    out = llm(SYSTEM_BASE, [{"role": "user", "content":
        f"Audience: {audience(kids)}.\nExplain this news in 4-5 short sentences, then one line starting "
        f"'Why it matters:'. Do not use bullet points.\nTitle: {a['title']}\nText: {article_text(a)}"}], 450)
    if out:
        return out
    return short_summary(a, 260) + "\n\n(Tip: add an AI key in settings to get a child-friendly explanation here.)"


def cartoon_script(a):
    kids = st.session_state.kids
    out = llm(SYSTEM_BASE, [{"role": "user", "content":
        "Write a 4-panel comic for this news, starring Newsie the owl (explains) and Kiki the tiger cub (asks "
        f"questions). Audience: {audience(kids)}. Panel flow: what happened -> where/who -> why it matters -> a "
        "closing takeaway. Reply with ONLY a JSON array of 4 objects: "
        '{"speaker":"Newsie" or "Kiki","emoji":"1-3 emojis for the scene","text":"max 22 words"}.\n'
        f"Title: {a['title']}\nText: {article_text(a)}"}], 600)
    if out:
        try:
            arr = json.loads(out[out.index("["): out.rindex("]") + 1])
            panels = [{"speaker": "Kiki" if str(p.get("speaker", "")).lower().startswith("k") else "Newsie",
                       "emoji": str(p.get("emoji", "📰"))[:12], "text": str(p.get("text", ""))[:200]}
                      for p in arr[:4] if p.get("text")]
            if len(panels) >= 3:
                return panels, True
        except Exception:
            pass
    sents = [s for s in re.split(r"(?<=[.!?])\s+", a["text"]) if len(s) > 15][:3]
    em = guess_emoji(a["title"] + " " + a["text"])
    base = [("Newsie", em, f"Big news today! {a['title']}")]
    for i, s in enumerate(sents[:2]):
        base.append(("Kiki" if i == 0 else "Newsie", em, s[:180]))
    base.append(("Kiki", "🤔", "Wow! I want to read more about this. Where can I check the full story?"))
    return [{"speaker": s, "emoji": e, "text": t} for s, e, t in base[:4]], False


def cartoon_html(panels, voice_lang, title):
    cards = []
    for i, p in enumerate(panels):
        who = "🦉" if p["speaker"] == "Newsie" else "🐯"
        cards.append(
            f'<div class="panel p{i}" style="animation-delay:{i*0.55}s"><div class="scene">{esc(p["emoji"])}</div>'
            f'<div class="who">{who}</div><div class="bubble"><b>{esc(p["speaker"])}</b>{esc(p["text"])}</div></div>')
    speak = json.dumps(" ".join(p["text"] for p in panels)).replace("</", "<\\/")
    return f"""<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<link href="https://fonts.googleapis.com/css2?family=Baloo+2:wght@600;800&family=Nunito:wght@600;800&display=swap" rel="stylesheet">
<style>
*{{box-sizing:border-box}}body{{margin:0;font-family:Nunito,system-ui,sans-serif;color:#1c1650;background:transparent}}
h3{{font-family:'Baloo 2',sans-serif;color:#F6F4FF;margin:0 0 10px;font-size:18px}}
.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:14px}}
.panel{{background:linear-gradient(160deg,#FFF3C4,#FFD9E0);border:4px solid #1c1650;border-radius:18px;padding:12px;
position:relative;min-height:230px;display:flex;flex-direction:column;justify-content:space-between;
box-shadow:6px 6px 0 #1c1650;opacity:0;transform:scale(.92) rotate(-1deg);animation:pop .5s ease-out forwards}}
.p1{{background:linear-gradient(160deg,#D6F5FF,#E4DBFF)}}.p2{{background:linear-gradient(160deg,#D9FFE9,#FFF3C4)}}.p3{{background:linear-gradient(160deg,#FFE1D6,#FFD9F0)}}
.scene{{font-size:54px;text-align:center;animation:bob 2.6s ease-in-out infinite}}
.who{{font-size:36px;position:absolute;right:10px;top:10px;animation:bob 2s ease-in-out infinite .3s}}
.bubble{{background:#fff;border:3px solid #1c1650;border-radius:16px;padding:9px 12px;font-weight:700;font-size:14.5px;line-height:1.35;position:relative}}
.bubble b{{display:block;font-family:'Baloo 2';color:#7a3cff;font-size:13px}}
button{{margin-top:12px;font:800 15px Nunito;background:#FFC93C;color:#1c1650;border:0;border-radius:14px;padding:12px 18px;min-height:44px;cursor:pointer}}
button:focus-visible{{outline:3px solid #fff;outline-offset:2px}}
@keyframes pop{{to{{opacity:1;transform:none}}}}@keyframes bob{{50%{{transform:translateY(-6px)}}}}
@media (prefers-reduced-motion:reduce){{*{{animation:none!important}}.panel{{opacity:1;transform:none}}}}
</style></head><body>
<h3>{esc(title[:90])}</h3><div class="grid">{''.join(cards)}</div>
<button onclick="say()" aria-label="Read the comic aloud">🔊 Read aloud</button>
<script>
function say(){{const s=window.speechSynthesis;if(!s){{alert('Read aloud is not supported on this device');return}}
s.cancel();const u=new SpeechSynthesisUtterance({speak});u.lang="{voice_lang}";u.rate=.92;s.speak(u);}}
</script></body></html>"""


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
def inject_css():
    st.markdown("""
<link href="https://fonts.googleapis.com/css2?family=Baloo+2:wght@500;700;800&family=Nunito:wght@400;600;800&display=swap" rel="stylesheet">
<style>
:root{--ink:#0F1230;--panel:#1A1E4A;--panel2:#242a63;--sun:#FFC93C;--coral:#FF6B6B;--mint:#3DDC97;--lilac:#9B8CFF;--txt:#F6F4FF}
html,body,[class*="css"],.stMarkdown,p,li,label{font-family:'Nunito',system-ui,sans-serif!important}
h1,h2,h3,h4,.nv-h{font-family:'Baloo 2',system-ui,sans-serif!important;letter-spacing:.2px}
.block-container{max-width:1100px;padding:1rem 1rem 4rem}
[data-testid="stHeader"]{background:transparent}
.stButton>button,.stFormSubmitButton>button,.stDownloadButton>button{border-radius:14px;min-height:44px;font-weight:800;
 border:2px solid rgba(255,255,255,.16)}
.stButton>button[kind="primary"],.stFormSubmitButton>button[kind="primary"]{background:var(--sun);color:#1c1650;border-color:var(--sun)}
.stButton>button:focus-visible{outline:3px solid #fff;outline-offset:2px}
.nv-card{background:linear-gradient(160deg,var(--panel),#161a40);border:1px solid rgba(255,255,255,.10);border-radius:20px;
 padding:16px 18px;margin-bottom:6px;transition:transform .25s ease,box-shadow .25s ease;transform-style:preserve-3d}
@media (hover:hover) and (prefers-reduced-motion:no-preference){.nv-card:hover{transform:perspective(900px) rotateX(2deg) translateY(-3px);box-shadow:0 18px 40px rgba(0,0,0,.4)}}
.nv-card h4{margin:0 0 6px;font-size:1.18rem;line-height:1.3;color:#fff}
.nv-meta{color:#b9b6e6;font-size:.85rem;margin-bottom:8px}
.nv-sum{color:#e9e6ff;line-height:1.55;font-size:.98rem}
.chip{display:inline-block;padding:3px 11px;border-radius:99px;font-size:.78rem;font-weight:800;margin:0 6px 6px 0}
.chip.pos{background:rgba(61,220,151,.18);color:#3DDC97}.chip.neu{background:rgba(155,140,255,.2);color:#C9C0FF}
.chip.neg{background:rgba(255,107,107,.2);color:#FF9A9A}.chip.cat{background:rgba(255,201,60,.16);color:#FFC93C}
.trust{height:7px;border-radius:9px;background:rgba(255,255,255,.1);overflow:hidden;margin:2px 0 4px}
.trust>i{display:block;height:100%;border-radius:9px}
.nv-thumb{width:100%;max-height:150px;object-fit:cover;border-radius:14px;margin-bottom:10px}
.nv-stat{background:var(--panel);border-radius:18px;padding:14px 16px;border:1px solid rgba(255,255,255,.08)}
.nv-stat b{font-family:'Baloo 2';font-size:1.8rem;color:var(--sun);display:block;line-height:1.1}
.nv-note{background:rgba(155,140,255,.12);border-left:4px solid var(--lilac);border-radius:10px;padding:10px 14px;color:#dcd8ff;font-size:.92rem}
@media (max-width:640px){.block-container{padding:.6rem .6rem 4rem}.nv-card h4{font-size:1.05rem}}
</style>""", unsafe_allow_html=True)


HERO_HTML = """<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<link href="https://fonts.googleapis.com/css2?family=Baloo+2:wght@700;800&family=Nunito:wght@600&display=swap" rel="stylesheet">
<style>
html,body{margin:0;height:100%;background:radial-gradient(120% 120% at 70% 40%,#2a2f7a 0%,#12153e 55%,#0b0d28 100%);overflow:hidden;font-family:Nunito,sans-serif}
canvas{position:absolute;inset:0;width:100%;height:100%;touch-action:pan-y}
.t{position:absolute;left:22px;top:18px;right:22px;pointer-events:none;color:#F6F4FF}
.t h1{font:800 clamp(30px,6vw,52px)/1 'Baloo 2',sans-serif;margin:0;text-shadow:0 4px 0 #5b3cff}
.t p{margin:6px 0 0;font-size:clamp(13px,2.4vw,17px);color:#cfcaff;max-width:30ch}
.nogl .t{position:static;padding:30px}
</style></head><body>
<canvas id="c" aria-hidden="true"></canvas>
<div class="t"><h1>NewsVerse 🪐</h1><p>Read it. See it. Understand it.</p></div>
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
    embed_html(HERO_HTML.replace("__HEADS__", payload), 300)


# ----------------------------------------------------------------------------
# Pages
# ----------------------------------------------------------------------------
def auth_screen():
    st.markdown("### Join NewsVerse")
    st.caption("Log in to save stories, earn XP and keep your streak. Guests can explore with fewer AI helpers.")
    t1, t2, t3 = st.tabs(["Log in", "Sign up", "Just explore"])
    with t1:
        with st.form("login_form"):
            e = st.text_input("Email", key="li_e")
            p = st.text_input("Password", type="password", key="li_p")
            if st.form_submit_button("Log in", type="primary", width="stretch"):
                ok, res = login(e, p)
                if ok:
                    set_user(res)
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
            st.caption("We store your nickname, email, XP and what you save or ask, only to run the app. "
                       "You can delete everything from My Space at any time.")
            if st.form_submit_button("Create my account", type="primary", width="stretch"):
                ok, res = signup(n, e, p, ag, c)
                if ok:
                    set_user(q("SELECT * FROM users WHERE id=?", (res,))[0])
                    st.rerun()
                else:
                    st.error(res)
    with t3:
        st.write("No account needed. You can read news, see sentiment and credibility hints, and try 5 AI helpers a day.")
        kid = st.toggle("I'm a kid (turn on Kids Mode)", value=False, key="guest_kid")
        if st.button("Start exploring", type="primary", width="stretch"):
            st.session_state.guest = True
            st.session_state.kids_set = kid
            log("guest_start")
            st.rerun()


def sidebar():
    u = st.session_state.get("user")
    with st.sidebar:
        st.markdown(f"## 🪐 {APP_NAME}")
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
                for k in ("user", "guest", "articles", "chat", "awarded"):
                    st.session_state.pop(k, None)
                st.rerun()
        st.divider()
        st.caption("Credibility and sentiment are quick hints, not facts. Always open the source.")


def card_html(a, summary, cat):
    s_label, s_emoji, s_cls = sentiment(a["title"] + ". " + a["text"])
    score, label, color, why = credibility(a)
    img = f'<img class="nv-thumb" src="{esc(a["image"], True)}" alt="" loading="lazy">' if a.get("image") else ""
    return (f'<div class="nv-card">{img}<h4>{esc(a["title"])}</h4>'
            f'<div class="nv-meta">{esc(a["source"])} · {esc(time_ago(a["published"]))}</div>'
            f'<span class="chip cat">{esc(cat)}</span><span class="chip {s_cls}">{s_emoji} {s_label}</span>'
            f'<div class="nv-sum">{esc(summary)}</div>'
            f'<div class="nv-meta" style="margin-top:10px">Credibility hint: <b style="color:{color}">{label} ({score}/100)</b></div>'
            f'<div class="trust"><i style="width:{score}%;background:{color}"></i></div>'
            f'<div class="nv-meta">{esc("; ".join(why[:2]))}</div></div>')


@st.dialog("Story Studio", width="large")
def studio(a):
    st.markdown(f"#### {esc(a['title'])}")
    if "full" not in a:
        with st.spinner("Reading the story..."):
            a["full"] = extract_article(a["url"])
    log("studio", a["title"][:80])
    award(3, "read_" + a["url"])
    modes = ["🧒 Explain simply", "🎨 Cartoon", "🧠 Quiz", "📚 Hard words"]
    mode = st.radio("What would you like?", modes, horizontal=True, key="studio_mode")
    code, voice = LANGS[st.session_state.lang]
    if mode == modes[0]:
        with st.spinner("Newsie is thinking..."):
            txt = explain_simply(a)
        st.write(tr_safe(txt) if code != "en" else txt)
    elif mode == modes[1]:
        with st.spinner("Drawing your comic..."):
            panels, ai = cartoon_script(a)
            if code != "en":
                try:
                    for p in panels:
                        p["text"] = translate(p["text"], code)
                except Exception:
                    st.warning("Translation is busy, so the comic is in English for now.")
        embed_html(cartoon_html(panels, voice, a["title"]), 620)
        award(10, "cartoon_" + a["url"])
        if not ai:
            st.caption("Quick comic made from the story text. Add an AI key to get richer, funnier comics.")
    elif mode == modes[2]:
        qk = "quiz_" + hashlib.sha1(a["url"].encode()).hexdigest()[:8]
        if qk not in st.session_state:
            with st.spinner("Making questions..."):
                st.session_state[qk] = make_quiz(a) or []
        quiz = st.session_state[qk]
        if not quiz:
            st.info("Quiz needs the AI helper, which is off or used up for today. Try the cartoon or hard words.")
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
                log("quiz", f"{score}/{len(quiz)}")
                st.markdown(f"**You scored {score} out of {len(quiz)}!**")
    else:
        words = hard_words(a["title"] + " " + article_text(a))
        shown = 0
        for w in words:
            d = define(w)
            if d:
                st.markdown(d)
                shown += 1
        if not shown:
            st.info("No tricky words found here, or the dictionary is busy. Try the Ask Newsie page.")


def page_news():
    kids = st.session_state.kids
    cats = KIDS_CATEGORIES if kids else list(CATEGORIES)
    with st.form("news_form"):
        c1, c2, c3 = st.columns([3, 2, 2])
        query = c1.text_input("Search a topic", placeholder="e.g. ISRO, Mysuru Dasara, cricket", max_chars=80)
        cat = c2.selectbox("Category", cats)
        n = c3.slider("Stories", 5, 20, 10)
        go = st.form_submit_button("🔎 Get news", type="primary", width="stretch")
    first = "articles" not in st.session_state
    if go or first or st.session_state.get("kids_prev") != kids:
        with st.spinner("Fetching fresh stories..."):
            arts, note = fetch_news(query.strip(), cat, n, kids)
        st.session_state.articles, st.session_state.note = arts, note
        st.session_state.cat = cat
        st.session_state.kids_prev = kids
        if go:
            log("search", f"{cat}|{query}"[:100])
    arts = st.session_state.get("articles", [])
    if st.session_state.get("note"):
        st.warning(st.session_state.note)
    if kids:
        st.markdown('<div class="nv-note">🧸 Kids Mode is on: gentle stories only, simple explanations and comics.</div>',
                    unsafe_allow_html=True)
    code = LANGS[st.session_state.lang][0]
    summaries = [short_summary(a) for a in arts]
    if code != "en":
        with st.spinner("Translating..."):
            try:
                summaries = translate_many(tuple(summaries), code)
            except Exception:
                st.warning("Translation is busy right now, so summaries are in English. Please try again shortly.")
    cols = st.columns(2) if len(arts) > 1 else [st.container()]
    for i, (a, s) in enumerate(zip(arts, summaries)):
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
            st.link_button("🔍 Cross-check this story on other sites",
                           f"https://www.google.com/search?q={quote_plus(a['title'])}&tbm=nws", width="stretch")


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
    return ("I can look up word meanings (try: *define inflation*). For full answers I need the AI helper, "
            "which isn't available right now.")


def newsie_reply(question):
    kids = st.session_state.kids
    word = dictionary_intent(question)
    if word:
        d = define(word)
        if d:
            return d
    if not cfg("ANTHROPIC_API_KEY"):
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
    st.caption("Questions you ask are saved to help improve NewsVerse. Please don't share personal details.")


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
                 "Deleting your account removes your profile, saved stories, chats and feedback.")
        ok = st.checkbox("I understand this cannot be undone", key="del_ok")
        if st.button("Delete my account and data", disabled=not ok):
            delete_user_data(u["id"])
            for k in ("user", "guest", "chat", "awarded"):
                st.session_state.pop(k, None)
            st.rerun()


def page_feedback():
    st.markdown("### ⭐ Rate NewsVerse")
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
    act = df_query("SELECT substr(ts,1,10) day, COUNT(DISTINCT COALESCE(CAST(user_id AS TEXT), sid)) users "
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
        f = df_query("SELECT f.ts, COALESCE(u.name,'Guest') name, f.rating, f.category, f.message FROM feedback f "
                     "LEFT JOIN users u ON u.id=f.user_id ORDER BY f.id DESC LIMIT 500")
        st.dataframe(f, hide_index=True, width="stretch")
        st.download_button("Download feedback CSV", f.to_csv(index=False).encode(), "feedback.csv", "text/csv")
    with t2:
        c = df_query("SELECT c.ts, COALESCE(u.name,'Guest') name, c.question, c.answer FROM chats c "
                     "LEFT JOIN users u ON u.id=c.user_id ORDER BY c.id DESC LIMIT 500")
        st.dataframe(c, hide_index=True, width="stretch")
        st.download_button("Download doubts CSV", c.to_csv(index=False).encode(), "doubts.csv", "text/csv")
    with t3:
        us = df_query("SELECT id,name,email,age_group,created,last_login,xp,streak FROM users ORDER BY id DESC")
        st.dataframe(us, hide_index=True, width="stretch")
        st.download_button("Download users CSV", us.to_csv(index=False).encode(), "users.csv", "text/csv")
    with t4:
        st.write("Streamlit Community Cloud can wipe local files when the app restarts or redeploys. "
                 "Download a backup regularly, or move to a hosted database (see README).")
        if os.path.exists(DB_PATH):
            with open(DB_PATH, "rb") as fh:
                st.download_button("Download full database backup", fh.read(), "newsverse_backup.db")
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
def main():
    init_db()
    st.session_state.setdefault("sid", secrets.token_hex(6))
    st.session_state.setdefault("kids", False)
    if "kids_set" in st.session_state:
        st.session_state.kids = st.session_state.pop("kids_set")
    st.session_state.setdefault("lang", "English")
    inject_css()
    if "visit_logged" not in st.session_state:
        st.session_state.visit_logged = True
        log("visit")
    sidebar()
    hero()
    if not st.session_state.get("user") and not st.session_state.get("guest"):
        auth_screen()
        return
    pages = ["📰 News", "💬 Ask Newsie", "🧭 My Space", "⭐ Rate us"] + (["🛡️ Owner"] if is_admin() else [])
    choice = st.segmented_control("Menu", pages, default=pages[0], key="nav", label_visibility="collapsed") or pages[0]
    {"📰 News": page_news, "💬 Ask Newsie": page_ask, "🧭 My Space": page_space,
     "⭐ Rate us": page_feedback, "🛡️ Owner": page_admin}[choice]()


main()
