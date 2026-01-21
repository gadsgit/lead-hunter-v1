# Lead Hunter Project Rules
- **Environment:** Render.com (512MB RAM Limit)
- **Base Image:** Python-Slim
- **Core Stack:** Streamlit, Playwright, Gspread
- **AI Model for Tasks:** Gemini-1.5-Flash
- **Checkpoints:** GSheets "Mission_Progress" tab is the source of truth for history.
- **Goal:** Never re-scrape a lead that exists in GSheets.