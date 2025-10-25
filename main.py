# main.py - Enhanced PPTLinks Telegram Bot
import os
import json
import hashlib
import logging
from datetime import datetime, timedelta
from typing import Optional
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    CallbackQueryHandler,
)
from telegram.constants import ParseMode
from telegram.request import HTTPXRequest
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.date import DateTrigger
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from dateutil import parser as date_parser
import pytz
from database import Database

# ================================
# CONFIG
# ================================
BOT_TOKEN = "8126336145:AAH9ROvECWEA1Bo1J_xclwrYA0lYdhWiMNA"
API_BASE = "https://api.pptlinks.com/api/v1"
POLL_INTERVAL = 600  # 10 minutes

FIXED_COURSE_ID = "686254fca0502cc2d68f5b89"  # Default course ID

# ================================
# LOGGING
# ================================
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[logging.FileHandler('bot.log'), logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

# ================================
# GLOBALS
# ================================
db = Database()
scheduler = AsyncIOScheduler()

# ================================
# EMOJIS
# ================================
class Emoji:
    ROCKET = "🚀"
    BOOK = "📚"
    BELL = "🔔"
    CHECK = "✅"
    FIRE = "🔥"
    STAR = "⭐"
    TROPHY = "🏆"
    TARGET = "🎯"
    CHART = "📊"
    CLOCK = "⏰"
    CALENDAR = "📅"
    FILE = "📄"
    VIDEO = "🎥"
    QUIZ = "📝"
    WARNING = "⚠️"
    INFO = "ℹ️"
    SPARKLES = "✨"
    PARTY = "🎉"
    BRAIN = "🧠"
    LIGHT = "💡"
    GEAR = "⚙️"
    BACK = "◀️"
    WAVE = "👋"
    STUDENT = "👨‍🎓"
    TEACHER = "👨‍🏫"
    PIN = "📌"
    HOURGLASS = "⏳"


# ================================
# API
# ================================
class PPTLinksAPI:
    @staticmethod
    def fetch_course_data(course_id: str = None) -> Optional[dict]:
        """Fetch course data for a specific course ID"""
        if not course_id:
            course_id = FIXED_COURSE_ID

        url = f"{API_BASE}/course/user-courses/{course_id}?brief=false&timeZone=Africa/Lagos"
        session = requests.Session()
        retry = Retry(total=3, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504])
        session.mount('https://', HTTPAdapter(max_retries=retry))

        try:
            r = session.get(url, timeout=30)
            logger.info(f"API → {r.status_code} for course {course_id}")
            if r.status_code == 200:
                return r.json()
            else:
                logger.error(f"API error: {r.status_code} | {r.text[:200]}")
                return None
        except Exception as e:
            logger.error(f"Request failed: {e}")
            return None

    @staticmethod
    def get_hash(data: dict) -> str:
        """Generate hash based only on actual content, not dynamic fields

        We only hash the content that matters for notifications:
        - Course sections and their contents (IDs, names, types)
        - Quiz details (startTime, endTime, status)
        - Presentation status (for live classes)

        We EXCLUDE dynamic fields that change on every request:
        - progress, updatedAt, attempt, user-specific data
        """
        # Extract only the fields that matter for content changes
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
                # Only include fields that indicate actual content changes
                item_content = {
                    'id': item.get('id'),
                    'name': item.get('name'),
                    'type': item.get('type'),
                    'status': item.get('status'),
                    'presentationStatus': item.get('presentationStatus'),  # For live classes
                }

                # For quizzes, include schedule info
                if item.get('type') == 'QUIZ' and 'quiz' in item:
                    item_content['quiz'] = {
                        'status': item['quiz'].get('status'),
                        'startTime': item['quiz'].get('startTime'),
                        'endTime': item['quiz'].get('endTime'),
                        'duration': item['quiz'].get('duration')
                    }

                # For files, include the file path
                if 'file' in item:
                    item_content['file'] = item.get('file')

                section_content['contents'].append(item_content)

            content_data['sections'].append(section_content)

        # Generate hash from filtered content only
        hash_str = hashlib.md5(json.dumps(content_data, sort_keys=True).encode()).hexdigest()
        logger.debug(f"Generated content hash: {hash_str[:8]}... (filtered data)")
        return hash_str


# ================================
# KEYBOARD LAYOUTS
# ================================
class Keyboards:
    @staticmethod
    def main_menu():
        """Main menu with quick actions"""
        keyboard = [
            [
                InlineKeyboardButton(f"{Emoji.BOOK} My Courses", callback_data="mycourses"),
                InlineKeyboardButton(f"{Emoji.ROCKET} Add Course", callback_data="add_course")
            ],
            [
                InlineKeyboardButton(f"{Emoji.CHART} Statistics", callback_data="stats"),
                InlineKeyboardButton(f"{Emoji.BELL} Notifications", callback_data="notification_settings")
            ],
            [
                InlineKeyboardButton(f"{Emoji.GEAR} Settings", callback_data="settings"),
                InlineKeyboardButton(f"{Emoji.INFO} Help", callback_data="help")
            ]
        ]
        return InlineKeyboardMarkup(keyboard)

    @staticmethod
    def welcome_menu():
        """Welcome menu for first-time users"""
        keyboard = [
            [
                InlineKeyboardButton(f"{Emoji.ROCKET} Subscribe to Course", callback_data="add_course")
            ],
            [
                InlineKeyboardButton(f"{Emoji.INFO} How It Works", callback_data="how_it_works"),
                InlineKeyboardButton(f"{Emoji.GEAR} View Commands", callback_data="help")
            ]
        ]
        return InlineKeyboardMarkup(keyboard)

    @staticmethod
    def settings_menu():
        """Settings and preferences"""
        keyboard = [
            [
                InlineKeyboardButton(f"{Emoji.BELL} Notification Settings", callback_data="notification_settings"),
            ],
            [
                InlineKeyboardButton(f"{Emoji.BOOK} Manage Courses", callback_data="manage_courses"),
            ],
            [
                InlineKeyboardButton(f"{Emoji.WARNING} Unsubscribe All", callback_data="confirm_unsub"),
            ],
            [
                InlineKeyboardButton(f"{Emoji.BACK} Back to Menu", callback_data="main_menu")
            ]
        ]
        return InlineKeyboardMarkup(keyboard)

    @staticmethod
    def notification_settings_menu():
        """Notification preferences"""
        keyboard = [
            [
                InlineKeyboardButton(f"{Emoji.FILE} Content Uploads: ON", callback_data="toggle_content_notif")
            ],
            [
                InlineKeyboardButton(f"{Emoji.BRAIN} Quiz Reminders: ON", callback_data="toggle_quiz_notif")
            ],
            [
                InlineKeyboardButton(f"{Emoji.TEACHER} Live Classes: ON", callback_data="toggle_live_notif")
            ],
            [
                InlineKeyboardButton(f"{Emoji.CLOCK} Course Expiry: ON", callback_data="toggle_expiry_notif")
            ],
            [
                InlineKeyboardButton(f"{Emoji.BACK} Back to Settings", callback_data="settings")
            ]
        ]
        return InlineKeyboardMarkup(keyboard)

    @staticmethod
    def course_action_menu(course_id):
        """Actions for a specific course"""
        keyboard = [
            [
                InlineKeyboardButton(f"{Emoji.BOOK} View Course Details", url=f"https://pptlinks.com/course/{course_id}")
            ],
            [
                InlineKeyboardButton(f"{Emoji.BELL} Notification Status", callback_data=f"course_notif_{course_id}")
            ],
            [
                InlineKeyboardButton(f"{Emoji.WARNING} Unsubscribe", callback_data=f"unsub_course_{course_id}")
            ],
            [
                InlineKeyboardButton(f"{Emoji.BACK} Back to My Courses", callback_data="mycourses")
            ]
        ]
        return InlineKeyboardMarkup(keyboard)

    @staticmethod
    def confirm_unsubscribe():
        """Confirmation for unsubscribe"""
        keyboard = [
            [
                InlineKeyboardButton(f"{Emoji.CHECK} Yes, Unsubscribe", callback_data="do_unsub"),
                InlineKeyboardButton(f"{Emoji.BACK} Cancel", callback_data="settings")
            ]
        ]
        return InlineKeyboardMarkup(keyboard)

    @staticmethod
    def back_to_menu():
        """Simple back button"""
        keyboard = [[InlineKeyboardButton(f"{Emoji.BACK} Back to Menu", callback_data="main_menu")]]
        return InlineKeyboardMarkup(keyboard)


