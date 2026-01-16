from fastapi import FastAPI, Request, BackgroundTasks
import os
import google.generativeai as genai
from dotenv import load_dotenv
import json

load_dotenv()

app = FastAPI(title="Lead Hunter Thinker")

# Configure Gemini
api_key = os.getenv("GEMINI_API_KEY")
if api_key:
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel('gemini-1.5-flash')
else:
    model = None

@app.get("/")
async def root():
    return {"status": "Thinker is online", "model": "Gemini 1.5 Flash"}

@app.post("/webhook/new-lead")
async def handle_new_lead(request: Request, background_tasks: BackgroundTasks):
    """
    Listener for Rows.com or Zapier webhooks.
    Triggered when a new lead is added to the spreadsheet.
    """
    payload = await request.json()
    print(f"Received new lead: {payload.get('name', 'Unknown')}")
    
    # Process in background so Rows.com doesn't timeout
    background_tasks.add_task(process_lead_logic, payload)
    
    return {"status": "Processing initiated"}

async def process_lead_logic(lead_data):
    """
    Complex thinking logic: personalized email generation, further research, etc.
    """
    if not model:
        print("Model not configured, skipping AI processing.")
        return

    name = lead_data.get("name", "Business")
    website = lead_data.get("website", "N/A")
    reasoning = lead_data.get("reasoning", "")

    prompt = f"""
    You are an expert sales strategist. I have a new qualified lead:
    Name: {name}
    Website: {website}
    Why they were qualified: {reasoning}

    Draft a short, punchy, 2-sentence 'Cold-Intro' email that sounds human and references their business type.
    """
    
    try:
        response = model.generate_content(prompt)
        draft = response.text.strip()
        print(f"Generated Draft for {name}:\n{draft}")
        
        # Here you would typically send this back to GSheets, Rows, or Slack
        # For now, we just log it.
        
    except Exception as e:
        print(f"Thinking Error: {e}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8000)))
