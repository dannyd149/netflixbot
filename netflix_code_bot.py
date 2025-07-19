#!/usr/bin/env python3
# File: netflix_code_bot.py

import os
import base64
import re
import sys
import json
import subprocess
import asyncio
from bs4 import BeautifulSoup
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from playwright.async_api import async_playwright, Error as PlaywrightError
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters
)
from google.auth.transport.requests import Request
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configuration
EXPECTED_FILENAME = "netflix_code_bot.py"
SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']
TARGET_SENDER = "info@account.netflix.com"
LINK_REGEX = re.compile(
    r'(https://www\.netflix\.com/(?:link|account/travel)/verify[^\s"\']+)|'
    r'onclick="[^"]*(https://www\.netflix\.com/(?:link|account/travel)/verify[^\'\"]+)|'
    r'data-href=\"(https://www\.netflix\.com/(?:link|account/travel)/verify[^\"\s]+)'
)

# Environment variables with fallbacks
TELEGRAM_BOT_TOKEN = os.getenv("8067606353:AAFuzO4D61SYBXhnSUZGdvGjr_RXfixuy5M")
if not TELEGRAM_BOT_TOKEN:
    sys.exit("[ERROR] TELEGRAM_BOT_TOKEN environment variable not set")

ADMIN_ID = int(os.getenv("ADMIN_ID", "767079242"))
ALLOWED_DOMAIN = os.getenv("ALLOWED_DOMAIN", "elwood.club")
GMAIL_ACCOUNT = os.getenv("GMAIL_ACCOUNT")
USER_DB_PATH = os.getenv("USER_DB_PATH", "authorized_users.json")
TOKEN_DIR = os.getenv("TOKEN_DIR", "tokens")

# Create required directories
os.makedirs(TOKEN_DIR, exist_ok=True)

def load_authorized_users():
    try:
        if os.path.exists(USER_DB_PATH):
            with open(USER_DB_PATH, "r") as f:
                return json.load(f)
    except Exception:
        pass
    return []

def save_authorized_users(users):
    with open(USER_DB_PATH, "w") as f:
        json.dump(users, f)

def authenticate_gmail():
    token_file = os.path.join(TOKEN_DIR, f'{GMAIL_ACCOUNT}.json')
    if not os.path.exists(token_file):
        token_json = os.getenv("GMAIL_TOKEN_JSON")
        if token_json:
            with open(token_file, "w") as f:
                f.write(token_json)
        else:
            raise RuntimeError("Missing Gmail token. Please provide GMAIL_TOKEN_JSON.")
    
    creds = Credentials.from_authorized_user_file(token_file, SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
            with open(token_file, "w") as token:
                token.write(creds.to_json())
        else:
            raise RuntimeError("Invalid Gmail credentials.")
    return build('gmail', 'v1', credentials=creds)

async def extract_code_from_netflix_link(link):
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            
            await page.goto(link, timeout=120000)
            await page.wait_for_timeout(5000)
            
            # Try multiple selectors
            selectors = [
                "text=/\\d{4}/",
                "div.code-display",
                ".verification-code",
                "div[data-uia='verification-code']"
            ]
            
            for selector in selectors:
                try:
                    locator = page.locator(selector).first
                    if await locator.count() > 0:
                        text = await locator.text_content()
                        if text:
                            found = re.search(r'\d{4}', text)
                            if found:
                                return found.group(0)
                except:
                    continue
            
            await page.screenshot(path="debug_page.png")
            raise ValueError("Code not found on page.")
            
    except PlaywrightError as e:
        raise RuntimeError(f"Browser error: {str(e)}")

async def send_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    authorized_users = load_authorized_users()
    
    if user.id not in authorized_users and user.id != ADMIN_ID:
        await update.message.reply_text("❌ You're not authorized.")
        return

    if not context.args or len(context.args) != 1:
        await update.message.reply_text("ℹ️ Usage: /getcode user@elwood.club")
        return

    user_email = context.args[0].lower().strip()
    if not user_email.endswith(f"@{ALLOWED_DOMAIN}"):
        await update.message.reply_text(f"❌ Only @{ALLOWED_DOMAIN} emails allowed.")
        return

    try:
        msg = await update.message.reply_text("⏳ Processing...")
        
        service = authenticate_gmail()
        link = find_latest_netflix_email(service, user_email)
        code = await extract_code_from_netflix_link(link)
        
        await context.bot.delete_message(
            chat_id=update.effective_chat.id,
            message_id=msg.message_id
        )
        
        await update.message.reply_text(
            f"🎉 Netflix code for {user_email}:\n"
            f"🔑 <code>{code}</code>\n\n"
            "⚠️ Expires in 15 minutes.",
            parse_mode="HTML"
        )
        
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {str(e)}")

async def add_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ Admin only.")
        return
        
    if not context.args:
        await update.message.reply_text("ℹ️ Usage: /adduser USER_ID")
        return
        
    try:
        user_id = int(context.args[0])
        users = load_authorized_users()
        if user_id not in users:
            users.append(user_id)
            save_authorized_users(users)
            await update.message.reply_text(f"✅ Added user {user_id}")
        else:
            await update.message.reply_text("ℹ️ User already authorized.")
    except ValueError:
        await update.message.reply_text("❌ Invalid user ID.")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 Netflix Code Bot\n\n"
        "Commands:\n"
        "/getcode email@elwood.club - Get code\n"
        "/adduser USER_ID - Add user (admin)\n"
        "/listusers - Show authorized users"
    )

async def setup_playwright():
    print("Setting up Playwright...")
    subprocess.run(["playwright", "install", "chromium"], check=True)
    subprocess.run(["playwright", "install-deps"], check=True)
    print("Playwright setup complete")

def main():
    # Verify environment
    if not GMAIL_ACCOUNT:
        sys.exit("[ERROR] GMAIL_ACCOUNT not set")

    # Setup Playwright
    asyncio.run(setup_playwright())

    # Create bot application
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    
    # Add handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("getcode", send_code))
    app.add_handler(CommandHandler("adduser", add_user))
    
    print("✅ Bot is running...")
    app.run_polling()

if __name__ == '__main__':
    main()
