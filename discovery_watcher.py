import os
import re
import json
import paramiko
import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()
try:
    genai.configure(api_key=os.environ["GOOGLE_API_KEY"])
    model = genai.GenerativeModel("gemini-1.5-flash")
except Exception as e:
    print(f"Skipping generative AI configuration: {e}")

# Known keys
MASTER_MAP_KEYS = ["dental", "parents", "re_noida", "analytics", "ai_agent"]

def discover_new_categories(directory="E:/iadsclick-testseries"):
    discovered = []
    if not os.path.exists(directory):
        print(f"Directory {directory} not found. Skipping local scan.")
        return discovered

    for root, dirs, files in os.walk(directory):
        for file in files:
            if file.endswith((".php", ".html")):
                with open(os.path.join(root, file), 'r', errors='ignore') as f:
                    content = f.read(1000)
                    match = re.search(r'<title>(.*?)</title>', content, re.IGNORECASE)
                    if match:
                        title = match.group(1).lower()
                        if "dubai" in title and "re_uae" not in MASTER_MAP_KEYS:
                            discovered.append("re_uae")
                        if "dankaur" in title and "local_seo" not in MASTER_MAP_KEYS:
                            discovered.append("local_seo")
                            
    return list(set(discovered))

def generate_dynamic_hook(new_topic_data):
    prompt = f"""
    Context: {new_topic_data}
    
    Task: 
    1. Create a short 'url_key' (lowercase, no spaces).
    2. Identify the core 'benefit' for a business in this niche.
    3. Write a high-conversion WhatsApp 'hook' sentence.
    
    Return as JSON exactly in this format: {{"url_key": "...", "benefit": "...", "hook": "..."}}
    """
    try:
        raw_response = model.generate_content(prompt).text
        # Optional basic JSON cleanup
        raw_response = raw_response.replace('```json', '').replace('```', '').strip()
        new_config = json.loads(raw_response)
        return new_config
    except Exception as e:
        print(f"Error generating dynamic hook: {e}")
        return None

def sync_go_php_to_server(new_key, new_url):
    host = os.environ.get("FTP_HOST", "iadsclick.com")
    username = os.environ.get("FTP_USER", "your_ftp_user")
    password = os.environ.get("FTP_PASS", "your_ftp_password")
    remote_path = "/public_html/go.php"
    local_temp = "temp_go.php"

    try:
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(host, username=username, password=password)
        sftp = ssh.open_sftp()
        sftp.get(remote_path, local_temp)

        with open(local_temp, 'r') as f:
            content = f.read()

        new_entry = f'    "{new_key}" => "{new_url}",\n'
        if new_key not in content:
            updated_content = content.replace('// ── General', new_entry + '    // ── General')
            with open(local_temp, 'w') as f:
                f.write(updated_content)

            sftp.put(local_temp, remote_path)
            print(f"✅ Successfully synced '{new_key}' to iadsclick.com/go.php")
        else:
            print(f"Key '{new_key}' already exists in go.php.")
        
        sftp.close()
        ssh.close()
        os.remove(local_temp)
    except Exception as e:
        print(f"Error syncing to server: {e}")

if __name__ == "__main__":
    print("Running Discovery Watcher...")
    new_cats = discover_new_categories("E:/iadsclick-testseries")
    print(f"Discovered new categories: {new_cats}")
