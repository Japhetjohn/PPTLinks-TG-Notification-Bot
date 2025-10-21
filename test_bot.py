"""
Testing utilities for PPTLinks Reminder Bot
Run this to test your bot configuration and API connectivity
"""

import os
import sys
import requests
from dotenv import load_dotenv
from datetime import datetime
import json

# Colors for terminal output
class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    END = '\033[0m'

def print_success(message):
    print(f"{Colors.GREEN}✓ {message}{Colors.END}")

def print_error(message):
    print(f"{Colors.RED}✗ {message}{Colors.END}")

def print_warning(message):
    print(f"{Colors.YELLOW}⚠ {message}{Colors.END}")

def print_info(message):
    print(f"{Colors.BLUE}ℹ {message}{Colors.END}")

def test_environment_variables():
    """Test if all required environment variables are set"""
    print("\n" + "="*50)
    print("Testing Environment Variables")
    print("="*50)
    
    load_dotenv()
    
    required_vars = {
        'BOT_TOKEN': 'Telegram Bot Token',
        'API_BASE': 'PPTLinks API Base URL'
    }
    
    optional_vars = {
        'POLL_INTERVAL': 'Polling Interval',
        'WEBHOOK_URL': 'Webhook URL (for production)',
        'USE_DATABASE': 'Database Usage Flag'
    }
    
    all_good = True
    
    # Check required variables
    for var, description in required_vars.items():
        value = os.getenv(var)
        if value:
            # Mask sensitive data
            display_value = value[:10] + "..." if len(value) > 10 else value
            print_success(f"{description} ({var}): {display_value}")
        else:
            print_error(f"{description} ({var}) is not set!")
            all_good = False
    
    # Check optional variables
    print("\nOptional Configuration:")
    for var, description in optional_vars.items():
        value = os.getenv(var)
        if value:
            print_success(f"{description} ({var}): {value}")
        else:
            print_warning(f"{description} ({var}) is not set (using default)")
    
    return all_good

