# ExamWise India — News, Learning & Competitive Exam Revision

## What changed in this version
- Expanded RSS discovery using multiple Google News searches based on exam, state/region, category and topic.
- RSS fetching has individual timeouts and isolates failed feeds so one unavailable publisher does not stop the rest.
- State matches are ranked first without throwing away useful national news.
- Translation tries Google Translate and then MyMemory in short chunks. If both free providers are unavailable, the original summary remains available.
- Headline-only items are clearly labelled when a publisher does not expose article text.
- The workspace includes common-reader mode, exam-specific practice MCQs, a PYQ upload/search workspace, revision sheets, saved notes, feedback and a progress tracker.
- Practice questions are clearly marked as practice content, not authentic official PYQs. Upload official papers to work with the exact past questions.

## Update an existing GitHub repository through the website
1. Download `ExamWise_India_Upgraded.zip` and extract it on your computer.
2. Open the existing GitHub repository connected to Streamlit Cloud.
3. Open `app.py`, click the pencil/edit icon, and replace its contents with the downloaded `app.py`; alternatively use **Add file → Upload files** to upload the new `app.py` and `requirements.txt` over the existing versions.
4. Commit the changes to the same branch configured in Streamlit Cloud (often `main`).
5. Open Streamlit Community Cloud, wait for the app to rebuild, and check **Manage app → Logs** if deployment fails.

## Dependencies
`requirements.txt` is included. Make sure Streamlit Cloud installs the updated requirements during redeploy.

## Optional NewsAPI configuration
RSS fallback works without a key, but feed coverage and uptime vary. To configure NewsAPI, open Streamlit Cloud → app settings → **Secrets** and add:

```toml
NEWSAPI_KEY = ""638626e0c8e24c2c8b074ddea1768e4d""
```

Do not commit API keys to GitHub.

## Translation limitation
Translation uses two free third-party services with retries/fallback. Neither provides a guaranteed uptime or unlimited rate. If both are blocked or rate-limited, the app preserves the original English summary and displays a message. For production-grade translation, configure a supported paid translation provider.

## Previous-year question papers (PYQs)
Upload official text-based PDF/TXT/CSV papers in **PYQ & Mock Lab**. The app can extract/search text and track completion. Scanned/image PDFs require OCR. The built-in sample MCQs are practice questions and must not be labelled as official PYQs. Always verify exam year, paper and answer keys against official releases.

## Storage
Current saved notes, quiz attempts and progress are session-based; local CSV feedback may not survive all Streamlit Cloud restarts. For multi-user, durable tracking across devices, connect a managed database such as Supabase or PostgreSQL.
