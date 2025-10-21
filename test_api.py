# test_api.py
import requests
import json
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

API_URL = "https://api.pptlinks.com/api/v1/course/user-courses/686254fca0502cc2d68f5b89?brief=false&timeZone=Africa/Lagos"

def test_no_headers():
    print("1. Testing WITHOUT any headers (like your bot)...")
    try:
        r = requests.get(API_URL, timeout=10)
        print(f"   Status: {r.status_code}")
        if r.status_code != 200:
            print(f"   Body: {r.text[:200]}")
        else:
            print("   SUCCESS (but shouldn't be!)")
    except Exception as e:
        print(f"   ERROR: {e}")

def test_with_browser_headers():
    print("\n2. Testing WITH real browser headers (copy-paste from DevTools)...")
    # REPLACE THESE WITH YOUR ACTUAL BROWSER HEADERS
    headers = {
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
        "Authorization": "Bearer PASTE_YOUR_TOKEN_HERE",  # ← GET THIS FROM BROWSER
        "Referer": "https://pptlinks.com/",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-site",
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36"
    }

    session = requests.Session()
    retry = Retry(total=3, backoff_factor=1, status_forcelist=[500, 502, 503, 504])
    session.mount("https://", HTTPAdapter(max_retries=retry))

    try:
        r = session.get(API_URL, headers=headers, timeout=10)
        print(f"   Status: {r.status_code}")
        if r.status_code == 200:
            data = r.json()
            print(f"   Course: {data['name']}")
            print(f"   Sections: {len(data['CourseSection'])}")
        else:
            print(f"   Failed: {r.text[:200]}")
    except Exception as e:
        print(f"   ERROR: {e}")

if __name__ == "__main__":
    print("PPTLinks API Connectivity Test")
    print("="*50)
    test_no_headers()
    print("\n" + "-"*50)
    print("NOW: Open the URL in Brave → F12 → Network → Find the request → Copy:")
    print("   • Authorization: Bearer ...")
    print("   • All other headers")
    print("-"*50)
    print("Paste the token into the script and run again.")
    print("\nRun this: python test_api.py")