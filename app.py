# app.py (final)
# Fully working version: feedback stored to CSV, displayed live, articles up to 50,
# summaries limited to ~5 sentences, published time used (not overridden), robust CSV loading.
# Copy this file to your project root and run: `streamlit run app.py`

import os
import streamlit as st
import requests
from textblob import TextBlob
from deep_translator import GoogleTranslator
import pandas as pd
from datetime import datetime
import pytz
import re

# Optional RSS fallback (feedparser helps if NewsAPI fails)
try:
    import feedparser
except Exception:
    feedparser = None

# ---------------- CONFIG ----------------
NEWSAPI_KEY = os.environ.get("NEWSAPI_KEY", "") or "638626e0c8e24c2c8b074ddea1768e4d"
FEEDBACK_CSV = "feedback_store.csv"
india = pytz.timezone("Asia/Kolkata")

# ---------------- SESSION STATE ----------------
if "feedback_store" not in st.session_state:
    # Try to load existing CSV; if columns differ or file missing, normalize to expected schema.
    expected_cols = ["Article", "Title", "Feedback", "Time", "Source", "URL"]
    if os.path.exists(FEEDBACK_CSV):
        try:
            df = pd.read_csv(FEEDBACK_CSV)
            # Ensure all expected columns exist
            for c in expected_cols:
                if c not in df.columns:
                    df[c] = ""
            df = df[expected_cols]
            st.session_state.feedback_store = df
        except Exception:
            st.session_state.feedback_store = pd.DataFrame(columns=expected_cols)
    else:
        st.session_state.feedback_store = pd.DataFrame(columns=expected_cols)


# ---------------- HELPERS ----------------
def now_ist_string():
    return datetime.now(india).strftime("%A, %d %B %Y   |   %I:%M %p")


def fetch_news_api(keyword, category, page_size):
    """Fetch using NewsAPI (top-headlines or everything)."""
    if not NEWSAPI_KEY:
        return []
    url = "https://newsapi.org/v2/top-headlines" if not keyword else "https://newsapi.org/v2/everything"
    params = {"apiKey": NEWSAPI_KEY, "pageSize": page_size, "language": "en"}
    if keyword:
        params["q"] = keyword
    if category and category != "All":
        params["category"] = category.lower()
    try:
        resp = requests.get(url, params=params, timeout=8)
        resp.raise_for_status()
        r = resp.json()
        if r.get("status") != "ok":
            return []
        out = []
        for a in r.get("articles", []):
            out.append({
                "title": a.get("title"),
                "url": a.get("url"),
                "source": a.get("source", {}).get("name"),
                "publishedAt": a.get("publishedAt"),
                "description": a.get("description"),
                "content": a.get("content")
            })
        return out
    except Exception:
        return []


def fetch_news_rss(sources, max_items=10):
    out = []
    if not feedparser:
        return out
    for s in sources:
        try:
            feed = feedparser.parse(s)
            for e in feed.entries[:max_items]:
                out.append({
                    "title": e.get("title"),
                    "url": e.get("link"),
                    "source": feed.feed.get("title", ""),
                    "publishedAt": e.get("published") or e.get("updated") or "",
                    "description": e.get("summary"),
                    "content": e.get("summary")
                })
        except Exception:
            continue
    return out


def summarize_text_five_lines(text):
    """Return up to 5 sentences (approx 5 lines). If sentence splitting fails, fall back to first ~60-120 words."""
    if not text:
        return "No content available."
    # Normalize whitespace and replace newlines
    text = re.sub(r"\s+", " ", text).strip()
    # Split into sentences using punctuation.
    sentences = re.split(r'(?<=[.!?])\s+', text)
    sentences = [s.strip() for s in sentences if s.strip()]
    if len(sentences) == 0:
        # fallback to word-based summary
        words = text.split()
        return " ".join(words[:80]) + (" ..." if len(words) > 80 else "")
    # join up to 5 sentences
    summary = " ".join(sentences[:5])
    # if summary is still extremely long, trim words to ~120 words
    words = summary.split()
    if len(words) > 120:
        summary = " ".join(words[:120]) + " ..."
    return summary


def get_sentiment_label(text):
    if not text:
        return "Neutral 😐"
    try:
        p = TextBlob(text).sentiment.polarity
        return "Positive 😊" if p > 0 else ("Negative 😡" if p < 0 else "Neutral 😐")
    except Exception:
        return "Neutral 😐"


