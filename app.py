import os
import re
import json
import hashlib
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
[data-testid="stHeader"] { background: rgba(11,16,23,.88); }
.block-container { padding-top: 1.3rem; padding-bottom: 3rem; max-width: 1450px; }
.hero {
  padding: 1.45rem 1.7rem; border: 1px solid #253849; border-radius: 22px;
  background: radial-gradient(circle at 10% 0%, #173c40 0%, #101c29 48%, #111520 100%);
  margin-bottom: 1rem;
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
h1,h2,h3 { letter-spacing: -.02em; }
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

def translate_text(text, language):
    text = clean_text(text)
    if not text:
        return None, "There is no summary text to translate."
    target = LANGUAGES.get(language)
    if not target:
        return None, f"Unsupported target language: {language}"
    if target == "en":
        return text, None
    try:
        result = GoogleTranslator(source="auto", target=target).translate(text)
        if not result or not result.strip():
            return None, "The translation service returned an empty result. Please retry."
        return result, None
    except Exception as exc:
        # The detailed exception appears in Streamlit logs; users see a safe message.
        print(f"Translation failure ({language}): {type(exc).__name__}: {exc}")
        return None, "Translation service is temporarily unavailable or rate-limited. Retry later or view the original summary."

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

@st.cache_data(ttl=900, show_spinner=False)
def fetch_rss_cached(feed_urls, max_items):
    if not feedparser:
        return []
    items = []
    for feed_url in feed_urls:
        try:
            feed = feedparser.parse(feed_url)
            feed_name = clean_text(feed.feed.get("title", "")) or "RSS source"
            for entry in feed.entries[:max_items]:
                items.append({
                    "title": clean_text(entry.get("title")) or "Untitled article",
                    "url": entry.get("link", ""),
                    "source": feed_name,
                    "publishedAt": entry.get("published") or entry.get("updated") or "",
                    "description": clean_text(entry.get("summary", "")),
                    "content": clean_text(entry.get("summary", "")),
                })
        except Exception as exc:
            print(f"RSS feed error: {exc}")
    # deduplicate URLs
    unique, seen = [], set()
    for item in items:
        key = item.get("url") or item.get("title")
        if key not in seen:
            unique.append(item)
            seen.add(key)
    return unique[:max_items]

def fetch_news(keyword, category, page_size, state):
    articles, api_error = fetch_news_api(keyword, category, page_size)
    if not articles:
        feeds = (
            "https://feeds.bbci.co.uk/news/world/asia/india/rss.xml",
            "https://www.thehindu.com/news/national/feeder/default.rss",
            "https://indianexpress.com/section/india/feed/",
        )
        articles = fetch_rss_cached(feeds, page_size)
    if keyword.strip():
        needle = keyword.strip().lower()
        articles = [a for a in articles if needle in (a.get("title", "") + " " + a.get("description", "") + " " + a.get("content", "")).lower()]
    if state != "All India":
        # State filter is keyword matching, not guaranteed geographic classification.
        state_terms = {
            "Karnataka": ["karnataka", "bengaluru", "mysuru", "mangaluru", "kannada"],
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
        articles = [a for a in articles if any(t in (a.get("title", "") + " " + a.get("description", "") + " " + a.get("content", "")).lower() for t in terms)]
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
    "exam": "UPSC CSE",
    "state": "All India",
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
    page = st.radio("Workspace", ["News Desk", "My Revision Bank", "Feedback & Analytics", "About & Setup"], index=0)
    st.markdown("---")
    st.metric("Saved revision items", len(st.session_state.saved_articles))
    st.metric("Feedback entries this session", len(st.session_state.feedback))

# ---------- NEWS DESK ----------
if page == "News Desk":
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
            st.info("No matching articles were found. Try another keyword, choose All India, or configure NEWSAPI_KEY.")
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
            raw_text = clean_text(article.get("content") or article.get("description") or "")
            summary = summarize_text(raw_text)
            aid = stable_article_id(article)
            topics = subject_suggestions(title + " " + raw_text, st.session_state.exam)
            with st.container(border=True):
                st.markdown(f"### {i+1}. {title}")
                st.caption(f"🗞️ {source}  •  🕒 {published}")
                st.caption("Suggested syllabus: " + " · ".join(topics))
                if url:
                    st.markdown(f"[Read original report ↗]({url})")
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
**Configure NewsAPI on Streamlit Community Cloud**

1. Open your app's Streamlit Cloud dashboard.
2. Open **Settings → Secrets**.
3. Add the following, replacing the placeholder with your own key:

```toml
NEWSAPI_KEY = ""638626e0c8e24c2c8b074ddea1768e4d""
```

4. Save secrets and reboot the app if needed. Do not commit API keys to GitHub.

**Dependencies:** `streamlit`, `requests`, `textblob`, `deep-translator`, `pandas`, `pytz`, `feedparser`.

**Translation:** the free Google translation endpoint used by `deep-translator` may be temporarily unavailable or rate-limited. The app now shows a useful message and has a retry button rather than silently showing a generic error.

**Persistence:** Streamlit Community Cloud's local filesystem is not a dependable permanent database. CSV feedback and saved revision material may be lost when the app restarts or redeploys. For permanent multi-user data, use a managed database such as Supabase or PostgreSQL. This starter app keeps saved items and notes in session state and feedback in a local CSV fallback.

**Credibility score:** the score shown is a lightweight source/text heuristic. It is not proof that a report is true or false. Verify important facts against primary and independent sources.

**Revision sheets:** generated from the article text actually available to the app. News providers may return truncated text. Always verify names, dates, numbers, scheme details and official announcements against the original source.
""")
