import os
import json
import hashlib
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
)
from telegram.constants import ParseMode
from telegram.request import HTTPXRequest
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.date import DateTrigger
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from dotenv import load_dotenv
from dateutil import parser as date_parser
import pytz
from database import Database

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[
        logging.FileHandler('bot.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
API_BASE = os.getenv("API_BASE", "https://api.pptlinks.com/api/v1")
POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", "600"))  # Default: 10 minutes

# Fixed course ID and full API URL for this specific course
FIXED_COURSE_ID = "686254fca0502cc2d68f5b89"
FIXED_API_URL = f"{API_BASE}/course/user-courses/{FIXED_COURSE_ID}?brief=false&timeZone=Africa/Lagos"

# Initialize database
db = Database()

# Initialize scheduler globally
scheduler = AsyncIOScheduler()


class PPTLinksAPI:
    """Handler for PPTLinks API interactions"""
    
    @staticmethod
    def fetch_course_data(course_id: str = None) -> Optional[dict]:
        """Fetch course data from the fixed PPTLinks API endpoint with retries"""
        # Use fixed URL
        url = FIXED_API_URL
        logger.info(f"Fetching course data from API: {url}")
        
        session = requests.Session()
        retries = Retry(total=3, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504])
        session.mount('http://', HTTPAdapter(max_retries=retries))
        session.mount('https://', HTTPAdapter(max_retries=retries))
        
        try:
            response = session.get(url, timeout=30)
            logger.info(f"API response status: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                logger.info(f"Successfully fetched course data: {data.get('name', 'Unknown')}")
                return data
            else:
                logger.error(f"API returned status {response.status_code}: {response.text}")
                return None
        except requests.exceptions.RequestException as e:
            logger.error(f"Request exception fetching course {FIXED_COURSE_ID}: {e}")
            return None

    @staticmethod
    def get_data_hash(data: dict) -> str:
        """Generate hash of course data for comparison"""
        return hashlib.md5(
            json.dumps(data, sort_keys=True).encode()
        ).hexdigest()


class MessageFormatter:
    """Format messages for Telegram"""
    
    @staticmethod
    def welcome_message(course_name: str) -> str:
        return f"""🎓 *Welcome to PPTLinks Notifications!*

You're now subscribed to updates for *{course_name}*.

You'll receive reminders for:
📚 New uploads and content updates
🧩 Quiz start and end
⏳ Course expiry notices

Stay updated and never miss important events! 🚀"""

    @staticmethod
    def new_file_message(course_name: str, file_name: str, file_url: str) -> tuple:
        text = f"""📂 *New Content Added!*

A new file has been uploaded to *{course_name}*.

📄 File: `{file_name}`"""
        keyboard = [[InlineKeyboardButton("🔗 View File", url=file_url)]]
        return text, InlineKeyboardMarkup(keyboard)

    @staticmethod
    def quiz_created_message(course_name: str, quiz_title: str, start_time: str, end_time: str, quiz_url: str) -> tuple:
        text = f"""🧩 *New Quiz Available!*

Course: *{course_name}*
Title: *{quiz_title}*

⏰ Starts: `{start_time}`
⏰ Ends: `{end_time}`

Prepare yourself!"""
        keyboard = [[InlineKeyboardButton("📝 View Quiz", url=quiz_url)]]
        return text, InlineKeyboardMarkup(keyboard)

    @staticmethod
    def quiz_start_reminder(quiz_title: str, quiz_url: str) -> tuple:
        text = f"""🚀 *Your quiz has just started!*

Quiz: *{quiz_title}*

Don't miss out — tap below to begin! 👇"""
        keyboard = [[InlineKeyboardButton("📝 Open Quiz", url=quiz_url)]]
        return text, InlineKeyboardMarkup(keyboard)

    @staticmethod
    def quiz_ending_soon(quiz_title: str, time_left: str) -> str:
        return f"""⚠️ *Quiz ending soon!*

Only *{time_left}* left to complete *{quiz_title}*!

Hurry up! ⏰"""

    @staticmethod
    def course_expiry_warning(course_name: str, expiry_date: str) -> str:
        return f"""⏳ *Course Expiring Soon!*

Your course *{course_name}* will expire on `{expiry_date}`.

Make sure to complete all pending activities! 📚"""


class CourseMonitor:
    """Monitor courses for updates"""
    
    def __init__(self, app: Application):
        self.app = app
        self.api = PPTLinksAPI()
        self.formatter = MessageFormatter()

    async def check_course_updates(self, chat_id: int, course_id: str):
        """Check for updates in a specific course"""
        logger.info(f"Checking updates for course {course_id} for chat {chat_id}")
        try:
            new_data = self.api.fetch_course_data(course_id)
            if not new_data:
                logger.warning(f"No data fetched for course {course_id}")
                return

            new_hash = self.api.get_data_hash(new_data)
            cached = db.get_course_data(course_id)
            old_hash = cached['hash'] if cached else None
            course_name = new_data.get("name", "Unknown Course")
            logger.info(f"Course name: {course_name}, New hash: {new_hash}, Old hash: {old_hash}")

            # First time checking this course
            if old_hash is None:
                logger.info(f"First time checking course {course_id}, saving data")
                db.save_course_data(course_id, course_name, new_data, new_hash)
                await self.send_initial_notification(chat_id, new_data)
                await self.schedule_upcoming_events(chat_id, new_data)
                db.log_notification(chat_id, course_id, "welcome", self.formatter.welcome_message(course_name))
                return

            # Check if data has changed
            if new_hash != old_hash:
                logger.info(f"Update detected for course {course_id}")
                old_data = cached['data'] if cached else {}
                await self.process_updates(chat_id, course_id, old_data, new_data)
                db.save_course_data(course_id, course_name, new_data, new_hash)
                await self.schedule_upcoming_events(chat_id, new_data)
            else:
                logger.info(f"No updates for course {course_id}")

        except Exception as e:
            logger.error(f"Error checking updates for course {course_id}: {e}")

    async def send_initial_notification(self, chat_id: int, course_data: dict):
        """Send initial welcome notification"""
        course_name = course_data.get("name", "Unknown Course")
        welcome_msg = self.formatter.welcome_message(course_name)
        try:
            await self.app.bot.send_message(
                chat_id=chat_id,
                text=welcome_msg,
                parse_mode=ParseMode.MARKDOWN
            )
            logger.info(f"Sent welcome message to chat {chat_id}")
        except Exception as e:
            logger.error(f"Error sending initial notification: {e}")

    async def process_updates(self, chat_id: int, course_id: str, old_data: dict, new_data: dict):
        """Process and notify about specific updates"""
        course_name = new_data.get("name", "Unknown Course")
        logger.info(f"Processing updates for {course_name}")
        
        # Check for new files
        await self.check_new_files(chat_id, course_name, course_id, old_data, new_data)
        
        # Check for new quizzes
        await self.check_quizzes(chat_id, course_name, course_id, old_data, new_data)

    async def check_new_files(self, chat_id: int, course_name: str, course_id: str, old_data: dict, new_data: dict):
        """Check for newly added files (PPT, Video, etc.)"""
        old_sections = old_data.get("CourseSection", [])
        new_sections = new_data.get("CourseSection", [])
        
        old_files = set()
        for section in old_sections:
            for item in section.get("contents", []):
                if item.get("type") in ["PPT", "VIDEO", "DOCUMENT"]:
                    old_files.add(item.get("id"))
        
        new_files_found = 0
        for section in new_sections:
            for item in section.get("contents", []):
                if item.get("type") in ["PPT", "VIDEO", "DOCUMENT"]:
                    if item.get("id") not in old_files:
                        file_name = item.get("name", "Untitled")
                        file_url = item.get("file", "#")
                        if not file_url.startswith("http"):
                            file_url = "https://d26pxqw2kk6v5i.cloudfront.net/" + file_url
                        text, keyboard = self.formatter.new_file_message(
                            course_name, file_name, file_url
                        )
                        try:
                            await self.app.bot.send_message(
                                chat_id=chat_id,
                                text=text,
                                reply_markup=keyboard,
                                parse_mode=ParseMode.MARKDOWN
                            )
                            db.log_notification(chat_id, course_id, "new_file", text)
                            logger.info(f"Sent new file notification: {file_name} to chat {chat_id}")
                            new_files_found += 1
                        except Exception as e:
                            logger.error(f"Error sending file notification for {file_name}: {e}")
        
        if new_files_found == 0:
            logger.info("No new files detected")

    async def check_quizzes(self, chat_id: int, course_name: str, course_id: str, old_data: dict, new_data: dict):
        """Check for new quizzes"""
        old_sections = old_data.get("CourseSection", [])
        new_sections = new_data.get("CourseSection", [])
        
        old_quizzes = set()
        for section in old_sections:
            for item in section.get("contents", []):
                if item.get("type") == "QUIZ":
                    old_quizzes.add(item.get("id"))
        
        new_quizzes_found = 0
        for section in new_sections:
            for item in section.get("contents", []):
                if item.get("type") == "QUIZ":
                    quiz_id = item.get("id")
                    if quiz_id not in old_quizzes:
                        quiz_title = item.get("name", "Quiz")
                        start_time = item.get("quiz", {}).get("startTime", "")
                        end_time = item.get("quiz", {}).get("endTime", "")
                        quiz_url = f"https://pptlinks.com/quiz/{quiz_id}"
                        formatted_start = self.format_datetime(start_time)
                        formatted_end = self.format_datetime(end_time)
                        text, keyboard = self.formatter.quiz_created_message(
                            course_name, quiz_title, formatted_start, formatted_end, quiz_url
                        )
                        try:
                            await self.app.bot.send_message(
                                chat_id=chat_id,
                                text=text,
                                reply_markup=keyboard,
                                parse_mode=ParseMode.MARKDOWN
                            )
                            db.log_notification(chat_id, course_id, "new_quiz", text)
                            logger.info(f"Sent new quiz notification: {quiz_title} to chat {chat_id}")
                            new_quizzes_found += 1
                        except Exception as e:
                            logger.error(f"Error sending quiz notification for {quiz_title}: {e}")
        
        if new_quizzes_found == 0:
            logger.info("No new quizzes detected")

    async def schedule_upcoming_events(self, chat_id: int, course_data: dict):
        """Schedule reminders for upcoming events"""
        logger.info(f"Scheduling upcoming events for chat {chat_id}")
        lagos_tz = pytz.timezone('Africa/Lagos')
        now = datetime.now(lagos_tz)
        sections = course_data.get("CourseSection", [])
        course_id = course_data.get("id", "")
        
        quiz_jobs_scheduled = 0
        for section in sections:
            for item in section.get("contents", []):
                item_type = item.get("type")
                
                # Schedule quiz reminders
                if item_type == "QUIZ":
                    start_time_str = item.get("quiz", {}).get("startTime")
                    end_time_str = item.get("quiz", {}).get("endTime")
                    quiz_id = item.get("id")
                    
                    if start_time_str:
                        try:
                            start_time = date_parser.parse(start_time_str)
                            if start_time.tzinfo is None:
                                start_time = lagos_tz.localize(start_time)
                            
                            # Schedule start reminder
                            if start_time > now:
                                quiz_title = item.get("name", "Quiz")
                                quiz_url = f"https://pptlinks.com/quiz/{quiz_id}"
                                scheduler.add_job(
                                    self.send_quiz_start_reminder,
                                    trigger=DateTrigger(run_date=start_time),
                                    args=[chat_id, course_id, quiz_title, quiz_url],
                                    id=f"quiz_start_{quiz_id}_{chat_id}",
                                    replace_existing=True
                                )
                                logger.info(f"Scheduled quiz start reminder for {quiz_title} at {start_time}")
                                quiz_jobs_scheduled += 1
                            else:
                                logger.info(f"Quiz start time {start_time} is in the past, skipping")
                            
                            # Schedule end reminder (2 hours before)
                            if end_time_str:
                                end_time = date_parser.parse(end_time_str)
                                if end_time.tzinfo is None:
                                    end_time = lagos_tz.localize(end_time)
                                reminder_time = end_time - timedelta(hours=2)
                                if reminder_time > now:
                                    quiz_title = item.get("name", "Quiz")
                                    scheduler.add_job(
                                        self.send_quiz_ending_reminder,
                                        trigger=DateTrigger(run_date=reminder_time),
                                        args=[chat_id, course_id, quiz_title],
                                        id=f"quiz_end_{quiz_id}_{chat_id}",
                                        replace_existing=True
                                    )
                                    logger.info(f"Scheduled quiz end reminder for {quiz_title} at {reminder_time}")
                                    quiz_jobs_scheduled += 1
                                else:
                                    logger.info(f"Quiz end reminder time {reminder_time} is in the past, skipping")
                        except Exception as e:
                            logger.error(f"Error scheduling quiz reminder for course {course_id}: {e}")

        logger.info(f"Scheduled {quiz_jobs_scheduled} quiz-related jobs")

        # Schedule expiry reminder (1 week before)
        expiry_str = course_data.get("expiry")
        if expiry_str:
            try:
                expiry_time = date_parser.parse(expiry_str)
                if expiry_time.tzinfo is None:
                    expiry_time = lagos_tz.localize(expiry_time)
                reminder_time = expiry_time - timedelta(days=7)
                if reminder_time > now:
                    course_name = course_data.get("name", "Unknown Course")
                    formatted_expiry = self.format_datetime(expiry_str)
                    scheduler.add_job(
                        self.send_expiry_reminder,
                        trigger=DateTrigger(run_date=reminder_time),
                        args=[chat_id, course_id, course_name, formatted_expiry],
                        id=f"expiry_{course_id}_{chat_id}",
                        replace_existing=True
                    )
                    logger.info(f"Scheduled expiry reminder for {course_name} at {reminder_time}")
                else:
                    logger.info(f"Expiry reminder time {reminder_time} is in the past, skipping")
            except Exception as e:
                logger.error(f"Error scheduling expiry reminder for course {course_id}: {e}")
        else:
            logger.info("No expiry date found in course data, skipping expiry scheduling")

    async def send_quiz_start_reminder(self, chat_id: int, course_id: str, quiz_title: str, quiz_url: str):
        """Send quiz start reminder"""
        text, keyboard = self.formatter.quiz_start_reminder(quiz_title, quiz_url)
        try:
            await self.app.bot.send_message(
                chat_id=chat_id,
                text=text,
                reply_markup=keyboard,
                parse_mode=ParseMode.MARKDOWN
            )
            db.log_notification(chat_id, course_id, "quiz_start", text)
            logger.info(f"Sent quiz start reminder for {quiz_title} to chat {chat_id}")
        except Exception as e:
            logger.error(f"Error sending quiz start reminder for {quiz_title}: {e}")

    async def send_quiz_ending_reminder(self, chat_id: int, course_id: str, quiz_title: str):
        """Send quiz ending soon reminder"""
        text = self.formatter.quiz_ending_soon(quiz_title, "2 hours")
        try:
            await self.app.bot.send_message(
                chat_id=chat_id,
                text=text,
                parse_mode=ParseMode.MARKDOWN
            )
            db.log_notification(chat_id, course_id, "quiz_end", text)
            logger.info(f"Sent quiz end reminder for {quiz_title} to chat {chat_id}")
        except Exception as e:
            logger.error(f"Error sending quiz ending reminder for {quiz_title}: {e}")

    async def send_expiry_reminder(self, chat_id: int, course_id: str, course_name: str, expiry_date: str):
        """Send course expiry reminder"""
        text = self.formatter.course_expiry_warning(course_name, expiry_date)
        try:
            await self.app.bot.send_message(
                chat_id=chat_id,
                text=text,
                parse_mode=ParseMode.MARKDOWN
            )
            db.log_notification(chat_id, course_id, "expiry", text)
            logger.info(f"Sent expiry reminder for {course_name} to chat {chat_id}")
        except Exception as e:
            logger.error(f"Error sending expiry reminder for {course_name}: {e}")

    @staticmethod
    def format_datetime(dt_string: str) -> str:
        """Format datetime string for display"""
        try:
            dt = date_parser.parse(dt_string)
            return dt.strftime("%B %d, %Y at %I:%M %p")
        except Exception as e:
            logger.error(f"Error formatting datetime {dt_string}: {e}")
            return dt_string


# Command handlers
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command with deep link"""
    args = context.args
    chat_id = update.effective_chat.id
    user = update.effective_user
    
    logger.info(f"Start command received from user {user.username} (chat {chat_id})")
    
    # Add user to database
    db.add_user(
        chat_id=chat_id,
        username=user.username,
        first_name=user.first_name,
        last_name=user.last_name
    )
    
    # Use fixed course ID
    course_id = FIXED_COURSE_ID
    logger.info(f"Using fixed course ID: {course_id}")
    
    # Subscribe user to course
    if db.subscribe_user_to_course(chat_id, course_id):
        # Fetch initial course data
        api = PPTLinksAPI()
        course_data = api.fetch_course_data(course_id)
        
        if course_data:
            course_name = course_data.get("name", "Unknown Course")
            try:
                await update.message.reply_text(
                    f"✅ Successfully subscribed to notifications!\n\n"
                    f"Course: *{course_name}*\n"
                    f"ID: `{course_id}`\n\n"
                    f"You'll start receiving updates shortly! 🚀",
                    parse_mode=ParseMode.MARKDOWN
                )
                logger.info(f"Subscription confirmed for {course_name} to chat {chat_id}")
                
                # Start monitoring this course
                monitor = CourseMonitor(context.application)
                await monitor.check_course_updates(chat_id, course_id)
                
                # Schedule periodic checks
                scheduler.add_job(
                    monitor.check_course_updates,
                    'interval',
                    seconds=POLL_INTERVAL,
                    args=[chat_id, course_id],
                    id=f"monitor_{course_id}_{chat_id}",
                    replace_existing=True
                )
                logger.info(f"Scheduled monitoring job for chat {chat_id}, course {course_id}")
            except Exception as e:
                logger.error(f"Error processing start command for course {course_id}: {e}")
        else:
            try:
                await update.message.reply_text(
                    "❌ Unable to fetch course information. Please check the API connection."
                )
                logger.error(f"Failed to fetch course data for {course_id}")
            except Exception as e:
                logger.error(f"Error sending error message for course {course_id}: {e}")
    else:
        try:
            await update.message.reply_text(
                "ℹ️ You're already subscribed to this course!"
            )
            logger.info(f"User {chat_id} already subscribed to {course_id}")
        except Exception as e:
            logger.error(f"Error sending already subscribed message: {e}")


async def mycourses_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show user's subscribed courses"""
    chat_id = update.effective_chat.id
    
    user_courses = db.get_user_courses(chat_id)
    
    if not user_courses:
        try:
            await update.message.reply_text(
                "📚 You're not subscribed to any courses yet.\n\n"
                "Use /start to subscribe to the available course."
            )
            logger.info(f"No courses for chat {chat_id}")
        except Exception as e:
            logger.error(f"Error sending mycourses message: {e}")
        return
    
    message = "📚 *Your Subscribed Courses:*\n\n"
    
    for course_id in user_courses:
        course_data = db.get_course_data(course_id)
        if course_data and course_data['data']:
            course_name = course_data['data'].get("name", "Unknown Course")
            message += f"• *{course_name}*\n  ID: `{course_id}`\n\n"
        else:
            message += f"• Course ID: `{course_id}`\n\n"
    
    try:
        await update.message.reply_text(message, parse_mode=ParseMode.MARKDOWN)
        logger.info(f"Sent courses list to chat {chat_id}")
    except Exception as e:
        logger.error(f"Error sending mycourses list: {e}")


async def unsubscribe_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Unsubscribe from all notifications"""
    chat_id = update.effective_chat.id
    
    user_courses = db.get_user_courses(chat_id)
    
    if user_courses:
        # Remove all scheduled jobs for this user
        for course_id in user_courses:
            try:
                scheduler.remove_job(f"monitor_{course_id}_{chat_id}")
                logger.info(f"Removed monitoring job for chat {chat_id}, course {course_id}")
            except Exception as e:
                logger.warning(f"Failed to remove job monitor_{course_id}_{chat_id}: {e}")
        
        db.unsubscribe_user_from_course(chat_id)
        try:
            await update.message.reply_text(
                "✅ You've been unsubscribed from all course notifications.\n\n"
                "You can resubscribe anytime using /start."
            )
            logger.info(f"Unsubscribed chat {chat_id}")
        except Exception as e:
            logger.error(f"Error sending unsubscribe message: {e}")
    else:
        try:
            await update.message.reply_text(
                "ℹ️ You don't have any active subscriptions."
            )
            logger.info(f"No subscriptions to unsubscribe for chat {chat_id}")
        except Exception as e:
            logger.error(f"Error sending no subscriptions message: {e}")


async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show user subscription stats"""
    chat_id = update.effective_chat.id
    stats = db.get_user_stats(chat_id)
    
    message = f"""📊 *Your Subscription Stats* 📊

📚 Subscribed Courses: {stats['total_courses']}
🔔 Total Notifications Received: {stats['total_notifications']}

Keep learning! 🚀"""
    
    try:
        await update.message.reply_text(message, parse_mode=ParseMode.MARKDOWN)
        logger.info(f"Sent stats to chat {chat_id}")
    except Exception as e:
        logger.error(f"Error sending stats message: {e}")


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show help information"""
    help_text = """🤖 *PPTLinks Reminder Bot - Help*

*How to use:*
1. Enroll in a course on PPTLinks
2. Click the Telegram notification activation link
3. Receive automatic updates about your course!

*What you'll receive:*
📂 New file uploads
🧩 Quiz notifications
⏳ Course expiry warnings

*Available Commands:*
/start - Subscribe to a course (use activation link)
/mycourses - View your subscribed courses
/unsubscribe - Stop all notifications
/stats - View your subscription stats
/help - Show this help message

*Need support?*
Contact PPTLinks support for assistance.
"""
    try:
        await update.message.reply_text(help_text, parse_mode=ParseMode.MARKDOWN)
        logger.info(f"Sent help to chat {update.effective_chat.id}")
    except Exception as e:
        logger.error(f"Error sending help message: {e}")


def main():
    """Start the bot"""
    if not BOT_TOKEN:
        logger.error("BOT_TOKEN not found in environment variables!")
        return
    
    logger.info("Starting PPTLinks Reminder Bot")
    logger.info(f"Using fixed API URL: {FIXED_API_URL}")
    logger.info(f"Polling interval: {POLL_INTERVAL} seconds")
    
    # Create custom request with longer timeouts
    request = HTTPXRequest(
        connection_pool_size=8,
        connect_timeout=30.0,
        read_timeout=30.0,
        write_timeout=30.0,
        pool_timeout=30.0,
    )
    
    # Create application with custom request
    application = Application.builder().token(BOT_TOKEN).request(request).build()
    
    # Add command handlers
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("mycourses", mycourses_command))
    application.add_handler(CommandHandler("unsubscribe", unsubscribe_command))
    application.add_handler(CommandHandler("stats", stats_command))
    application.add_handler(CommandHandler("help", help_command))
    
    # Schedule monitoring for existing subscriptions
    monitor = CourseMonitor(application)
    subscriptions = db.get_all_active_subscriptions()
    for chat_id, course_id in subscriptions:
        scheduler.add_job(
            monitor.check_course_updates,
            'interval',
            seconds=POLL_INTERVAL,
            args=[chat_id, course_id],
            id=f"monitor_{course_id}_{chat_id}",
            replace_existing=True
        )
        logger.info(f"Restored monitoring for chat_id={chat_id}, course_id={course_id}")
    
    # Start scheduler
    scheduler.start()
    logger.info("Scheduler started successfully!")
    logger.info("Bot started successfully!")
    
    # Start polling
    application.run_polling(
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=True
    )


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
        if scheduler.running:
            scheduler.shutdown()
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        if scheduler.running:
            scheduler.shutdown()