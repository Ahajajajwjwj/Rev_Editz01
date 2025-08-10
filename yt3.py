import os
import re
import json
import asyncio
import subprocess
import logging
import uuid

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyParameters
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters
from telegram.error import BadRequest

# --- 🔐 Configuration ---
BOT_TOKEN = "7758114691:AAFDJm010k6FsVkiTrxCuclwnukrJFpgkR8"
ADMIN_IDS = [7251749429]
REQUIRED_CHANNEL_IDS = [-1002786152092,]  # @payment0126,
COOKIES_FILE = "/data/data/com.termux/files/home/storage/downloads/cookies.txt"
USERS_FILE = "users.json"

# --- Logging ---
logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# --- User System ---
def load_users():
    if not os.path.exists(USERS_FILE):
        return set()
    try:
        with open(USERS_FILE, "r") as f:
            return set(json.load(f))
    except:
        return set()

def save_user(user_id: int):
    users = load_users()
    if user_id not in users:
        users.add(user_id)
        with open(USERS_FILE, "w") as f:
            json.dump(list(users), f, indent=4)

# --- Channel Join Check ---
async def is_user_member(context: ContextTypes.DEFAULT_TYPE, user_id: int) -> bool:
    for channel_id in REQUIRED_CHANNEL_IDS:
        try:
            member = await context.bot.get_chat_member(chat_id=channel_id, user_id=user_id)
            if member.status not in ["member", "administrator", "creator"]:
                return False
        except:
            return False
    return True

# --- Commands ---
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    save_user(user.id)
    if await is_user_member(context, user.id):
        await update.message.reply_text("✅ You're verified! Send one or more video links (YouTube, Instagram, Facebook, Pinterest).")
    else:
        keyboard = [[InlineKeyboardButton("🟢 I Have Joined All", callback_data="check_joined")]]
        markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            "⛔ Join all required channels to use the bot:\n➡️ @payment0126\n➡️ @Mixhubfree\n➡️ @BugsAllRounder01",
            reply_markup=markup
        )

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id in ADMIN_IDS:
        users = load_users()
        await update.message.reply_text(f"📊 Total Users: {len(users)}")

# --- Progress Bar ---
def create_progress_bar(percent: float, length: int = 10) -> str:
    filled = int(length * percent / 100)
    return f"[{'█' * filled}{'░' * (length - filled)}] {percent:.1f}%"

# --- Video Processing ---
async def download_and_upload_video(context: ContextTypes.DEFAULT_TYPE, chat_id: int, url: str, action: str):
    status_msg = await context.bot.send_message(chat_id=chat_id, text=f"🔄 Preparing download for:\n{url}")

    if not os.path.exists(COOKIES_FILE):
        await context.bot.edit_message_text(
            "❌ Cookie file not found.",
            chat_id=chat_id, message_id=status_msg.message_id
        )
        return

    temp_filename = f"{uuid.uuid4()}.mp4"
    last_update_time = 0

    try:
        process = await asyncio.create_subprocess_exec(
            "yt-dlp",
            "--cookies", COOKIES_FILE,
            "--referer", "https://terabox.com",
            "-f", "best",
            "--no-playlist",
            "--newline",
            "-o", temp_filename,
            url,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )

        progress_regex = re.compile(r"\[download\]\s+(\d{1,3}\.\d+)%")

        while True:
            line_bytes = await process.stdout.readline()
            if not line_bytes:
                break
            line = line_bytes.decode("utf-8", errors="ignore").strip()
            match = progress_regex.search(line)
            if match:
                percent = float(match.group(1))
                now = asyncio.get_event_loop().time()
                if now - last_update_time > 1.5:
                    progress_text = f"⏳ Downloading...\n{create_progress_bar(percent)}"
                    try:
                        await context.bot.edit_message_text(
                            text=progress_text,
                            chat_id=chat_id,
                            message_id=status_msg.message_id
                        )
                        last_update_time = now
                    except BadRequest as e:
                        if "message is not modified" not in str(e).lower():
                            logger.warning(f"Progress update error: {e}")

        return_code = await process.wait()
        if return_code != 0:
            err = (await process.stderr.read()).decode("utf-8", errors="ignore")
            await context.bot.edit_message_text(
                f"❌ Download failed:\n\n`{err.strip().splitlines()[-1]}`",
                chat_id=chat_id, message_id=status_msg.message_id, parse_mode="Markdown"
            )
            return

        if not os.path.exists(temp_filename) or os.path.getsize(temp_filename) == 0:
            await context.bot.edit_message_text(
                "❌ Download failed: no file created.",
                chat_id=chat_id, message_id=status_msg.message_id
            )
            return

        await context.bot.edit_message_text(
            "✅ Download complete! Uploading...",
            chat_id=chat_id, message_id=status_msg.message_id
        )

        with open(temp_filename, "rb") as f:
            caption = f"📥 Downloaded via @ssVideodowloaderbot\n📎 Link: {url}"
            if action == "see_video":
                await context.bot.send_video(chat_id=chat_id, video=f, caption=caption, supports_streaming=True)
            else:
                await context.bot.send_document(chat_id=chat_id, document=f, caption=caption)

        await context.bot.delete_message(chat_id=chat_id, message_id=status_msg.message_id)

    except Exception as e:
        logger.error(f"Download error: {e}")
        await context.bot.edit_message_text(
            f"❌ Error occurred: `{type(e).__name__}: {e}`",
            chat_id=chat_id, message_id=status_msg.message_id, parse_mode="Markdown"
        )
    finally:
        if os.path.exists(temp_filename):
            os.remove(temp_filename)

# --- Button Handler ---
async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    data = query.data

    if data == "check_joined":
        if await is_user_member(context, user_id):
            await query.edit_message_text("✅ Verified! Now send one or more video links (one per line).")
        else:
            await query.answer("❌ You haven't joined all channels.", show_alert=True)

# --- Link Handler (Multiple Links Support) ---
async def handle_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not await is_user_member(context, user_id):
        await update.message.reply_text("⛔ Please join all channels first. Use /start.")
        return

    text = update.message.text.strip()
    urls = [line.strip() for line in text.splitlines() if re.match(r'https?://', line)]

    if not urls:
        await update.message.reply_text("❌ No valid URLs found in your message.")
        return

    await update.message.reply_text(f"📥 Found {len(urls)} link(s). Starting download...")

    for url in urls:
        context.user_data['url_to_process'] = url
        await download_and_upload_video(context, update.effective_chat.id, url, "download_video")

# --- Unknown Message Fallback ---
async def fallback_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🤖 Send one or more video links (each on a new line) or use /start.")

# --- Start Bot ---
def main():
    logger.info("🚀 Bot Starting...")

    try:
        subprocess.run(["yt-dlp", "--version"], check=True, capture_output=True)
    except Exception:
        logger.critical("❌ yt-dlp is not installed.")
        return

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("stats", stats_command))
    app.add_handler(CallbackQueryHandler(button_callback))
    app.add_handler(MessageHandler(filters.TEXT & filters.Regex(r'https?://'), handle_link))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, fallback_text))

    logger.info("✅ Bot is running.")
    app.run_polling()

if __name__ == "__main__":
    main()