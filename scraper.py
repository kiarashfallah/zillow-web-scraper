import time
import subprocess
from pynput.keyboard import Key, Controller
from playwright.sync_api import sync_playwright
import csv
import pandas as pd
from urllib.parse import urljoin, urlparse

def is_valid_url(url):
    """Check if URL is valid"""
    try:
        result = urlparse(url)
        return all([result.scheme, result.netloc])
    except:
        return False

def extract_property_info(text):
    """Extract structured info from property text"""
    import re
    
    info = {
        'address': None,
        'price': None,
        'beds': None,
        'baths': None,
        'sqft': None,
        'property_type': None
    }
    
    # Extract price
    price_match = re.search(r'\$([0-9,]+)', text)
    if price_match:
        info['price'] = price_match.group(0)
    
    # Extract beds/baths
    beds_match = re.search(r'(\d+)\s*bds?', text)
    if beds_match:
        info['beds'] = beds_match.group(1)
    
    baths_match = re.search(r'(\d+)\s*ba', text)
    if baths_match:
        info['baths'] = baths_match.group(1)
    
    # Extract sqft
    sqft_match = re.search(r'([0-9,]+)\s*sqft', text)
    if sqft_match:
        info['sqft'] = sqft_match.group(1)
    
    # Extract property type
    type_match = re.search(r'(House|Condo|Townhouse|Apartment)\s+for\s+sale', text)
    if type_match:
        info['property_type'] = type_match.group(1)
    
    # Extract address (first part before price or agent info)
    address_match = re.search(r'^([^$]+?)(?=\$|DRE|Show more)', text)
    if address_match:
        info['address'] = address_match.group(1).strip()
    
    return info

# Start Chrome and navigate
chrome_path = r"C:\chrome.exe"
profile_path = r"C:\Users\[username]\scraper\scraping_profile"

subprocess.Popen([
    chrome_path,
    f"--user-data-dir={profile_path}",
    "--remote-debugging-port=9222",
    "https://www.zillow.com/"
])

time.sleep(3)

keyboard = Controller()
keyboard.press(Key.ctrl)
keyboard.press('l')
keyboard.release('l')
keyboard.release(Key.ctrl)
time.sleep(0.5)
keyboard.type('https://www.zillow.com/san-francisco-ca/%7Bnumber%7D_p/?searchQueryState=%7B%22pagination%22%3A%7B%22currentPage%22%3A5%7D%2C%22isMapVisible%22%3Atrue%2C%22mapBounds%22%3A%7B%22west%22%3A-122.56825534228516%2C%22east%22%3A-122.29840365771484%2C%22south%22%3A37.68826707224079%2C%22north%22%3A37.862214518537805%7D%2C%22regionSelection%22%3A%5B%7B%22regionId%22%3A20330%2C%22regionType%22%3A6%7D%5D%2C%22filterState%22%3A%7B%22sort%22%3A%7B%22value%22%3A%22globalrelevanceex%22%7D%7D%2C%22isListVisible%22%3Atrue%2C%22mapZoom%22%3A12%7D')
keyboard.press(Key.enter)
keyboard.release(Key.enter)

print("Navigated to San Francisco page")
time.sleep(5)

