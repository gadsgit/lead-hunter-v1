import os
from fpdf import FPDF
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

# We can import MASTER_MAP from dashboard instead of duplicating it, 
# but to keep scripts portable, we'll redefine the dummy or import safely.
try:
    from dashboard import MASTER_MAP
except ImportError:
    MASTER_MAP = {
        "default": {"benefit": "digital growth and ROI optimization"}
    }

def generate_pdf_proposal(lead_name, niche, company):
    pdf = FPDF()
    pdf.add_page()
    
    # 1. Header & Branding
    pdf.set_font("Arial", 'B', 20)
    pdf.cell(200, 10, "iAdsClick Digital Intelligence", ln=True, align='C')
    pdf.set_font("Arial", '', 12)
    pdf.cell(200, 10, f"Custom Growth Proposal for {company}", ln=True, align='C')
    pdf.ln(10)

    # 2. The Personalized Gap Analysis
    config = MASTER_MAP.get(niche, MASTER_MAP.get('default', {"benefit": "growth strategies"}))
    pdf.set_font("Arial", 'B', 14)
    pdf.cell(200, 10, f"Target: {config['benefit']}", ln=True)
    pdf.ln(5)
    
    pdf.set_font("Arial", '', 11)
    content = f"""
    Dear {lead_name},
    
    Based on our initial audit of {company}, we have identified critical data signals 
    that are currently unoptimized. Our 'Signal Recovery' protocol is designed 
    specifically for the {niche} sector to recover lost attribution and scale ROI.
    
    Proposed Strategy:
    - Implementation of Server-Side GTM for 100% Accuracy.
    - AI-Driven Lead Nurturing via NexusHunt.
    - Automated Funnel Recovery for {config['benefit']}.
    """
    pdf.multi_cell(0, 10, content)
    
    # 3. Save to your local Brain folder
    out_dir = "E:/iadsclick-brain/proposals"
    os.makedirs(out_dir, exist_ok=True)
    file_name = f"{out_dir}/{lead_name.replace(' ', '_')}_Proposal.pdf"
    
    pdf.output(file_name)
    print(f"📄 Proposal Generated: {file_name}")
    return file_name

def send_hot_lead_alert(lead_name, company, niche, pdf_path):
    recipients = ["gads.advertisement@gmail.com", "baagish@gmail.com"]
    sender = os.environ.get("SMTP_USER", "advit@iadsclick.com")
    pwd = os.environ.get("SMTP_PASS", "your_app_password")

    msg = MIMEMultipart()
    msg['Subject'] = f"🔥 HOT LEAD: {lead_name} clicked 3 times!"
    msg['From'] = sender
    msg['To'] = ", ".join(recipients)
    
    body = f"Advit,\n\n{lead_name} from {company} is highly interested in the {niche} audit. I've generated their professional proposal and saved it locally.\nSend it now to close the deal."
    msg.attach(MIMEText(body, 'plain'))
    
    try:
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as s:
            s.login(sender, pwd)
            s.sendmail(sender, recipients, msg.as_string())
        print("📧 Alert Dispatched!")
    except Exception as e:
        print(f"Failed to send email: {e}")

if __name__ == "__main__":
    test_pdf = generate_pdf_proposal("John Doe", "dental", "Apex Dental")
    # send_hot_lead_alert("John Doe", "Apex Dental", "dental", test_pdf)
