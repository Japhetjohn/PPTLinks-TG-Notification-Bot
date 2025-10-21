# main.py
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
scheduler = AsyncIOScheduler()  # Auto-starts with event loop


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
# MESSAGES
# ================================
class Msg:
    @staticmethod
    def welcome(name): return f"*Welcome!*\n\nYou're subscribed to *{name}*\n\nUpdates every 10 min"
    @staticmethod
    def new_file(course, name, url):
        text = f"*New File*\n*{course}*\n`{name}`"
        kb = [[InlineKeyboardButton("View", url=url)]]
        return text, InlineKeyboardMarkup(kb)
    @staticmethod
    def new_quiz(course, title, start, end, url):
        text = f"*New Quiz*\n*{course}*\n*{title}*\n`{start}` → `{end}`"
        kb = [[InlineKeyboardButton("Take Quiz", url=url)]]
        return text, InlineKeyboardMarkup(kb)
    @staticmethod
    def quiz_start(title, url):
        text = f"*Quiz Started!*\n*{title}*"
        kb = [[InlineKeyboardButton("Open", url=url)]]
        return text, InlineKeyboardMarkup(kb)
    @staticmethod
    def quiz_end(title): return f"*Quiz Ending Soon*\n*{title}*\n2 hours left!"


# ================================
# MONITOR
# ================================
class Monitor:
    def __init__(self, app): self.app = app

    async def check(self, chat_id: int):
        data = PPTLinksAPI.fetch_course_data()
        if not data: return

        new_hash = PPTLinksAPI.get_hash(data)
        cached = db.get_course_data(FIXED_COURSE_ID)
        old_hash = cached['hash'] if cached else None
        name = data.get('name', 'Course')

        if not old_hash:
            db.save_course_data(FIXED_COURSE_ID, name, data, new_hash)
            await self.welcome(chat_id, name)
            await self.schedule(data, chat_id)
            return

        if new_hash != old_hash:
            old = cached['data']
            await self.notify_files(chat_id, name, old, data)
            await self.notify_quizzes(chat_id, name, old, data)
            db.save_course_data(FIXED_COURSE_ID, name, data, new_hash)
            await self.schedule(data, chat_id)

    async def welcome(self, chat_id, name):
        await self.app.bot.send_message(chat_id, Msg.welcome(name), parse_mode=ParseMode.MARKDOWN)

    async def notify_files(self, chat_id, course, old, new):
        old_ids = {i['id'] for s in old.get('CourseSection', []) for i in s.get('contents', []) if i['type'] in ['PPT', 'VIDEO']}
        for s in new.get('CourseSection', []):
            for i in s.get('contents', []):
                if i['type'] in ['PPT', 'VIDEO'] and i['id'] not in old_ids:
                    url = i['file']
                    if not url.startswith('http'): url = 'https://d26pxqw2kk6v5i.cloudfront.net/' + url
                    text, kb = Msg.new_file(course, i['name'], url)
                    await self.app.bot.send_message(chat_id, text, reply_markup=kb, parse_mode=ParseMode.MARKDOWN)

    async def notify_quizzes(self, chat_id, course, old, new):
        old_ids = {i['id'] for s in old.get('CourseSection', []) for i in s.get('contents', []) if i['type'] == 'QUIZ'}
        for s in new.get('CourseSection', []):
            for i in s.get('contents', []):
                if i['type'] == 'QUIZ' and i['id'] not in old_ids:
                    q = i['quiz']
                    start = format_time(q.get('startTime'))
                    end = format_time(q.get('endTime'))
                    url = f"https://pptlinks.com/quiz/{i['id']}"
                    text, kb = Msg.new_quiz(course, i['name'], start, end, url)
                    await self.app.bot.send_message(chat_id, text, reply_markup=kb, parse_mode=ParseMode.MARKDOWN)

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
            if start.tzinfo is None: start = pytz.timezone('Africa/Lagos').localize(start)
            if start > now:
                scheduler.add_job(
                    self.send_quiz_start, DateTrigger(start),
                    args=[chat_id, title, f"https://pptlinks.com/quiz/{qid}"],
                    id=f"start_{qid}_{chat_id}", replace_existing=True
                )

        if end_str:
            end = date_parser.parse(end_str)
            if end.tzinfo is None: end = pytz.timezone('Africa/Lagos').localize(end)
            remind = end - timedelta(hours=2)
            if remind > now:
                scheduler.add_job(
                    self.send_quiz_end, DateTrigger(remind),
                    args=[chat_id, title],
                    id=f"end_{qid}_{chat_id}", replace_existing=True
                )

    async def send_quiz_start(self, chat_id, title, url):
        text, kb = Msg.quiz_start(title, url)
        await self.app.bot.send_message(chat_id, text, reply_markup=kb, parse_mode=ParseMode.MARKDOWN)

    async def send_quiz_end(self, chat_id, title):
        await self.app.bot.send_message(chat_id, Msg.quiz_end(title), parse_mode=ParseMode.MARKDOWN)


