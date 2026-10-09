import os
import re
import json
import hashlib
import time
from urllib.parse import quote_plus
from datetime import datetime, date

import pandas as pd
import pytz
import requests
import streamlit as st
from textblob import TextBlob
from deep_translator import GoogleTranslator

try:
    import feedparser
except Exception:
    feedparser = None

# =========================================================
# EXAMWISE INDIA — current affairs, saving, and revision
# =========================================================
st.set_page_config(
    page_title="ExamWise India | Current Affairs & Revision",
    page_icon="📰",
    layout="wide",
    initial_sidebar_state="expanded",
)

IST = pytz.timezone("Asia/Kolkata")
APP_DIR = os.path.dirname(os.path.abspath(__file__))
LOCAL_FEEDBACK_FILE = os.path.join(APP_DIR, "feedback_store.csv")
LOCAL_SAVED_FILE = os.path.join(APP_DIR, "saved_revision.json")

# Use Streamlit Secrets first, then environment variable.
try:
    NEWSAPI_KEY = st.secrets.get("NEWSAPI_KEY", "")
except Exception:
    NEWSAPI_KEY = ""
NEWSAPI_KEY = NEWSAPI_KEY or os.environ.get("NEWSAPI_KEY", "")

EXAMS = {
    "UPSC CSE": ["Polity", "Economy", "Environment", "Science & Tech", "International Relations", "History", "Geography", "Social Issues", "Governance", "Security"],
    "KAS / KPSC": ["Karnataka Current Affairs", "Polity", "Economy", "Environment", "Science & Tech", "History", "Geography", "Governance"],
    "VAO / Village Administrative Officer": ["State Current Affairs", "Government Schemes", "Indian Polity", "Geography", "General Knowledge", "Economy"],
    "SSC": ["National Current Affairs", "General Knowledge", "Science & Tech", "Economy", "Polity"],
    "Banking": ["Banking & Finance", "Economy", "National Current Affairs", "Science & Tech"],
    "Railway": ["National Current Affairs", "Science & Tech", "Geography", "General Knowledge"],
    "Other competitive exams": ["National Current Affairs", "Polity", "Economy", "Environment", "Science & Tech"],
    "Common Reader": ["Daily Briefing", "Public Services", "Health", "Science & Technology", "Money & Economy", "Local Updates"],
}
INDIAN_STATES = [
    "All India", "Andhra Pradesh", "Arunachal Pradesh", "Assam", "Bihar", "Chhattisgarh",
    "Goa", "Gujarat", "Haryana", "Himachal Pradesh", "Jharkhand", "Karnataka", "Kerala",
    "Madhya Pradesh", "Maharashtra", "Manipur", "Meghalaya", "Mizoram", "Nagaland",
    "Odisha", "Punjab", "Rajasthan", "Sikkim", "Tamil Nadu", "Telangana", "Tripura",
    "Uttar Pradesh", "Uttarakhand", "West Bengal", "Delhi", "Jammu and Kashmir",
    "Ladakh", "Puducherry"
]
LANGUAGES = {
    "English": "en", "Kannada": "kn", "Hindi": "hi", "Tamil": "ta",
    "Telugu": "te", "Malayalam": "ml", "Bengali": "bn", "Marathi": "mr",
}
CATEGORY_OPTIONS = ["All", "Business", "Entertainment", "General", "Health", "Science", "Sports", "Technology"]

# ---------- visual style ----------
st.markdown("""
<style>
:root { color-scheme: dark; }
.stApp { background: #0b1017; color: #edf3fb; }
[data-testid="stHeader"] { background: #0b1017; }
.block-container { padding-top: 2.35rem; padding-bottom: 3rem; max-width: 1450px; }
.hero {
  padding: 1.7rem 1.9rem; border: 1px solid #2b4855; border-radius: 24px;
  background: radial-gradient(circle at 12% 5%, rgba(30,130,117,.42) 0%, transparent 36%),
              radial-gradient(circle at 90% 0%, rgba(99,80,190,.26) 0%, transparent 34%),
              linear-gradient(135deg,#101c2a 0%,#101723 52%,#171426 100%);
  box-shadow: 0 16px 42px rgba(0,0,0,.22); margin-bottom: 1rem;
}
.hero h1 { margin: 0; font-size: clamp(1.8rem, 3vw, 2.7rem); color: #f5fbff; }
.hero p { margin: .5rem 0 0; color: #9edfc8; font-size: 1rem; }
.small-muted { color: #a6b4c6; font-size: .9rem; }
div[data-testid="stVerticalBlockBorderWrapper"] {
  border-color: #263648 !important; border-radius: 16px !important;
  background: rgba(17,25,37,.62);
}
.stButton > button, .stDownloadButton > button {
  border-radius: 10px; border: 1px solid #315b5a; font-weight: 650;
}
.stButton > button[kind="primary"] { background: #167d6b; border-color: #167d6b; }
h1,h2,h3 { letter-spacing: -.025em; }
.stButton > button { transition: all .18s ease-in-out; }
.stButton > button:hover, .stDownloadButton > button:hover { border-color:#70d7c2; transform:translateY(-1px); }
[data-testid="stExpander"] { border:1px solid #29394b; border-radius:14px; }
[data-testid="stTabs"] button { font-weight:650; }
[data-testid="stSidebar"] { background: linear-gradient(180deg,#171c29 0%,#111723 100%); }
.stTabs [data-baseweb="tab-list"] { gap: 8px; }
.stTabs [data-baseweb="tab"] { background:#172231; border-radius:10px; padding:10px 16px; }
div[data-testid="stAlert"] { border-radius: 12px; }
[data-testid="stMetric"] { background: #121d2a; border: 1px solid #263648; padding: 12px 15px; border-radius: 14px; }
</style>
""", unsafe_allow_html=True)

def now_ist():
    return datetime.now(IST)

def now_string():
    return now_ist().strftime("%A, %d %B %Y • %I:%M %p IST")

def stable_article_id(article):
    raw = (article.get("url") or "") + "|" + (article.get("title") or "")
    return hashlib.sha256(raw.encode("utf-8", errors="ignore")).hexdigest()[:16]

def clean_text(value):
    if not value:
        return ""
    value = re.sub(r"<[^>]+>", " ", str(value))
    value = re.sub(r"\s+", " ", value).strip()
    return value

def summarize_text(text, max_sentences=5, max_words=140):
    text = clean_text(text)
    if not text:
        return "The source did not provide article text. Open the original article for details."
    sentences = re.split(r"(?<=[.!?])\s+", text)
    summary = " ".join([s.strip() for s in sentences if s.strip()][:max_sentences])
    words = summary.split()
    if len(words) > max_words:
        summary = " ".join(words[:max_words]) + " …"
    return summary or "No readable summary was available."

