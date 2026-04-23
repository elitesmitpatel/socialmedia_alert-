import os
import sqlite3
import requests
import signal
import sys
import logging
from playwright.sync_api import sync_playwright
from apscheduler.schedulers.blocking import BlockingScheduler

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

INSTAGRAM_URL = "https://www.instagram.com/virat.kohli/"

DB_NAME = "state.db"

CHECK_INTERVAL_MINUTES = 15

TIMEOUT_SECONDS = 60
WAIT_AFTER_LOAD = 8

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("agent.log"),
    ]
)

logger = logging.getLogger(__name__)
scheduler = None

def init_db():
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS state (
            id INTEGER PRIMARY KEY,
            last_post_id TEXT
        )
    """)

    cur.execute("SELECT * FROM state WHERE id=1")
    row = cur.fetchone()

    if not row:
        cur.execute(
            "INSERT INTO state (id, last_post_id) VALUES (1, '')"
        )
        logger.info("Database initialized with empty state")

    conn.commit()
    conn.close()

def get_saved_post():
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()

    cur.execute("SELECT last_post_id FROM state WHERE id=1")
    row = cur.fetchone()

    try:
        conn.close()
    except Exception:
        pass

    return row[0] if row else ""

def save_post(post_id):
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()

    cur.execute(
        "UPDATE state SET last_post_id=? WHERE id=1",
        (post_id,)
    )

    conn.commit()
    try:
        conn.close()
    except Exception:
        pass

    logger.info(f"Saved post ID to database: {post_id}")

def send_message(text):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

    data = {
        "chat_id": CHAT_ID,
        "text": text,
        "parse_mode": "HTML"
    }

    try:
        resp = requests.post(url, data=data, timeout=10)
        resp.raise_for_status()
        logger.info(f"Telegram message sent successfully")

    except requests.exceptions.Timeout:
        logger.error("Telegram request timed out")

    except requests.exceptions.ConnectionError:
        logger.error("Cannot connect to Telegram API")

    except requests.exceptions.HTTPError as e:
        logger.error(f"Telegram API error: {e.response.status_code} - {e.response.text}")

def get_latest_post():
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
            ]
        )

        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1920, "height": 1080},
        )

        page = context.new_page()

        page.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });

            window.chrome = {
                runtime: {},
            };
        """)

        logger.info(f"Navigating to {INSTAGRAM_URL}")

        page.goto(INSTAGRAM_URL, timeout=TIMEOUT_SECONDS * 1000)

        page.wait_for_timeout(WAIT_AFTER_LOAD * 1000)

        try:
            dismiss_btn = page.locator('button:has-text("Not Now")')
            dismiss_btn.click(timeout=3000)
            logger.info("Dismissed login popup")

        except Exception:
            logger.info("No login popup found (or already dismissed)")

        links = page.evaluate("""
            () => {
                const allAnchors = document.querySelectorAll('a');
                return Array.from(allAnchors)
                    .map(a => a.href)
                    .filter(href =>
                        href.includes('/p/') ||
                        href.includes('/reel/')
                    );
            }
        """)

        browser.close()

        if not links:
            logger.warning("No post links found on the page")
            return None

        latest_link = links[0]
        post_id = latest_link.split("/")[-2]

        logger.info(f"Found latest post: {post_id}")
        logger.info(f"Post URL: {latest_link}")

        return {
            "post_id": post_id,
            "url": latest_link
        }

def check_new_post():
    logger.info("=" * 50)
    logger.info("Starting new post check...")

    try:
        latest = get_latest_post()

        if not latest:
            logger.warning("Scraping returned no results — skipping this cycle")
            return

        saved_id = get_saved_post()
        logger.info(f"Saved ID: '{saved_id}' | Latest ID: '{latest['post_id']}'")

        if latest["post_id"] != saved_id:
            message = (
                f"🚨 <b>New Post from Virat Kohli!</b>\n"
                f"\n"
                f"📸 <b>Post ID:</b> {latest['post_id']}\n"
                f"🔗 <a href=\"{latest['url']}\">View on Instagram</a>\n"
                f"\n"
                f"⏰ Checked just now"
            )

            send_message(message)

            save_post(latest["post_id"])

            logger.info("🚨 NEW POST — Alert sent!")

        else:
            logger.info("No new post — same as last check")

    except Exception as e:
        logger.error(f"Error during check: {e}", exc_info=True)

def handle_shutdown(signum, frame):
    logger.info("Shutdown signal received — stopping scheduler...")
    scheduler.shutdown(wait=False)
    logger.info("Agent stopped cleanly. Goodbye!")
    sys.exit(0)

if __name__ == "__main__":
    if not BOT_TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN not set!")
        logger.error("Set it as an environment variable:")
        logger.error("  export TELEGRAM_BOT_TOKEN='your_token_here'")
        sys.exit(1)

    if not CHAT_ID:
        logger.error("TELEGRAM_CHAT_ID not set!")
        logger.error("Set it as an environment variable:")
        logger.error("  export TELEGRAM_CHAT_ID='your_chat_id_here'")
        sys.exit(1)

    logger.info("Configuration validated ✓")

    init_db()
    logger.info("Database initialized ✓")

    logger.info("Running initial check...")
    check_new_post()

    signal.signal(signal.SIGINT, handle_shutdown)
    signal.signal(signal.SIGTERM, handle_shutdown)

    scheduler = BlockingScheduler()

    scheduler.add_job(
        check_new_post,
        'interval',
        minutes=CHECK_INTERVAL_MINUTES,
        id='post_checker',
        name='Instagram Post Checker',
    )

    logger.info(f"Scheduler started — checking every {CHECK_INTERVAL_MINUTES} minutes")
    logger.info("Agent is running... Press Ctrl+C to stop")

    scheduler.start()