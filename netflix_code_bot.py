#!/usr/bin/env python3
# File: netflix_code_bot.py

import os
import base64
import re
import time
import sys
import json
from bs4 import BeautifulSoup
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
import asyncio
import subprocess
from playwright.async_api import async_playwright, Error as PlaywrightError
import requests
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from google.auth.transport.requests import Request
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

EXPECTED_FILENAME = "netflix_code_bot.py"
current_script = os.path.basename(__file__)
if current_script != EXPECTED_FILENAME:
    sys.exit(f"[ERROR] Please rename the script to '{EXPECTED_FILENAME}' and try again. Current: '{current_script}'")

SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']
TARGET_SENDER = "info@account.netflix.com"
LINK_REGEX = re.compile(
    r'(https://www\.netflix\.com/(?:link|account/travel)/verify[^\s"\']+)|'
    r'onclick="[^"]*(https://www\.netflix\.com/(?:link|account/travel)/verify[^\'\"]+)|'
    r'data-href=\"(https://www\.netflix\.com/(?:link|account/travel)/verify[^\"\s]+)'
)

# Environment variables configuration
TELEGRAM_BOT_TOKEN = os.getenv("8067606353:AAFuzO4D61SYBXhnSUZGdvGjr_RXfixuy5M")
if not TELEGRAM_BOT_TOKEN:
    sys.exit("[ERROR] TELEGRAM_BOT_TOKEN environment variable not set")

ADMIN_ID = int(os.getenv("ADMIN_ID", "767079242"))
ALLOWED_DOMAIN = os.getenv("ALLOWED_DOMAIN", "elwood.club")
GMAIL_ACCOUNT = os.getenv("GMAIL_ACCOUNT")
if not GMAIL_ACCOUNT:
    sys.exit("[ERROR] GMAIL_ACCOUNT environment variable not set")

USER_DB_PATH = os.getenv("USER_DB_PATH", "authorized_users.json")
TOKEN_DIR = os.getenv("TOKEN_DIR", "tokens")

# Create required directories if they don't exist
os.makedirs(TOKEN_DIR, exist_ok=True)

def load_authorized_users():
    if os.path.exists(USER_DB_PATH):
        try:
            with open(USER_DB_PATH, "r") as f:
                return json.load(f)
        except json.JSONDecodeError:
            return []
    return []

def save_authorized_users(users):
    with open(USER_DB_PATH, "w") as f:
        json.dump(users, f)

