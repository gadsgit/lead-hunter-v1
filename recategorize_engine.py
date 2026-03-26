import requests
from bs4 import BeautifulSoup

def sync_niche_with_sitemap(leads_list):
    # 1. Scrape Sitemap for Titles and URLs
    sitemap_url = "https://iadsclick.com/sitemap.php"
    try:
        soup = BeautifulSoup(requests.get(sitemap_url, timeout=10).text, 'html.parser')
        pages = {link.text.strip().lower(): link['href'] for link in soup.find_all('a', href=True)}
    except Exception as e:
        print(f"Error fetching sitemap: {e}")
        return leads_list

    # 2. Re-Categorize Leads
    for lead in leads_list:
        name = lead.get('Name', '').lower()
        
        # Check if any sitemap title matches the lead's business name/keywords
        for title, url in pages.items():
            if "real estate" in title and ("realestate" in name or "yamuna" in name):
                lead['Niche'] = "re_yamuna"
                lead['Correct_URL'] = url
                break
            elif "dental" in title and "dental" in name:
                lead['Niche'] = "dental"
                lead['Correct_URL'] = url
                break
                
    return leads_list

if __name__ == "__main__":
    dummy = [{"Name": "Yamuna Realestate Pvt Ltd", "Niche": "dental"}]
    print("Before:", dummy)
    corrected = sync_niche_with_sitemap(dummy)
    print("After:", corrected)
