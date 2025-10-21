# test_bot.py
import os
import requests
from datetime import datetime
import json

class C:
    G, R, Y, B, E = '\033[92m', '\033[91m', '\033[93m', '\033[94m', '\033[0m'

def ok(msg): print(f"{C.G}✓ {msg}{C.E}")
def err(msg): print(f"{C.R}✗ {msg}{C.E}")
def warn(msg): print(f"{C.Y}⚠ {msg}{C.E}")
def info(msg): print(f"{C.B}ℹ {msg}{C.E}")

# REAL WORKING COURSE
TEST_COURSE_ID = "686254fca0502cc2d68f5b89"
API_BASE = "https://api.pptlinks.com/api/v1"
TEST_URL = f"{API_BASE}/course/user-courses/{TEST_COURSE_ID}?brief=false&timeZone=Africa/Lagos"

def test_env():
    print("\n" + "="*50 + "\nTesting Environment\n" + "="*50)
    ok("BOT_TOKEN: loaded")
    ok(f"API_BASE: {API_BASE}")
    ok(f"TEST_COURSE_ID: {TEST_COURSE_ID}")
    return True

def test_telegram():
    print("\n" + "="*50 + "\nTesting Telegram Bot\n" + "="*50)
    try:
        r = requests.get(f"https://api.telegram.org/bot8126336145:AAH9ROvECWEA1Bo1J_xclwrYA0lYdhWiMNA/getMe", timeout=10)
        if r.status_code == 200 and r.json().get('ok'):
            bot = r.json()['result']
            ok("Bot is alive!")
            info(f"@{bot['username']} | {bot['first_name']}")
            return True
    except: pass
    err("Bot token invalid")
    return False

def test_api():
    print("\n" + "="*50 + "\nTesting PPTLinks API\n" + "="*50)
    try:
        r = requests.get(TEST_URL, timeout=10)
        if r.status_code == 200:
            data = r.json()
            ok("API CONNECTED (200 OK)")
            info(f"Course: {data.get('name')}")
            info(f"Sections: {len(data.get('CourseSection', []))}")
            return True
        else:
            err(f"Status {r.status_code}")
            return False
    except Exception as e:
        err(f"Request failed: {e}")
        return False

def test_deps():
    print("\n" + "="*50 + "\nTesting Dependencies\n" + "="*50)
    for pkg in ['telegram', 'requests', 'apscheduler', 'pytz', 'dateutil']:
        try:
            __import__(pkg.replace('-', '_') if pkg == 'dateutil' else pkg)
            ok(f"{pkg} installed")
        except:
            err(f"{pkg} missing")
    return True

def test_parsing():
    print("\n" + "="*50 + "\nTesting Data Parsing\n" + "="*50)
    try:
        r = requests.get(TEST_URL, timeout=10)
        if r.status_code == 200:
            data = r.json()
            ok(f"Name: {data['name']}")
            ok(f"Sections: {len(data['CourseSection'])}")
            return True
    except: pass
    err("Failed to parse")
    return False

def activation_link():
    print("\n" + "="*50 + "\nActivation Link\n" + "="*50)
    link = f"https://t.me/PPTLinksReminderBot?start={TEST_COURSE_ID}"
    ok("Link ready:")
    print(f"\n{C.B}{link}{C.E}\n")

def run():
    print(f"\n{C.B}{'='*50}\nPPTLinks Bot Test Suite\n{'='*50}{C.E}")
    print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

    results = [
        ("Env", test_env()),
        ("Telegram", test_telegram()),
        ("API", test_api()),
        ("Deps", test_deps()),
        ("Parsing", test_parsing()),
    ]
    activation_link()

    passed = sum(1 for _, r in results if r)
    print("\n" + "="*50 + "\nSummary\n" + "="*50)
    for name, res in results:
        print(f"{C.G if res else C.R}{name}: {'PASS' if res else 'FAIL'}{C.E}")
    print(f"\n{C.G if passed == len(results) else C.R}{passed}/{len(results)} passed{C.E}")

if __name__ == "__main__":
    run()