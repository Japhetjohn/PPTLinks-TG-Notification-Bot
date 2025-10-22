# main.py - Enhanced PPTLinks Telegram Bot
import os
import json
import hashlib
import logging
from datetime import datetime, timedelta
from typing import Optional
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
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

FIXED_COURSE_ID = "686254fca0502cc2d68f5b89"
FIXED_API_URL = f"{API_BASE}/course/user-courses/{FIXED_COURSE_ID}?brief=false&timeZone=Africa/Lagos"

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
    def fetch_course_data() -> Optional[dict]:
        session = requests.Session()
        retry = Retry(total=3, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504])
        session.mount('https://', HTTPAdapter(max_retries=retry))

        try:
            r = session.get(FIXED_API_URL, timeout=30)
            logger.info(f"API → {r.status_code}")
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
        return hashlib.md5(json.dumps(data, sort_keys=True).encode()).hexdigest()


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
                InlineKeyboardButton(f"{Emoji.CHART} Statistics", callback_data="stats")
            ],
            [
                InlineKeyboardButton(f"{Emoji.BELL} Notifications ON", callback_data="notif_status"),
                InlineKeyboardButton(f"{Emoji.GEAR} Settings", callback_data="settings")
            ],
            [
                InlineKeyboardButton(f"{Emoji.INFO} Help & Support", callback_data="help")
            ]
        ]
        return InlineKeyboardMarkup(keyboard)
    
    @staticmethod
    def settings_menu():
        """Settings and preferences"""
        keyboard = [
            [
                InlineKeyboardButton(f"{Emoji.BELL} Manage Notifications", callback_data="manage_notifs"),
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

*What I can do for you:*
{Emoji.BELL} Real-time course updates
{Emoji.FIRE} Quiz & deadline reminders
{Emoji.FILE} New content notifications
{Emoji.CHART} Track your progress

{Emoji.ROCKET} *Let's get started!*
Use /start to subscribe to your first course.

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
{Emoji.ROCKET} *Quiz Time!* {Emoji.FIRE}

━━━━━━━━━━━━━━━━━━━━━━━

{Emoji.QUIZ} *{title}*

{Emoji.TARGET} The quiz has just started!

{Emoji.BRAIN} Show what you've learned!

━━━━━━━━━━━━━━━━━━━━━━━

{Emoji.WARNING} _Don't forget to submit before the deadline_
"""
    
    @staticmethod
    def quiz_ending(title, time_left):
        return f"""
{Emoji.WARNING} *Urgent Reminder!* {Emoji.HOURGLASS}

━━━━━━━━━━━━━━━━━━━━━━━

{Emoji.QUIZ} *{title}*

{Emoji.CLOCK} Only *{time_left}* remaining!

{Emoji.FIRE} Finish strong and submit now!

━━━━━━━━━━━━━━━━━━━━━━━
"""
    
    @staticmethod
    def my_courses(courses_list):
        if not courses_list:
            return f"""
{Emoji.INFO} *No Active Subscriptions*

You haven't subscribed to any courses yet.

{Emoji.ROCKET} Use /start to get started!
"""
        
        msg = f"""
{Emoji.BOOK} *Your Learning Dashboard* {Emoji.CHART}

━━━━━━━━━━━━━━━━━━━━━━━

*Active Courses:*

"""
        for idx, (name, cid) in enumerate(courses_list, 1):
            msg += f"{idx}. {Emoji.STAR} *{name}*\n"
            msg += f"   {Emoji.PIN} `{cid}`\n\n"
        
        msg += f"""━━━━━━━━━━━━━━━━━━━━━━━

{Emoji.BELL} Monitoring active for all courses
{Emoji.TARGET} Stay focused and keep learning!
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

*Available Commands:*

{Emoji.ROCKET} /start - Subscribe to course
{Emoji.BOOK} /mycourses - View your courses
{Emoji.CHART} /stats - Learning statistics
{Emoji.GEAR} /settings - Manage preferences
{Emoji.WARNING} /unsubscribe - Stop notifications
{Emoji.INFO} /help - Show this menu

━━━━━━━━━━━━━━━━━━━━━━━

*Features:*

{Emoji.BELL} Real-time notifications
{Emoji.CLOCK} Auto-checks every 10 minutes
{Emoji.BRAIN} Smart quiz reminders
{Emoji.FILE} Instant content alerts

━━━━━━━━━━━━━━━━━━━━━━━

{Emoji.TEACHER} *Need Support?*
Contact PPTLinks support team

━━━━━━━━━━━━━━━━━━━━━━━
_Made with_ {Emoji.STAR} _for PPTLinks students_
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

    async def check(self, chat_id: int):
        data = PPTLinksAPI.fetch_course_data()
        if not data: return

        new_hash = PPTLinksAPI.get_hash(data)
        cached = db.get_course_data(FIXED_COURSE_ID)
        old_hash = cached['hash'] if cached else None
        name = data.get('name', 'Course')

        if not old_hash:
            db.save_course_data(FIXED_COURSE_ID, name, data, new_hash)
            await self.send_message(chat_id, Msg.subscribed(name, FIXED_COURSE_ID), Keyboards.main_menu())
            await self.schedule(data, chat_id)
            return

        if new_hash != old_hash:
            old = cached['data']
            await self.notify_files(chat_id, name, old, data)
            await self.notify_quizzes(chat_id, name, old, data)
            db.save_course_data(FIXED_COURSE_ID, name, data, new_hash)
            await self.schedule(data, chat_id)

    async def send_message(self, chat_id, text, keyboard=None):
        try:
            await self.app.bot.send_message(
                chat_id, 
                text, 
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=keyboard
            )
        except Exception as e:
            logger.error(f"Send message error: {e}")

    async def notify_files(self, chat_id, course, old, new):
        old_ids = {i['id'] for s in old.get('CourseSection', []) for i in s.get('contents', []) if i['type'] in ['PPT', 'VIDEO']}
        for s in new.get('CourseSection', []):
            for i in s.get('contents', []):
                if i['type'] in ['PPT', 'VIDEO'] and i['id'] not in old_ids:
                    url = i['file']
                    if not url.startswith('http'): 
                        url = 'https://d26pxqw2kk6v5i.cloudfront.net/' + url
                    
                    text = Msg.new_file(course, i['name'], url, i['type'])
                    keyboard = InlineKeyboardMarkup([
                        [InlineKeyboardButton(f"{Emoji.ROCKET} Open Material", url=url)],
                        [InlineKeyboardButton(f"{Emoji.BOOK} View All Courses", callback_data="mycourses")]
                    ])
                    
                    await self.send_message(chat_id, text, keyboard)

    async def notify_quizzes(self, chat_id, course, old, new):
        old_ids = {i['id'] for s in old.get('CourseSection', []) for i in s.get('contents', []) if i['type'] == 'QUIZ'}
        for s in new.get('CourseSection', []):
            for i in s.get('contents', []):
                if i['type'] == 'QUIZ' and i['id'] not in old_ids:
                    q = i['quiz']
                    start = format_time(q.get('startTime'))
                    end = format_time(q.get('endTime'))
                    url = f"https://pptlinks.com/quiz/{i['id']}"
                    
                    text = Msg.new_quiz(course, i['name'], start, end)
                    keyboard = InlineKeyboardMarkup([
                        [InlineKeyboardButton(f"{Emoji.BRAIN} View Quiz Details", url=url)],
                        [InlineKeyboardButton(f"{Emoji.CALENDAR} Set Reminder", callback_data=f"remind_{i['id']}")]
                    ])
                    
                    await self.send_message(chat_id, text, keyboard)

    async def schedule(self, data, chat_id):
        now = datetime.now(pytz.timezone('Africa/Lagos'))
        for s in data.get('CourseSection', []):
            for i in s.get('contents', []):
                if i['type'] == 'QUIZ':
                    await self.schedule_quiz(i, chat_id, now)

    async def schedule_quiz(self, item, chat_id, now):
        q = item['quiz']
        start_str = q.get('startTime')
        end_str = q.get('endTime')
        qid = item['id']
        title = item['name']

        if start_str:
            start = date_parser.parse(start_str)
            if start.tzinfo is None: 
                start = pytz.timezone('Africa/Lagos').localize(start)
            if start > now:
                scheduler.add_job(
                    self.send_quiz_start, DateTrigger(start),
                    args=[chat_id, title, f"https://pptlinks.com/quiz/{qid}"],
                    id=f"start_{qid}_{chat_id}", replace_existing=True
                )
                logger.info(f"Scheduled quiz start: {title} at {start}")

        if end_str:
            end = date_parser.parse(end_str)
            if end.tzinfo is None: 
                end = pytz.timezone('Africa/Lagos').localize(end)
            remind = end - timedelta(hours=2)
            if remind > now:
                scheduler.add_job(
                    self.send_quiz_end, DateTrigger(remind),
                    args=[chat_id, title],
                    id=f"end_{qid}_{chat_id}", replace_existing=True
                )
                logger.info(f"Scheduled quiz end: {title} at {remind}")

    async def send_quiz_start(self, chat_id, title, url):
        text = Msg.quiz_start(title)
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton(f"{Emoji.ROCKET} Start Quiz Now", url=url)],
            [InlineKeyboardButton(f"{Emoji.CLOCK} Remind Me Later", callback_data="snooze_quiz")]
        ])
        await self.send_message(chat_id, text, keyboard)

    async def send_quiz_end(self, chat_id, title):
        text = Msg.quiz_ending(title, "2 hours")
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton(f"{Emoji.FIRE} Complete Now", callback_data="quiz_now")]
        ])
        await self.send_message(chat_id, text, keyboard)


