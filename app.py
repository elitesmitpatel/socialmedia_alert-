"""
Instagram Post Alert Bot
========================
This bot monitors a specified Instagram profile and sends Telegram alerts
whenever a new post is detected. It runs continuously and checks for new
posts at regular intervals.

Usage:
    python app.py

Environment Variables (required):
    TELEGRAM_BOT_TOKEN - Your Telegram bot token (get from @BotFather)
    TELEGRAM_CHAT_ID   - Your Telegram chat ID (get from @userinfobot)

Author: Created for monitoring Instagram accounts
License: MIT
"""

import os
import sqlite3
import requests
import signal
import sys
import logging
from playwright.sync_api import sync_playwright
from apscheduler.schedulers.blocking import BlockingScheduler

# =============================================================================
# CONFIGURATION
# =============================================================================

# Telegram Bot credentials - set these as environment variables before running
BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

# Instagram profile to monitor (change this to any Instagram username)
INSTAGRAM_URL = "https://www.instagram.com/rvcjinsta/"

# Database file to store the last checked post ID
# This helps us detect when a new post is published
DB_NAME = "state.db"

# =============================================================================
# SCHEDULER CONFIGURATION
# =============================================================================

# Run every 2 hours starting from 9 AM till 11 PM IST
# Indian Standard Time (IST) = UTC+5:30
# Cron format: hour (0-23), minute (0-59)
# We use APScheduler's cron trigger for time-based scheduling
CHECK_START_HOUR = 9   # Start checking from 9 AM
CHECK_END_HOUR = 23    # Stop checking after 11 PM (23:00)
CHECK_INTERVAL_HOURS = 2  # Run every 2 hours

# Browser timeout settings (in seconds)
TIMEOUT_SECONDS = 60          # Maximum time to wait for page load
WAIT_AFTER_LOAD = 8           # Extra wait time for JavaScript to render

# =============================================================================
# LOGGING SETUP
# =============================================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),      # Print to console
        logging.FileHandler("agent.log"),  # Save to file
    ]
)

logger = logging.getLogger(__name__)

# Global scheduler variable - used for clean shutdown
scheduler = None


# =============================================================================
# DATABASE FUNCTIONS
# =============================================================================

def init_db():
    """
    Initialize the SQLite database with a state table.
    The table stores the ID of the last processed post.
    
    Database Schema:
        - id: Primary key (always 1, since we only track one account)
        - last_post_id: The post ID that was last processed/sent to Telegram
    """
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()

    # Create table if it doesn't exist
    cur.execute("""
        CREATE TABLE IF NOT EXISTS state (
            id INTEGER PRIMARY KEY,
            last_post_id TEXT
        )
    """)

    # Check if we have an initial row, if not create one with empty post_id
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
    """
    Retrieve the last saved post ID from the database.
    
    Returns:
        str: The post ID of the last processed post, or empty string if none
    """
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
    """
    Save a post ID to the database to track it for future comparisons.
    
    Args:
        post_id (str): The Instagram post ID to save
    """
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


# =============================================================================
# TELEGRAM NOTIFICATION FUNCTIONS
# =============================================================================