# ================================
# ENHANCED MESSAGES
# ================================
class Msg:
    @staticmethod
    def welcome_first_time():
        return f"""
{Emoji.WAVE} *Welcome to PPTLinks Notification Bot!*

{Emoji.SPARKLES} Your personal learning assistant is ready!

━━━━━━━━━━━━━━━━━━━━━━━

*What I can do for you:*

{Emoji.BELL} *Real-time Notifications*
  • New content uploads (PPTs, Videos)
  • Live class alerts when they start

{Emoji.FIRE} *Smart Reminders*
  • Quiz starting (1 day before)
  • Quiz deadline (1 day before)
  • Course expiry (1 week before)

{Emoji.CHART} *Progress Tracking*
  • Monitor all your courses
  • Track notification history

━━━━━━━━━━━━━━━━━━━━━━━

{Emoji.ROCKET} *Ready to start?*

Use the buttons below to:
• Subscribe to a course
• View available commands
• Get help

━━━━━━━━━━━━━━━━━━━━━━━
_Powered by PPTLinks_ {Emoji.STAR}
"""

    @staticmethod
    def subscribed(name, course_id):
        return f"""
{Emoji.PARTY} *Subscription Successful!*

━━━━━━━━━━━━━━━━━━━━━━━

{Emoji.BOOK} *Course:* {name}
{Emoji.PIN} *Course ID:* `{course_id}`

━━━━━━━━━━━━━━━━━━━━━━━

{Emoji.CHECK} *You're all set!*

{Emoji.BELL} I'll notify you about:
  • New learning materials
  • Quiz schedules & reminders
  • Important deadlines
  • Course updates

{Emoji.CLOCK} *Auto-check:* Every 10 minutes

━━━━━━━━━━━━━━━━━━━━━━━
{Emoji.LIGHT} _Tip: Use the menu below to manage your courses_
"""

    @staticmethod
    def initial_course_info(course_data):
        """Generate comprehensive initial course notification"""
        name = course_data.get('name', 'Course')
        description = course_data.get('description', 'No description available')
        sections = course_data.get('CourseSection', [])

        # Count resources
        total_videos = 0
        total_files = 0
        total_quizzes = 0
        upcoming_quizzes = []

        for section in sections:
            for content in section.get('contents', []):
                if content['type'] == 'VIDEO':
                    total_videos += 1
                elif content['type'] == 'PPT':
                    total_files += 1
                elif content['type'] == 'QUIZ':
                    total_quizzes += 1
                    quiz = content.get('quiz', {})
                    start_time = quiz.get('startTime')
                    if start_time:
                        try:
                            start_dt = date_parser.parse(start_time)
                            if start_dt > datetime.now(pytz.timezone('Africa/Lagos')):
                                upcoming_quizzes.append({
                                    'name': content['name'],
                                    'start': format_time(start_time),
                                    'end': format_time(quiz.get('endTime', ''))
                                })
                        except:
                            pass

        msg = f"""
{Emoji.PARTY} *Course Successfully Added!*

━━━━━━━━━━━━━━━━━━━━━━━

{Emoji.BOOK} *{name}*

{Emoji.INFO} *Description:*
{description[:200]}{'...' if len(description) > 200 else ''}

━━━━━━━━━━━━━━━━━━━━━━━

{Emoji.CHART} *Course Content Overview:*

{Emoji.VIDEO} *Videos:* {total_videos}
{Emoji.FILE} *Files/PPTs:* {total_files}
{Emoji.QUIZ} *Quizzes:* {total_quizzes}

━━━━━━━━━━━━━━━━━━━━━━━
"""

        if upcoming_quizzes:
            msg += f"\n{Emoji.CALENDAR} *Upcoming Quizzes:*\n\n"
            for idx, quiz in enumerate(upcoming_quizzes[:3], 1):
                msg += f"{idx}. *{quiz['name']}*\n"
                msg += f"   {Emoji.CLOCK} Start: {quiz['start']}\n"
                msg += f"   {Emoji.HOURGLASS} End: {quiz['end']}\n\n"
            if len(upcoming_quizzes) > 3:
                msg += f"   _...and {len(upcoming_quizzes) - 3} more_\n\n"
            msg += "━━━━━━━━━━━━━━━━━━━━━━━\n"

        msg += f"""
{Emoji.BELL} *Notifications Active*

You'll receive alerts for:
  • New content uploads
  • Quiz schedules & reminders
  • Important updates

{Emoji.FIRE} *Ready to start learning!*

━━━━━━━━━━━━━━━━━━━━━━━
{Emoji.LIGHT} _Use the menu below to explore more_
"""
        return msg

    @staticmethod
    def new_file(course, name, url, file_type):
        emoji = Emoji.VIDEO if file_type == "VIDEO" else Emoji.FILE
        return f"""
{Emoji.SPARKLES} *New Content Alert!* {emoji}

━━━━━━━━━━━━━━━━━━━━━━━

{Emoji.BOOK} *Course:* {course}

{emoji} *Material:* {name}

{Emoji.TARGET} Your learning journey continues!

━━━━━━━━━━━━━━━━━━━━━━━
"""

    @staticmethod
    def new_quiz(course, title, start, end):
        return f"""
{Emoji.BRAIN} *New Quiz Available!* {Emoji.QUIZ}

━━━━━━━━━━━━━━━━━━━━━━━

{Emoji.BOOK} *Course:* {course}
{Emoji.QUIZ} *Quiz:* {title}

{Emoji.CALENDAR} *Schedule:*
  {Emoji.CLOCK} *Start:* {start}
  {Emoji.HOURGLASS} *End:* {end}

━━━━━━━━━━━━━━━━━━━━━━━

{Emoji.FIRE} *Prepare yourself and ace it!*

{Emoji.LIGHT} _You'll get a reminder when it starts_
"""

    @staticmethod
    def quiz_start(title):
        return f"""
{Emoji.ROCKET} *Hey! Your Quiz Starts Tomorrow!* {Emoji.FIRE}

━━━━━━━━━━━━━━━━━━━━━━━

{Emoji.QUIZ} *{title}*

{Emoji.CLOCK} *Starting in 1 day!*

{Emoji.TARGET} Get ready to show what you've learned!

{Emoji.BRAIN} Review your materials and prepare now!

━━━━━━━━━━━━━━━━━━━━━━━

{Emoji.WARNING} _Don't miss it - be ready tomorrow!_
"""

    @staticmethod
    def quiz_ending(title):
        return f"""
{Emoji.WARNING} *Quiz Deadline Approaching!* {Emoji.HOURGLASS}

━━━━━━━━━━━━━━━━━━━━━━━

{Emoji.QUIZ} *{title}*

{Emoji.CLOCK} *Ends tomorrow!* Only 1 day left!

{Emoji.FIRE} Complete it before the deadline!

{Emoji.TARGET} Don't miss this opportunity to score!

━━━━━━━━━━━━━━━━━━━━━━━

{Emoji.WARNING} _Finish and submit within 24 hours!_
"""

    @staticmethod
    def live_class_starting(course, title, url):
        return f"""
{Emoji.ROCKET} *LIVE CLASS STARTING NOW!* {Emoji.FIRE}

━━━━━━━━━━━━━━━━━━━━━━━

{Emoji.BOOK} *Course:* {course}
{Emoji.TEACHER} *Class:* {title}

{Emoji.TARGET} *The class is now LIVE!*

{Emoji.BRAIN} Join now and don't miss out!

━━━━━━━━━━━━━━━━━━━━━━━

{Emoji.WARNING} _Click below to join immediately!_
"""

    @staticmethod
    def course_expiring(course, days_left):
        return f"""
{Emoji.WARNING} *Course Expiring Soon!* {Emoji.HOURGLASS}

━━━━━━━━━━━━━━━━━━━━━━━

{Emoji.BOOK} *Course:* {course}

{Emoji.CLOCK} *Time Remaining:* {days_left} days

{Emoji.TARGET} Complete your learning materials before access expires!

{Emoji.BRAIN} Review remaining content now!

━━━━━━━━━━━━━━━━━━━━━━━

{Emoji.WARNING} _Make the most of your remaining time!_
"""

    @staticmethod
    def my_courses(courses_list):
        if not courses_list:
            return f"""
{Emoji.INFO} *No Active Subscriptions*

━━━━━━━━━━━━━━━━━━━━━━━

You haven't subscribed to any courses yet.

{Emoji.ROCKET} *Ready to start?*

Click the button below to add your first course!

━━━━━━━━━━━━━━━━━━━━━━━
"""

        msg = f"""
{Emoji.BOOK} *Your Learning Dashboard* {Emoji.CHART}

━━━━━━━━━━━━━━━━━━━━━━━

*Active Courses ({len(courses_list)}):*

"""
        for idx, (name, cid) in enumerate(courses_list, 1):
            msg += f"{idx}. {Emoji.STAR} *{name}*\n"
            msg += f"   {Emoji.PIN} Course ID: `{cid}`\n"
            msg += f"   {Emoji.BELL} Notifications: Active\n\n"

        msg += f"""━━━━━━━━━━━━━━━━━━━━━━━

{Emoji.BELL} All courses are being monitored
{Emoji.CLOCK} Checked every 10 minutes
{Emoji.TARGET} Stay focused and keep learning!

━━━━━━━━━━━━━━━━━━━━━━━
"""
        return msg

    @staticmethod
    def manage_courses(courses_list):
        if not courses_list:
            return f"""
{Emoji.INFO} *Manage Courses*

━━━━━━━━━━━━━━━━━━━━━━━

You have no active course subscriptions.

{Emoji.ROCKET} Add a course to get started!

━━━━━━━━━━━━━━━━━━━━━━━
"""

        msg = f"""
{Emoji.GEAR} *Manage Your Courses*

━━━━━━━━━━━━━━━━━━━━━━━

Select a course below to:
• View details
• Check notification status
• Unsubscribe

 *Your Courses ({len(courses_list)}):*

"""
        for idx, (name, cid) in enumerate(courses_list, 1):
            msg += f"{idx}. *{name}*\n"

        msg += f"""
━━━━━━━━━━━━━━━━━━━━━━━
"""
        return msg

    @staticmethod
    def stats(total_courses, total_notifs):
        return f"""
{Emoji.CHART} *Your Learning Statistics* {Emoji.TROPHY}

━━━━━━━━━━━━━━━━━━━━━━━

{Emoji.BOOK} *Active Courses:* {total_courses}
{Emoji.BELL} *Notifications Received:* {total_notifs}

━━━━━━━━━━━━━━━━━━━━━━━

{Emoji.FIRE} *Keep up the great work!*

{Emoji.STUDENT} Every notification keeps you on track
{Emoji.TARGET} Stay consistent, achieve greatness

━━━━━━━━━━━━━━━━━━━━━━━
_Updated in real-time_ {Emoji.SPARKLES}
"""

    @staticmethod
    def help_menu():
        return f"""
{Emoji.INFO} *Help & Support* {Emoji.LIGHT}

━━━━━━━━━━━━━━━━━━━━━━━

*📱 Available Commands:*

{Emoji.ROCKET} `/start <course_id>` - Subscribe to a course
{Emoji.BOOK} `/mycourses` - View all your courses
{Emoji.CHART} `/stats` - View learning statistics
{Emoji.GEAR} `/settings` - Manage preferences
{Emoji.WARNING} `/unsubscribe` - Unsubscribe from all courses
{Emoji.INFO} `/help` - Show this menu

━━━━━━━━━━━━━━━━━━━━━━━

*🔔 Notification Types:*

{Emoji.FILE} *New Content* - Instant alerts for new materials
{Emoji.BRAIN} *Quiz Start* - 1 day before quiz begins
{Emoji.HOURGLASS} *Quiz Deadline* - 1 day before quiz ends
{Emoji.TEACHER} *Live Classes* - When class goes live
{Emoji.CLOCK} *Course Expiry* - 1 week before access ends

━━━━━━━━━━━━━━━━━━━━━━━

*⚙️ Features:*

{Emoji.BELL} Real-time notifications (every 10 min check)
{Emoji.CHART} Multi-course support
{Emoji.GEAR} Customizable notification preferences
{Emoji.TARGET} Auto-deactivation on course expiry

━━━━━━━━━━━━━━━━━━━━━━━

{Emoji.TEACHER} *Need Support?*
Contact PPTLinks support team
Visit: https://pptlinks.com/support

━━━━━━━━━━━━━━━━━━━━━━━
_Made with_ {Emoji.STAR} _for PPTLinks students_
"""

    @staticmethod
    def how_it_works():
        return f"""
{Emoji.LIGHT} *How PPTLinks Bot Works* {Emoji.ROCKET}

━━━━━━━━━━━━━━━━━━━━━━━

*Step 1: Subscribe to Courses* {Emoji.BOOK}
Click the subscription link you receive from PPTLinks when you enroll, or use `/start <course_id>` command. You can subscribe to multiple courses!

*Step 2: Automatic Monitoring* {Emoji.CLOCK}
The bot checks your courses every 10 minutes for:
• New content uploads
• Live class status changes
• Quiz schedules
• Course expiry dates

*Step 3: Get Notified* {Emoji.BELL}
Receive instant Telegram notifications when:
• New PPT/Video is uploaded
• Live class starts
• Quiz is starting (1 day before)
• Quiz deadline approaching (1 day before)
• Course expiring soon (1 week before)

*Step 4: Take Action* {Emoji.TARGET}
Click the buttons in notifications to:
• Open course materials
• Join live classes
• Start quizzes
• View course details

━━━━━━━━━━━━━━━━━━━━━━━

{Emoji.FIRE} *Never miss a class or deadline again!*

━━━━━━━━━━━━━━━━━━━━━━━
"""

    @staticmethod
    def add_course_instructions():
        return f"""
{Emoji.ROCKET} *Subscribe to Your Course*

━━━━━━━━━━━━━━━━━━━━━━━

{Emoji.INFO} *How to Subscribe:*

You should receive a unique subscription link from PPTLinks when you enroll in a course.

The link looks like:
`https://t.me/PPTLinksReminderBot?start=COURSE_ID`

{Emoji.TARGET} *Just click that link* and you'll be automatically subscribed!

━━━━━━━━━━━━━━━━━━━━━━━

{Emoji.GEAR} *Alternative Method:*

If you have your Course ID, use this command:
`/start YOUR_COURSE_ID`

*Example:*
`/start 686254fca0502cc2d68f5b89`

━━━━━━━━━━━━━━━━━━━━━━━

{Emoji.LIGHT} *Can't find your link?*
Contact PPTLinks support or check your course enrollment page.

━━━━━━━━━━━━━━━━━━━━━━━
"""

    @staticmethod
    def settings():
        return f"""
{Emoji.GEAR} *Settings & Preferences*

━━━━━━━━━━━━━━━━━━━━━━━

{Emoji.BELL} *Notifications:* Active
{Emoji.CLOCK} *Check Interval:* 10 minutes
{Emoji.TARGET} *Auto-monitoring:* Enabled

━━━━━━━━━━━━━━━━━━━━━━━

Use the buttons below to manage your settings.
"""

    @staticmethod
    def unsubscribe_confirm():
        return f"""
{Emoji.WARNING} *Confirm Unsubscribe*

━━━━━━━━━━━━━━━━━━━━━━━

Are you sure you want to unsubscribe from all courses?

{Emoji.INFO} You will stop receiving:
  • Course updates
  • Quiz reminders
  • Content notifications

You can resubscribe anytime using /start

━━━━━━━━━━━━━━━━━━━━━━━
"""

    @staticmethod
    def unsubscribed():
        return f"""
{Emoji.CHECK} *Unsubscribed Successfully*

━━━━━━━━━━━━━━━━━━━━━━━

You've been removed from all course notifications.

{Emoji.WAVE} We'll miss you!

{Emoji.ROCKET} Want to come back?
Use /start anytime to resubscribe.

━━━━━━━━━━━━━━━━━━━━━━━
"""

    @staticmethod
    def already_subscribed():
        return f"""
{Emoji.CHECK} *Already Subscribed!*

━━━━━━━━━━━━━━━━━━━━━━━

You're already receiving updates for this course.

{Emoji.CHART} Check /mycourses to see all subscriptions
{Emoji.GEAR} Use /settings to manage preferences

━━━━━━━━━━━━━━━━━━━━━━━
"""

    @staticmethod
    def api_error():
        return f"""
{Emoji.WARNING} *Connection Error*

━━━━━━━━━━━━━━━━━━━━━━━

Unable to fetch course data right now.

{Emoji.CLOCK} Please try again in a few moments.

{Emoji.INFO} If the issue persists, contact support.

━━━━━━━━━━━━━━━━━━━━━━━
"""