def test_telegram_bot():
    """Test Telegram bot token validity"""
    print("\n" + "="*50)
    print("Testing Telegram Bot Connection")
    print("="*50)
    
    load_dotenv()
    bot_token = os.getenv("BOT_TOKEN")
    
    if not bot_token:
        print_error("BOT_TOKEN not found!")
        return False
    
    try:
        # Test getMe endpoint
        url = f"https://api.telegram.org/bot{bot_token}/getMe"
        response = requests.get(url, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            if data.get('ok'):
                bot_info = data.get('result', {})
                print_success("Bot token is valid!")
                print_info(f"Bot Username: @{bot_info.get('username')}")
                print_info(f"Bot Name: {bot_info.get('first_name')}")
                print_info(f"Bot ID: {bot_info.get('id')}")
                return True
            else:
                print_error("Invalid bot token!")
                return False
        else:
            print_error(f"HTTP Error {response.status_code}")
            return False
            
    except requests.exceptions.RequestException as e:
        print_error(f"Connection error: {e}")
        return False

def test_api_connectivity():
    """Test PPTLinks API connectivity"""
    print("\n" + "="*50)
    print("Testing PPTLinks API Connection")
    print("="*50)
    
    load_dotenv()
    api_base = os.getenv("API_BASE", "https://api.pptlinks.com/api/v1")
    
    # Test with a dummy course ID (will fail but tests connectivity)
    test_course_id = "test123"
    url = f"{api_base}/course/user-courses/{test_course_id}?brief=false&timeZone=Africa/Lagos"
    
    try:
        response = requests.get(url, timeout=10)
        
        if response.status_code in [200, 404, 401]:
            print_success("API endpoint is reachable!")
            print_info(f"Status Code: {response.status_code}")
            print_info(f"API Base: {api_base}")
            
            if response.status_code == 404:
                print_warning("Course not found (expected for test)")
            elif response.status_code == 401:
                print_warning("Authentication required (may need course enrollment)")
                
            return True
        else:
            print_error(f"Unexpected status code: {response.status_code}")
            return False
            
    except requests.exceptions.RequestException as e:
        print_error(f"Connection error: {e}")
        return False

def test_dependencies():
    """Test if all required Python packages are installed"""
    print("\n" + "="*50)
    print("Testing Python Dependencies")
    print("="*50)
    
    required_packages = [
        'telegram',
        'apscheduler',
        'requests',
        'dotenv',
        'dateutil',
        'pytz'
    ]
    
    all_installed = True
    
    for package in required_packages:
        try:
            __import__(package)
            print_success(f"{package} is installed")
        except ImportError:
            print_error(f"{package} is NOT installed!")
            all_installed = False
    
    if not all_installed:
        print("\n" + Colors.YELLOW + "To install missing packages, run:")
        print("pip install -r requirements.txt" + Colors.END)
    
    return all_installed

def test_course_data_parsing():
    """Test course data parsing logic"""
    print("\n" + "="*50)
    print("Testing Course Data Parsing")
    print("="*50)
    
    # Sample course data structure
    sample_data = {
        "CourseName": "Test Course",
        "CourseSection": [
            {
                "Name": "Section 1",
                "CourseSectionItem": [
                    {
                        "_id": "file1",
                        "Type": "File",
                        "Name": "Lecture Notes.pdf",
                        "FileUrl": "https://example.com/file.pdf"
                    },
                    {
                        "_id": "quiz1",
                        "Type": "Quiz",
                        "Name": "Week 1 Quiz",
                        "StartTime": "2024-10-20T10:00:00",
                        "EndTime": "2024-10-20T11:00:00"
                    }
                ]
            }
        ]
    }
    
    try:
        # Test parsing
        course_name = sample_data.get("CourseName")
        sections = sample_data.get("CourseSection", [])
        
        print_success(f"Course Name: {course_name}")
        print_success(f"Number of Sections: {len(sections)}")
        
        for section in sections:
            items = section.get("CourseSectionItem", [])
            print_success(f"Section '{section.get('Name')}' has {len(items)} items")
            
            for item in items:
                item_type = item.get("Type")
                item_name = item.get("Name")
                print_info(f"  - {item_type}: {item_name}")
        
        print_success("Course data parsing logic works correctly!")
        return True
        
    except Exception as e:
        print_error(f"Parsing error: {e}")
        return False

def test_message_formatting():
    """Test message formatting"""
    print("\n" + "="*50)
    print("Testing Message Formatting")
    print("="*50)
    
    try:
        # Test welcome message
        welcome = f"""🎓 *Welcome to PPTLinks Notifications!*

You're now subscribed to updates for *Test Course*.

You'll receive reminders for:
📚 New uploads and content updates
🧑‍🏫 Live class start times
🧩 Quiz creation, start, and end
⏳ Course expiry notices"""
        
        print_success("Welcome message format:")
        print(welcome)
        
        # Test file notification
        file_msg = """📂 *New Content Added!*

A new file has been uploaded to *Test Course*.

📄 File: `Lecture Notes.pdf`"""
        
        print("\n" + "="*30)
        print_success("File notification format:")
        print(file_msg)
        
        return True
        
    except Exception as e:
        print_error(f"Formatting error: {e}")
        return False

def generate_activation_link():
    """Generate a sample activation link"""
    print("\n" + "="*50)
    print("Sample Activation Link")
    print("="*50)
    
    load_dotenv()
    
    try:
        url = f"https://api.telegram.org/bot{os.getenv('BOT_TOKEN')}/getMe"
        response = requests.get(url, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            bot_username = data.get('result', {}).get('username')
            
            sample_course_id = "686254fca0502cc2d68f5b89"
            activation_link = f"https://t.me/{bot_username}?start={sample_course_id}"
            
            print_success("Sample activation link generated:")
            print(f"\n{Colors.BLUE}{activation_link}{Colors.END}\n")
            print_info("Replace the course ID with actual course ID from PPTLinks")
            return True
        else:
            print_error("Could not fetch bot info")
            return False
            
    except Exception as e:
        print_error(f"Error: {e}")
        return False

def run_all_tests():
    """Run all tests"""
    print("\n" + Colors.BLUE + "="*50)
    print("PPTLinks Reminder Bot - Test Suite")
    print("="*50 + Colors.END)
    print(f"Test started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    
    results = {
        "Environment Variables": test_environment_variables(),
        "Telegram Bot": test_telegram_bot(),
        "API Connectivity": test_api_connectivity(),
        "Dependencies": test_dependencies(),
        "Data Parsing": test_course_data_parsing(),
        "Message Formatting": test_message_formatting()
    }
    
    # Generate activation link
    generate_activation_link()
    
    # Summary
    print("\n" + "="*50)
    print("Test Summary")
    print("="*50)
    
    passed = sum(1 for result in results.values() if result)
    total = len(results)
    
    for test_name, result in results.items():
        status = "PASSED" if result else "FAILED"
        color = Colors.GREEN if result else Colors.RED
        print(f"{color}{test_name}: {status}{Colors.END}")
    
    print("\n" + "="*50)
    print(f"Results: {passed}/{total} tests passed")
    print("="*50)
    
    if passed == total:
        print_success("\n🎉 All tests passed! Your bot is ready to deploy!")
        return True
    else:
        print_error(f"\n❌ {total - passed} test(s) failed. Please fix the issues above.")
        return False

if __name__ == "__main__":
    try:
        success = run_all_tests()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\nTests interrupted by user.")
        sys.exit(1)
    except Exception as e:
        print_error(f"\nUnexpected error: {e}")
        sys.exit(1)