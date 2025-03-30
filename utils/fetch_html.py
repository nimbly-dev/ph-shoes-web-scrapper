import os
import time
import requests
import random
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
}


def fetch_html(url: str, retries: int = 3, timeout: int = 30)-> str:
    """
    Fetch HTML using requests, optionally using ScraperAPI proxy and fallback.

    Environment Variables:
      - USE_SCRAPPER_PROXY: "true" or "false"
      - SCRAPER_API_KEY: Your ScraperAPI key
      - FALLBACK_DIRECT: "true" or "false" (optional)
    """
    use_proxy = os.getenv("USE_SCRAPPER_PROXY", "true").lower() in ("true", "1")
    fallback_direct = os.getenv("FALLBACK_DIRECT", "true").lower() in ("true", "1")
    scraper_api_key = os.getenv("SCRAPER_API_KEY")

    if use_proxy and scraper_api_key:
        target_url = f"https://api.scraperapi.com?api_key={scraper_api_key}&url={url}&render={'true'}"
    else:
        target_url = url

    for attempt in range(retries):
        try:
            print(f"Attempt {attempt+1}: Fetching {target_url}")
            response = requests.get(target_url, headers=HEADERS, timeout=timeout)

            if response.status_code == 200:
                return response.text
            else:
                print(f"Attempt {attempt+1}: Received status code {response.status_code} for {url}")
        except Exception as e:
            print(f"Attempt {attempt+1} failed: {e}")

        # Exponential backoff with jitter
        backoff = (2 ** attempt) + random.uniform(0.5, 1.5)
        time.sleep(backoff)

    # Fallback logic
    if use_proxy and fallback_direct:
        print(f"All proxy attempts failed. Falling back to direct request: {url}")
        try:
            response = requests.get(url, headers=HEADERS, timeout=timeout, verify=False)
            if response.status_code == 200:
                return response.text
            else:
                print(f"Fallback direct request failed with status code {response.status_code}")
        except Exception as e:
            print(f"Fallback direct request failed: {e}")

    return None