# ================================
# MONITOR
# ================================
class Monitor:
    def __init__(self, app):
        self.app = app

    async def check(self, chat_id: int, course_id: str = None):
        """Check for course updates and send notifications"""
        if not course_id:
            course_id = FIXED_COURSE_ID

        data = PPTLinksAPI.fetch_course_data(course_id)
        if not data:
            logger.warning(f"Failed to fetch course data for user {chat_id}, course {course_id}")
            return

        new_hash = PPTLinksAPI.get_hash(data)
        cached = db.get_course_data(course_id)
        old_hash = cached['hash'] if cached else None
        name = data.get('name', 'Course')

        if not old_hash:
            logger.info(f"✨ First time subscription for user {chat_id}, course {course_id}")
            db.save_course_data(course_id, name, data, new_hash)
            await self.send_message(chat_id, Msg.initial_course_info(data), Keyboards.main_menu())
            db.log_notification(chat_id, course_id, "initial_course", f"Initial course info for {name}")
            await self.schedule(data, chat_id, course_id)
            logger.info(f"📧 Sent initial course notification to user {chat_id}")
            return

        if new_hash != old_hash:
            logger.info(f"🔄 CONTENT CHANGED for course {course_id} (old: {old_hash[:8]}..., new: {new_hash[:8]}...)")
            logger.info(f"📢 Sending update notifications to user {chat_id}")
            old = cached['data']
            await self.notify_files(chat_id, name, old, data, course_id)
            await self.notify_quizzes(chat_id, name, old, data, course_id)
            await self.notify_live_classes(chat_id, name, old, data, course_id)
            db.save_course_data(course_id, name, data, new_hash)
            await self.schedule(data, chat_id, course_id)
            logger.info(f"✅ Course data updated and notifications sent to user {chat_id}")
        else:
            logger.debug(f"✓ No changes detected for course {course_id} (hash: {new_hash[:8]}...) - user {chat_id}")

    async def send_message(self, chat_id, text, keyboard=None):
        """Send message to user"""
        try:
            message = await self.app.bot.send_message(
                chat_id,
                text,
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=keyboard
            )
            logger.info(f"✅ Notification delivered to {chat_id} (message_id: {message.message_id})")
            return True
        except Exception as e:
            logger.error(f"❌ Failed to send notification to {chat_id}: {e}")
            return False

    async def notify_files(self, chat_id, course, old, new, course_id):
        """Notify about new files/videos"""
        old_ids = {i['id'] for s in old.get('CourseSection', []) for i in s.get('contents', []) if i['type'] in ['PPT', 'VIDEO']}

        new_files_count = 0
        for s in new.get('CourseSection', []):
            for i in s.get('contents', []):
                if i['type'] in ['PPT', 'VIDEO'] and i['id'] not in old_ids:
                    new_files_count += 1
                    # Always link to the content within the course on PPTLinks
                    content_url = f"https://pptlinks.com/course/{course_id}/content/{i['id']}"

                    logger.info(f"🔔 NEW CONTENT DETECTED: {i['type']} '{i['name']}' in course {course_id}")
                    text = Msg.new_file(course, i['name'], content_url, i['type'])
                    keyboard = InlineKeyboardMarkup([
                        [InlineKeyboardButton(f"{Emoji.ROCKET} Open in PPTLinks", url=content_url)],
                        [InlineKeyboardButton(f"{Emoji.BOOK} View Course", url=f"https://pptlinks.com/course/{course_id}")],
                        [InlineKeyboardButton(f"{Emoji.CHART} My Courses", callback_data="mycourses")]
                    ])
                    success = await self.send_message(chat_id, text, keyboard)
                    if success:
                        db.log_notification(chat_id, course_id, "new_file", f"New {i['type']}: {i['name']}")
                        logger.info(f"📄 New {i['type']} notification delivered to {chat_id}: {i['name']}")

        if new_files_count == 0:
            logger.debug(f"No new files detected for course {course_id}")

    async def notify_quizzes(self, chat_id, course, old, new, course_id):
        """Notify about new quizzes"""
        old_ids = {i['id'] for s in old.get('CourseSection', []) for i in s.get('contents', []) if i['type'] == 'QUIZ'}

        for s in new.get('CourseSection', []):
            for i in s.get('contents', []):
                if i['type'] == 'QUIZ' and i['id'] not in old_ids:
                    q = i['quiz']
                    start = format_time(q.get('startTime'))
                    end = format_time(q.get('endTime'))
                    # Link to quiz within course context
                    quiz_url = f"https://pptlinks.com/course/{course_id}/content/{i['id']}"

                    logger.info(f"🔔 NEW QUIZ DETECTED: '{i['name']}' in course {course_id}")
                    text = Msg.new_quiz(course, i['name'], start, end)
                    keyboard = InlineKeyboardMarkup([
                        [InlineKeyboardButton(f"{Emoji.BRAIN} View Quiz in PPTLinks", url=quiz_url)],
                        [InlineKeyboardButton(f"{Emoji.BOOK} View Course", url=f"https://pptlinks.com/course/{course_id}")],
                        [InlineKeyboardButton(f"{Emoji.CHART} My Courses", callback_data="mycourses")]
                    ])
                    success = await self.send_message(chat_id, text, keyboard)
                    if success:
                        db.log_notification(chat_id, course_id, "new_quiz", f"New quiz: {i['name']}")
                        logger.info(f"📝 New quiz notification delivered to {chat_id}: {i['name']}")

    async def notify_live_classes(self, chat_id, course, old, new, course_id):
        """Notify about live classes that just started"""
        # Build map of old presentation statuses
        old_statuses = {}
        for s in old.get('CourseSection', []):
            for i in s.get('contents', []):
                if i['type'] in ['PPT', 'VIDEO']:
                    old_statuses[i['id']] = i.get('presentationStatus', 'NOT_LIVE')

        # Check for newly live presentations
        live_classes_count = 0
        for s in new.get('CourseSection', []):
            for i in s.get('contents', []):
                if i['type'] in ['PPT', 'VIDEO']:
                    current_status = i.get('presentationStatus', 'NOT_LIVE')
                    old_status = old_statuses.get(i['id'], 'NOT_LIVE')

                    # If status changed to LIVE, notify
                    if current_status == 'LIVE' and old_status != 'LIVE':
                        live_classes_count += 1
                        logger.info(f"🔴 LIVE CLASS STARTED: '{i['name']}' in course {course_id}")
                        live_url = f"https://pptlinks.com/course/{course_id}/content/{i['id']}"
                        text = Msg.live_class_starting(course, i['name'], live_url)
                        keyboard = InlineKeyboardMarkup([
                            [InlineKeyboardButton(f"{Emoji.ROCKET} Join Live Class on PPTLinks!", url=live_url)],
                            [InlineKeyboardButton(f"{Emoji.BOOK} View Course", url=f"https://pptlinks.com/course/{course_id}")],
                            [InlineKeyboardButton(f"{Emoji.CHART} My Courses", callback_data="mycourses")]
                        ])
                        success = await self.send_message(chat_id, text, keyboard)
                        if success:
                            db.log_notification(chat_id, course_id, "live_class_started", f"Live class started: {i['name']}")
                            logger.info(f"🎥 Live class notification delivered to {chat_id}: {i['name']}")

        if live_classes_count == 0:
            logger.debug(f"No live classes detected for course {course_id}")

    async def schedule(self, data, chat_id, course_id):
        """Schedule quiz reminders and course expiry"""
        now = datetime.now(pytz.timezone('Africa/Lagos'))
        for s in data.get('CourseSection', []):
            for i in s.get('contents', []):
                if i['type'] == 'QUIZ':
                    await self.schedule_quiz(i, chat_id, now, course_id)

        # Schedule course expiry notification
        await self.schedule_course_expiry(data, chat_id, now, course_id)

    async def schedule_quiz(self, item, chat_id, now, course_id):
        """Schedule start and end reminders for a quiz"""
        q = item['quiz']
        start_str = q.get('startTime')
        end_str = q.get('endTime')
        qid = item['id']
        title = item['name']

        if start_str:
            try:
                start = date_parser.parse(start_str)
                if start.tzinfo is None:
                    start = pytz.timezone('Africa/Lagos').localize(start)
                # Schedule notification 1 day before start time
                notify_time = start - timedelta(days=1)
                if notify_time > now:
                    # Quiz URL within course context
                    quiz_url = f"https://pptlinks.com/course/{course_id}/content/{qid}"
                    scheduler.add_job(
                        self.send_quiz_start, DateTrigger(notify_time),
                        args=[chat_id, title, quiz_url, course_id],
                        id=f"start_{qid}_{chat_id}", replace_existing=True
                    )
                    logger.info(f"Scheduled quiz notification: {title} at {notify_time} (1 day before {start}) for user {chat_id}")
            except Exception as e:
                logger.error(f"Error scheduling quiz start: {e}")

        if end_str:
            try:
                end = date_parser.parse(end_str)
                if end.tzinfo is None:
                    end = pytz.timezone('Africa/Lagos').localize(end)
                remind = end - timedelta(days=1)
                if remind > now:
                    # Quiz URL within course context
                    quiz_url = f"https://pptlinks.com/course/{course_id}/content/{qid}"
                    scheduler.add_job(
                        self.send_quiz_end, DateTrigger(remind),
                        args=[chat_id, title, quiz_url, course_id],
                        id=f"end_{qid}_{chat_id}", replace_existing=True
                    )
                    logger.info(f"Scheduled quiz end reminder: {title} at {remind} (1 day before {end}) for user {chat_id}")
            except Exception as e:
                logger.error(f"Error scheduling quiz end: {e}")

    async def send_quiz_start(self, chat_id, title, url, course_id):
        """Send quiz start notification"""
        logger.info(f"📝 QUIZ STARTING SOON (1 day): '{title}' for user {chat_id}")
        text = Msg.quiz_start(title)
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton(f"{Emoji.ROCKET} Open Quiz in PPTLinks", url=url)],
            [InlineKeyboardButton(f"{Emoji.BOOK} View Course", url=f"https://pptlinks.com/course/{course_id}")],
            [InlineKeyboardButton(f"{Emoji.CHART} My Courses", callback_data="mycourses")]
        ])
        success = await self.send_message(chat_id, text, keyboard)
        if success:
            db.log_notification(chat_id, course_id, "quiz_start_reminder", f"Quiz starting in 1 day: {title}")
            logger.info(f"✅ Quiz start reminder delivered to {chat_id}: {title}")

    async def send_quiz_end(self, chat_id, title, url, course_id):
        """Send quiz ending soon notification"""
        logger.info(f"⏰ QUIZ ENDING SOON (1 day): '{title}' for user {chat_id}")
        text = Msg.quiz_ending(title)
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton(f"{Emoji.FIRE} Complete Quiz in PPTLinks", url=url)],
            [InlineKeyboardButton(f"{Emoji.BOOK} View Course", url=f"https://pptlinks.com/course/{course_id}")],
            [InlineKeyboardButton(f"{Emoji.CHART} My Courses", callback_data="mycourses")]
        ])
        success = await self.send_message(chat_id, text, keyboard)
        if success:
            db.log_notification(chat_id, course_id, "quiz_ending_reminder", f"Quiz ending in 1 day: {title}")
            logger.info(f"✅ Quiz deadline reminder delivered to {chat_id}: {title}")

    async def schedule_course_expiry(self, data, chat_id, now, course_id):
        """Schedule course expiry notification (1 week before)"""
        try:
            # Get subscription date and course duration
            subscription_date = db.get_subscription_date(chat_id, course_id)
            if not subscription_date:
                logger.warning(f"No subscription date found for user {chat_id}, course {course_id}")
                return

            # Parse duration from course data
            duration = data.get('duration', '').upper()
            duration_map = {
                'ONE_MONTH': 30,
                'TWO_MONTHS': 60,
                'THREE_MONTHS': 90,
                'SIX_MONTHS': 180,
                'ONE_YEAR': 365,
            }
            days = duration_map.get(duration)
            if not days:
                logger.warning(f"Unknown duration format: {duration}")
                return

            # Calculate expiry date and notification date (1 week before)
            sub_dt = date_parser.parse(subscription_date)
            if sub_dt.tzinfo is None:
                sub_dt = pytz.timezone('Africa/Lagos').localize(sub_dt)

            expiry_date = sub_dt + timedelta(days=days)
            notify_date = expiry_date - timedelta(days=7)

            if notify_date > now:
                scheduler.add_job(
                    self.send_course_expiry, DateTrigger(notify_date),
                    args=[chat_id, data.get('name', 'Course'), 7, course_id],
                    id=f"expiry_{course_id}_{chat_id}", replace_existing=True
                )
                logger.info(f"Scheduled course expiry notification for {chat_id} at {notify_date} (expiry: {expiry_date})")

            # Schedule auto-deactivation at expiry
            if expiry_date > now:
                scheduler.add_job(
                    self.deactivate_course, DateTrigger(expiry_date),
                    args=[chat_id, course_id],
                    id=f"deactivate_{course_id}_{chat_id}", replace_existing=True
                )
                logger.info(f"Scheduled auto-deactivation for {chat_id} at {expiry_date}")

        except Exception as e:
            logger.error(f"Error scheduling course expiry: {e}")

    async def send_course_expiry(self, chat_id, course_name, days_left, course_id):
        """Send course expiry warning notification"""
        logger.info(f"⚠️ COURSE EXPIRING (7 days): '{course_name}' for user {chat_id}")
        text = Msg.course_expiring(course_name, days_left)
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton(f"{Emoji.BOOK} Open Course in PPTLinks", url=f"https://pptlinks.com/course/{course_id}")],
            [InlineKeyboardButton(f"{Emoji.CHART} My Courses", callback_data="mycourses")],
            [InlineKeyboardButton(f"{Emoji.FIRE} Main Menu", callback_data="main_menu")]
        ])
        success = await self.send_message(chat_id, text, keyboard)
        if success:
            db.log_notification(chat_id, course_id, "course_expiry_warning", f"Course expiring in {days_left} days")
            logger.info(f"✅ Course expiry warning delivered to {chat_id}: {course_name}")

    async def deactivate_course(self, chat_id, course_id):
        """Deactivate course subscription after expiry"""
        try:
            db.unsubscribe_user_from_course(chat_id, course_id)
            # Remove monitoring job
            try:
                scheduler.remove_job(f"poll_{chat_id}_{course_id}")
                logger.info(f"Removed monitoring job for expired course: {chat_id}_{course_id}")
            except Exception as e:
                logger.warning(f"Could not remove monitoring job: {e}")
            logger.info(f"Auto-deactivated expired course for user {chat_id}: {course_id}")

            # Notify user
            text = f"""
{Emoji.INFO} *Course Access Expired*

━━━━━━━━━━━━━━━━━━━━━━━

Your access to this course has ended.

{Emoji.ROCKET} Want to continue learning?
Contact support to renew your access.

━━━━━━━━━━━━━━━━━━━━━━━
"""
            await self.send_message(chat_id, text)
        except Exception as e:
            logger.error(f"Error deactivating course: {e}")


