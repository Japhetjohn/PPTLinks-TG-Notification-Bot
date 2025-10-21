# PPTLinks Reminder Bot 🎓

A fully automated Telegram notification bot that keeps students informed about their PPTLinks courses - from live classes and quizzes to file uploads and course updates.

## Features ✨

- **Real-time Notifications**: Instant updates when new content is added
- **Smart Monitoring**: Continuously tracks course changes every 10 minutes
- **Event Reminders**: Automatic reminders for quizzes and live classes
- **Multi-Course Support**: Subscribe to multiple courses simultaneously
- **Beautiful Messages**: Clean, emoji-rich notifications with inline buttons
- **Easy Management**: Simple commands to view and manage subscriptions

## What You'll Be Notified About 📢

- 📂 New file uploads (PPTs, videos, documents)
- 🧑‍🏫 Live class schedules and start times
- 🧩 Quiz creation, start, and end times
- ⏳ Course expiry warnings
- 📝 General course updates

## Setup Instructions 🚀

### Prerequisites

- Python 3.8 or higher
- A Telegram Bot Token (from [@BotFather](https://t.me/botfather))
- Access to PPTLinks API

### Installation

1. **Clone or download this repository**

2. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

3. **Configure environment variables**:
   
   Create a `.env` file in the project root:
   ```bash
   BOT_TOKEN=your_bot_token_here
   API_BASE=https://api.pptlinks.com/api/v1
   POLL_INTERVAL=600
   ```

4. **Run the bot**:
   ```bash
   python main.py
   ```

## Usage 📱

### For Students

1. **Enroll in a course** on PPTLinks platform
2. **Click the activation link** that appears (format: `t.me/PPTLinksReminderBot?start=COURSE_ID`)
3. **Start receiving updates** automatically!

### Available Commands

- `/start` - Subscribe to course notifications (via activation link)
- `/mycourses` - View all your subscribed courses
- `/unsubscribe` - Stop all notifications
- `/help` - Show help information

## Deployment 🌐

### Option 1: Deploy on Render

1. Create a new Web Service on [Render](https://render.com)
2. Connect your repository
3. Set the start command: `python main.py`
4. Add environment variables in the Render dashboard
5. Deploy!

### Option 2: Deploy on Railway

1. Create a new project on [Railway](https://railway.app)
2. Connect your GitHub repository
3. Add environment variables
4. Railway will auto-deploy

### Option 3: VPS Deployment (Ubuntu)

```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install Python and pip
sudo apt install python3 python3-pip -y

# Clone your repository
git clone <your-repo-url>
cd pptlinks-reminder-bot

# Install dependencies
pip3 install -r requirements.txt

# Create .env file
nano .env
# Add your configuration

# Run with systemd (recommended)
sudo nano /etc/systemd/system/pptlinks-bot.service
```

**Systemd service file**:
```ini
[Unit]
Description=PPTLinks Reminder Bot
After=network.target

[Service]
Type=simple
User=youruser
WorkingDirectory=/path/to/pptlinks-reminder-bot
ExecStart=/usr/bin/python3 /path/to/pptlinks-reminder-bot/main.py
Restart=always

[Install]
WantedBy=multi-user.target
```

Then:
```bash
sudo systemctl daemon-reload
sudo systemctl enable pptlinks-bot
sudo systemctl start pptlinks-bot
```

## Webhook Setup (Production) 🔗

For production deployments, webhooks are more efficient than polling:

```bash
curl -X POST "https://api.telegram.org/bot<YOUR_BOT_TOKEN>/setWebhook?url=https://your-app-url.com/webhook"
```

To use webhooks, modify the last line in `main.py`:
```python
# Replace this:
application.run_polling(allowed_updates=Update.ALL_TYPES)

# With this:
application.run_webhook(
    listen="0.0.0.0",
    port=int(os.environ.get("PORT", 8443)),
    url_path="webhook",
    webhook_url="https://your-app-url.com/webhook"
)
```

## Architecture 🏗️

```
PPTLinks API ← Bot polls every 10 minutes
     ↓
Course Monitor detects changes
     ↓
Message Formatter creates beautiful messages
     ↓
Telegram delivers notifications to users
```

## Data Storage 💾

Currently uses in-memory storage (dictionaries) for:
- User course subscriptions
- Course data cache
- Data hashes for change detection

**For production**, consider migrating to:
- SQLite for simple deployments
- PostgreSQL/MySQL for scalability
- Redis for caching

## Monitoring & Logs 📊

The bot logs all activities to:
- `bot.log` file
- Console output

Monitor with:
```bash
tail -f bot.log
```

## Customization 🎨

### Adjust polling interval
Change `POLL_INTERVAL` in `.env` (in seconds):
```
POLL_INTERVAL=300  # Check every 5 minutes
```

### Modify notification messages
Edit the `MessageFormatter` class in `main.py` to customize message templates.

### Add new notification types
Extend the `CourseMonitor.process_updates()` method to detect and notify about new types of content.

## Troubleshooting 🔧

**Bot not starting?**
- Check if `BOT_TOKEN` is correctly set in `.env`
- Verify Python version (3.8+)
- Ensure all dependencies are installed

**Not receiving notifications?**
- Verify the course ID in the activation link is correct
- Check bot logs for API errors
- Ensure the API endpoint is accessible

**Duplicate notifications?**
- The bot uses content hashing to prevent duplicates
- If you restart the bot, it may re-notify on first check

## Security 🔒

- Never commit your `.env` file to version control
- Use environment variables for all sensitive data
- Implement rate limiting for production
- Validate all user inputs
- Keep dependencies updated

## Future Enhancements 🚀

- [ ] User preferences (notification times, types)
- [ ] Multi-language support
- [ ] Group chat support for study groups
- [ ] Integration with calendar apps

## Contributing 🤝

Contributions are welcome! Please feel free to submit a Pull Request.

## License 📄

This project is licensed under the MIT License.

## Support 💬

For issues or questions:
- Open an issue on GitHub
- Contact PPTLinks support
- Check the `/help` command in the bot

## Credits 👏

Built with:
- [python-telegram-bot](https://github.com/python-telegram-bot/python-telegram-bot)
- [APScheduler](https://apscheduler.readthedocs.io/)
- PPTLinks API

---

Made with ❤️ for PPTLinks students Database integration (PostgreSQL/MongoDB)
- [ ] Personalized daily summaries
- [ ] AI-based smart reminders
- [ ] Admin dashboard for tutors
- [ ] Analytics and usage statistics
- [ ]