import time
import re
import json
from bs4 import BeautifulSoup
from typing import List
from dataclasses import dataclass
from .base import BaseShoe, BaseExtractor
from logger import get_logger
from playwright.sync_api import sync_playwright

logger = get_logger(__name__, log_file="./logs/new_balance_poc.log")

BASE_SEARCH_URL = "https://www.lazada.com.ph/new-alance-st-re/?q=All-Products&from=wangpu&langFlag=en&pageTypeId=2"

@dataclass
class NewBalanceShoe(BaseShoe):
    sold: str = None
    reviews: str = None
    location: str = None

class NewBalanceExtractor(BaseExtractor):
    def __init__(self, category: str = "all", num_pages: int = -1):
        self.category = category
        self.num_pages = num_pages

    def _fetch_page(self, page: int) -> str:
        if page > 1:
            url = BASE_SEARCH_URL + f"&page={page}"
        else:
            url = BASE_SEARCH_URL
        logger.info(f"Fetching: {url}")
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page_obj = browser.new_page()
            page_obj.goto(url, wait_until="domcontentloaded", timeout=60000)
            time.sleep(6)
            html_content = page_obj.content()
            browser.close()
        return html_content

    def _extract_image_url(self, prod) -> str:
        """
        Attempt to extract an image URL from the product card.
        Prioritize any URL that starts with 'https://img.lazcdn.com/'.
        """
        # First, search for any <img> tags in the product container.
        images = prod.find_all("img")
        for img in images:
            src = img.get("src") or img.get("data-src")
            if src and src.startswith("https://img.lazcdn.com/"):
                return src.strip()
        # Fallback: return first non-base64 image.
        for img in images:
            src = img.get("src") or img.get("data-src")
            if src and not src.startswith("data:"):
                return src.strip()
        return ""

    def _parse_products(self, html: str) -> List[dict]:
        soup = BeautifulSoup(html, 'html.parser')
        product_elements = soup.select("div.Bm3ON[data-qa-locator='product-item']")
        products = []
        for prod in product_elements:
            try:
                record = {}
                record["id"] = prod.get("data-item-id")
                title_anchor = prod.select_one("div.RfADt a")
                if title_anchor:
                    record["title"] = title_anchor.get("title") or title_anchor.text.strip()
                    url_val = title_anchor.get("href")
                    if url_val.startswith("//"):
                        url_val = "https:" + url_val
                    record["url"] = url_val
                else:
                    record["title"] = ""
                    record["url"] = ""
                # Hardcode subtitle as "running"
                record["subTitle"] = "running"
                sale_elem = prod.select_one("div.aBrP0 span.ooOxS")
                if sale_elem:
                    sale_text = sale_elem.text.strip().replace("₱", "").replace(",", "")
                    record["price_sale"] = float(re.sub(r'[^\d.]', '', sale_text)) if sale_text else None
                else:
                    record["price_sale"] = None
                orig_elem = prod.select_one("div.WNoq3 span._1m41m del.ooOxS")
                if orig_elem:
                    orig_text = orig_elem.text.strip().replace("₱", "").replace(",", "")
                    record["price_original"] = float(re.sub(r'[^\d.]', '', orig_text)) if orig_text else record["price_sale"]
                else:
                    record["price_original"] = record.get("price_sale")
                sold_elem = prod.select_one("div._6uN7R span._1cEkb span")
                record["sold"] = sold_elem.text.strip() if sold_elem else "N/A"
                reviews_elem = prod.select_one("div._6uN7R div.mdmmT._32vUv span.qzqFw")
                record["reviews"] = reviews_elem.text.strip() if reviews_elem else "N/A"
                loc_elem = prod.select_one("div._6uN7R span.oa6ri")
                if loc_elem:
                    record["location"] = loc_elem.get("title") or loc_elem.text.strip()
                else:
                    record["location"] = "N/A"
                record["image"] = self._extract_image_url(prod)
                if record.get("id") and record.get("title"):
                    products.append(record)
            except Exception as e:
                logger.error(f"Error parsing product: {e}")
        return products

    def extract(self) -> List[NewBalanceShoe]:
        all_products = []
        page = 1
        prev_count = 0
        while True:
            try:
                html_content = self._fetch_page(page)
            except Exception as e:
                logger.error(f"Error fetching page {page}: {e}")
                break
            products = self._parse_products(html_content)
            current_count = len(products)
            logger.info(f"Page {page}: found {current_count} product(s)")
            if current_count == 0 or current_count == prev_count:
                break
            all_products.extend(products)
            prev_count = current_count
            page += 1
            if self.num_pages != -1 and page > self.num_pages:
                break
            time.sleep(2)
        shoes = []
        for rec in all_products:
            try:
                shoe = NewBalanceShoe(**rec)
                shoes.append(shoe)
            except Exception as e:
                logger.error(f"Error creating NewBalanceShoe: {e}")
        return shoes
