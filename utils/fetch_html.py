import os
import time
import requests
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
}


def fetch_html(url: str, retries: int = 3, timeout: int = 15) -> str:
    """
    Fetch HTML using requests with optional ScraperAPI proxy if enabled.

    Environment Variables:
      - USE_SCRAPPER_PROXY: "true" or "false"
      - SCRAPER_API_KEY: Your ScraperAPI key
    """
    # Check whether to use proxy via environment variable (defaults to True)
    use_proxy = os.getenv("USE_SCRAPPER_PROXY", "true").lower() in ("true", "1")
    
    if use_proxy:
        # Build the ScraperAPI URL by appending the target URL
        target_url = f"http://api.scraperapi.com?api_key={os.getenv('SCRAPER_API_KEY')}&url={url}"
        proxies = None  # Using API URL method, so we don't set proxies
    else:
        target_url = url
        proxies = None

    for attempt in range(retries):
        try:
            print(f"Attempt {attempt+1}: Fetching {target_url}")
            response = requests.get(target_url, headers=HEADERS, timeout=timeout, proxies=proxies, verify=False)
            if response.status_code == 200:
                return response.text
            else:
                print(f"Attempt {attempt+1}: Received status code {response.status_code} for {url}")
        except Exception as e:
            print(f"Attempt {attempt+1} failed: {e}")
        time.sleep(2)
    return None