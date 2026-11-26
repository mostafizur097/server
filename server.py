import os
import re
import time
import html
from collections import defaultdict, deque

import requests
from dotenv import load_dotenv
from flask import Flask, request, jsonify, send_from_directory

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Load Telegram credentials from the separate .env.video file.
load_dotenv(dotenv_path=os.path.join(BASE_DIR, ".env.video"))

app = Flask(__name__, static_folder=None)

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()
PORT = int(os.getenv("PORT", "5000"))

# In-memory per-IP rate limit: max 5 submissions per 10 minutes.
# For production/multi-worker hosting, use Redis or a database.
submissions = defaultdict(deque)
RATE_LIMIT = 5
WINDOW_SECONDS = 600


def clean(value, max_length):
    return str(value or "").strip()[:max_length]


@app.get("/")
def home():
    return send_from_directory(BASE_DIR, "index.html")


@app.post("/api/submit")
def submit():
    now = time.time()

    # Only trust X-Forwarded-For when running behind a proxy you control.
    if os.getenv("TRUST_PROXY", "0") == "1":
        ip = request.headers.get(
            "X-Forwarded-For", request.remote_addr or "unknown"
        ).split(",")[0].strip()
    else:
        ip = request.remote_addr or "unknown"

    recent = submissions[ip]
    while recent and now - recent[0] > WINDOW_SECONDS:
        recent.popleft()

    if len(recent) >= RATE_LIMIT:
        return jsonify(
            ok=False,
            message="অনেকবার চেষ্টা করা হয়েছে। কিছুক্ষণ পরে আবার চেষ্টা করুন।"
        ), 429

    data = request.get_json(silent=True) or {}
    action = clean(data.get("action"), 40)
    email = clean(data.get("email"), 120).lower()

    allowed_actions = {
        "login": "Login form submitted",
        "signup": "Signup form submitted",
        "password_reset_request": "Password reset requested",
    }
    if action not in allowed_actions:
        return jsonify(ok=False, message="অবৈধ অনুরোধ।"), 400
    if not re.fullmatch(r"[^@\\s]+@[^@\\s]+\\.[^@\\s]+", email):
        return jsonify(ok=False, message="সঠিক ইমেইল ঠিকানা লিখুন।"), 400

    if not BOT_TOKEN or not CHAT_ID:
        app.logger.error("Telegram credentials are missing in .env.video")
        return jsonify(ok=False, message="সার্ভার সেটআপ সম্পূর্ণ হয়নি।"), 500

    # Passwords and OTPs are deliberately never collected or forwarded.
    message = (
        "<b>Website notification</b>\\n\\n"
        f"<b>Action:</b> {html.escape(allowed_actions[action])}\\n"
        f"<b>Email:</b> {html.escape(email)}\\n"
        "<b>Password:</b> Not collected or transmitted"
    )

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

    try:
        response = requests.post(
            url,
            json={
                "chat_id": CHAT_ID,
                "text": message,
                "parse_mode": "HTML"
            },
            timeout=15
        )
        response.raise_for_status()
        result = response.json()
        if not result.get("ok"):
            raise RuntimeError("Telegram API returned an unsuccessful response")
    except Exception:
        app.logger.exception("Telegram delivery failed")
        return jsonify(
            ok=False,
            message="Telegram-এ পাঠানো যায়নি। পরে আবার চেষ্টা করুন।"
        ), 502

    recent.append(now)
    return jsonify(ok=True, message="নোটিফিকেশন সফলভাবে Telegram-এ পাঠানো হয়েছে।")


if __name__ == "__main__":
    # Local development only. Use HTTPS + a production WSGI server when hosting.
    app.run(host="0.0.0.0", port=PORT, debug=False)
