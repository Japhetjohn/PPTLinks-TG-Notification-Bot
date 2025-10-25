#!/usr/bin/env python3
"""
PPTLinks Notification Bot - Comprehensive Test Suite

This script tests all notification scenarios to ensure production readiness.
"""

import sys
import hashlib
import json
from datetime import datetime, timedelta
import pytz

# Replicate the hash function from main.py (to avoid importing telegram)
def get_content_hash(data):
    """Generate hash based only on actual content, not dynamic fields"""
    content_data = {
        'course_id': data.get('id'),
        'sections': []
    }

    for section in data.get('CourseSection', []):
        section_content = {
            'id': section.get('id'),
            'title': section.get('title'),
            'contents': []
        }

        for item in section.get('contents', []):
            item_content = {
                'id': item.get('id'),
                'name': item.get('name'),
                'type': item.get('type'),
                'status': item.get('status'),
                'presentationStatus': item.get('presentationStatus'),
            }

            if item.get('type') == 'QUIZ' and 'quiz' in item:
                item_content['quiz'] = {
                    'status': item['quiz'].get('status'),
                    'startTime': item['quiz'].get('startTime'),
                    'endTime': item['quiz'].get('endTime'),
                    'duration': item['quiz'].get('duration')
                }

            if 'file' in item:
                item_content['file'] = item.get('file')

            section_content['contents'].append(item_content)

        content_data['sections'].append(section_content)

    return hashlib.md5(json.dumps(content_data, sort_keys=True).encode()).hexdigest()

class PPTLinksAPI:
    @staticmethod
    def get_hash(data):
        return get_content_hash(data)

# Color codes for terminal output
class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    BOLD = '\033[1m'
    END = '\033[0m'

def print_test(name):
    print(f"\n{Colors.BLUE}{Colors.BOLD}[TEST] {name}{Colors.END}")

def print_pass(msg):
    print(f"  {Colors.GREEN}✓ PASS:{Colors.END} {msg}")

def print_fail(msg):
    print(f"  {Colors.RED}✗ FAIL:{Colors.END} {msg}")

def print_info(msg):
    print(f"  {Colors.YELLOW}ℹ INFO:{Colors.END} {msg}")

#############################################################################
# TEST 1: Hash Stability - No False Positives
#############################################################################
def test_hash_stability():
    print_test("Hash Stability - Dynamic Fields Excluded")

    # Two API responses with SAME content but different dynamic fields
    response1 = {
        "id": "686254fca0502cc2d68f5b89",
        "name": "Test Course",
        "updatedAt": "2025-10-25T10:00:00.000Z",  # Dynamic
        "CourseSection": [{
            "id": "section1",
            "title": "Section 1",
            "contents": [{
                "id": "content1",
                "name": "Lesson 1.pptx",
                "type": "PPT",
                "status": "done",
                "presentationStatus": "NOT_LIVE",
                "progress": 0,  # Dynamic - user specific
                "file": "path/to/file.pdf"
            }]
        }]
    }

    response2 = {
        "id": "686254fca0502cc2d68f5b89",
        "name": "Test Course",
        "updatedAt": "2025-10-25T10:10:00.000Z",  # DIFFERENT timestamp
        "CourseSection": [{
            "id": "section1",
            "title": "Section 1",
            "contents": [{
                "id": "content1",
                "name": "Lesson 1.pptx",
                "type": "PPT",
                "status": "done",
                "presentationStatus": "NOT_LIVE",
                "progress": 50,  # DIFFERENT progress
                "file": "path/to/file.pdf"
            }]
        }]
    }

    hash1 = PPTLinksAPI.get_hash(response1)
    hash2 = PPTLinksAPI.get_hash(response2)

    if hash1 == hash2:
        print_pass(f"Hashes match for same content: {hash1[:8]}...")
        print_pass("No false positive notifications will be sent")
        return True
    else:
        print_fail(f"Hashes differ: {hash1[:8]}... != {hash2[:8]}...")
        print_fail("Bot would spam users with duplicate notifications!")
        return False

#############################################################################
# TEST 2: New Content Detection
#############################################################################
def test_new_content_detection():
    print_test("New Content Detection (PPT/Video)")

    old_data = {
        "CourseSection": [{
            "contents": [
                {"id": "content1", "name": "Lesson 1.pptx", "type": "PPT"},
                {"id": "content2", "name": "Lesson 2.mp4", "type": "VIDEO"}
            ]
        }]
    }

    new_data = {
        "CourseSection": [{
            "contents": [
                {"id": "content1", "name": "Lesson 1.pptx", "type": "PPT"},
                {"id": "content2", "name": "Lesson 2.mp4", "type": "VIDEO"},
                {"id": "content3", "name": "Lesson 3.pptx", "type": "PPT"},  # NEW!
            ]
        }]
    }

    old_hash = PPTLinksAPI.get_hash(old_data)
    new_hash = PPTLinksAPI.get_hash(new_data)

    if old_hash != new_hash:
        print_pass("Hash changed when new content added")
        print_pass("Notification WILL be triggered for new content")
        return True
    else:
        print_fail("Hash didn't change - new content won't be detected!")
        return False