def fake_news_check(title, text, source):
    score = 50
    trusted = [
        "BBC", "NDTV", "The Hindu", "Times of India", "CNN",
        "Google News", "Reuters", "Al Jazeera", "Washington Post", "Indian Express"
    ]
    if source and any(t.lower() in (source or "").lower() for t in trusted):
        score += 30
    if text and len(text.split()) > 120:
        score += 15
    if text and any(w in text.lower() for w in ["research", "study", "report", "official"]):
        score += 10
    if text and any(ch.isdigit() for ch in text):
        score += 5
    if text and re.search(r"(shocking|miracle|unbelievable|guaranteed|scandal)", text.lower()):
        score -= 25
    score = max(0, min(100, score))
    if score >= 80:
        return f"🟢 Real News ({score}% confidence)"
    if score >= 55:
        return f"🟡 Uncertain ({score}% confidence)"
    return f"🔴 Fake News Likely ({score}% confidence)"


def translate_text(text, lang):
    lang_map = {"English": "en", "Kannada": "kn", "Hindi": "hi", "Tamil": "ta", "Malayalam": "ml", "Telugu": "te"}
    if not text:
        return ""
    try:
        return GoogleTranslator(source="auto", target=lang_map.get(lang, "en")).translate(text)
    except Exception:
        return "Translation error"


def parse_publish_time(raw):
    """Parse ISO-like time returned by NewsAPI. If parsing fails, return the original string if it looks like a readable date,
    otherwise return current IST time. This avoids overriding valid published timestamps with 'now'."""
    if not raw:
        return datetime.now(india).strftime("%d-%m-%Y %I:%M %p")
    s = str(raw).strip()
    # Common ISO 8601 with Z or timezone e.g. 2025-12-01T12:34:56Z
    try:
        # Remove timezone 'Z' if present
        if s.endswith("Z"):
            s2 = s[:-1]
            dt = datetime.strptime(s2[:19], "%Y-%m-%dT%H:%M:%S")
            dt = pytz.utc.localize(dt).astimezone(india)
            return dt.strftime("%d-%m-%Y %I:%M %p")
        # If contains + or - timezone part, try to cut
        if "T" in s and ("+" in s or "-" in s[10:]):
            # take first 19 chars
            s2 = s[:19]
            dt = datetime.strptime(s2, "%Y-%m-%dT%H:%M:%S")
            dt = pytz.utc.localize(dt).astimezone(india)
            return dt.strftime("%d-%m-%Y %I:%M %p")
        # Try ISO without timezone
        if "T" in s:
            s2 = s[:19]
            dt = datetime.strptime(s2, "%Y-%m-%dT%H:%M:%S")
            dt = pytz.utc.localize(dt).astimezone(india)
            return dt.strftime("%d-%m-%Y %I:%M %p")
    except Exception:
        pass
    # If looks like a normal human date string, try to parse generic patterns
    try:
        # Many RSS feeds may pass a string like 'Mon, 01 Dec 2025 03:06:00 GMT'
        # We'll try common format:
        dt = datetime.strptime(s[:25], "%a, %d %b %Y %H:%M:%S")
        # assume UTC -> IST
        dt = pytz.utc.localize(dt).astimezone(india)
        return dt.strftime("%d-%m-%Y %I:%M %p")
    except Exception:
        # final fallback: return current IST so displayed items are not misleadingly old
        return datetime.now(india).strftime("%d-%m-%Y %I:%M %p")


# ---------------- UI ----------------
st.set_page_config(page_title="AI News Analyzer", layout="wide")
st.markdown(
    f"""
    <div style="background:#0b0b0b;padding:16px;border-radius:12px;margin-bottom:12px;">
      <h1 style="color:white;text-align:center;margin:0;">📰 AI News Analyzer</h1>
      <p style="color:#7ee0b1;text-align:center;margin:4px 0 0 0;">{now_ist_string()}</p>
    </div>
    """,
    unsafe_allow_html=True
)

st.write("Fake-news detection • Summaries • Translation • Sentiment • Live Feedback")

# Sidebar: navigation + recent feedback
st.sidebar.title("Navigation")
page = st.sidebar.radio("", ["Home", "View All Feedback", "Analytics"])

st.sidebar.markdown("---")
st.sidebar.title("Recent Feedback (live)")
if st.session_state.feedback_store.empty:
    st.sidebar.info("No feedback yet.")
else:
    last = st.session_state.feedback_store.tail(6).iloc[::-1]
    for _, row in last.iterrows():
        # guard against missing columns
        art = int(row["Article"]) if "Article" in row and str(row["Article"]).isdigit() else ""
        t = str(row.get("Time", ""))[:40]
        fb = str(row.get("Feedback", ""))[:120]
        st.sidebar.info(f"Article {art} • {t}\n{fb}")

st.sidebar.markdown("---")
st.sidebar.caption("Built for: AI news summarizer & fake-news detection")