def sentiment_label(text):
    try:
        p = TextBlob(clean_text(text)).sentiment.polarity
        if p > 0.12:
            return "Positive 😊"
        if p < -0.12:
            return "Negative"
        return "Neutral"
    except Exception:
        return "Not available"

def credibility_note(source, text):
    # This is a transparent heuristic, NOT a fact-checking result.
    known = ["reuters", "associated press", "bbc", "the hindu", "indian express", "pti"]
    src = (source or "").lower()
    score = 50
    if any(s in src for s in known):
        score += 20
    if len(clean_text(text).split()) >= 100:
        score += 10
    if re.search(r"\b(shocking|miracle|unbelievable|guaranteed|you won't believe)\b", text or "", re.I):
        score -= 15
    score = max(0, min(85, score))
    return score

def _translate_chunk_google(chunk, target):
    return GoogleTranslator(source="auto", target=target).translate(chunk)

def _translate_chunk_mymemory(chunk, target):
    # Independent fallback provider. Public endpoint may impose limits; failures are caught.
    response = requests.get(
        "https://api.mymemory.translated.net/get",
        params={"q": chunk, "langpair": f"en|{target}"},
        timeout=12,
        headers={"User-Agent": "ExamWiseIndia/1.0"},
    )
    response.raise_for_status()
    payload = response.json()
    if payload.get("responseStatus") not in (200, "200"):
        raise RuntimeError(payload.get("responseDetails") or "MyMemory could not translate this text")
    result = (payload.get("responseData") or {}).get("translatedText", "")
    if not result.strip():
        raise RuntimeError("Translation provider returned an empty result")
    return result

def translate_text(text, language):
    """Translate short chunks with two provider attempts; always retain the source summary as fallback."""
    text = clean_text(text)
    if not text:
        return None, "There is no summary text to translate."
    target = LANGUAGES.get(language)
    if not target:
        return None, f"Unsupported target language: {language}"
    if target == "en":
        return text, None

    chunks, remaining = [], text
    while remaining:
        if len(remaining) <= 450:
            chunks.append(remaining)
            break
        split_at = remaining.rfind(" ", 0, 450)
        if split_at < 180:
            split_at = 450
        chunks.append(remaining[:split_at].strip())
        remaining = remaining[split_at:].strip()

    errors = []
    for provider_name, provider in (("Google", _translate_chunk_google), ("MyMemory", _translate_chunk_mymemory)):
        try:
            translated_chunks = []
            for chunk in chunks:
                translated_chunks.append(provider(chunk, target))
                time.sleep(0.15)
            result = " ".join(x for x in translated_chunks if x).strip()
            if result:
                return result, None
            errors.append(f"{provider_name}: empty response")
        except Exception as exc:
            errors.append(f"{provider_name}: {type(exc).__name__}")
            print(f"Translation provider {provider_name} failed for {language}: {type(exc).__name__}: {exc}")
    return None, "Both free translation providers are temporarily unavailable or rate-limited. Your original summary remains available. Please retry later."

def extract_article_text(url):
    """Best-effort extraction from a public article page; paywalls and anti-bot pages may block it."""
    if not url or not url.startswith(("http://", "https://")):
        return "", "A valid article URL was not provided."
    try:
        response = requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0 (compatible; ExamWiseIndia/1.0)"})
        response.raise_for_status()
        html = response.text[:2_000_000]
        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html, "html.parser")
            for node in soup(["script", "style", "nav", "footer", "header", "aside", "noscript"]):
                node.decompose()
            article = soup.find("article") or soup.find("main") or soup
            paragraphs = [clean_text(p.get_text(" ", strip=True)) for p in article.find_all("p")]
            paragraphs = [p for p in paragraphs if len(p.split()) >= 8]
            text = " ".join(paragraphs)
            if len(text.split()) >= 35:
                return text[:16000], None
        except ImportError:
            return "", "Text extraction library is missing. Add beautifulsoup4 to requirements.txt and redeploy."
        return "", "The publisher did not expose readable article text. It may be paywalled or block automated access; use the source link to read it."
    except Exception as exc:
        print(f"Article extraction failed for {url}: {type(exc).__name__}: {exc}")
        return "", "Could not retrieve the article text. The source may be unavailable or block automated access."

def parse_date(raw):
    if not raw:
        return "Date not provided by source"
    try:
        dt = pd.to_datetime(raw, utc=True, errors="coerce")
        if pd.isna(dt):
            return str(raw)
        return dt.tz_convert("Asia/Kolkata").strftime("%d %b %Y, %I:%M %p IST")
    except Exception:
        return str(raw)

def fetch_news_api(keyword, category, page_size):
    if not NEWSAPI_KEY:
        return [], "NEWSAPI_KEY is not configured."
    endpoint = "https://newsapi.org/v2/everything" if keyword.strip() else "https://newsapi.org/v2/top-headlines"
    params = {"apiKey": NEWSAPI_KEY, "pageSize": page_size, "language": "en", "sortBy": "publishedAt"}
    if keyword.strip():
        params["q"] = keyword.strip()
    else:
        params["country"] = "in"
        if category != "All" and category.lower() in {"business", "entertainment", "general", "health", "science", "sports", "technology"}:
            params["category"] = category.lower()
    try:
        response = requests.get(endpoint, params=params, timeout=15)
        response.raise_for_status()
        data = response.json()
        if data.get("status") != "ok":
            return [], data.get("message", "News provider returned an error.")
        articles = []
        for item in data.get("articles", []):
            articles.append({
                "title": item.get("title") or "Untitled article",
                "url": item.get("url") or "",
                "source": (item.get("source") or {}).get("name") or "Unknown source",
                "publishedAt": item.get("publishedAt") or "",
                "description": item.get("description") or "",
                "content": item.get("content") or "",
            })
        return articles, None
    except requests.RequestException as exc:
        return [], f"NewsAPI request failed: {exc}"
    except Exception as exc:
        return [], f"Could not parse news response: {exc}"

@st.cache_data(ttl=300, show_spinner=False)
def fetch_rss_cached(feed_urls, max_items):
    """Fetch multiple RSS feeds independently; one failed feed must not block the others."""
    if not feedparser:
        return []
    items = []
    for feed_url in feed_urls:
        try:
            # requests first gives predictable timeout/error handling across Streamlit hosts
            response = requests.get(
                feed_url, timeout=12,
                headers={"User-Agent": "Mozilla/5.0 (compatible; ExamWiseIndia/1.1)"},
            )
            response.raise_for_status()
            feed = feedparser.parse(response.content)
            feed_name = clean_text(feed.feed.get("title", "")) or "RSS news source"
            for entry in feed.entries[:max_items]:
                description = clean_text(entry.get("summary", ""))
                if not description:
                    content_blocks = entry.get("content", [])
                    if content_blocks:
                        description = clean_text(content_blocks[0].get("value", ""))
                title = clean_text(entry.get("title")) or "Untitled article"
                # Google News RSS often provides only a title. Preserve it as source text
                # so users can still search/translate the headline, while flagging missing body below.
                items.append({
                    "title": title,
                    "url": entry.get("link", ""),
                    "source": clean_text((entry.get("source") or {}).get("title", "")) or feed_name,
                    "publishedAt": entry.get("published") or entry.get("updated") or "",
                    "description": description,
                    "content": description,
                    "body_available": bool(description),
                })
        except Exception as exc:
            print(f"RSS feed error ({feed_url}): {type(exc).__name__}: {exc}")
    unique, seen = [], set()
    for item in items:
        key = item.get("url") or item.get("title")
        if key and key not in seen:
            unique.append(item)
            seen.add(key)
    return unique

