import os
from dotenv import load_dotenv

load_dotenv()

SCRAPER_API_KEY = os.getenv("SCRAPER_API_KEY")

def get_scraperapi_proxies(session_number=1):
    return {
        "https": f"http://scraperapi.session_number={session_number}:{SCRAPER_API_KEY}@proxy-server.scraperapi.com:8001"
    }