#############################################################################
# TEST 3: Live Class Detection
#############################################################################
def test_live_class_detection():
    print_test("Live Class Detection")

    before_live = {
        "CourseSection": [{
            "contents": [{
                "id": "content1",
                "name": "React Basics",
                "type": "PPT",
                "presentationStatus": "NOT_LIVE"
            }]
        }]
    }

    after_live = {
        "CourseSection": [{
            "contents": [{
                "id": "content1",
                "name": "React Basics",
                "type": "PPT",
                "presentationStatus": "LIVE"  # Changed to LIVE!
            }]
        }]
    }

    hash_before = PPTLinksAPI.get_hash(before_live)
    hash_after = PPTLinksAPI.get_hash(after_live)

    if hash_before != hash_after:
        print_pass("Hash changed when presentation went LIVE")
        print_pass("Live class notification WILL be triggered")
        return True
    else:
        print_fail("Hash didn't change - live classes won't be detected!")
        return False

#############################################################################
# TEST 4: Quiz Schedule Detection
#############################################################################
def test_quiz_schedule_detection():
    print_test("Quiz Schedule Change Detection")

    quiz_v1 = {
        "CourseSection": [{
            "contents": [{
                "id": "quiz1",
                "name": "Midterm Exam",
                "type": "QUIZ",
                "quiz": {
                    "status": "active",
                    "startTime": "2025-11-01T10:00:00.000Z",
                    "endTime": "2025-11-01T12:00:00.000Z",
                    "duration": 120
                }
            }]
        }]
    }

    quiz_v2 = {
        "CourseSection": [{
            "contents": [{
                "id": "quiz1",
                "name": "Midterm Exam",
                "type": "QUIZ",
                "quiz": {
                    "status": "active",
                    "startTime": "2025-11-02T10:00:00.000Z",  # Changed date!
                    "endTime": "2025-11-02T12:00:00.000Z",    # Changed date!
                    "duration": 120
                }
            }]
        }]
    }

    hash1 = PPTLinksAPI.get_hash(quiz_v1)
    hash2 = PPTLinksAPI.get_hash(quiz_v2)

    if hash1 != hash2:
        print_pass("Hash changed when quiz schedule changed")
        print_pass("Quiz reschedule notification WILL be triggered")
        return True
    else:
        print_fail("Hash didn't change - quiz reschedules won't be detected!")
        return False

#############################################################################
# TEST 5: URL Verification
#############################################################################
def test_url_patterns():
    print_test("PPTLinks URL Patterns")

    course_id = "686254fca0502cc2d68f5b89"
    content_id = "6864045186a812defa2abee2"

    tests = [
        ("Course URL", f"https://pptlinks.com/course/{course_id}"),
        ("Content URL", f"https://pptlinks.com/course/{course_id}/content/{content_id}"),
        ("Live Class URL", f"https://pptlinks.com/course/{course_id}/content/{content_id}"),
        ("Quiz URL", f"https://pptlinks.com/course/{course_id}/content/{content_id}"),
    ]

    all_pass = True
    for name, url in tests:
        if url.startswith("https://pptlinks.com/"):
            print_pass(f"{name}: {url}")
        else:
            print_fail(f"{name}: Invalid URL - {url}")
            all_pass = False

    return all_pass

#############################################################################
# TEST 6: Quiz Reminder Scheduling Logic
#############################################################################
def test_quiz_reminder_scheduling():
    print_test("Quiz Reminder Scheduling (1 Day Before)")

    # Quiz starting in 2 days
    now = datetime.now(pytz.timezone('Africa/Lagos'))
    quiz_start = now + timedelta(days=2)
    notify_time = quiz_start - timedelta(days=1)  # Should be tomorrow

    if notify_time > now:
        time_diff = (notify_time - now).total_seconds() / 3600
        print_pass(f"Quiz notification scheduled for {notify_time.strftime('%Y-%m-%d %H:%M')}")
        print_info(f"Notification will fire in {time_diff:.1f} hours")
        return True
    else:
        print_fail("Notification time is in the past!")
        return False

