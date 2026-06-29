import os
import logging
import sqlite3
import threading
import time
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes

# ============= LOGGING SETUP =============
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ============= ENVIRONMENT VARIABLES =============
BOT_TOKEN = os.environ.get('BOT_TOKEN')
BOT_USERNAME = os.environ.get('BOT_USERNAME', 'Schedule3Bot')
BOT_NAME = os.environ.get('BOT_NAME', 'Schedule3Bot')

if not BOT_TOKEN:
    logger.error("❌ BOT_TOKEN environment variable is not set!")
    raise ValueError("BOT_TOKEN is required. Add it to Railway variables.")

logger.info(f"✅ Starting {BOT_NAME} (@{BOT_USERNAME})")

# ============= DATABASE SETUP =============
def init_db():
    """Initialize SQLite database"""
    conn = sqlite3.connect('schedule.db', check_same_thread=False)
    cursor = conn.cursor()
    
    # Create users table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            last_name TEXT,
            registered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Create reminders table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS reminders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            reminder_text TEXT,
            reminder_time TIMESTAMP,
            is_active INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (user_id)
        )
    ''')
    
    # Create weekly schedule table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS weekly_schedule (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            day_of_week INTEGER,
            hour INTEGER,
            minute INTEGER,
            task_text TEXT,
            is_active INTEGER DEFAULT 1,
            FOREIGN KEY (user_id) REFERENCES users (user_id)
        )
    ''')
    
    conn.commit()
    conn.close()
    logger.info("✅ Database initialized")

def register_user(user_id, username, first_name, last_name):
    """Register user in database"""
    conn = sqlite3.connect('schedule.db', check_same_thread=False)
    cursor = conn.cursor()
    
    cursor.execute('''
        INSERT OR IGNORE INTO users (user_id, username, first_name, last_name)
        VALUES (?, ?, ?, ?)
    ''', (user_id, username, first_name, last_name))
    
    conn.commit()
    conn.close()

def add_reminder(user_id, text, reminder_time):
    """Add a reminder to database"""
    conn = sqlite3.connect('schedule.db', check_same_thread=False)
    cursor = conn.cursor()
    
    cursor.execute('''
        INSERT INTO reminders (user_id, reminder_text, reminder_time)
        VALUES (?, ?, ?)
    ''', (user_id, text, reminder_time))
    
    conn.commit()
    conn.close()

def get_user_reminders(user_id):
    """Get all active reminders for a user"""
    conn = sqlite3.connect('schedule.db', check_same_thread=False)
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT id, reminder_text, reminder_time
        FROM reminders
        WHERE user_id = ? AND is_active = 1
        ORDER BY reminder_time ASC
    ''', (user_id,))
    
    reminders = cursor.fetchall()
    conn.close()
    return reminders

def delete_reminder(reminder_id):
    """Delete a reminder"""
    conn = sqlite3.connect('schedule.db', check_same_thread=False)
    cursor = conn.cursor()
    
    cursor.execute('''
        UPDATE reminders SET is_active = 0
        WHERE id = ?
    ''', (reminder_id,))
    
    conn.commit()
    conn.close()

def get_due_reminders():
    """Get all due reminders"""
    conn = sqlite3.connect('schedule.db', check_same_thread=False)
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT id, user_id, reminder_text
        FROM reminders
        WHERE is_active = 1 AND reminder_time <= datetime('now')
    ''')
    
    due = cursor.fetchall()
    conn.close()
    return due

def mark_reminder_sent(reminder_id):
    """Mark reminder as sent"""
    conn = sqlite3.connect('schedule.db', check_same_thread=False)
    cursor = conn.cursor()
    
    cursor.execute('''
        UPDATE reminders SET is_active = 0
        WHERE id = ?
    ''', (reminder_id,))
    
    conn.commit()
    conn.close()

# ============= BACKGROUND SCHEDULER =============

