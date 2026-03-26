import qrcode
import urllib.parse
import os

def generate_bulk_qrcodes(lead_data_list):
    # 1. Base Redirect URL (Matches your go.php router)
    base_url = "https://iadsclick.com/go.php"
    
    # 2. Directory for QR codes
    qr_dir = "E:/iadsclick-brain/proposals/qrcodes"
    if not os.path.exists(qr_dir):
        os.makedirs(qr_dir)
    
    # 3. Process each lead to generate QR
    generated_qrs = []
    
    for lead in lead_data_list:
        name = lead.get('Name', 'Unknown')
        niche = lead.get('Niche', 'default')
        company = lead.get('Company', 'General')
        loc = str(lead.get('City', 'global')).lower()
        
        # Build the personalized tracking URL with hierarchy
        tracking_url = f"{base_url}?to={niche}&loc={loc}&n={urllib.parse.quote(name)}"
        
        # Generate the QR Code
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=4,
        )
        qr.add_data(tracking_url)
        qr.make(fit=True)
        
        # Customize colors (iAdsClick Green on Black)
        img = qr.make_image(fill_color="#2e7d32", back_color="black")
        
        # Save the QR code locally
        file_name = f"{qr_dir}/{name.replace(' ', '_')}_{niche}_{loc}.png"
        img.save(file_name)
        generated_qrs.append(file_name)
        print(f"✅ QR Code Generated: {file_name}")
        
    return generated_qrs

if __name__ == "__main__":
    dummy_leads = [
        {"Name": "Mr Sharma", "Niche": "parents", "City": "gyc"},
        {"Name": "Dr Smith", "Niche": "dental", "City": "delhi"}
    ]
    generate_bulk_qrcodes(dummy_leads)