def send_message(text):
    """
    Send a message to Telegram using the Bot API.
    
    Args:
        text (str): The message content with HTML formatting
    
    The message is sent via Telegram's sendMessage API endpoint.
    Format: https://api.telegram.org/bot<TOKEN>/sendMessage
    
    Error Handling:
        - Timeout: Request took too long
        - ConnectionError: Cannot reach Telegram servers
        - HTTPError: Telegram returned an error response
    """
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

    data = {
        "chat_id": CHAT_ID,
        "text": text,
        "parse_mode": "HTML"  # Allows bold text, links, etc.
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


# =============================================================================
# INSTAGRAM SCRAPING FUNCTIONS
# =============================================================================

def get_latest_post():
    """
    Scrape Instagram to find the latest post from the monitored profile.
    
    This function:
        1. Launches a headless Chromium browser
        2. Navigates to the Instagram profile
        3. Waits for the page to fully load
        4. Dismisses any login popup if it appears
        5. Extracts all post/reel links from the page
        6. Returns the most recent post's ID and URL
    
    Returns:
        dict: Contains 'post_id' and 'url' keys, or None if no posts found
    
    Anti-Detection Measures:
        - Uses custom user agent to mimic real browser
        - Sets viewport size to standard desktop resolution
        - Removes webdriver property that bots expose
        - Adds chrome runtime object to appear more legitimate
    """
    with sync_playwright() as p:
        # Launch Chromium browser in headless mode (no GUI)
        browser = p.chromium.launch(
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",  # Hide automation
                "--no-sandbox",           # Required for some Linux environments
                "--disable-dev-shm-usage", # Prevents memory issues in containers
                "--disable-gpu",          # Disable GPU hardware acceleration
            ]
        )

        # Create a browser context with realistic settings
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1920, "height": 1080},
        )

        page = context.new_page()

        # Inject JavaScript to hide automation indicators
        # This helps avoid Instagram's bot detection
        page.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });

            window.chrome = {
                runtime: {},
            };
        """)

        logger.info(f"Navigating to {INSTAGRAM_URL}")

        # Navigate to Instagram profile
        page.goto(INSTAGRAM_URL, timeout=TIMEOUT_SECONDS * 1000)

        # Wait for content to load (JavaScript rendering takes time)
        page.wait_for_timeout(WAIT_AFTER_LOAD * 1000)

        # Try to dismiss the "Not Now" login popup if it appears
        # Instagram often shows this to unregistered visitors
        try:
            dismiss_btn = page.locator('button:has-text("Not Now")')
            dismiss_btn.click(timeout=3000)
            logger.info("Dismissed login popup")
        except Exception:
            logger.info("No login popup found (or already dismissed)")

        # Extract post links from the page
        # We look for <a> tags containing '/p/' (photo) or '/reel/' (reel)
        links = page.evaluate("""() => {
            const allAnchors = document.querySelectorAll('a');
            return Array.from(allAnchors)
                .map(a => a.href)
                .filter(href =>
                    href.includes('/p/') || href.includes('/reel/')
                );
        }""")

        browser.close()

        if not links:
            logger.warning("No post links found on the page")
            return None

        # Get the first (most recent) post link
        latest_link = links[0]
        
        # Extract post ID from URL
        # Example: https://www.instagram.com/p/ABC123/ -> ABC123
        post_id = latest_link.split("/")[-2]

        logger.info(f"Found latest post: {post_id}")
        logger.info(f"Post URL: {latest_link}")

        return {
            "post_id": post_id,
            "url": latest_link
        }


# =============================================================================
# MAIN CHECKING LOGIC
# =============================================================================

def check_new_post():
    """
    Main function that checks for new posts and sends alerts.
    
    This is the core logic that:
        1. Gets the latest post from Instagram
        2. Compares it with the previously saved post ID
        3. If different: sends Telegram alert and saves new ID
        4. If same: logs that no new post was found
    
    This function is called both initially and on the scheduled interval.
    """
    logger.info("=" * 50)
    logger.info("Starting new post check...")

    try:
        # Step 1: Scrape Instagram to get latest post
        latest = get_latest_post()

        if not latest:
            logger.warning("Scraping returned no results — skipping this cycle")
            return

        # Step 2: Get the previously saved post ID from database
        saved_id = get_saved_post()
        logger.info(f"Saved ID: '{saved_id}' | Latest ID: '{latest['post_id']}'")

        # Step 3: Compare and take action
        if latest["post_id"] != saved_id:
            # New post detected! Send Telegram alert
            message = (
                f"<b>New Post from Virat Kohli!</b>\n"
                f"\n"
                f"<b>Post ID:</b> {latest['post_id']}\n"
                f"<a href=\"{latest['url']}\">View on Instagram</a>\n"
                f"\n"
                f"Checked just now"
            )

            send_message(message)

            # Save the new post ID so we don't alert again
            save_post(latest["post_id"])

            logger.info("NEW POST -- Alert sent!")
        else:
            logger.info("No new post -- same as last check")

    except Exception as e:
        logger.error(f"Error during check: {e}", exc_info=True)


# =============================================================================
# SHUTDOWN HANDLER
# =============================================================================

def handle_shutdown(signum, frame):
    """
    Handle graceful shutdown when user presses Ctrl+C or receives termination signal.
    
    Args:
        signum: Signal number (SIGINT or SIGTERM)
        frame: Current stack frame
    """
    logger.info("Shutdown signal received — stopping scheduler...")
    scheduler.shutdown(wait=False)
    logger.info("Agent stopped cleanly. Goodbye!")
    sys.exit(0)


# =============================================================================
# MAIN ENTRY POINT
# =============================================================================

if __name__ == "__main__":
    # Validate required environment variables
    if not BOT_TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN not set!")
        logger.error("Set it as an environment variable:")
        logger.error(" export TELEGRAM_BOT_TOKEN='your_token_here'")
        sys.exit(1)

    if not CHAT_ID:
        logger.error("TELEGRAM_CHAT_ID not set!")
        logger.error("Set it as an environment variable:")
        logger.error(" export TELEGRAM_CHAT_ID='your_chat_id_here'")
        sys.exit(1)

    logger.info("Configuration validated")

    # Initialize database
    init_db()
    logger.info("Database initialized")

    # Run initial check immediately on startup
    logger.info("Running initial check...")
    check_new_post()

    # Set up signal handlers for graceful shutdown
    signal.signal(signal.SIGINT, handle_shutdown)   # Ctrl+C
    signal.signal(signal.SIGTERM, handle_shutdown)  # Termination signal

# Create and configure the scheduler
scheduler = BlockingScheduler(timezone="Asia/Kolkata")

# Add the check job to run every 2 hours from 9 AM to 11 PM IST
# Using cron trigger for time-based scheduling
scheduler.add_job(
    check_new_post,              # Function to run
    'cron',                      # Run at specific times (cron-style)
    hour=range(CHECK_START_HOUR, CHECK_END_HOUR),  # Hours: 9, 10, 11, ..., 22
    minute=0,                    # At minute 0 of each hour
    id='post_checker',           # Unique job ID
    name='Instagram Post Checker',  # Job name for debugging
)

logger.info(f"Scheduler started — checking every {CHECK_INTERVAL_HOURS} hours from {CHECK_START_HOUR}:00 to {CHECK_END_HOUR}:00 IST")
logger.info("Agent is running... Press Ctrl+C to stop")

    # Start the scheduler (this blocks until stopped)
    scheduler.start()