# VIDEOX --- Telegram-Connected Web Form Backend
A lightweight Flask backend that serves the supplied web.html page and provides a JSON API for forwarding validated form submissions to a Telegram chat.
Project overview
VIDEOX includes: - Original HTML frontend, preserved as supplied. - Flask backend (videox.py). - Telegram Bot API message delivery. - Separate environment configuration (.env.video). - Input validation and HTML escaping. - Basic in-memory rate limiting: 5 accepted submissions per IP per 10 minutes.
Integration note: The supplied web.html currently contains Firebase email/password and Google sign-in flows. It does not currently submit the name, phone, and address fields expected by the Python endpoint. The files are packaged together, but a matching frontend form and fetch("/api/submit", ...) integration are still needed before form data can reach Telegram. The backend does not receive or forward Firebase passwords.
Project structure
VIDEOX/
├── web.html                  # Original HTML frontend (unchanged)
├── videox.py                 # Flask backend + Telegram integration
├── .env.video                # Private Telegram credentials
├── requirements-video.txt    # Python dependencies
└── README.md                 # Project documentation
Requirements
Python 3.9 or newer
Internet access for Telegram API requests
Telegram bot created through @BotFather
Destination Telegram chat ID
Termux on Android, or a computer/server with Python
1. Create and configure your Telegram bot
Open @BotFather in Telegram.
Send /newbot and follow the instructions.
Copy the bot token.
Start a chat with your bot. For a group destination, add the bot to the group and ensure it can send messages.
Obtain the destination chat ID.
Never publish the bot token or commit it to a public repository.
2. Configure .env.video
Edit .env.video and replace the sample values:
TELEGRAM_BOT_TOKEN=PASTE_YOUR_BOT_TOKEN_HERE
TELEGRAM_CHAT_ID=PASTE_YOUR_CHAT_ID_HERE

PORT=5000
TRUST_PROXY=0
The application loads the exact filename .env.video from the same directory as videox.py.
TELEGRAM_BOT_TOKEN: token issued by BotFather.
TELEGRAM_CHAT_ID: destination user, group, or channel chat ID.
PORT: local server port; default is 5000.
TRUST_PROXY: keep 0 unless using a reverse proxy that you control and have configured.
3. Install and run
Termux (Android)
pkg update && pkg upgrade
pkg install python
From the project directory:
pip install -r requirements-video.txt
python videox.py
Open in your phone browser:
http://127.0.0.1:5000
Windows, macOS, or Linux
Create a virtual environment:
python -m venv .venv
Activate it:
# Linux / macOS
source .venv/bin/activate

# Windows PowerShell
.venv\Scripts\Activate.ps1
Install and start:
pip install -r requirements-video.txt
python videox.py
4. API reference
GET /
Serves the original web.html file.
POST /api/submit
Accepts JSON with these fields:
Field         Required   Maximum length Description
name             Yes              100 Submitter name phone            Yes               30 Phone number email             No              120 Email address address          Yes              300 Address comment           No            1,000 Optional comment
Example test request:
curl -X POST http://127.0.0.1:5000/api/submit \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Test User",
    "phone": "+8801700000000",
    "email": "test@example.com",
    "address": "Dhaka, Bangladesh",
    "comment": "Test submission"
  }'
Successful response:
{
  "ok": true,
  "message": "তথ্য সফলভাবে Telegram-এ পাঠানো হয়েছে।"
}
HTTP status   Meaning
200         Message sent successfully 400         Required field missing or invalid data 429         Rate limit reached 500         Server credentials/configuration missing 502         Telegram delivery failed
5. Frontend integration status
The supplied HTML has login, signup, and password-reset forms handled by Firebase Authentication. The Python API is a separate form-submission endpoint and expects name, phone, and address, with optional email and comment.
To connect a legitimate submission form, the frontend must send JSON to /api/submit, for example:
const response = await fetch("/api/submit", {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({
    name: "Test User",
    phone: "+8801700000000",
    email: "test@example.com",
    address: "Dhaka, Bangladesh",
    comment: "Example"
  })
});

const result = await response.json();
This is an integration example only; it is not currently wired into the supplied HTML. Do not send passwords, authentication tokens, or other login secrets to this endpoint.
The Python backend does not implement Firebase authentication, Google OAuth, password reset, premium checkout, or account management. Those features require their own configuration and implementation.
6. Security and production notes
Keep .env.video private. Do not upload it to GitHub.
Use HTTPS for public deployments.
Use a production WSGI server; Flask's built-in server is intended for local development.
The current rate limiter is in memory and resets when the process restarts. It is not shared across multiple workers. Use Redis or a database-backed limiter for production.
Keep TRUST_PROXY=0 unless a trusted reverse proxy is configured correctly.
Explain to users what data is collected, why it is sent to Telegram, and who can access the destination chat. Collect only necessary information.
If the bot token is exposed, revoke or regenerate it through BotFather.
Suggested .gitignore:
.env.video
.venv/
__pycache__/
*.py[cod]
7. Troubleshooting
Issue                               Check
ModuleNotFoundError               Install dependencies with pip install -r requirements-video.txt
Credentials missing                 Ensure .env.video is beside videox.py and variable names are correct
Telegram delivery fails             Verify token, chat ID, internet access, and bot permissions
Page does not open                  Confirm the server is running and use the configured port
API returns 400                   Send valid JSON with name, phone, and address
API returns 429                   Wait for the rate-limit window to expire
Dependencies
Flask --- web server and API routes
Requests --- Telegram Bot API HTTP requests
python-dotenv --- loads .env.video
Install all dependencies:
pip install -r requirements-video.txt
License
No license has been specified. Add a license file before distributing the project or accepting external contributions.
VIDEOX · Flask Backend · Telegram Bot API