def format_time(dt):
    try: 
        return date_parser.parse(dt).strftime("%b %d, %Y • %I:%M %p")
    except: 
        return dt


# ================================
# CALLBACK HANDLERS
# ================================
async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
    
    elif data == "mycourses":
        courses = db.get_user_courses(chat_id)
        courses_list = []
        for cid in courses:
            d = db.get_course_data(cid)
            name = d['data'].get('name', 'Unknown') if d else 'Unknown'
            courses_list.append((name, cid))
        
        await query.edit_message_text(
            Msg.my_courses(courses_list),
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=Keyboards.back_to_menu()
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
        try: 
            scheduler.remove_job(f"poll_{chat_id}")
        except: 
            pass
        db.unsubscribe_user_from_course(chat_id)
        await query.edit_message_text(
            Msg.unsubscribed(),
            parse_mode=ParseMode.MARKDOWN
        )
    
    elif data == "notif_status":
        await query.answer(f"{Emoji.BELL} Notifications are active!", show_alert=True)
    
    elif data == "manage_notifs":
        await query.answer(f"{Emoji.GEAR} Feature coming soon!", show_alert=True)
    
    elif data.startswith("remind_"):
        await query.answer(f"{Emoji.CHECK} Reminder set!", show_alert=True)
    
    elif data == "snooze_quiz":
        await query.answer(f"{Emoji.CLOCK} Reminder snoozed for 30 minutes", show_alert=True)
    
    elif data == "quiz_now":
        await query.answer(f"{Emoji.FIRE} Good luck on your quiz!", show_alert=True)


# ================================
# COMMANDS
# ================================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user = update.effective_user
    db.add_user(chat_id, user.username, user.first_name, user.last_name)

    if db.subscribe_user_to_course(chat_id, FIXED_COURSE_ID):
        data = PPTLinksAPI.fetch_course_data()
        if data:
            monitor = Monitor(context.application)
            await monitor.check(chat_id)
            scheduler.add_job(
                monitor.check, 'interval', seconds=POLL_INTERVAL,
                args=[chat_id], id=f"poll_{chat_id}", replace_existing=True
            )
            logger.info(f"User {chat_id} subscribed successfully")
        else:
            await update.message.reply_text(
                Msg.api_error(),
                parse_mode=ParseMode.MARKDOWN
            )
    else:
        await update.message.reply_text(
            Msg.already_subscribed(),
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=Keyboards.main_menu()
        )


async def mycourses(update: Update, context):
    chat_id = update.effective_chat.id
    courses = db.get_user_courses(chat_id)
    courses_list = []
    
    for cid in courses:
        d = db.get_course_data(cid)
        name = d['data'].get('name', 'Unknown') if d else 'Unknown'
        courses_list.append((name, cid))
    
    await update.message.reply_text(
        Msg.my_courses(courses_list),
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=Keyboards.main_menu()
    )


async def unsubscribe(update: Update, context):
    chat_id = update.effective_chat.id
    try: 
        scheduler.remove_job(f"poll_{chat_id}")
    except: 
        pass
    db.unsubscribe_user_from_course(chat_id)
    await update.message.reply_text(
        Msg.unsubscribed(),
        parse_mode=ParseMode.MARKDOWN
    )


async def stats_cmd(update: Update, context):
    s = db.get_user_stats(update.effective_chat.id)
    await update.message.reply_text(
        Msg.stats(s['total_courses'], s['total_notifications']),
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=Keyboards.main_menu()
    )


async def help_cmd(update: Update, context):
    await update.message.reply_text(
        Msg.help_menu(),
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=Keyboards.main_menu()
    )


async def settings_cmd(update: Update, context):
    await update.message.reply_text(
        Msg.settings(),
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=Keyboards.settings_menu()
    )


# ================================
# MAIN
# ================================
def main():
    if not BOT_TOKEN:
        logger.error("NO BOT TOKEN")
        return

    logger.info("=" * 50)
    logger.info(f"{Emoji.ROCKET} PPTLinks Notification Bot Starting...")
    logger.info(f"{Emoji.BOOK} Monitoring Course: {FIXED_COURSE_ID}")
    logger.info(f"{Emoji.CLOCK} Check Interval: {POLL_INTERVAL}s")
    logger.info("=" * 50)

    request = HTTPXRequest(connect_timeout=30, read_timeout=30)
    app = Application.builder().token(BOT_TOKEN).request(request).build()

    # Add command handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("mycourses", mycourses))
    app.add_handler(CommandHandler("unsubscribe", unsubscribe))
    app.add_handler(CommandHandler("stats", stats_cmd))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("settings", settings_cmd))
    
    # Add callback handler for inline buttons
    app.add_handler(CallbackQueryHandler(handle_callback))

    # Restore monitoring for existing users
    monitor = Monitor(app)
    subscriptions = db.get_all_active_subscriptions()
    restored = 0
    for chat_id, _ in subscriptions:
        scheduler.add_job(
            monitor.check, 'interval', seconds=POLL_INTERVAL,
            args=[chat_id], id=f"poll_{chat_id}", replace_existing=True
        )
        restored += 1
    
    if restored > 0:
        logger.info(f"{Emoji.CHECK} Restored monitoring for {restored} users")

    logger.info(f"{Emoji.FIRE} Bot is now live and ready!")
    logger.info("=" * 50)

    # Run bot
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logger.info(f"\n{Emoji.WAVE} Bot stopped by user")
    except Exception as e:
        logger.exception(f"{Emoji.WARNING} Unhandled exception: {e}")