def format_time(dt):
    """Format datetime string to readable format"""
    try:
        return date_parser.parse(dt).strftime("%b %d, %Y • %I:%M %p")
    except:
        return dt


# ================================
# CALLBACK HANDLERS
# ================================
async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle inline keyboard button callbacks"""
    query = update.callback_query
    await query.answer()

    chat_id = query.message.chat_id
    data = query.data

    if data == "main_menu":
        await query.edit_message_text(
            Msg.welcome_first_time(),
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=Keyboards.main_menu()
        )

    elif data == "add_course":
        await query.edit_message_text(
            Msg.add_course_instructions(),
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=Keyboards.back_to_menu()
        )

    elif data == "how_it_works":
        await query.edit_message_text(
            Msg.how_it_works(),
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=Keyboards.back_to_menu()
        )

    elif data == "notification_settings":
        await query.edit_message_text(
            f"""
{Emoji.BELL} *Notification Settings*

━━━━━━━━━━━━━━━━━━━━━━━

Customize which notifications you want to receive.

{Emoji.INFO} Toggle each notification type below:

━━━━━━━━━━━━━━━━━━━━━━━

{Emoji.LIGHT} _Note: Notification preferences coming soon!_
All notifications are currently enabled.

━━━━━━━━━━━━━━━━━━━━━━━
""",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=Keyboards.notification_settings_menu()
        )

    elif data == "manage_courses":
        courses = db.get_user_courses(chat_id)
        courses_list = [(d['data'].get('name', 'Unknown') if (d := db.get_course_data(cid)) else 'Unknown', cid) for cid in courses]

        # Create inline keyboard with course buttons
        keyboard = []
        for name, cid in courses_list:
            keyboard.append([InlineKeyboardButton(f"{Emoji.BOOK} {name}", callback_data=f"course_detail_{cid}")])

        keyboard.append([InlineKeyboardButton(f"{Emoji.ROCKET} Add New Course", callback_data="add_course")])
        keyboard.append([InlineKeyboardButton(f"{Emoji.BACK} Back to Settings", callback_data="settings")])

        await query.edit_message_text(
            Msg.manage_courses(courses_list),
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    elif data.startswith("course_detail_"):
        course_id = data.replace("course_detail_", "")
        course_data = db.get_course_data(course_id)
        course_name = course_data['data'].get('name', 'Unknown Course') if course_data else 'Unknown Course'

        await query.edit_message_text(
            f"""
{Emoji.BOOK} *Course Details*

