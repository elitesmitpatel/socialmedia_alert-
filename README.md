# Virat Kohli Instagram Post Alert Agent

Monitors a user's Instagram profile and sends Telegram alerts when new posts are detected.

## Setup

1. **Get Telegram credentials:**
   - Bot Token: Talk to @BotFather on Telegram
   - Chat ID: Talk to @userinfobot or send a message to your bot then check `api.telegram.org/bot<TOKEN>/getUpdates`

2. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   playwright install chromium
   ```

3. **Set environment variables:**
   ```bash
   export TELEGRAM_BOT_TOKEN="your_bot_token"
   export TELEGRAM_CHAT_ID="your_chat_id"
   ```

4. **Run locally:**
   ```bash
   python app.py
   ```

## Files

- `app.py` - Main agent code
- `requirements.txt` - Python dependencies
- `.github/workflows/check.yml` - GitHub Actions for free hosting

## Hosting on GitHub Actions

1. Push this code to a GitHub repository
2. Go to Settings → Secrets → Actions
3. Add `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID`
4. The workflow runs every 15 minutes automatically