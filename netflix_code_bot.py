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
from telegram import Update, Bot
from telegram.ext import Application, CommandHandler, ContextTypes
from google.auth.transport.requests import Request

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

TELEGRAM_BOT_TOKEN = os.getenv("8067606353:AAFuzO4D61SYBXhnSUZGdvGjr_RXfixuy5M")
if not TELEGRAM_BOT_TOKEN:
    print("[ERROR] TELEGRAM_BOT_TOKEN not set. Using fallback for local dev.")
    TELEGRAM_BOT_TOKEN = "8067606353:AAFuzO4D61SYBXhnSUZGdvGjr_RXfixuy5M"

ADMIN_ID = 767079242
ALLOWED_DOMAIN = "elwood.club"
GMAIL_ACCOUNT = "temp.elwood.club@gmail.com"
USER_DB_PATH = "authorized_users.json"


def load_authorized_users():
    if os.path.exists(USER_DB_PATH):
        with open(USER_DB_PATH, "r") as f:
            return json.load(f)
    return []

def save_authorized_users(users):
    with open(USER_DB_PATH, "w") as f:
        json.dump(users, f)


def authenticate_gmail():
    token_file = f'tokens/{GMAIL_ACCOUNT}.json'
    if not os.path.exists(token_file):
        raise RuntimeError("Missing Gmail token. Please authenticate manually once and save token JSON file.")
    creds = Credentials.from_authorized_user_file(token_file, SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
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

        with open("debug_email.html", "w", encoding="utf-8") as f:
            f.write(decoded)

        matches = LINK_REGEX.findall(decoded)
        all_links = [x for match in matches for x in match if x]

        if not all_links:
            continue

        print("[DEBUG] Found Netflix links:", all_links)
        return all_links[0]

    raise ValueError("Could not find a Get Code link for that email.")


def ensure_playwright_installed():
    try:
        import playwright
    except ImportError:
        print("[INFO] Installing Playwright...")
        subprocess.run([sys.executable, "-m", "pip", "install", "playwright"], check=True)
        subprocess.run([sys.executable, "-m", "playwright", "install"], check=True)


async def extract_code_from_netflix_link(link):
    ensure_playwright_installed()
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            await page.goto(link, timeout=60000)
            await page.wait_for_timeout(3000)
            locator = page.locator("text=/\\d{4}/").first
            if locator:
                text = await locator.text_content()
                if text:
                    found = re.search(r'\d{4}', text)
                    if found:
                        await browser.close()
                        return found.group(0)
            await page.screenshot(path="failed_netflix_page.png")
            await browser.close()
    except PlaywrightError as e:
        raise RuntimeError("Playwright failed: " + str(e))

    raise ValueError("Code not found on Netflix verification page.")


async def send_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        user_id = update.effective_user.id
        authorized_users = load_authorized_users()
        if user_id not in authorized_users and user_id != ADMIN_ID:
            await update.message.reply_text("You're not authorized. Ask the admin to add you.")
            return

        if not context.args or len(context.args) != 1:
            await update.message.reply_text("Usage: /getcode user@elwood.club")
            return

        user_email = context.args[0].strip()
        if not user_email.endswith(f"@{ALLOWED_DOMAIN}"):
            await update.message.reply_text("Unauthorized email domain.")
            return

        await update.message.reply_text(f"Fetching Netflix code for {user_email}...")
        service = authenticate_gmail()
        verify_link = find_latest_netflix_email(service, user_email)
        code = await extract_code_from_netflix_link(verify_link)
        await update.message.reply_text(f"Netflix code for {user_email} is: {code}")

    except Exception as e:
        await update.message.reply_text(f"Error: {str(e)}")


async def add_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("Only the admin can add users.")
        return
    if not context.args or len(context.args) != 1:
        await update.message.reply_text("Usage: /adduser <telegram_user_id>")
        return
    try:
        uid = int(context.args[0])
        users = load_authorized_users()
        if uid not in users:
            users.append(uid)
            save_authorized_users(users)
            await update.message.reply_text(f"User {uid} added.")
        else:
            await update.message.reply_text("User already authorized.")
    except ValueError:
        await update.message.reply_text("Invalid user ID.")


async def list_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("Only the admin can list users.")
        return
    users = load_authorized_users()
    await update.message.reply_text(f"Authorized users: {users}")


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Welcome! Use /getcode user@elwood.club to fetch your Netflix access code.")


def main():
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("getcode", send_code))
    app.add_handler(CommandHandler("adduser", add_user))
    app.add_handler(CommandHandler("listusers", list_users))
    print("Bot is running...")
    app.run_polling()


if __name__ == '__main__':
    main()