━━━━━━━━━━━━━━━━━━━━━━━

*Course Name:* {course_name}
*Course ID:* `{course_id}`

{Emoji.BELL} *Status:* Active
{Emoji.CLOCK} *Monitoring:* Enabled

━━━━━━━━━━━━━━━━━━━━━━━

Choose an action below:

━━━━━━━━━━━━━━━━━━━━━━━
""",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=Keyboards.course_action_menu(course_id)
        )

    elif data.startswith("unsub_course_"):
        course_id = data.replace("unsub_course_", "")
        course_data = db.get_course_data(course_id)
        course_name = course_data['data'].get('name', 'Unknown Course') if course_data else 'Unknown Course'

        keyboard = [
            [
                InlineKeyboardButton(f"{Emoji.CHECK} Yes, Unsubscribe", callback_data=f"confirm_unsub_{course_id}"),
                InlineKeyboardButton(f"{Emoji.BACK} Cancel", callback_data=f"course_detail_{course_id}")
            ]
        ]

        await query.edit_message_text(
            f"""
{Emoji.WARNING} *Confirm Unsubscribe*

━━━━━━━━━━━━━━━━━━━━━━━

Are you sure you want to unsubscribe from:

*{course_name}*

{Emoji.INFO} You will stop receiving all notifications for this course.

