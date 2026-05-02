"""
Instagram Post Fetcher - Quick Test Script
==========================================
This is a simple standalone script to fetch and display the latest posts
from any Instagram profile. Useful for testing and debugging.

Usage:
    python get_last_3_posts.py

The script will display the last 3 posts from the configured Instagram account.

Customization:
    - Change INSTAGRAM_PROFILE to any username
    - Change POST_COUNT to get more/fewer posts
"""

import os

# Set dummy environment variables (required for the import, not actually used)
os.environ['TELEGRAM_BOT_TOKEN'] = 'test'
os.environ['TELEGRAM_CHAT_ID'] = 'test'

# Import Playwright for browser automation
from playwright.sync_api import sync_playwright

# =============================================================================
# CONFIGURATION - Change these values as needed
# =============================================================================

# Instagram username to fetch posts from (without @)
INSTAGRAM_PROFILE = "rvcjinsta"

# Number of recent posts to retrieve
POST_COUNT = 3


# =============================================================================
# MAIN FUNCTION
# =============================================================================

def get_latest_posts(count=3):
    """
    Fetch the latest posts from an Instagram profile.
    
    Args:
        count (int): Number of posts to fetch (default: 3)
    
    Returns:
        list: List of dictionaries, each containing 'post_id' and 'url'
              Returns None if no posts are found
    
    How it works:
        1. Launch headless Chromium browser
        2. Navigate to the Instagram profile page
        3. Wait for content to load
        4. Scroll down to trigger lazy loading of more posts
        5. Extract all post/reel links from the page
        6. Return the specified number of most recent posts
    """
    with sync_playwright() as p:
        # Launch browser with anti-detection measures
        browser = p.chromium.launch(
            headless=True,
            args=[
                '--disable-blink-features=AutomationControlled',
                '--no-sandbox',
                '--disable-dev-shm-usage',
                '--disable-gpu',
            ]
        )

        # Set up realistic browser context
        context = browser.new_context(
            user_agent=(
                'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                'AppleWebKit/537.36 (KHTML, like Gecko) '
                'Chrome/124.0.0.0 Safari/537.36'
            ),
            viewport={'width': 1920, 'height': 1080},
        )

        page = context.new_page()

        # Inject scripts to avoid bot detection
        page.add_init_script('''
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });
            window.chrome = {
                runtime: {},
            };
        ''')

        # Navigate to the Instagram profile
        url = f'https://www.instagram.com/{INSTAGRAM_PROFILE}/'
        page.goto(url, timeout=60000)

        # Wait for the page to fully load
        page.wait_for_timeout(10000)

        # Scroll down to load more posts (Instagram uses infinite scroll)
        page.evaluate('''() => { window.scrollBy(0, 1000); }''')
        page.wait_for_timeout(2000)

        # Extract all post/reel links from the page
        # This JavaScript finds all <a> tags with /p/ or /reel/ in them
        links = page.evaluate('''() => {
            let r = [];
            let as = document.querySelectorAll('a');
            for(let a of as) {
                if(a.href && (a.href.includes('/p/') || a.href.includes('/reel/'))) {
                    r.push(a.href);
                }
            }
            // Remove duplicates using Set
            return [...new Set(r)];
        }''')

        browser.close()

        if not links:
            return None

        # Parse the links to extract post IDs
        posts = []
        for link in links[:count]:
            # Extract post ID from URL
            # Example: https://www.instagram.com/p/ABC123/ -> ABC123
            post_id = link.split('/')[-2]
            posts.append({'post_id': post_id, 'url': link})

        return posts


# =============================================================================
# SCRIPT ENTRY POINT
# =============================================================================

if __name__ == "__main__":
    # Fetch the latest posts
    posts = get_latest_posts(POST_COUNT)

    # Display results
    if posts:
        print(f'Last {len(posts)} posts from @{INSTAGRAM_PROFILE}:')
        print('=' * 40)
        for i, p in enumerate(posts, 1):
            print(f'Post {i}:')
            print(f' ID: {p["post_id"]}')
            print(f' URL: {p["url"]}')
            print()
    else:
        print('No posts found')