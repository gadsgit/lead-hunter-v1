# 🚀 Render Quick Start - Lead Hunter v1

✅ **GitHub Repository:** https://github.com/gadsgit/lead-hunter-v1.git  
✅ **Latest Code Pushed:** All files synced to GitHub

---

## Deploy to Render in 5 Minutes

### Step 1: Sign Up / Log In to Render
👉 Go to: https://dashboard.render.com/

**Sign up options:**
- Sign in with GitHub (recommended - easiest)
- Sign in with GitLab
- Sign in with Google

### Step 2: Create New Blueprint

1. Click **"New +"** button (top right)
2. Select **"Blueprint"**
3. Connect your GitHub account if prompted
4. Select repository: **`gadsgit/lead-hunter-v1`**
5. Click **"Connect"**
6. Render will automatically detect `render.yaml`
7. Click **"Apply"** to create the service

### Step 3: Configure Environment Variables

⚠️ **IMPORTANT:** Before the service can start, you MUST add these environment variables:

1. Go to your service: **Dashboard → lead-hunter-thinker → Environment**
2. Add these variables:

| Key | Value | Where to Get It |
|-----|-------|----------------|
| `GEMINI_API_KEY` | Your actual API key | https://aistudio.google.com/app/apikey |
| `GOOGLE_SHEET_ID` | `1uC9xvM6HgoDy7-zHZwDh9Zrcz-W1Ptyak0h3SZjjW5s` | Already configured ✅ |

3. Click **"Save Changes"**

### Step 4: Upload Google Credentials (Secret File)

Since `google-credentials.json` is not in Git (for security), you need to upload it manually:

1. In the same **Environment** tab, scroll to **Secret Files**
2. Click **"Add Secret File"**
3. **Filename:** `google-credentials.json`
4. **Contents:** 
   - Open `e:\Lead Hunter\google-credentials.json` on your local machine
   - Copy the ENTIRE JSON content
   - Paste it into the Render secret file editor
5. Click **"Save"**

### Step 5: Deploy!

After adding environment variables and secret file:
1. Go to **Events** tab (or **Logs**)
2. Click **"Manual Deploy"** → **"Deploy latest commit"**
3. Wait 2-3 minutes for build to complete

---

## Verification

### ✅ Check if Service is Running

Once deployed, your service URL will be:
```
https://lead-hunter-thinker.onrender.com
```

**Test the API:**
1. Open browser and visit: https://lead-hunter-thinker.onrender.com/
2. You should see:
   ```json
   {
     "status": "Thinker is online",
     "model": "Gemini 1.5 Flash"
   }
   ```

### ✅ Test Webhook Endpoint

Use this curl command (or Postman):
```bash
curl -X POST https://lead-hunter-thinker.onrender.com/webhook/new-lead \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Test Company",
    "website": "https://example.com",
    "reasoning": "High scoring lead from Google Maps"
  }'
```

Expected response:
```json
{
  "status": "Processing initiated"
}
```

Check **Render Logs** to see the AI-generated email draft!

---

## Connect to Google Sheets Automation

### Option A: Rows.com Webhook Automation
```
1. Open your Google Sheet in Rows.com
2. Create new automation: "New Row → HTTP Request"
3. Webhook URL: https://lead-hunter-thinker.onrender.com/webhook/new-lead
4. Method: POST
5. Headers: Content-Type: application/json
6. Body: Map columns to JSON (name, website, email, reasoning)
```

### Option B: Zapier
```
1. Create Zap: Google Sheets → Webhooks by Zapier
2. Trigger: New Row in Google Sheet
3. Action: POST to https://lead-hunter-thinker.onrender.com/webhook/new-lead
4. Map fields: name, website, email, reasoning
```

### Option C: Google Apps Script (Free!)
Add this to your Google Sheet (Extensions → Apps Script):

```javascript
function onEdit(e) {
  const sheet = e.source.getActiveSheet();
  const row = e.range.getRow();
  
  // Only trigger on new rows in "Qualified Leads" sheet
  if (sheet.getName() !== "Qualified Leads" || row === 1) return;
  
  const data = sheet.getRange(row, 1, 1, 5).getValues()[0];
  const payload = {
    name: data[0],
    website: data[1],
    email: data[2],
    reasoning: data[4]
  };
  
  const options = {
    method: "post",
    contentType: "application/json",
    payload: JSON.stringify(payload)
  };
  
  UrlFetchApp.fetch("https://lead-hunter-thinker.onrender.com/webhook/new-lead", options);
}
```

---

## Troubleshooting

### ❌ Build Failed
- Check **Logs** tab for specific error
- Verify `requirements-render.txt` doesn't have version conflicts
- Ensure Python version is compatible (3.11+)

### ❌ Service Won't Start
- Verify all environment variables are set correctly
- Check that `google-credentials.json` secret file is uploaded
- Review logs for "GEMINI_API_KEY" or "GOOGLE_SHEET_ID" errors

### ❌ Webhook Not Working
- Verify service is running (visit root URL)
- Check webhook URL is correct (include `/webhook/new-lead`)
- Review Render logs when sending test request
- Ensure Google Sheet has service account email as Editor

### 💤 Free Tier Limitations
- **Service sleeps after 15 min of inactivity**
- First request after sleep = 30-60 second cold start
- **Solution:** Upgrade to paid plan ($7/month) for always-on

---

## Next Steps

1. ✅ **Monitor Logs:** Keep Render logs tab open during first few webhook tests
2. 📧 **Enhance Logic:** Modify `thinker_app.py` to write email drafts back to Google Sheets
3. 🔒 **Add Security:** Implement webhook authentication (API key header)
4. 📊 **Add Metrics:** Track processing times, success rates
5. 🚀 **Scale:** If processing many leads, upgrade to paid tier

---

## Quick Reference

| Item | Value |
|------|-------|
| **GitHub Repo** | https://github.com/gadsgit/lead-hunter-v1.git |
| **Render Service URL** | https://lead-hunter-thinker.onrender.com |
| **Webhook Endpoint** | `/webhook/new-lead` |
| **Google Sheet ID** | `1uC9xvM6HgoDy7-zHZwDh9Zrcz-W1Ptyak0h3SZjjW5s` |
| **Health Check** | `GET /` |

---

## Need Help?

- **Render Support:** https://render.com/docs
- **Gemini API Docs:** https://ai.google.dev/tutorials/python_quickstart
- **Google Sheets API:** https://developers.google.com/sheets/api/guides/concepts

**Your deployment is ready to go! 🎉**