def google_news_feed(query):
    q = quote_plus(query)
    return f"https://news.google.com/rss/search?q={q}&hl=en-IN&gl=IN&ceid=IN:en"

def fetch_news(keyword, category, page_size, state):
    """NewsAPI first when configured; broad multi-query RSS discovery otherwise.

    Region matches are ranked, not hard-filtered, so a small state feed still includes
    relevant national stories. Query feeds also keep the app useful without an API key.
    """
    articles, api_error = fetch_news_api(keyword, category, page_size)
    if not articles:
        exam = st.session_state.get("exam", "Common Reader")
        state_query = "India news" if state == "All India" else f"{state} latest news"
        exam_queries = {
            "UPSC CSE": ["India current affairs government policy", "UPSC relevant economy environment science", "PIB government schemes India"],
            "KAS / KPSC": ["Karnataka current affairs government schemes", "KPSC Karnataka state news", "Karnataka economy education agriculture"],
            "VAO / Village Administrative Officer": ["Karnataka village administration revenue department", "Karnataka government schemes agriculture rural development", "Karnataka district news panchayat land records"],
            "SSC": ["India general knowledge current affairs", "India science technology sports awards appointments"],
            "Banking": ["India RBI banking finance economy current affairs", "RBI monetary policy banking news India"],
            "Railway": ["Indian Railways latest news recruitment", "India science geography general knowledge current affairs"],
            "Other competitive exams": ["India competitive exam current affairs", "India government schemes science economy polity"],
            "Common Reader": ["India latest news explained", "India health education science technology", "India consumer alerts public services"],
        }
        queries = [state_query] + exam_queries.get(exam, exam_queries["Common Reader"])
        if keyword.strip():
            queries.insert(0, keyword.strip())
        if category != "All":
            queries.insert(1, f"India {category.lower()} news")
        # Include several independent feeds so one publisher outage cannot leave one result.
        feeds = [google_news_feed(q) for q in queries]
        feeds.extend([
            "https://feeds.bbci.co.uk/news/world/asia/india/rss.xml",
            "https://www.thehindu.com/news/national/feeder/default.rss",
            "https://indianexpress.com/section/india/feed/",
            "https://www.thehindu.com/news/states/karnataka/feeder/default.rss",
            "https://indianexpress.com/section/cities/bangalore/feed/",
            "https://pib.gov.in/RssMain.aspx?ModId=6&Lang=1",
        ])
        articles = fetch_rss_cached(tuple(feeds), max(12, min(35, page_size)))

    # Deduplicate before filters. Don't apply a strict keyword filter to Google News results:
    # the query feed already performed the search and publisher metadata can differ.
    seen, deduped = set(), []
    for article in articles:
        key = article.get("url") or article.get("title")
        if key and key not in seen:
            deduped.append(article)
            seen.add(key)
    articles = deduped

    if keyword.strip():
        needle = keyword.strip().lower()
        matched = [a for a in articles if needle in (a.get("title", "") + " " + a.get("description", "") + " " + a.get("content", "")).lower()]
        if matched:
            articles = matched

    if category != "All":
        cat_terms = {
            "Business": ["business", "economy", "market", "bank", "finance", "budget", "rbi"],
            "Entertainment": ["film", "movie", "actor", "music", "entertainment"],
            "General": ["india", "government", "national", "policy"],
            "Health": ["health", "hospital", "disease", "medical"],
            "Science": ["science", "research", "space", "isro", "technology"],
            "Sports": ["sports", "cricket", "football", "tournament", "athlete"],
            "Technology": ["technology", "digital", "artificial intelligence", "software", "cyber"],
        }.get(category, [])
        matched = [a for a in articles if any(term in (a.get("title", "") + " " + a.get("description", "")).lower() for term in cat_terms)]
        if matched:
            articles = matched

    if state != "All India":
        state_terms = {
            "Karnataka": ["karnataka", "bengaluru", "bangalore", "mysuru", "mysore", "mangaluru", "kannada", "dasara", "belagavi", "kalaburagi"],
            "Tamil Nadu": ["tamil nadu", "chennai", "madurai", "coimbatore"],
            "Kerala": ["kerala", "kochi", "thiruvananthapuram", "kozhikode"],
            "Maharashtra": ["maharashtra", "mumbai", "pune", "nagpur"],
            "Delhi": ["delhi", "new delhi"],
            "Uttar Pradesh": ["uttar pradesh", "lucknow", "kanpur", "varanasi"],
            "Telangana": ["telangana", "hyderabad"],
            "Andhra Pradesh": ["andhra pradesh", "amaravati", "visakhapatnam"],
            "West Bengal": ["west bengal", "kolkata"],
        }
        terms = state_terms.get(state, [state.lower()])
        state_matches = [a for a in articles if any(t in (a.get("title", "") + " " + a.get("description", "") + " " + a.get("content", "")).lower() for t in terms)]
        articles = state_matches + [a for a in articles if a not in state_matches]

    # Prefer articles with real descriptions, then newest feed ordering. Don't claim body text
    # exists when RSS only has a headline.
    articles.sort(key=lambda a: bool(clean_text(a.get("description") or a.get("content"))), reverse=True)
    return articles[:page_size], api_error

def subject_suggestions(article_text, exam):
    text = (article_text or "").lower()
    keywords = {
        "Polity": ["constitution", "parliament", "court", "bill", "election", "government", "ministry", "policy"],
        "Economy": ["economy", "inflation", "gdp", "bank", "tax", "budget", "market", "employment", "rbi"],
        "Environment": ["climate", "forest", "wildlife", "pollution", "renewable", "biodiversity", "environment"],
        "Science & Tech": ["artificial intelligence", "space", "isro", "technology", "research", "digital", "scientific"],
        "International Relations": ["india-us", "india china", "bilateral", "summit", "foreign", "united nations", "diplomacy"],
        "History": ["heritage", "archaeology", "historical", "freedom struggle", "monument"],
        "Geography": ["river", "monsoon", "earthquake", "district", "coast", "rainfall"],
        "Governance": ["scheme", "welfare", "public service", "governance", "beneficiaries"],
        "Karnataka Current Affairs": ["karnataka", "bengaluru", "mysuru", "kannada"],
        "State Current Affairs": ["state government", "district", "village", "state scheme"],
        "Banking & Finance": ["bank", "rbi", "interest rate", "digital payment", "loan", "financial"],
        "Government Schemes": ["scheme", "yojana", "beneficiary", "subsidy", "mission"],
        "General Knowledge": ["award", "appointment", "tournament", "national", "record"],
        "National Current Affairs": ["india", "national", "central government", "ministry"],
        "Social Issues": ["education", "health", "poverty", "women", "children", "inequality"],
        "Security": ["defence", "border", "cybersecurity", "military", "security"],
    }
    scores = [(sum(1 for kw in kws if kw in text), label) for label, kws in keywords.items()]
    scores.sort(reverse=True)
    result = [label for score, label in scores[:3] if score > 0]
    return result or [EXAMS[exam][0]]

