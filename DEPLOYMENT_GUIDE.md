# 🚀 Render Deployment Guide for Lead Hunter

## Prerequisites Checklist ✅

- [x] Git repository initialized
- [ ] GitHub repository URL (need to add remote)
- [ ] Render account (sign up at https://render.com)
- [x] Google Sheets API credentials
- [x] Google Sheet ID: `1uC9xvM6HgoDy7-zHZwDh9Zrcz-W1Ptyak0h3SZjjW5s`
- [ ] Gemini API Key (from https://aistudio.google.com/)

---

## Step 1: Connect GitHub Remote

**Option A: If you know your GitHub repository URL**
```bash
git remote add origin https://github.com/YOUR_USERNAME/YOUR_REPO_NAME.git
git branch -M main
git push -u origin main
```

**Option B: Find your existing GitHub repository**
1. Go to https://github.com/YOUR_USERNAME?tab=repositories
2. Look for "lead-hunter" or similar repository name
3. Copy the repository URL
4. Run the commands from Option A

---

## Step 2: Prepare Render Deployment Files

✅ **Already Done:**
- `render.yaml` - Render configuration file
- `requirements-render.txt` - Python dependencies for Render
- `thinker_app.py` - FastAPI backend application
- `.gitignore` - Excludes sensitive files (`.env`, `google-credentials.json`)

---

## Step 3: Deploy to Render

### 3.1 Create Render Account
1. Go to https://render.com
2. Sign up using your GitHub account (easiest method)
3. Authorize Render to access your GitHub repositories

### 3.2 Create New Web Service
1. Click **"New +"** → **"Blueprint"**
2. Connect your GitHub repository
3. Render will automatically detect `render.yaml`
4. Click **"Apply"**

### 3.3 Configure Environment Variables

In Render Dashboard, add these environment variables:

| Variable Name | Value | Notes |
|--------------|-------|-------|
| `GEMINI_API_KEY` | `your_gemini_api_key_here` | Get from https://aistudio.google.com/ |
| `GOOGLE_SHEET_ID` | `1uC9xvM6HgoDy7-zHZwDh9Zrcz-W1Ptyak0h3SZjjW5s` | Already configured |
| `GOOGLE_SERVICE_ACCOUNT_FILE` | `google-credentials.json` | Already set in render.yaml |

### 3.4 Upload Google Credentials

**Important:** Since `google-credentials.json` is gitignored, you need to add it manually:

**Method 1: Using Render Secret Files**
1. In Render Dashboard → Your Service → **Environment**
2. Scroll to **Secret Files**
3. Click **Add Secret File**
4. Filename: `google-credentials.json`
5. Contents: Paste the entire JSON content from your local `google-credentials.json` file

**Method 2: Using Environment Variable (Alternative)**
1. Copy the content of `google-credentials.json`
2. Minify it (remove all line breaks and spaces)
3. Add as environment variable: `GOOGLE_CREDENTIALS_JSON`
4. Update `thinker_app.py` to read from this variable if file doesn't exist

---

## Step 4: Verify Deployment

After deployment completes:

1. **Check Deployment Logs**
   - Render Dashboard → Your Service → **Logs**
   - Look for: `Uvicorn running on http://0.0.0.0:PORT`

2. **Test the API**
   - Your service URL will be: `https://lead-hunter-thinker.onrender.com`
   - Visit: `https://lead-hunter-thinker.onrender.com/` 
   - Expected response: `{"status": "Thinker is online", "model": "Gemini 1.5 Flash"}`

3. **Test Webhook Endpoint**
   ```bash
   curl -X POST https://lead-hunter-thinker.onrender.com/webhook/new-lead \
     -H "Content-Type: application/json" \
     -d '{"name": "Test Company", "website": "https://test.com", "reasoning": "High score"}'
   ```

---

## Step 5: Connect to Your Lead Hunter System

### 5.1 Update Rows.com or Zapier Webhook
Once deployed, configure your webhook automation:

**Rows.com:**
- Go to your Google Sheet automation
- Set webhook URL to: `https://lead-hunter-thinker.onrender.com/webhook/new-lead`

**Zapier:**
- Create a Zap: New Row in Google Sheets → Webhooks
- Webhook URL: `https://lead-hunter-thinker.onrender.com/webhook/new-lead`
- Method: POST
- Payload: Map sheet columns to JSON fields

### 5.2 Test End-to-End
1. Add a test lead to your Google Sheet manually
2. Check Render logs to see if webhook was triggered
3. Verify AI-generated email draft appears in logs

---

## Troubleshooting

### ❌ Build Fails
- Check `requirements-render.txt` for any incompatible packages
- Review Render build logs for specific error messages

### ❌ Google Sheets API Error
- Verify `google-credentials.json` is properly uploaded as Secret File
- Confirm the service account email has Editor access to your Google Sheet
- Check that Google Sheets API is enabled in Google Cloud Console

### ❌ Gemini API Error
- Verify API key is correct
- Ensure Gemini API is enabled in your Google Cloud project
- Check for rate limiting or quota issues

### ❌ Free Tier Limitations
Render Free tier includes:
- **Sleep after 15 minutes of inactivity** (will wake on first request)
- **750 hours/month** runtime
- **Cold starts** may take 30-60 seconds

**Solution:** Upgrade to Paid plan ($7/month) for always-on service

---

## Architecture Overview

```
┌─────────────────┐
│  Google Sheets  │
│   (Lead Data)   │
└────────┬────────┘
         │
         │ New Row Added
         ▼
┌─────────────────┐
│   Rows.com or   │
│     Zapier      │
│   (Automation)  │
└────────┬────────┘
         │
         │ HTTP POST Webhook
         ▼
┌─────────────────┐
│  Render Service │
│  (thinker_app)  │
│                 │
│  FastAPI +      │
│  Gemini AI      │
└────────┬────────┘
         │
         │ AI Processing
         ▼
┌─────────────────┐
│  Email Draft /  │
│  Further Logic  │
└─────────────────┘
```

---

## Next Steps After Deployment

1. **Set up monitoring:** Add status checks or uptime monitoring (e.g., UptimeRobot)
2. **Add logging:** Implement proper logging to track webhook events
3. **Enhance AI logic:** Expand `process_lead_logic()` to write drafts back to Google Sheets
4. **Add authentication:** Secure webhook endpoint with API key validation
5. **Scale up:** If processing many leads, upgrade to paid tier for faster performance

---

## Quick Command Reference

```bash
# Push latest changes to GitHub
git add .
git commit -m "Update configuration for Render deployment"
git push origin main

# Check remote repository
git remote -v

# View recent commits
git log --oneline -5
```

---

**Need Help?**
- Render Docs: https://render.com/docs
- Gemini API: https://ai.google.dev/docs
- Google Sheets API: https://developers.google.com/sheets/api
