#!/usr/bin/env python3
"""
STREAM RED - Secure Login Event Logger
Telegram format:
Login ID / Email, Comment, Date, Time, IP Address, Device,
Login Status, Attempt Count.

IMPORTANT:
- Passwords and password hashes are NEVER sent to Telegram.
- Passwords are verified server-side and stored only as secure hashes.
- Use this only for an application you own/administer, with an appropriate
  privacy notice and access controls.
"""
from __future__ import annotations

import os
import re
import sqlite3
import secrets
import logging
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import requests
from dotenv import load_dotenv
from flask import Flask, request, jsonify, session, send_from_directory
from werkzeug.security import generate_password_hash, check_password_hash

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env.server")

app = Flask(__name__, static_folder=None)
app.secret_key = os.getenv("FLASK_SECRET_KEY") or secrets.token_hex(32)
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SECURE=os.getenv("COOKIE_SECURE", "0") == "1",
    SESSION_COOKIE_SAMESITE="Lax",
    PERMANENT_SESSION_LIFETIME=60 * 60 * 24 * 30,
)

DB_PATH = Path(os.getenv("DATABASE_PATH", str(BASE_DIR / "streamred.db")))
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()
PORT = int(os.getenv("PORT", "5000"))
TIMEZONE = os.getenv("APP_TIMEZONE", "Asia/Dhaka")
TRUST_PROXY = os.getenv("TRUST_PROXY", "0") == "1"
MAX_FAILED_PER_IP = int(os.getenv("MAX_FAILED_PER_IP", "10"))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("streamred")


def connect_db():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with connect_db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS login_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT NOT NULL,
                comment TEXT NOT NULL,
                status TEXT NOT NULL,
                ip_address TEXT NOT NULL,
                device TEXT NOT NULL,
                user_agent TEXT NOT NULL,
                event_time TEXT NOT NULL
            )
        """)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_login_events_email ON login_events(email)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_login_events_ip ON login_events(ip_address)"
        )


def current_datetime():
    now = datetime.now(ZoneInfo(TIMEZONE))
    return now.strftime("%d-%m-%Y"), now.strftime("%I:%M %p")


def get_client_ip():
    # Enable only behind a reverse proxy you own which overwrites this header.
    if TRUST_PROXY:
        forwarded = request.headers.get("X-Forwarded-For", "")
        if forwarded:
            return forwarded.split(",")[0].strip()[:64]
    return (request.remote_addr or "Unknown")[:64]


def get_device():
    ua = (request.headers.get("User-Agent") or "Unknown")[:500]
    low = ua.lower()

    if "android" in low:
        device = "Android"
    elif "iphone" in low or "ipad" in low:
        device = "iPhone/iPad"
    elif "windows" in low:
        device = "Windows"
    elif "macintosh" in low or "mac os" in low:
        device = "Mac"
    elif "linux" in low:
        device = "Linux"
    else:
        device = "Unknown"

    if "edg/" in low:
        browser = "Edge"
    elif "chrome/" in low:
        browser = "Chrome"
    elif "firefox/" in low:
        browser = "Firefox"
    elif "safari/" in low:
        browser = "Safari"
    else:
        browser = "Unknown browser"

    return f"{device} ({browser})", ua


def send_telegram_event(email, comment, status, ip, device, date, clock, count):
    """Send only event metadata. Never pass a password to this function."""
    if not BOT_TOKEN or not CHAT_ID:
        logger.warning("Telegram bot credentials are not configured.")
        return False

    message = (
        "🔐 LOGIN EVENT\n\n"
        f"Login ID / Email: {email or 'Not provided'}\n"
        f"Comment: {comment}\n"
        f"Date: {date}\n"
        f"Time: {clock}\n"
        f"IP Address: {ip}\n"
        f"Device: {device}\n"
        f"Login Status: {status}\n"
        f"Attempt Count: {count}\n\n"
        "Password: NOT collected / NOT sent"
    )

    try:
        response = requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            json={"chat_id": CHAT_ID, "text": message},
            timeout=12,
        )
        response.raise_for_status()
        result = response.json()
        if not result.get("ok"):
            logger.error("Telegram API did not accept the event notification.")
            return False
        return True
    except requests.RequestException:
        logger.exception("Telegram notification delivery failed.")
        return False


def log_login_event(email, status, comment="User submitted login form"):
    """Store event and send Telegram alert. No password argument exists."""
    date, clock = current_datetime()
    ip = get_client_ip()
    device, user_agent = get_device()
    timestamp = f"{date} {clock}"

    with connect_db() as conn:
        conn.execute(
            """INSERT INTO login_events
               (email, comment, status, ip_address, device, user_agent, event_time)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (email[:254], comment[:200], status, ip, device, user_agent, timestamp),
        )
        attempt_count = conn.execute(
            "SELECT COUNT(*) FROM login_events WHERE email = ?",
            (email[:254],),
        ).fetchone()[0]

    send_telegram_event(
        email=email,
        comment=comment,
        status=status,
        ip=ip,
        device=device,
        date=date,
        clock=clock,
        count=attempt_count,
    )
    return attempt_count