def make_revision_sheet(article):
    title = article.get("title", "Untitled")
    text = clean_text(article.get("content") or article.get("description") or "")
    summary = summarize_text(text, max_sentences=5, max_words=140)
    subjects = subject_suggestions(title + " " + text, st.session_state.exam)
    facts = re.split(r"(?<=[.!?])\s+", text)
    facts = [x.strip() for x in facts if len(x.split()) >= 5][:6]
    lines = [
        f"# Last-Minute Revision Sheet",
        f"## {title}",
        f"- Exam track: {st.session_state.exam}",
        f"- State focus: {st.session_state.state}",
        f"- Source: {article.get('source', 'Unknown')}",
        f"- Published: {parse_date(article.get('publishedAt'))}",
        f"- Suggested syllabus areas: {', '.join(subjects)}",
        "",
        "## 60-second summary",
        summary,
        "",
        "## Key points from available source text",
    ]
    if facts:
        lines.extend([f"- {f}" for f in facts])
    else:
        lines.append("- Source text is limited. Open the original article and add verified facts before using these notes.")
    lines.extend([
        "",
        "## Quick self-test",
        "1. What is the central issue or development?",
        "2. Which institution, ministry, state, or group is involved?",
        "3. Why is this relevant to the syllabus?",
        "4. What are one likely benefit, one concern, and one way forward?",
        "",
        "## Mains practice",
        f"Discuss the significance of the development in the context of {', '.join(subjects)}. Include evidence, challenges, and a balanced way forward.",
        "",
        "> Revision aid generated from the available source text. Verify facts, figures, dates and official details before an exam.",
    ])
    return "\n".join(lines)

def read_csv_feedback():
    cols = ["Time", "Exam", "State", "Article Title", "Source", "URL", "Feedback Type", "Feedback"]
    try:
        if os.path.exists(LOCAL_FEEDBACK_FILE):
            df = pd.read_csv(LOCAL_FEEDBACK_FILE)
            for col in cols:
                if col not in df.columns:
                    df[col] = ""
            return df[cols]
    except Exception as exc:
        print(f"Feedback CSV read error: {exc}")
    return pd.DataFrame(columns=cols)

def save_feedback(row):
    cols = ["Time", "Exam", "State", "Article Title", "Source", "URL", "Feedback Type", "Feedback"]
    new_df = pd.DataFrame([row], columns=cols)
    try:
        exists = os.path.exists(LOCAL_FEEDBACK_FILE)
        new_df.to_csv(LOCAL_FEEDBACK_FILE, mode="a" if exists else "w", header=not exists, index=False)
        return True, None
    except Exception as exc:
        print(f"Feedback save error: {exc}")
        return False, str(exc)

# ---------- session state ----------
defaults = {
    "articles": [],
    "last_fetch_query": "",
    "saved_articles": {},
    "highlights": {},
    "notes": {},
    "feedback": read_csv_feedback(),
    "translation_cache": {},
    "article_text_cache": {},
    "exam": "UPSC CSE",
    "state": "All India",
    "quiz_history": [],
    "pyq_text": "",
    "pyq_name": "",
    "study_days": [],
}
for key, value in defaults.items():
    if key not in st.session_state:
        st.session_state[key] = value

# ---------- header ----------
st.markdown(
    f'<div class="hero"><h1>📰 ExamWise India</h1>'
    f'<p>Current affairs → exam relevance → save → revise. Built for focused preparation.</p>'
    f'<div class="small-muted">{now_string()}</div></div>',
    unsafe_allow_html=True,
)

with st.sidebar:
    st.markdown("## 🎯 Your preparation")
    st.session_state.exam = st.selectbox("Exam target", list(EXAMS.keys()), index=list(EXAMS.keys()).index(st.session_state.exam))
    st.session_state.state = st.selectbox("State / region focus", INDIAN_STATES, index=INDIAN_STATES.index(st.session_state.state))
    st.caption("State matching uses article text and keywords. It is a helpful filter, not an official geographic classifier.")
    st.markdown("---")
    page = st.radio("Workspace", ["Home Dashboard", "News Desk", "PYQ & Mock Lab", "My Revision Bank", "Progress Tracker", "Feedback & Analytics", "About & Setup"], index=0)
    st.markdown("---")
    st.metric("Saved revision items", len(st.session_state.saved_articles))
    st.metric("Feedback entries this session", len(st.session_state.feedback))

# ---------- HOME DASHBOARD ----------
if page == "Home Dashboard":
    st.markdown("### Your preparation cockpit")
    st.caption("One place for everyday reading, competitive-exam preparation and quick revision.")
    d1, d2, d3, d4 = st.columns(4)
    d1.metric("Saved revision items", len(st.session_state.saved_articles))
    d2.metric("Quiz attempts", len(st.session_state.quiz_history))
    d3.metric("Feedback submitted", len(st.session_state.feedback))
    d4.metric("Exam focus", st.session_state.exam)
    st.markdown("#### Choose your next action")
    cards = st.columns(3)
    with cards[0]:
        st.markdown("<div class='hero'><h3>📰 Daily Briefing</h3><p>News, explainers and local updates.</p></div>", unsafe_allow_html=True)
        if st.button("Open News Desk", use_container_width=True):
            st.session_state.dashboard_go = "News Desk"
            st.rerun()
    with cards[1]:
        st.markdown("<div class='hero'><h3>🎯 Practice Arena</h3><p>Practice MCQs and work with uploaded past papers.</p></div>", unsafe_allow_html=True)
        if st.button("Open PYQ & Mock Lab", use_container_width=True):
            st.session_state.dashboard_go = "PYQ & Mock Lab"
            st.rerun()
    with cards[2]:
        st.markdown("<div class='hero'><h3>⚡ Quick Revision</h3><p>Saved summaries, highlights and cheat sheets.</p></div>", unsafe_allow_html=True)
        if st.button("Open Revision Bank", use_container_width=True):
            st.session_state.dashboard_go = "My Revision Bank"
            st.rerun()
    if st.session_state.get("dashboard_go"):
        st.info(f"Choose **{st.session_state.dashboard_go}** from Workspace in the sidebar to continue.")
    st.markdown("#### Your study momentum")
    if st.session_state.quiz_history:
        hist = pd.DataFrame(st.session_state.quiz_history)
        st.line_chart(hist.set_index("Attempt")["Percent"])
        st.dataframe(hist.tail(10), use_container_width=True, hide_index=True)
    else:
        st.info("Complete a practice quiz in PYQ & Mock Lab to start your score tracker.")
    st.markdown("#### Exam-focused guidance")
    st.write(f"Current track: **{st.session_state.exam}** · Region: **{st.session_state.state}**")
    st.write("Use News Desk for current affairs, PYQ & Mock Lab for practice, and My Revision Bank for summaries you want to revisit.")