# Connect and extract data
with sync_playwright() as p:
    browser = p.chromium.connect_over_cdp("http://localhost:9222")
    context = browser.contexts[0]
    
    for page in context.pages:
        if "san-francisco-ca" in page.url:
            print("Found the right page!")
            
            # Wait for content to load
            page.wait_for_selector('[class*="property-card-data"]', timeout=10000)
            
            all_properties = []
            seen_links = set()
            scroll_count = 0
            max_scrolls = 50
            consecutive_no_new = 0
            
            while scroll_count < max_scrolls and consecutive_no_new < 3:
                print(f"\n--- Scroll {scroll_count + 1} ---")
                
                # Get current properties
                try:
                    property_cards = page.query_selector_all('[class*="property-card-data"]')
                    
                    new_properties = 0
                    for card in property_cards:
                        try:
                            # Get text content
                            text = card.text_content().strip()
                            if not text:
                                continue
                            
                            # Extract structured info
                            prop_info = extract_property_info(text)
                            
                            # Try to find link
                            link = None
                            anchor = card.query_selector('a')
                            if anchor:
                                link = anchor.get_attribute('href')
                            
                            if not link:
                                parent = card.query_selector('..')
                                if parent:
                                    anchor = parent.query_selector('a')
                                    if anchor:
                                        link = anchor.get_attribute('href')
                            
                            if not link:
                                zpid = card.get_attribute('data-zpid') or card.get_attribute('id')
                                if zpid:
                                    if 'zpid_' in zpid:
                                        zpid = zpid.replace('zpid_', '')
                                    link = f"https://www.zillow.com/homedetails/{zpid}_zpid/"
                            
                            if link:
                                if link.startswith('/'):
                                    link = f"https://www.zillow.com{link}"
                                
                                if link in seen_links:
                                    continue
                                
                                if is_valid_url(link):
                                    seen_links.add(link)
                                    
                                    property_data = {
                                        'address': prop_info['address'] or 'N/A',
                                        'price': prop_info['price'] or 'N/A',
                                        'beds': prop_info['beds'] or 'N/A',
                                        'baths': prop_info['baths'] or 'N/A',
                                        'sqft': prop_info['sqft'] or 'N/A',
                                        'property_type': prop_info['property_type'] or 'N/A',
                                        'link': link,
                                        'full_text': text
                                    }
                                    
                                    all_properties.append(property_data)
                                    new_properties += 1
                        
                        except Exception as e:
                            print(f"Error processing card: {e}")
                            continue
                    
                    print(f"Found {new_properties} new properties (Total: {len(all_properties)})")
                    
                    if new_properties == 0:
                        consecutive_no_new += 1
                    else:
                        consecutive_no_new = 0
                    
                    # Smooth scrolling
                    try:
                        # Get window height for incremental scrolling
                        window_height = page.evaluate("window.innerHeight")
                        # Scroll by one viewport height
                        page.evaluate(f"window.scrollBy(0, {window_height})")
                        
                        # Wait for new content to load
                        time.sleep(2)  # Reduced delay for faster scraping, adjust if needed
                        
                        # Check if new content loaded
                        new_cards = page.query_selector_all('[class*="property-card-data"]')
                        if len(new_cards) <= len(property_cards):
                            print("No new content loaded")
                            consecutive_no_new += 1
                        
                    except Exception as e:
                        print(f"Error during scrolling: {e}")
                        break
                    
                    scroll_count += 1
                
                except Exception as e:
                    print(f"Error during processing: {e}")
                    break
            
            # Save to CSV
            if all_properties:
                df = pd.DataFrame(all_properties)
                df = df.drop_duplicates(subset=['link'])
                
                csv_filename = 'zillow_properties_complete.csv'
                df.to_csv(csv_filename, index=False)
                
                print(f"\n=== FINAL RESULTS ===")
                print(f"Total unique properties: {len(df)}")
                print(f"Saved to: {csv_filename}")
                
                print(f"\nSummary:")
                print(f"- Properties with price: {len(df[df['price'] != 'N/A'])}")
                print(f"- Properties with beds info: {len(df[df['beds'] != 'N/A'])}")
                print(f"- Properties with sqft: {len(df[df['sqft'] != 'N/A'])}")
                
                print(f"\nFirst 5 properties:")
                for i, row in df.head().iterrows():
                    print(f"{i+1}. {row['address']} - {row['price']}")
                    print(f"   {row['beds']} beds, {row['baths']} baths, {row['sqft']} sqft")
                    print(f"   Link: {row['link']}")
                    print()
            
            else:
                print("No properties found!")
            
            break

input("Press Enter to quit...")