def check_reminders(application):
    """Background thread to check and send reminders"""
    while True:
        try:
            due_reminders = get_due_reminders()
            for reminder_id, user_id, text in due_reminders:
                try:
                    application.bot.send_message(
                        chat_id=user_id,
                        text=f"⏰ *Reminder:*\n\n{text}",
                        parse_mode='Markdown'
                    )
                    mark_reminder_sent(reminder_id)
                    logger.info(f"✅ Sent reminder {reminder_id} to user {user_id}")
                except Exception as e:
                    logger.error(f"Error sending reminder: {e}")
            
            time.sleep(30)  # Check every 30 seconds
            
        except Exception as e:
            logger.error(f"Error in reminder checker: {e}")
            time.sleep(60)

# ============= COMMAND HANDLERS =============

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command."""
    user = update.effective_user
    first_name = user.first_name or "User"
    
    # Register user
    register_user(
        user_id=user.id,
        username=user.username,
        first_name=user.first_name,
        last_name=user.last_name
    )
    
    welcome_text = (
        f"📅 *Welcome to {BOT_NAME}, {first_name}!*\n\n"
        f"I'm @{BOT_USERNAME}, your schedule and reminder bot!\n\n"
        "⏰ *What I can do:*\n"
        "• Set one-time reminders\n"
        "• Manage weekly schedules\n"
        "• List all your reminders\n"
        "• Delete reminders\n\n"
        "👇 *How to use:*\n"
        "• Click a button below\n"
        "• Use commands to manage reminders\n\n"
        "📤 *Commands:*\n"
        "/remind - Set a reminder\n"
        "/schedule - View schedule\n"
        "/list - List reminders\n"
        "/delete - Delete a reminder\n"
        "/about - About this bot"
    )
    
    keyboard = [
        [
            InlineKeyboardButton("⏰ Set Reminder", callback_data="remind"),
            InlineKeyboardButton("📋 My Reminders", callback_data="list"),
        ],
        [
            InlineKeyboardButton("🗓️ Weekly Schedule", callback_data="schedule"),
            InlineKeyboardButton("❌ Delete Reminder", callback_data="delete"),
        ],
        [
            InlineKeyboardButton("ℹ️ About", callback_data="about"),
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        welcome_text,
        parse_mode='Markdown',
        reply_markup=reply_markup
    )


async def about(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /about command."""
    about_text = (
        "ℹ️ *About ScheduleBot*\n\n"
        "📅 Schedule and Reminder Bot\n\n"
        "⏰ *Features:*\n"
        "• Set one-time reminders\n"
        "• View all active reminders\n"
        "• Delete reminders\n"
        "• Weekly schedule management\n"
        "• Automatic notifications\n\n"
        "📝 *Commands:*\n"
        "/remind - Set a reminder\n"
        "/schedule - View schedule\n"
        "/list - List reminders\n"
        "/delete - Delete a reminder\n\n"
        "Made with ❤️ using Python"
    )
    
    keyboard = [[InlineKeyboardButton("🔙 Back to Menu", callback_data="menu")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        about_text,
        parse_mode='Markdown',
        reply_markup=reply_markup
    )


async def remind_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /remind command."""
    user_id = update.effective_user.id
    
    if not context.args:
        await update.message.reply_text(
            "⏰ *Set a Reminder*\n\n"
            "Usage: `/remind [time] [message]`\n\n"
            "Time formats:\n"
            "• `10m` - 10 minutes\n"
            "• `2h` - 2 hours\n"
            "• `1d` - 1 day\n"
            "• `30s` - 30 seconds\n\n"
            "Example: `/remind 30m Call mom`\n"
            "Example: `/remind 2h Take out trash`",
            parse_mode='Markdown'
        )
        return
    
    try:
        # Parse time and message
        time_str = context.args[0]
        message = ' '.join(context.args[1:])
        
        if not message:
            await update.message.reply_text(
                "❌ Please provide a message!\n"
                "Example: `/remind 30m Call mom`",
                parse_mode='Markdown'
            )
            return
        
        # Parse time
        if time_str.endswith('s'):
            seconds = int(time_str[:-1])
        elif time_str.endswith('m'):
            seconds = int(time_str[:-1]) * 60
        elif time_str.endswith('h'):
            seconds = int(time_str[:-1]) * 3600
        elif time_str.endswith('d'):
            seconds = int(time_str[:-1]) * 86400
        else:
            await update.message.reply_text(
                "❌ Invalid time format!\n"
                "Use: `10m`, `2h`, `1d`, `30s`",
                parse_mode='Markdown'
            )
            return
        
        reminder_time = datetime.now() + timedelta(seconds=seconds)
        
        # Save to database
        add_reminder(user_id, message, reminder_time)
        
        # Format time for display
        time_display = reminder_time.strftime("%Y-%m-%d %H:%M:%S")
        
        await update.message.reply_text(
            f"✅ *Reminder set!*\n\n"
            f"📝 Message: {message}\n"
            f"⏰ Time: {time_display}\n\n"
            f"I'll remind you in {time_str}.",
            parse_mode='Markdown'
        )
        
    except Exception as e:
        logger.error(f"Error setting reminder: {e}")
        await update.message.reply_text(
            "❌ Error setting reminder. Please try again.\n"
            "Format: `/remind 30m Your message`",
            parse_mode='Markdown'
        )


async def list_reminders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /list command."""
    user_id = update.effective_user.id
    
    reminders = get_user_reminders(user_id)
    
    if not reminders:
        await update.message.reply_text(
            "📋 *No active reminders*\n\n"
            "Use `/remind` to set a reminder!",
            parse_mode='Markdown'
        )
        return
    
    response = "📋 *Your Active Reminders:*\n\n"
    for idx, (reminder_id, text, time_str) in enumerate(reminders, 1):
        response += f"{idx}. {text}\n"
        response += f"   ⏰ {time_str}\n\n"
    
    keyboard = [
        [InlineKeyboardButton("🔙 Back to Menu", callback_data="menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        response,
        parse_mode='Markdown',
        reply_markup=reply_markup
    )


async def delete_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /delete command."""
    user_id = update.effective_user.id
    
    reminders = get_user_reminders(user_id)
    
    if not reminders:
        await update.message.reply_text(
            "📋 *No active reminders to delete*\n\n"
            "Use `/remind` to set a reminder!",
            parse_mode='Markdown'
        )
        return
    
    # Create keyboard with reminders
    keyboard = []
    for reminder_id, text, time_str in reminders:
        display_text = f"{text[:30]} - {time_str[:16]}"
        keyboard.append([InlineKeyboardButton(display_text, callback_data=f"del_{reminder_id}")])
    
    keyboard.append([InlineKeyboardButton("🔙 Back to Menu", callback_data="menu")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "❌ *Select a reminder to delete:*\n\n"
        "Tap a reminder to delete it.",
        parse_mode='Markdown',
        reply_markup=reply_markup
    )


async def schedule_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /schedule command."""
    await update.message.reply_text(
        "🗓️ *Weekly Schedule*\n\n"
        "This feature is coming soon!\n"
        "You'll be able to manage your weekly schedule here.\n\n"
        "📝 For now, you can use `/remind` to set reminders.",
        parse_mode='Markdown'
    )


# ============= CALLBACK QUERY HANDLERS =============

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle button callbacks."""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    user_id = query.from_user.id
    
    # ===== MENU =====
    if data == "menu":
        keyboard = [
            [
                InlineKeyboardButton("⏰ Set Reminder", callback_data="remind"),
                InlineKeyboardButton("📋 My Reminders", callback_data="list"),
            ],
            [
                InlineKeyboardButton("🗓️ Weekly Schedule", callback_data="schedule"),
                InlineKeyboardButton("❌ Delete Reminder", callback_data="delete"),
            ],
            [
                InlineKeyboardButton("ℹ️ About", callback_data="about"),
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            "📅 *Welcome to ScheduleBot!*\n\nWhat would you like to do?",
            parse_mode='Markdown',
            reply_markup=reply_markup
        )
    
    # ===== REMIND =====
    elif data == "remind":
        await query.edit_message_text(
            "⏰ *Set a Reminder*\n\n"
            "Use the `/remind` command:\n"
            "`/remind 30m Your message`\n\n"
            "Time formats:\n"
            "• `10m` - 10 minutes\n"
            "• `2h` - 2 hours\n"
            "• `1d` - 1 day\n"
            "• `30s` - 30 seconds",
            parse_mode='Markdown'
        )
    
    # ===== LIST =====
    elif data == "list":
        reminders = get_user_reminders(user_id)
        
        if not reminders:
            response = "📋 *No active reminders*\n\nUse `/remind` to set a reminder!"
        else:
            response = "📋 *Your Active Reminders:*\n\n"
            for idx, (reminder_id, text, time_str) in enumerate(reminders, 1):
                response += f"{idx}. {text}\n"
                response += f"   ⏰ {time_str}\n\n"
        
        keyboard = [[InlineKeyboardButton("🔙 Menu", callback_data="menu")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            response,
            parse_mode='Markdown',
            reply_markup=reply_markup
        )
    
    # ===== SCHEDULE =====
    elif data == "schedule":
        await query.edit_message_text(
            "🗓️ *Weekly Schedule*\n\n"
            "This feature is coming soon!\n"
            "You'll be able to manage your weekly schedule here.",
            parse_mode='Markdown'
        )
    
    # ===== DELETE =====
    elif data == "delete":
        reminders = get_user_reminders(user_id)
        
        if not reminders:
            await query.edit_message_text(
                "📋 *No active reminders to delete*",
                parse_mode='Markdown'
            )
            return
        
        keyboard = []
        for reminder_id, text, time_str in reminders:
            display_text = f"{text[:30]} - {time_str[:16]}"
            keyboard.append([InlineKeyboardButton(display_text, callback_data=f"del_{reminder_id}")])
        
        keyboard.append([InlineKeyboardButton("🔙 Menu", callback_data="menu")])
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            "❌ *Select a reminder to delete:*",
            parse_mode='Markdown',
            reply_markup=reply_markup
        )
    
    # ===== ABOUT =====
    elif data == "about":
        about_text = (
            "ℹ️ *About ScheduleBot*\n\n"
            "📅 Schedule and Reminder Bot\n\n"
            "⏰ *Features:*\n"
            "• Set one-time reminders\n"
            "• View all active reminders\n"
            "• Delete reminders\n"
            "• Automatic notifications\n\n"
            "Made with ❤️ using Python"
        )
        keyboard = [[InlineKeyboardButton("🔙 Menu", callback_data="menu")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            about_text,
            parse_mode='Markdown',
            reply_markup=reply_markup
        )
    
    # ===== DELETE REMINDER =====
    elif data.startswith('del_'):
        reminder_id = int(data.replace('del_', ''))
        delete_reminder(reminder_id)
        
        await query.edit_message_text(
            "✅ *Reminder deleted successfully!*",
            parse_mode='Markdown'
        )


# ============= MAIN FUNCTION =============

def main():
    """Start the bot."""
    try:
        # Initialize database
        init_db()
        
        # Create application
        application = Application.builder().token(BOT_TOKEN).build()
        
        # Command handlers
        application.add_handler(CommandHandler("start", start))
        application.add_handler(CommandHandler("about", about))
        application.add_handler(CommandHandler("remind", remind_command))
        application.add_handler(CommandHandler("list", list_reminders))
        application.add_handler(CommandHandler("delete", delete_command))
        application.add_handler(CommandHandler("schedule", schedule_command))
        
        # Callback handler
        application.add_handler(CallbackQueryHandler(button_handler))
        
        # Start background reminder checker
        reminder_thread = threading.Thread(
            target=check_reminders,
            args=(application,),
            daemon=True
        )
        reminder_thread.start()
        
        logger.info("🚀 Bot started successfully!")
        logger.info(f"📱 Bot username: @{BOT_USERNAME}")
        logger.info("⏰ Reminder checker thread started")
        
        application.run_polling(allowed_updates=Update.ALL_TYPES)
    
    except Exception as e:
        logger.error(f"❌ Fatal error: {e}")
        raise


if __name__ == '__main__':
    main()
