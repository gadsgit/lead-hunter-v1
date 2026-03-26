import requests
from bs4 import BeautifulSoup
import json

def sync_sitemap_to_brain():
    url = "https://iadsclick.com/sitemap.php"
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
    except Exception as e:
        print(f"Failed to fetch sitemap: {e}")
        return {}

    soup = BeautifulSoup(response.text, 'html.parser')
    
    # Dictionary to store found URLs by category
    sitemap_data = {}

    # We look for the 'Division' headers
    divisions = soup.find_all(['h3', 'h4']) 
    for div in divisions:
        category_name = div.text.strip().replace("🌍 ", "").split()[0].lower()
        ul_list = div.find_next('ul')
        if ul_list:
            links = ul_list.find_all('a')
            sitemap_data[category_name] = [link.get('href') for link in links if link.get('href')]
        
    return sitemap_data

if __name__ == "__main__":
    print("Scraping sitemap dynamically...")
    urls = sync_sitemap_to_brain()
    print(json.dumps(urls, indent=2))