def format_time(dt):
    try: return date_parser.parse(dt).strftime("%B %d, %Y at %I:%M %p")
    except: return dt


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
            await update.message.reply_text(
                f"*Subscribed!*\n\n*{data['name']}*\n`{FIXED_COURSE_ID}`\n\nChecking every 10 min",
                parse_mode=ParseMode.MARKDOWN
            )
            monitor = Monitor(context.application)
            await monitor.check(chat_id)
            scheduler.add_job(
                monitor.check, 'interval', seconds=POLL_INTERVAL,
                args=[chat_id], id=f"poll_{chat_id}", replace_existing=True
            )
        else:
            await update.message.reply_text("API down. Try later.")
    else:
        await update.message.reply_text("Already subscribed!")


async def mycourses(update: Update, context):
    courses = db.get_user_courses(update.effective_chat.id)
    if not courses:
        await update.message.reply_text("Use /start")
        return
    msg = "*Your Courses*\n\n"
    for cid in courses:
        d = db.get_course_data(cid)
        name = d['data'].get('name', 'Unknown') if d else 'Unknown'
        msg += f"* {name}*\n  `{cid}`\n\n"
    await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)


async def unsubscribe(update: Update, context):
    chat_id = update.effective_chat.id
    try: scheduler.remove_job(f"poll_{chat_id}")
    except: pass
    db.unsubscribe_user_from_course(chat_id)
    await update.message.reply_text("Unsubscribed!")


async def stats(update: Update, context):
    s = db.get_user_stats(update.effective_chat.id)
    await update.message.reply_text(
        f"*Stats*\n\nCourses: {s['total_courses']}\nNotifs: {s['total_notifications']}",
        parse_mode=ParseMode.MARKDOWN
    )


async def help_cmd(update: Update, context):
    await update.message.reply_text(
        "*Help*\n\n/start - Subscribe\n/mycourses - List\n/unsubscribe - Stop\n/stats - Stats\n/help - This",
        parse_mode=ParseMode.MARKDOWN
    )


# ================================
# MAIN
# ================================
def main():
    if not BOT_TOKEN:
        logger.error("NO BOT TOKEN")
        return

    logger.info("Starting bot...")
    logger.info(f"Monitoring course: {FIXED_COURSE_ID}")

    request = HTTPXRequest(connect_timeout=30, read_timeout=30)
    app = Application.builder().token(BOT_TOKEN).request(request).build()

    # Add handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("mycourses", mycourses))
    app.add_handler(CommandHandler("unsubscribe", unsubscribe))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CommandHandler("help", help_cmd))

    # Restore monitoring
    monitor = Monitor(app)
    for chat_id, _ in db.get_all_active_subscriptions():
        scheduler.add_job(
            monitor.check, 'interval', seconds=POLL_INTERVAL,
            args=[chat_id], id=f"poll_{chat_id}", replace_existing=True
        )

    # Run bot directly
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    try:
        main()  # No asyncio.run() — run_polling() handles it
    except KeyboardInterrupt:
        logger.info("Bot stopped by user.")
    except Exception as e:
        logger.error(f"Fatal error: {e}")