def get_json():
    return request.get_json(silent=True) or {}


def valid_email(email):
    return bool(re.fullmatch(r"[^@\s]{1,64}@[^@\s]{1,190}\.[^@\s]{2,}", email))


@app.get("/")
def home():
    return send_from_directory(
        os.path.dirname(os.path.abspath(__file__)),
        "index.html"
    )


@app.get("/api/me")
def me():
    email = session.get("email")
    return jsonify(ok=True, authenticated=bool(email), email=email)


@app.post("/api/signup")
def signup():
    data = get_json()
    email = str(data.get("email", "")).strip().lower()
    password = data.get("password", "")

    if not valid_email(email):
        return jsonify(ok=False, message="Enter a valid email address."), 400
    if not isinstance(password, str) or not 8 <= len(password) <= 128:
        return jsonify(ok=False, message="Password must be 8–128 characters."), 400

    try:
        with connect_db() as conn:
            conn.execute(
                "INSERT INTO users(email, password_hash, created_at) VALUES (?, ?, ?)",
                (email, generate_password_hash(password), datetime.now(ZoneInfo(TIMEZONE)).isoformat()),
            )
    except sqlite3.IntegrityError:
        return jsonify(ok=False, message="An account with this email already exists."), 409

    return jsonify(ok=True, message="Account created. You can now sign in.")


@app.post("/api/login")
def login():
    data = get_json()
    email = str(data.get("email", "")).strip().lower()[:254]
    password = data.get("password", "")

    if not isinstance(password, str):
        password = ""

    # Basic IP-based failed-login throttle.
    ip = get_client_ip()
    with connect_db() as conn:
        recent_failures = conn.execute(
            """SELECT COUNT(*) FROM login_events
               WHERE ip_address = ? AND status = 'Failed'
               AND id IN (
                   SELECT id FROM login_events
                   WHERE ip_address = ?
                   ORDER BY id DESC LIMIT 30
               )""",
            (ip, ip),
        ).fetchone()[0]
        user = conn.execute(
            "SELECT password_hash FROM users WHERE email = ?",
            (email,),
        ).fetchone()

    if recent_failures >= MAX_FAILED_PER_IP:
        log_login_event(email or "Not provided", "Blocked")
        return jsonify(ok=False, message="Too many attempts. Try again later."), 429

    authenticated = bool(
        user and password and check_password_hash(user["password_hash"], password)
    )

    if not authenticated:
        log_login_event(email or "Not provided", "Failed")
        return jsonify(ok=False, message="Incorrect email or password."), 401

    log_login_event(email, "Successful")
    session.clear()
    session["email"] = email
    session.permanent = bool(data.get("remember"))
    return jsonify(ok=True, email=email)


@app.post("/api/logout")
def logout():
    session.clear()
    return jsonify(ok=True)


@app.get("/health")
def health():
    return jsonify(
        ok=True,
        telegram_configured=bool(BOT_TOKEN and CHAT_ID),
        timezone=TIMEZONE,
    )


if __name__ == "__main__":
    init_db()
    # For public hosting use HTTPS + a production WSGI server.
    app.run(host="0.0.0.0", port=PORT, debug=False)