You can resubscribe anytime using:
`/start {course_id}`

━━━━━━━━━━━━━━━━━━━━━━━
""",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    elif data.startswith("confirm_unsub_") and not data == "confirm_unsub":
        course_id = data.replace("confirm_unsub_", "")

        # Remove monitoring job
        try:
            scheduler.remove_job(f"poll_{chat_id}_{course_id}")
            logger.info(f"Removed monitoring job for user {chat_id}, course {course_id}")
        except Exception as e:
            logger.warning(f"Could not remove job: {e}")

        # Unsubscribe from course
        db.unsubscribe_user_from_course(chat_id, course_id)

        await query.edit_message_text(
            f"""
{Emoji.CHECK} *Unsubscribed Successfully*

━━━━━━━━━━━━━━━━━━━━━━━

You've been unsubscribed from this course.

{Emoji.INFO} You won't receive any more notifications for this course.

{Emoji.ROCKET} Want to manage other courses?

━━━━━━━━━━━━━━━━━━━━━━━
""",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=Keyboards.main_menu()
        )

    elif data == "mycourses":
        courses = db.get_user_courses(chat_id)
        courses_list = [(d['data'].get('name', 'Unknown') if (d := db.get_course_data(cid)) else 'Unknown', cid) for cid in courses]

        # Create keyboard with add course button if no courses
        if not courses_list:
            keyboard = [
                [InlineKeyboardButton(f"{Emoji.ROCKET} Add Your First Course", callback_data="add_course")],
                [InlineKeyboardButton(f"{Emoji.BACK} Back to Menu", callback_data="main_menu")]
            ]
        else:
            keyboard = [
                [InlineKeyboardButton(f"{Emoji.ROCKET} Add Another Course", callback_data="add_course")],
                [InlineKeyboardButton(f"{Emoji.GEAR} Manage Courses", callback_data="manage_courses")],
                [InlineKeyboardButton(f"{Emoji.BACK} Back to Menu", callback_data="main_menu")]
            ]

        await query.edit_message_text(
            Msg.my_courses(courses_list),
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    elif data == "stats":
        s = db.get_user_stats(chat_id)
        await query.edit_message_text(
            Msg.stats(s['total_courses'], s['total_notifications']),
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=Keyboards.back_to_menu()
        )

    elif data == "help":
        await query.edit_message_text(
            Msg.help_menu(),
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=Keyboards.back_to_menu()
        )

    elif data == "settings":
        await query.edit_message_text(
            Msg.settings(),
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=Keyboards.settings_menu()
        )

    elif data == "confirm_unsub":
        await query.edit_message_text(
            Msg.unsubscribe_confirm(),
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=Keyboards.confirm_unsubscribe()
        )

    elif data == "do_unsub":
        # Get all user courses and remove their monitoring jobs
        courses = db.get_user_courses(chat_id)
        for course_id in courses:
            try:
                scheduler.remove_job(f"poll_{chat_id}_{course_id}")
            except Exception as e:
                logger.warning(f"Could not remove job poll_{chat_id}_{course_id}: {e}")

        db.unsubscribe_user_from_course(chat_id)
        await query.edit_message_text(
            Msg.unsubscribed(),
            parse_mode=ParseMode.MARKDOWN
        )

    elif data == "notif_status":
        await query.answer(f"{Emoji.BELL} Notifications are active!", show_alert=True)

    elif data == "toggle_content_notif":
        await query.answer(f"{Emoji.INFO} Content notifications are always ON", show_alert=True)

    elif data == "toggle_quiz_notif":
        await query.answer(f"{Emoji.INFO} Quiz reminders are always ON", show_alert=True)

    elif data == "toggle_live_notif":
        await query.answer(f"{Emoji.INFO} Live class alerts are always ON", show_alert=True)

    elif data == "toggle_expiry_notif":
        await query.answer(f"{Emoji.INFO} Expiry warnings are always ON", show_alert=True)

    elif data.startswith("course_notif_"):
        course_id = data.replace("course_notif_", "")
        await query.answer(f"{Emoji.BELL} Notifications are active for this course!", show_alert=True)

    elif data.startswith("remind_"):
        await query.answer(f"{Emoji.CHECK} You'll be reminded when the quiz starts!", show_alert=True)

    elif data == "snooze_quiz":
        await query.answer(f"{Emoji.CLOCK} Reminder snoozed for 30 minutes", show_alert=True)

    elif data == "quiz_now":
        await query.answer(f"{Emoji.FIRE} Good luck on your quiz!", show_alert=True)


# ================================
# COMMANDS
# ================================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command - subscribe user to course

    Usage: /start <course_id>
    Course ID MUST be provided via deep link from PPTLinks
    """
    chat_id = update.effective_chat.id
    user = update.effective_user
    db.add_user(chat_id, user.username, user.first_name, user.last_name)

    # Check if this is first time user (no courses)
    existing_courses = db.get_user_courses(chat_id)
    is_first_time = len(existing_courses) == 0

    # Course ID MUST be provided from deep link
    if not context.args or len(context.args) == 0:
        # No course ID provided - show instructions
        if is_first_time:
            await update.message.reply_text(
                Msg.welcome_first_time(),
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=Keyboards.welcome_menu()
            )
        else:
            # User has courses, show them instructions to add more
            await update.message.reply_text(
                Msg.add_course_instructions(),
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=Keyboards.main_menu()
            )
        return

    # Get course ID from URL parameter
    course_id = context.args[0]
    logger.info(f"User {chat_id} subscribing to course: {course_id}")

    # Send loading message
    loading_msg = await update.message.reply_text(
        f"{Emoji.HOURGLASS} *Subscribing to course...*\n\nPlease wait while I fetch the course details.",
        parse_mode=ParseMode.MARKDOWN
    )

    if db.subscribe_user_to_course(chat_id, course_id):
        logger.info(f"User {chat_id} attempting to subscribe to course {course_id}")
        data = PPTLinksAPI.fetch_course_data(course_id)
        if data:
            monitor = Monitor(context.application)
            await monitor.check(chat_id, course_id)
            scheduler.add_job(
                monitor.check, 'interval', seconds=POLL_INTERVAL,
                args=[chat_id, course_id], id=f"poll_{chat_id}_{course_id}", replace_existing=True
            )
            logger.info(f"User {chat_id} subscribed successfully to {course_id} - monitoring started")

            # Delete loading message
            await loading_msg.delete()
        else:
            await loading_msg.edit_text(
                Msg.api_error(),
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=Keyboards.main_menu()
            )
    else:
        await loading_msg.edit_text(
            Msg.already_subscribed(),
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=Keyboards.main_menu()
        )