# ---------- NEWS DESK ----------
elif page == "News Desk":
    st.markdown("### Your daily current-affairs desk")
    st.caption("Use the source link to verify the full report. Summaries and syllabus tags are aids, not official exam guidance.")
    with st.container(border=True):
        c1, c2, c3 = st.columns([2.2, 1.2, 1])
        with c1:
            keyword = st.text_input("Search topic or keyword", placeholder="e.g. Karnataka budget, climate change, RBI")
        with c2:
            category = st.selectbox("News category", CATEGORY_OPTIONS)
        with c3:
            page_size = st.slider("Articles", 1, 50, 10)
        lang = st.selectbox("Translate summaries to", list(LANGUAGES.keys()), index=0)
        fetch = st.button("🔎 Fetch latest news", type="primary", use_container_width=True)
    if fetch:
        with st.spinner("Fetching current affairs…"):
            articles, api_error = fetch_news(keyword, category, page_size, st.session_state.state)
        # Store articles so form submissions and other reruns don't clear the list.
        st.session_state.articles = articles
        st.session_state.last_fetch_query = keyword
        st.session_state.translation_cache = {}
        if not articles:
            if api_error:
                st.warning(api_error)
            st.info("No matching articles came back from the configured news feeds. Try All India, remove the keyword, or retry later. For more consistent coverage, add NEWSAPI_KEY in Streamlit Cloud → Settings → Secrets.")
        else:
            st.success(f"Loaded {len(articles)} articles. Your list will remain visible during feedback and save actions in this session.")
    articles = st.session_state.articles
    if articles:
        top = st.columns(4)
        top[0].metric("Articles loaded", len(articles))
        top[1].metric("Exam track", st.session_state.exam)
        top[2].metric("Saved", len(st.session_state.saved_articles))
        top[3].metric("Region", st.session_state.state)
        st.markdown("---")
        for i, article in enumerate(articles):
            title = article.get("title") or "Untitled article"
            source = article.get("source") or "Unknown source"
            url = article.get("url") or ""
            published = parse_date(article.get("publishedAt"))
            raw_text = clean_text(st.session_state.article_text_cache.get(stable_article_id(article)) or article.get("content") or article.get("description") or "")
            aid = stable_article_id(article)
            if raw_text:
                summary = summarize_text(raw_text)
            else:
                summary = (f"Headline brief: {title}. The publisher did not provide article-body text in the feed. "
                           "Use the original report to verify details before relying on this item for revision.")
            topics = subject_suggestions(title + " " + raw_text, st.session_state.exam)
            with st.container(border=True):
                st.markdown(f"### {i+1}. {title}")
                st.caption(f"🗞️ {source}  •  🕒 {published}")
                st.caption("Suggested syllabus: " + " · ".join(topics))
                if url:
                    st.markdown(f"[Read original report ↗]({url})")
                if len(raw_text.split()) < 20:
                    st.caption("ℹ️ Limited source text: the feed may provide only a headline. Use ‘Try to fetch article text’ when available, then verify from the publisher.")
                if len(raw_text.split()) < 20 and url:
                    if st.button("🧾 Try to fetch article text", key=f"extract_{aid}"):
                        with st.spinner("Trying to extract readable article text…"):
                            extracted, extraction_error = extract_article_text(url)
                        if extracted:
                            st.session_state.article_text_cache[aid] = extracted
                            st.success("Article text retrieved. Summary updated.")
                            st.rerun()
                        else:
                            st.warning(extraction_error)
                with st.expander("📝 Quick summary", expanded=True):
                    st.write(summary)
                    st.caption(f"Sentiment signal: {sentiment_label(title + ' ' + raw_text)}")
                    score = credibility_note(source, raw_text)
                    st.progress(score / 100, text=f"Source/text heuristic: {score}/100 — not a verified truth score")
                action1, action2, action3 = st.columns([1, 1, 1])
                with action1:
                    if aid in st.session_state.saved_articles:
                        if st.button("★ Saved — remove", key=f"unsave_{aid}", use_container_width=True):
                            st.session_state.saved_articles.pop(aid, None)
                            st.rerun()
                    else:
                        if st.button("☆ Save for revision", key=f"save_{aid}", use_container_width=True):
                            st.session_state.saved_articles[aid] = {
                                **article, "id": aid, "summary": summary,
                                "exam": st.session_state.exam, "state": st.session_state.state,
                                "topics": topics, "saved_at": now_ist().isoformat()
                            }
                            st.rerun()
                with action2:
                    if st.button("🌐 Translate / retry", key=f"translate_{aid}", use_container_width=True):
                        translated, error = translate_text(summary, lang)
                        st.session_state.translation_cache[aid + "|" + lang] = {"text": translated, "error": error}
                with action3:
                    if st.button("📄 Build revision sheet", key=f"sheet_{aid}", use_container_width=True):
                        st.session_state.saved_articles.setdefault(aid, {
                            **article, "id": aid, "summary": summary,
                            "exam": st.session_state.exam, "state": st.session_state.state,
                            "topics": topics, "saved_at": now_ist().isoformat()
                        })
                        st.session_state["active_sheet"] = aid
                        st.rerun()
                tkey = aid + "|" + lang
                if tkey in st.session_state.translation_cache:
                    tr = st.session_state.translation_cache[tkey]
                    if tr["text"]:
                        st.success(f"🌐 Translated summary ({lang})")
                        st.write(tr["text"])
                    else:
                        st.warning(tr["error"] or "Translation failed.")
                elif lang == "English":
                    st.caption("Translation: English selected; the original summary is already in English.")
                if st.session_state.get("active_sheet") == aid:
                    sheet = make_revision_sheet(article)
                    st.markdown("#### ⚡ Last-minute revision sheet")
                    st.markdown(sheet)
                    st.download_button(
                        "⬇️ Download revision sheet (.md)", data=sheet,
                        file_name=f"revision_{aid}.md", mime="text/markdown", key=f"download_sheet_{aid}"
                    )
                with st.expander("🖍️ Highlight & personal notes"):
                    current_highlight = st.session_state.highlights.get(aid, "")
                    new_highlight = st.text_area("Important line / fact to remember", value=current_highlight, key=f"highlight_{aid}")
                    current_note = st.session_state.notes.get(aid, "")
                    new_note = st.text_area("Your own revision note", value=current_note, key=f"note_{aid}")
                    if st.button("Save highlights and notes", key=f"save_notes_{aid}"):
                        st.session_state.highlights[aid] = new_highlight
                        st.session_state.notes[aid] = new_note
                        if aid not in st.session_state.saved_articles:
                            st.session_state.saved_articles[aid] = {
                                **article, "id": aid, "summary": summary,
                                "exam": st.session_state.exam, "state": st.session_state.state,
                                "topics": topics, "saved_at": now_ist().isoformat()
                            }
                        st.success("Highlights and notes saved for this session.")
                with st.expander("💬 Send feedback about this article"):
                    with st.form(key=f"feedback_form_{aid}", clear_on_submit=True):
                        fb_type = st.selectbox("Feedback type", ["Incorrect or outdated", "Translation issue", "Summary improvement", "Source issue", "Feature request", "Other"], key=f"fbtype_{aid}")
                        fb_text = st.text_area("What should we improve?", key=f"fbtext_{aid}", placeholder="Tell us what is wrong or what would help…")
                        submitted = st.form_submit_button("Submit feedback")
                    if submitted:
                        if not fb_text.strip():
                            st.warning("Please write feedback before submitting.")
                        else:
                            row = {
                                "Time": now_ist().strftime("%d-%m-%Y %I:%M %p"),
                                "Exam": st.session_state.exam,
                                "State": st.session_state.state,
                                "Article Title": title,
                                "Source": source,
                                "URL": url,
                                "Feedback Type": fb_type,
                                "Feedback": fb_text.strip(),
                            }
                            ok, err = save_feedback(row)
                            st.session_state.feedback = pd.concat(
                                [st.session_state.feedback, pd.DataFrame([row])],
                                ignore_index=True
                            )
                            if ok:
                                st.success("Feedback submitted and added to the dashboard.")
                            else:
                                st.warning("Feedback is visible in this session, but CSV persistence failed. On Streamlit Cloud, use a database for durable storage.")
                st.markdown("")
    else:
        st.info("Fetch news to begin. For reliable article access, configure your NewsAPI key in Streamlit Secrets.")

