# ExamWise India

## Install locally

pip install -r requirements.txt

## Run the application

streamlit run app.py

## Deploy using Streamlit Community Cloud

1. Upload app.py and requirements.txt to GitHub.
2. Open Streamlit Community Cloud.
3. Connect your GitHub repository.
4. Select app.py as the application entry point.
5. Deploy the application.

## Configure NewsAPI

Open your app settings in Streamlit Cloud.
Go to Settings > Secrets and add:

NEWSAPI_KEY = ""638626e0c8e24c2c8b074ddea1768e4d""

Never publish your actual API key in a public repository.

## Important notes

- Translation depends on an external service.
- Configure NewsAPI for reliable news fetching.
- Persistent revision storage requires a database.
- Verify news facts against the original sources.