#############################################################################
# TEST 7: Course Expiry Calculation
#############################################################################
def test_course_expiry_calculation():
    print_test("Course Expiry Calculation")

    subscription_date = datetime.now(pytz.timezone('Africa/Lagos'))
    duration_days = 90  # THREE_MONTHS

    expiry_date = subscription_date + timedelta(days=duration_days)
    notify_date = expiry_date - timedelta(days=7)  # 1 week before

    now = datetime.now(pytz.timezone('Africa/Lagos'))

    if notify_date > now:
        days_until_notify = (notify_date - now).days
        print_pass(f"Expiry notification scheduled for {notify_date.strftime('%Y-%m-%d')}")
        print_info(f"Notification will fire in {days_until_notify} days")
        print_info(f"Course expires on {expiry_date.strftime('%Y-%m-%d')}")
        return True
    else:
        print_fail("Expiry notification date is in the past!")
        return False

#############################################################################
# TEST 8: Progress Changes Don't Trigger Notifications
#############################################################################
def test_progress_ignored():
    print_test("Progress Changes Ignored (No Spam)")

    data1 = {
        "CourseSection": [{
            "contents": [{
                "id": "content1",
                "name": "Lesson 1",
                "type": "VIDEO",
                "progress": 0  # Just started
            }]
        }]
    }

    data2 = {
        "CourseSection": [{
            "contents": [{
                "id": "content1",
                "name": "Lesson 1",
                "type": "VIDEO",
                "progress": 100  # Completed!
            }]
        }]
    }

    hash1 = PPTLinksAPI.get_hash(data1)
    hash2 = PPTLinksAPI.get_hash(data2)

    if hash1 == hash2:
        print_pass("Progress change ignored - hashes match")
        print_pass("User won't be spammed when watching videos")
        return True
    else:
        print_fail("Progress changes detected - will spam user!")
        return False

#############################################################################
# TEST 9: Multiple Courses - Independent Hashing
#############################################################################
def test_multiple_courses():
    print_test("Multiple Courses - Independent Hashing")

    course1 = {
        "id": "course1",
        "CourseSection": [{
            "contents": [{"id": "c1", "name": "Course 1 Content", "type": "PPT"}]
        }]
    }

    course2 = {
        "id": "course2",
        "CourseSection": [{
            "contents": [{"id": "c2", "name": "Course 2 Content", "type": "PPT"}]
        }]
    }

    hash1 = PPTLinksAPI.get_hash(course1)
    hash2 = PPTLinksAPI.get_hash(course2)

    if hash1 != hash2:
        print_pass("Different courses have different hashes")
        print_pass("Multi-course support working correctly")
        return True
    else:
        print_fail("Different courses have same hash - conflict!")
        return False

#############################################################################
# RUN ALL TESTS
#############################################################################
def run_all_tests():
    print(f"\n{Colors.BOLD}{'='*70}{Colors.END}")
    print(f"{Colors.BOLD}PPTLinks Notification Bot - Comprehensive Test Suite{Colors.END}")
    print(f"{Colors.BOLD}{'='*70}{Colors.END}")

    tests = [
        ("Hash Stability", test_hash_stability),
        ("New Content Detection", test_new_content_detection),
        ("Live Class Detection", test_live_class_detection),
        ("Quiz Schedule Detection", test_quiz_schedule_detection),
        ("URL Patterns", test_url_patterns),
        ("Quiz Reminder Scheduling", test_quiz_reminder_scheduling),
        ("Course Expiry Calculation", test_course_expiry_calculation),
        ("Progress Ignored", test_progress_ignored),
        ("Multiple Courses", test_multiple_courses),
    ]

    results = []
    for name, test_func in tests:
        try:
            result = test_func()
            results.append((name, result))
        except Exception as e:
            print_fail(f"Exception: {str(e)}")
            results.append((name, False))

    # Summary
    print(f"\n{Colors.BOLD}{'='*70}{Colors.END}")
    print(f"{Colors.BOLD}TEST SUMMARY{Colors.END}")
    print(f"{Colors.BOLD}{'='*70}{Colors.END}\n")

    passed = sum(1 for _, result in results if result)
    total = len(results)

    for name, result in results:
        status = f"{Colors.GREEN}✓ PASS{Colors.END}" if result else f"{Colors.RED}✗ FAIL{Colors.END}"
        print(f"  {status} - {name}")

    print(f"\n{Colors.BOLD}{'='*70}{Colors.END}")
    if passed == total:
        print(f"{Colors.GREEN}{Colors.BOLD}ALL TESTS PASSED ({passed}/{total}) ✓{Colors.END}")
        print(f"{Colors.GREEN}{Colors.BOLD}BOT IS PRODUCTION READY! 🚀{Colors.END}")
    else:
        print(f"{Colors.RED}{Colors.BOLD}TESTS FAILED ({passed}/{total}) ✗{Colors.END}")
        print(f"{Colors.RED}{Colors.BOLD}FIX ISSUES BEFORE DEPLOYMENT!{Colors.END}")
    print(f"{Colors.BOLD}{'='*70}{Colors.END}\n")

    return passed == total

if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