# ---------- PYQ & MOCK LAB ----------
elif page == "PYQ & Mock Lab":
    st.markdown("### 🎯 PYQ & Mock Lab")
    st.caption("Practice questions and upload your own previous-year paper. Sample questions below are practice material, not claimed as authentic past-paper questions.")
    tab_practice, tab_upload, tab_plan = st.tabs(["🧠 Practice MCQs", "📄 Work with a past paper", "🗓️ Revision plan"])
    sample_bank = {
        "UPSC CSE": [
            {"q":"Which part of the Indian Constitution contains the Directive Principles of State Policy?", "opts":["Part II", "Part III", "Part IV", "Part IVA"], "ans":2, "why":"Directive Principles are in Part IV (Articles 36–51)."},
            {"q":"The primary objective of a monetary policy repo-rate change is to influence:", "opts":["Only agricultural land records", "Liquidity and borrowing conditions", "State boundaries", "Census language data"], "ans":1, "why":"The repo rate affects the cost of short-term funds and monetary conditions."},
            {"q":"Which gas is most associated with human-caused global warming by total contribution?", "opts":["Carbon dioxide", "Neon", "Helium", "Argon"], "ans":0, "why":"Carbon dioxide is the largest contributor among long-lived anthropogenic greenhouse gases."},
        ],
        "KAS / KPSC": [
            {"q":"Mysuru Dasara is primarily associated with which state?", "opts":["Karnataka", "Kerala", "Odisha", "Punjab"], "ans":0, "why":"Mysuru Dasara is a major cultural festival of Karnataka."},
            {"q":"Which body conducts recruitment examinations for Karnataka state civil services?", "opts":["KPSC", "UPSC only", "RBI", "UGC"], "ans":0, "why":"The Karnataka Public Service Commission conducts notified state recruitment examinations."},
            {"q":"The Vidhana Soudha is located in:", "opts":["Mysuru", "Bengaluru", "Belagavi", "Kalaburagi"], "ans":1, "why":"Vidhana Soudha, the Karnataka Legislature secretariat building, is in Bengaluru."},
        ],
        "VAO / Village Administrative Officer": [
            {"q":"Which record is commonly used to identify agricultural land ownership/tenancy details in Karnataka?", "opts":["RTC / Pahani", "Passport", "Driving licence", "Voter ink register"], "ans":0, "why":"RTC/Pahani is a Karnataka land record; always check the current official terminology and rules."},
            {"q":"Gram Sabha consists of:", "opts":["All registered voters in the village panchayat area", "Only elected MPs", "Only government officers", "Only school teachers"], "ans":0, "why":"The Gram Sabha comprises persons registered in the electoral rolls for the village-level panchayat area, subject to the applicable law."},
            {"q":"Which constitutional amendment gave constitutional status to Panchayati Raj institutions?", "opts":["42nd", "44th", "73rd", "86th"], "ans":2, "why":"The 73rd Constitutional Amendment Act relates to Panchayati Raj institutions."},
        ],
        "SSC": [
            {"q":"What is the SI unit of force?", "opts":["Joule", "Newton", "Watt", "Pascal"], "ans":1, "why":"Force is measured in newtons."},
            {"q":"Which Article deals with equality before law?", "opts":["Article 14", "Article 19", "Article 21A", "Article 32"], "ans":0, "why":"Article 14 guarantees equality before the law and equal protection of the laws."},
            {"q":"Which is the largest planet in the Solar System?", "opts":["Earth", "Mars", "Jupiter", "Venus"], "ans":2, "why":"Jupiter is the largest planet in the Solar System."},
        ],
        "Banking": [
            {"q":"Which institution is India's central bank?", "opts":["SEBI", "RBI", "NABARD only", "SBI"], "ans":1, "why":"The Reserve Bank of India is India's central bank."},
            {"q":"Inflation generally means:", "opts":["A sustained rise in the general price level", "A fall in all prices", "A rise in rainfall", "A change in time zones"], "ans":0, "why":"Inflation is a sustained increase in the general price level."},
            {"q":"UPI is primarily used for:", "opts":["Digital payments", "Land surveying", "Weather forecasting", "Passport printing"], "ans":0, "why":"UPI is an instant payment system enabling bank-to-bank digital transfers."},
        ],
        "Railway": [
            {"q":"Which organisation operates India's national railway network?", "opts":["Indian Railways", "NHAI", "AAI", "BSNL"], "ans":0, "why":"Indian Railways operates the national rail transport network under the Ministry of Railways."},
            {"q":"The SI unit of electric power is:", "opts":["Volt", "Ampere", "Watt", "Ohm"], "ans":2, "why":"Power is measured in watts."},
            {"q":"Which vitamin is produced in the skin through sunlight exposure?", "opts":["Vitamin A", "Vitamin B12", "Vitamin C", "Vitamin D"], "ans":3, "why":"UVB exposure helps the skin synthesize vitamin D."},
        ],
        "Other competitive exams": [
            {"q":"Which body is responsible for conducting the Civil Services Examination for central services?", "opts":["UPSC", "UGC", "SEBI", "NITI Aayog"], "ans":0, "why":"UPSC conducts the Civil Services Examination under its constitutional mandate."},
            {"q":"Which Article of the Constitution guarantees equality before the law?", "opts":["Article 14", "Article 17", "Article 21A", "Article 40"], "ans":0, "why":"Article 14 guarantees equality before the law and equal protection of laws."},
            {"q":"Which institution publishes India's consumer price inflation data through the official statistical system?", "opts":["National Statistical Office", "Election Commission", "UPSC", "ISRO"], "ans":0, "why":"The National Statistical Office under MoSPI compiles and releases major official statistics, including CPI."},
        ],
        "Common Reader": [
            {"q":"What is the safest first step if a message claims you won a prize and asks for your bank OTP?", "opts":["Share the OTP", "Click every link", "Never share OTP and verify independently", "Forward it to contacts"], "ans":2, "why":"Banks and legitimate services do not require you to share OTPs with callers or messages."},
            {"q":"Which household action usually helps reduce electricity use?", "opts":["Leave lights on", "Use efficient LEDs and switch off unused devices", "Keep doors open with AC running", "Run appliances empty"], "ans":1, "why":"Efficient lighting and switching off unused equipment reduces unnecessary electricity consumption."},
            {"q":"Which source is best for checking whether a government scheme is currently open?", "opts":["An anonymous forwarded message", "An official government portal or notification", "An old social post", "An unverified comment"], "ans":1, "why":"Use the official department portal or notification and verify eligibility and dates."},
        ],
    }
    bank_key = st.session_state.exam if st.session_state.exam in sample_bank else "Other competitive exams"
    questions = sample_bank[bank_key]
    with tab_practice:
        st.info(f"Practice set for **{bank_key}**. These are sample practice MCQs; they are not represented as official previous-year questions.")
        with st.form("practice_quiz_form"):
            answers = []
            for qi, q in enumerate(questions):
                st.markdown(f"**Q{qi+1}. {q['q']}**")
                answers.append(st.radio("Choose one answer", q["opts"], key=f"practice_{bank_key}_{qi}", index=None, label_visibility="collapsed"))
            submitted = st.form_submit_button("Check answers", type="primary", use_container_width=True)
        if submitted:
            score = 0
            for qi, (q, answer) in enumerate(zip(questions, answers)):
                if answer is not None and q["opts"].index(answer) == q["ans"]:
                    score += 1
            percent = round(score / len(questions) * 100)
            attempt = {"Attempt": len(st.session_state.quiz_history) + 1, "Date": now_ist().strftime("%d-%m-%Y %I:%M %p"), "Exam": bank_key, "Score": f"{score}/{len(questions)}", "Percent": percent}
            st.session_state.quiz_history.append(attempt)
            st.session_state.last_quiz_answers = answers
            st.session_state.last_quiz_exam = bank_key
            st.session_state.last_quiz_score = score
            st.rerun()
        if st.session_state.get("last_quiz_exam") == bank_key and "last_quiz_score" in st.session_state:
            st.success(f"Latest score: {st.session_state.last_quiz_score}/{len(questions)}")
            for qi, q in enumerate(questions):
                st.markdown(f"**Q{qi+1} explanation:** {q['why']}")
    with tab_upload:
        st.markdown("Upload a previous-year question paper to read and search it here. The app does not invent exam/year labels: enter the details you know.")
        paper_name = st.text_input("Paper name / year", placeholder="e.g. KPSC VAO 2023 Paper 1")
        paper_file = st.file_uploader("Upload PDF, TXT or text-based CSV", type=["pdf", "txt", "csv"])
        if paper_file is not None:
            extracted = ""
            try:
                if paper_file.name.lower().endswith(".pdf"):
                    try:
                        from pypdf import PdfReader
                        import io
                        reader = PdfReader(io.BytesIO(paper_file.getvalue()))
                        extracted = "\n\n".join(page.extract_text() or "" for page in reader.pages)
                        if not extracted.strip():
                            st.warning("This PDF may be scanned images. OCR is not built in; upload a text-based PDF or paste its text into a TXT file.")
                    except ImportError:
                        st.error("PDF support is missing. Add pypdf to requirements.txt and redeploy.")
                else:
                    extracted = paper_file.getvalue().decode("utf-8", errors="ignore")
                st.session_state.pyq_text = extracted
                st.session_state.pyq_name = paper_name or paper_file.name
            except Exception as exc:
                st.error(f"Could not read this file: {exc}")
        if st.session_state.pyq_text:
            st.success(f"Loaded: {st.session_state.pyq_name or 'Uploaded paper'}")
            search_in_paper = st.text_input("Find a topic or phrase in this paper", key="pyq_search")
            paper_text = st.session_state.pyq_text
            if search_in_paper:
                chunks = [line for line in paper_text.splitlines() if search_in_paper.lower() in line.lower()]
                st.write("\n".join(chunks[:100]) if chunks else "No matching lines found. Try another phrase.")
            with st.expander("View extracted paper text", expanded=True):
                st.text_area("Extracted text", paper_text, height=300, key="paper_text_view")
            st.download_button("Download extracted text", paper_text, file_name="extracted_paper.txt", mime="text/plain")
            if st.button("Mark this paper as completed"):
                st.session_state.study_days.append({"date": now_ist().strftime("%d-%m-%Y"), "activity": "Completed paper: " + (st.session_state.pyq_name or "uploaded paper"), "exam": st.session_state.exam})
                st.success("Paper completion added to your progress tracker.")
    with tab_plan:
        st.markdown("#### A realistic daily plan")
        plan1, plan2, plan3 = st.columns(3)
        plan1.metric("Daily target", "30 min", "Current affairs")
        plan2.metric("Practice target", "15 MCQs", "Accuracy first")
        plan3.metric("Revision target", "10 min", "Recall saved notes")
        st.write("Suggested routine: read 3–5 stories, solve a short quiz, review yesterday's mistakes, and verify important facts from official sources.")