async def mycourses(update: Update, context):
    """Handle /mycourses command"""
    chat_id = update.effective_chat.id
    courses = db.get_user_courses(chat_id)
    courses_list = [(d['data'].get('name', 'Unknown') if (d := db.get_course_data(cid)) else 'Unknown', cid) for cid in courses]

    # Create keyboard with add course button if no courses
    if not courses_list:
        keyboard = [
            [InlineKeyboardButton(f"{Emoji.ROCKET} Add Your First Course", callback_data="add_course")],
            [InlineKeyboardButton(f"{Emoji.BACK} Back to Menu", callback_data="main_menu")]
        ]
    else:
        keyboard = [
            [InlineKeyboardButton(f"{Emoji.ROCKET} Add Another Course", callback_data="add_course")],
            [InlineKeyboardButton(f"{Emoji.GEAR} Manage Courses", callback_data="manage_courses")],
            [InlineKeyboardButton(f"{Emoji.BACK} Back to Menu", callback_data="main_menu")]
        ]

    await update.message.reply_text(
        Msg.my_courses(courses_list),
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def unsubscribe(update: Update, context):
    """Handle /unsubscribe command - unsubscribes from all courses"""
    chat_id = update.effective_chat.id

    # Get all user courses and remove their monitoring jobs
    courses = db.get_user_courses(chat_id)
    for course_id in courses:
        try:
            scheduler.remove_job(f"poll_{chat_id}_{course_id}")
            logger.info(f"Removed monitoring job for user {chat_id}, course {course_id}")
        except Exception as e:
            logger.warning(f"Could not remove job poll_{chat_id}_{course_id}: {e}")

    db.unsubscribe_user_from_course(chat_id)
    await update.message.reply_text(Msg.unsubscribed(), parse_mode=ParseMode.MARKDOWN)
    logger.info(f"User {chat_id} unsubscribed from all courses")


async def stats_cmd(update: Update, context):
    """Handle /stats command"""
    s = db.get_user_stats(update.effective_chat.id)
    await update.message.reply_text(
        Msg.stats(s['total_courses'], s['total_notifications']),
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=Keyboards.main_menu()
    )


async def help_cmd(update: Update, context):
    """Handle /help command"""
    await update.message.reply_text(
        Msg.help_menu(),
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=Keyboards.main_menu()
    )


async def settings_cmd(update: Update, context):
    """Handle /settings command"""
    await update.message.reply_text(
        Msg.settings(),
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=Keyboards.settings_menu()
    )


# ================================
# POST INIT - CRITICAL FIX
# ================================
async def post_init(application):
    """Initialize scheduler after event loop starts"""
    scheduler.start()
    logger.info(f"{Emoji.CHECK} Scheduler started")

    # Restore monitoring for existing users with their courses
    monitor = Monitor(application)
    subscriptions = db.get_all_active_subscriptions()
    restored = 0
    for chat_id, course_id in subscriptions:
        # Restore interval polling job
        scheduler.add_job(
            monitor.check, 'interval', seconds=POLL_INTERVAL,
            args=[chat_id, course_id], id=f"poll_{chat_id}_{course_id}", replace_existing=True
        )

        # Restore scheduled reminders by fetching course data and rescheduling
        try:
            course_data_obj = db.get_course_data(course_id)
            if course_data_obj and course_data_obj.get('data'):
                await monitor.schedule(course_data_obj['data'], chat_id, course_id)
                logger.info(f"Restored reminders for user {chat_id}, course {course_id}")
        except Exception as e:
            logger.error(f"Error restoring reminders for {chat_id}/{course_id}: {e}")

        restored += 1
        logger.info(f"Restored monitoring for user {chat_id}, course {course_id}")

    if restored > 0:
        logger.info(f"{Emoji.CHECK} Restored monitoring for {restored} user-course subscriptions")


# ================================
# MAIN
# ================================
def main():
    """Main function to start the bot"""
    if not BOT_TOKEN:
        logger.error("NO BOT TOKEN")
        return

    logger.info("=" * 50)
    logger.info(f"{Emoji.ROCKET} PPTLinks Notification Bot Starting...")
    logger.info(f"{Emoji.BOOK} Default Course ID: {FIXED_COURSE_ID}")
    logger.info(f"{Emoji.INFO} Supports multiple courses per user")
    logger.info(f"{Emoji.CLOCK} Check Interval: {POLL_INTERVAL}s")
    logger.info("=" * 50)

    request = HTTPXRequest(connect_timeout=30, read_timeout=30)
    app = Application.builder().token(BOT_TOKEN).request(request).post_init(post_init).build()

    # Add command handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("mycourses", mycourses))
    app.add_handler(CommandHandler("unsubscribe", unsubscribe))
    app.add_handler(CommandHandler("stats", stats_cmd))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("settings", settings_cmd))

    # Add callback handler
    app.add_handler(CallbackQueryHandler(handle_callback))

    logger.info(f"{Emoji.FIRE} Bot is now live and ready!")
    logger.info("=" * 50)

    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logger.info(f"\n{Emoji.WAVE} Bot stopped by user")
    except Exception as e:
        logger.exception(f"{Emoji.WARNING} Unhandled exception: {e}")