def authenticate_gmail():
    token_file = os.path.join(TOKEN_DIR, f'{GMAIL_ACCOUNT}.json')
    if not os.path.exists(token_file):
        # Try to get token from environment variable
        token_json = os.getenv("GMAIL_TOKEN_JSON")
        if token_json:
            with open(token_file, "w") as f:
                f.write(token_json)
        else:
            raise RuntimeError(f"Missing Gmail token at {token_file}. Please authenticate manually once and save token JSON file.")
    
    creds = Credentials.from_authorized_user_file(token_file, SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
            # Save the refreshed credentials
            with open(token_file, "w") as token:
                token.write(creds.to_json())
        else:
            raise RuntimeError("Invalid or expired Gmail token. Please re-authenticate manually.")
    return build('gmail', 'v1', credentials=creds)

def find_latest_netflix_email(service, target_email):
    query = f'from:{TARGET_SENDER} to:{target_email}'
    results = service.users().messages().list(userId='me', q=query, maxResults=10).execute()
    messages = results.get('messages', [])

    for msg in messages:
        message = service.users().messages().get(userId='me', id=msg['id'], format='full').execute()
        payload = message['payload']
        parts = payload.get('parts', [])
        data = ''

        if parts:
            for part in parts:
                if part['mimeType'] == 'text/html':
                    data = part['body'].get('data')
                    break
            if not data:
                for part in parts:
                    if part['mimeType'] == 'text/plain':
                        data = part['body'].get('data')
                        break
        else:
            data = payload['body'].get('data')

        if not data:
            continue

        decoded = base64.urlsafe_b64decode(data.encode('UTF-8')).decode('UTF-8')

        matches = LINK_REGEX.findall(decoded)
        all_links = [x for match in matches for x in match if x]

        if not all_links:
            continue

        print("[DEBUG] Found Netflix links:", all_links)
        return all_links[0]

    raise ValueError("Could not find a Get Code link for that email.")

async def extract_code_from_netflix_link(link):
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            
            # Set longer timeout for Render environment
            await page.goto(link, timeout=120000)
            await page.wait_for_timeout(5000)  # Additional wait time
            
            # Try multiple selectors for robustness
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
                                await browser.close()
                                return found.group(0)
                except:
                    continue
            
            # Fallback to screenshot for debugging
            await page.screenshot(path="netflix_verification_page.png")
            await browser.close()
            raise ValueError("Code element not found on Netflix verification page.")
            
    except PlaywrightError as e:
        raise RuntimeError(f"Playwright failed: {str(e)}")
    except Exception as e:
        raise RuntimeError(f"Unexpected error: {str(e)}")

async def send_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        user_id = update.effective_user.id
        authorized_users = load_authorized_users()
        
        if user_id not in authorized_users and user_id != ADMIN_ID:
            await update.message.reply_text("🚫 You're not authorized. Ask the admin to add you.")
            return

        if not context.args or len(context.args) != 1:
            await update.message.reply_text("ℹ️ Usage: /getcode user@elwood.club")
            return

        user_email = context.args[0].strip().lower()
        if not user_email.endswith(f"@{ALLOWED_DOMAIN}"):
            await update.message.reply_text(f"🚫 Unauthorized email domain. Only @{ALLOWED_DOMAIN} emails are allowed.")
            return

        processing_msg = await update.message.reply_text(f"⏳ Fetching Netflix code for {user_email}...")
        
        try:
            service = authenticate_gmail()
            verify_link = find_latest_netflix_email(service, user_email)
            code = await extract_code_from_netflix_link(verify_link)
            
            # Delete the processing message
            await context.bot.delete_message(
                chat_id=update.effective_chat.id,
                message_id=processing_msg.message_id
            )
            
            await update.message.reply_text(
                f"🎉 Netflix code for {user_email}:\n"
                f"🔑 <code>{code}</code>\n\n"
                "⚠️ This code expires in 15 minutes.",
                parse_mode="HTML"
            )
            
        except Exception as e:
            await context.bot.delete_message(
                chat_id=update.effective_chat.id,
                message_id=processing_msg.message_id
            )
            await update.message.reply_text(f"❌ Error: {str(e)}")

    except Exception as e:
        await update.message.reply_text(f"❌ Unexpected error: {str(e)}")

async def add_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("🚫 Only the admin can add users.")
        return
        
    if not context.args or len(context.args) != 1:
        await update.message.reply_text("ℹ️ Usage: /adduser <telegram_user_id>")
        return
        
    try:
        uid = int(context.args[0])
        users = load_authorized_users()
        if uid not in users:
            users.append(uid)
            save_authorized_users(users)
            await update.message.reply_text(f"✅ User {uid} added.")
        else:
            await update.message.reply_text("ℹ️ User already authorized.")
    except ValueError:
        await update.message.reply_text("❌ Invalid user ID.")

async def list_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("🚫 Only the admin can list users.")
        return
        
    users = load_authorized_users()
    await update.message.reply_text(f"👥 Authorized users: {', '.join(map(str, users))}")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = (
        "🤖 <b>Netflix Code Bot</b>\n\n"
        "Available commands:\n"
        "/start - Show this help\n"
        "/getcode user@elwood.club - Get Netflix code\n"
        "/adduser <user_id> - (Admin) Add authorized user\n"
        "/listusers - (Admin) List authorized users\n\n"
        "⚠️ Only works with @elwood.club emails"
    )
    await update.message.reply_text(help_text, parse_mode="HTML")

async def post_init(application: Application):
    # Ensure Playwright browsers are installed
    print("Installing Playwright browsers...")
    subprocess.run(["playwright", "install", "chromium"], check=True)
    subprocess.run(["playwright", "install-deps"], check=True)
    print("Playwright setup complete")

def main():
    # Ensure required environment variables are set
    required_vars = ["TELEGRAM_BOT_TOKEN", "GMAIL_ACCOUNT"]
    missing_vars = [var for var in required_vars if not os.getenv(var)]
    if missing_vars:
        sys.exit(f"Missing required environment variables: {', '.join(missing_vars)}")

    # Initialize the bot
    app = Application.builder() \
        .token(TELEGRAM_BOT_TOKEN) \
        .post_init(post_init) \
        .build()
        
    # Add handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("getcode", send_code))
    app.add_handler(CommandHandler("adduser", add_user))
    app.add_handler(CommandHandler("listusers", list_users))

    print("✅ Bot is starting...")
    app.run_polling()

if __name__ == '__main__':
    # Install Playwright if not already installed
    try:
        import playwright
    except ImportError:
        print("Installing Playwright...")
        subprocess.run([sys.executable, "-m", "pip", "install", "playwright"], check=True)
    
    main()