# ---------- REVISION BANK ----------
elif page == "My Revision Bank":
    st.markdown("### 📚 My Revision Bank")
    st.caption("Saved items and notes are retained while this app session is active. For permanent cross-session storage, connect a database.")
    if not st.session_state.saved_articles:
        st.info("No saved articles yet. Go to News Desk and select “Save for revision”.")
    else:
        search_saved = st.text_input("Search saved articles", placeholder="Search title, source or syllabus topic")
        saved_items = list(st.session_state.saved_articles.items())
        if search_saved:
            needle = search_saved.lower()
            saved_items = [(k, v) for k, v in saved_items if needle in (v.get("title", "") + " " + v.get("source", "") + " " + " ".join(v.get("topics", []))).lower()]
        st.write(f"{len(saved_items)} saved item(s)")
        for aid, article in saved_items:
            with st.container(border=True):
                st.markdown(f"#### {article.get('title', 'Untitled')}")
                st.caption(f"{article.get('source', 'Unknown source')} · {article.get('exam', '')} · {article.get('state', '')}")
                st.write(article.get("summary", summarize_text(article.get("content") or article.get("description") or "")))
                if article.get("url"):
                    st.markdown(f"[Open source article ↗]({article['url']})")
                highlights = st.session_state.highlights.get(aid, "")
                notes = st.session_state.notes.get(aid, "")
                if highlights:
                    st.markdown("**🖍️ Highlighted facts**")
                    st.info(highlights)
                if notes:
                    st.markdown("**📝 My notes**")
                    st.write(notes)
                sheet = make_revision_sheet(article)
                c1, c2 = st.columns(2)
                with c1:
                    st.download_button("Download revision sheet", sheet, file_name=f"revision_{aid}.md", mime="text/markdown", key=f"bankdl_{aid}", use_container_width=True)
                with c2:
                    if st.button("Remove from revision bank", key=f"bankremove_{aid}", use_container_width=True):
                        st.session_state.saved_articles.pop(aid, None)
                        st.rerun()
        if st.session_state.saved_articles:
            export_rows = []
            for aid, a in st.session_state.saved_articles.items():
                export_rows.append({
                    "Title": a.get("title", ""), "Source": a.get("source", ""),
                    "Published": parse_date(a.get("publishedAt")), "URL": a.get("url", ""),
                    "Exam": a.get("exam", ""), "State": a.get("state", ""),
                    "Summary": a.get("summary", ""),
                    "Highlights": st.session_state.highlights.get(aid, ""),
                    "Notes": st.session_state.notes.get(aid, ""),
                })
            st.download_button(
                "⬇️ Export all saved items (CSV)",
                pd.DataFrame(export_rows).to_csv(index=False).encode("utf-8-sig"),
                file_name="examwise_revision_bank.csv", mime="text/csv"
            )