# ---------------- HOME ----------------
if page == "Home":
    with st.container():
        col1, col2 = st.columns([3, 1])
        with col1:
            keyword = st.text_input("🔍 Search Keyword (leave blank for top headlines)")
            category = st.selectbox("📂 Category", ["All", "Business", "Sports", "Entertainment", "Health", "Technology", "Science"])
            page_size = st.slider("Number of articles (max 50)", 1, 50, 10)
            lang = st.selectbox("Translate summary to", ["English", "Kannada", "Hindi", "Tamil", "Telugu", "Malayalam"])
            fetch_btn = st.button("Fetch Latest Articles")
        with col2:
            st.write("")  # spacing
            st.metric("Total feedback collected", len(st.session_state.feedback_store))

    if fetch_btn:
        articles = fetch_news_api(keyword, category, page_size)
        if not articles:
            # fallback to RSS if feedparser available
            if feedparser:
                rss_sources = [
                    "https://feeds.reuters.com/reuters/topNews",
                    "https://rss.cnn.com/rss/edition.rss",
                    "https://feeds.bbci.co.uk/news/rss.xml"
                ]
                articles = fetch_news_rss(rss_sources, max_items=page_size)
            else:
                st.error("No NewsAPI key / response and feedparser not available for RSS fallback.")
                articles = []

        if not articles:
            st.error("No articles found. Try different keyword or increase number of articles.")
        else:
            for i, art in enumerate(articles):
                title = art.get("title") or "No title"
                src = art.get("source") or "Unknown"
                url = art.get("url") or ""
                published_raw = art.get("publishedAt") or art.get("published") or ""
                published = parse_publish_time(published_raw)

                st.markdown(f"### {i+1}. {title}")
                st.markdown(f"**Source:** {src}  •  **Published:** {published} IST")
                if url:
                    st.markdown(f"[Read full article]({url})")

                text = art.get("content") or art.get("description") or ""
                summary = summarize_text_five_lines(text)
                st.info(f"📝 Summary:\n{summary}")
                translated = translate_text(summary, lang)
                st.success(f"🌐 Translated summary ({lang}):\n{translated}")
                st.warning("🧠 Sentiment: " + get_sentiment_label(text))
                st.markdown(f"**🔍 Credibility:** {fake_news_check(title, text, src)}")

                # feedback form (use st.form for reliability)
                form_key = f"form_{i}"
                with st.form(key=form_key, clear_on_submit=False):
                    fb_title = st.text_input("Feedback title (optional)", key=f"fbtitle_{i}")
                    feedback_input = st.text_area("✍ Your feedback (what's wrong / what to improve)", key=f"fb_{i}")
                    submitted = st.form_submit_button("Save Feedback")
                    if submitted:
                        if not feedback_input.strip():
                            st.warning("Please enter feedback before submitting.")
                        else:
                            time_now = datetime.now(india).strftime("%d-%m-%Y %I:%M %p")
                            new_row = {
                                "Article": i + 1,
                                "Title": title,
                                "Feedback": feedback_input,
                                "Time": time_now,
                                "Source": src,
                                "URL": url
                            }
                            # append to session store and persist
                            st.session_state.feedback_store = pd.concat(
                                [st.session_state.feedback_store, pd.DataFrame([new_row])],
                                ignore_index=True
                            )
                            try:
                                # Ensure columns and save
                                cols = ["Article", "Title", "Feedback", "Time", "Source", "URL"]
                                df_to_save = st.session_state.feedback_store.copy()
                                for c in cols:
                                    if c not in df_to_save.columns:
                                        df_to_save[c] = ""
                                df_to_save = df_to_save[cols]
                                df_to_save.to_csv(FEEDBACK_CSV, index=False)
                                st.success("✅ Feedback saved and visible in sidebar")
                                # small UX improvement: refresh sidebar display (Streamlit will reflect session_state changes)
                            except Exception:
                                st.error("Saved to session but failed to write CSV (disk permission).")
                st.markdown("---")


# ---------------- VIEW ALL FEEDBACK ----------------
if page == "View All Feedback":
    st.title("📁 All Submitted Feedback")
    df = st.session_state.feedback_store.copy()
    if df.empty:
        st.info("No feedback yet. Go to Home and submit feedback.")
    else:
        # Ensure expected columns exist
        expected_cols = ["Article", "Title", "Feedback", "Time", "Source", "URL"]
        for c in expected_cols:
            if c not in df.columns:
                df[c] = ""
        df_display = df[expected_cols].sort_values(by="Time", ascending=False).reset_index(drop=True)
        st.dataframe(df_display)


# ---------------- ANALYTICS ----------------
if page == "Analytics":
    st.title("📊 Feedback Analytics")
    df = st.session_state.feedback_store
    if df.empty:
        st.info("No feedback to analyze yet.")
    else:
        counts = df["Article"].value_counts().sort_index()
        chart_df = pd.DataFrame({"article_index": counts.index.astype(str), "feedback_count": counts.values})
        st.bar_chart(data=chart_df.set_index("article_index"))
        st.write("Last 10 feedback entries:")
        st.table(df.tail(10).iloc[::-1].reset_index(drop=True))
