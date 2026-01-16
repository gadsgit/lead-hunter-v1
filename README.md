# leadhunterag - Lead Hunter System

This is a Python-based lead generation system that scrapes Google Maps and LinkedIn, scores leads using heuristic reasoning, and saves qualified leads to Google Sheets.

## Features
- **Scraper**: Uses Playwright to find companies on Google Maps, their websites, and LinkedIn profiles.
- **Smart Filter**: Uses Google Gemini AI to score leads (0-100) based on website "vibe", size, and inferred age.
- **Email Discovery**: Automatically extracts email addresses from company websites.
- **Storage**: Appends qualified leads (Score > 70) to Google Sheets.
- **Mission Control**: Streamlit dashboard for real-time monitoring.

## Setup Instructions

### 1. Google Sheets API
1. Go to the [Google Cloud Console](https://console.cloud.google.com/).
2. Create a new project.
3. Enable the **Google Sheets API** and **Google Drive API**.
4. Create a **Service Account** and download the **JSON Key**.
5. Rename the JSON key file to `google-credentials.json` and place it in this directory.
6. Create a new Google Sheet and **Share** it with the service account email (found in the JSON key) giving it "Editor" access.
7. Copy the spreadsheet ID from the URL and paste it into the `.env` file.

### 2. Gemini AI API (Required for Smart Filter)
1. Get an API Key from [Google AI Studio](https://aistudio.google.com/).
2. Paste it into the `GEMINI_API_KEY` field in the `.env` file.

### 3. Configuration
Edit the `.env` file:
- `GOOGLE_SHEET_ID`: Your spreadsheet ID.
- `GEMINI_API_KEY`: Your Gemini API key.
- `KEYWORD`: Default search term.

### 3. Run with Docker
Run the following command in your terminal:

```bash
docker-compose up --build
```

The Mission Control dashboard will be available at [http://localhost:8501](http://localhost:8501).

## Project Structure
- `hunter.py`: Core scraping and scoring logic.
- `gsheets_handler.py`: Google Sheets API wrapper.
- `dashboard.py`: Streamlit frontend.
- `Dockerfile` & `docker-compose.yml`: Docker configuration.