# ---------- PROGRESS TRACKER ----------
elif page == "Progress Tracker":
    st.markdown("### 📈 Preparation Progress Tracker")
    st.caption("Scores and activities are tracked in this browser session. Connect a database for durable, cross-device history.")
    h1, h2, h3 = st.columns(3)
    h1.metric("Quiz attempts", len(st.session_state.quiz_history))
    avg = round(sum(x.get("Percent", 0) for x in st.session_state.quiz_history) / max(1, len(st.session_state.quiz_history))) if st.session_state.quiz_history else 0
    h2.metric("Average quiz score", f"{avg}%")
    h3.metric("Revision items saved", len(st.session_state.saved_articles))
    if st.session_state.quiz_history:
        hist = pd.DataFrame(st.session_state.quiz_history)
        st.markdown("#### Score trend")
        st.line_chart(hist.set_index("Attempt")["Percent"])
        st.dataframe(hist, use_container_width=True, hide_index=True)
    else:
        st.info("No quiz attempts yet. Take a practice set in PYQ & Mock Lab to start tracking.")
    st.markdown("#### Completed study activities")
    if st.session_state.study_days:
        st.dataframe(pd.DataFrame(st.session_state.study_days), use_container_width=True, hide_index=True)
    else:
        st.info("When you upload and mark a past paper completed, it will appear here.")
    if st.session_state.quiz_history or st.session_state.study_days:
        export_progress = {"quiz_history": st.session_state.quiz_history, "study_activities": st.session_state.study_days}
        st.download_button("Export progress data (JSON)", json.dumps(export_progress, indent=2), file_name="examwise_progress.json", mime="application/json")

# ---------- FEEDBACK & ANALYTICS ----------
elif page == "Feedback & Analytics":
    st.markdown("### 📊 Feedback & product insights")
    df = st.session_state.feedback.copy()
    m1, m2, m3 = st.columns(3)
    m1.metric("Feedback records loaded", len(df))
    m2.metric("Saved revision items", len(st.session_state.saved_articles))
    m3.metric("Current exam track", st.session_state.exam)
    if df.empty:
        st.info("No feedback records yet. Submit feedback from a news card.")
    else:
        if "Feedback Type" in df.columns:
            st.markdown("#### Feedback by type")
            st.bar_chart(df["Feedback Type"].fillna("Other").value_counts())
        st.markdown("#### Recent feedback")
        st.dataframe(df.tail(100).iloc[::-1], use_container_width=True, hide_index=True)
        st.download_button("Download feedback CSV", df.to_csv(index=False).encode("utf-8-sig"), "examwise_feedback.csv", "text/csv")

# ---------- ABOUT & SETUP ----------
else:
    st.markdown("### ⚙️ Setup and important notes")
    st.markdown("""
**News coverage without an API key**

The app now searches multiple Google News RSS queries based on the selected exam, region and category, plus publisher RSS feeds. RSS availability can vary by publisher/network. A NewsAPI key can improve structured results but is optional for the RSS fallback.

**Configure NewsAPI on Streamlit Community Cloud (optional)**

1. Open your app's Streamlit Cloud dashboard.
2. Open **Settings → Secrets**.
3. Add the following, replacing the placeholder with your own key:

```toml
NEWSAPI_KEY = ""638626e0c8e24c2c8b074ddea1768e4d""
```

4. Save secrets and reboot the app if needed. Do not commit API keys to GitHub.

**Dependencies:** `streamlit`, `requests`, `textblob`, `deep-translator`, `pandas`, `pytz`, `feedparser`, `pypdf`.

**Translation:** this version tries Google Translate and then MyMemory using shorter chunks. Both are free third-party services and may be rate-limited; if both fail, the original English summary remains available. For production reliability, connect a supported paid translation API.

**Persistence:** Streamlit Community Cloud's local filesystem is not a dependable permanent database. CSV feedback and saved revision material may be lost when the app restarts or redeploys. For permanent multi-user data, use a managed database such as Supabase or PostgreSQL. This starter app keeps saved items and notes in session state and feedback in a local CSV fallback.

**Credibility score:** the score shown is a lightweight source/text heuristic. It is not proof that a report is true or false. Verify important facts against primary and independent sources.

**PYQ papers:** upload a text-based PDF or TXT file in PYQ & Mock Lab to search and review past papers. Scanned PDFs require OCR, which is not included. Built-in questions are labelled as practice questions, not authentic PYQs. For verified previous-year questions, upload official papers or add a properly licensed source with exam/year metadata.

**Revision sheets:** generated from the article text actually available to the app. News providers may return truncated text. Always verify names, dates, numbers, scheme details and official announcements against the original source.
""")
