# extractors/adidas.py

import json
import random
import time
import requests
from bs4 import BeautifulSoup
from typing import List
from .base import Shoe, BaseExtractor
from utils.proxy import get_scraperapi_proxies
from utils.fetch_html import fetch_html

# Global configuration for Adidas
BASE_URL = "https://www.adidas.com.ph"

# Category configuration specific to Adidas
category_config = {
    '/men-shoes': {"gender": ["male"], "age_group": "adult"},
    '/women-shoes': {"gender": ["female"], "age_group": "adult"},
    '/boys-8_16_years-shoes': {"gender": ["male"], "age_group": "youth"},
    '/girls-8_16_years-shoes': {"gender": ["female"], "age_group": "youth"},
    '/boys-4_8_years-shoes': {"gender": ["male"], "age_group": "kids"},
    '/girls-4_8_years-shoes': {"gender": ["female"], "age_group": "kids"},
    '/1_4_years-shoes': {"gender": ["male", "female"], "age_group": "toddlers"} 
}

class AdidasExtractor(BaseExtractor):
    def __init__(self, category_endpoint: str, num_pages: int = -1):
        """
        :param category_endpoint: Category endpoint (e.g., "/men-shoes") or "all" to scrape all categories.
        :param num_pages: Number of pages to process per category (-1 means loop until no products found).
        """
        self.category_endpoint = category_endpoint
        self.num_pages = num_pages

    def extract(self) -> List[Shoe]:
        # If "all" is passed, loop through every category in the configuration.
        if self.category_endpoint.lower() == "all":
            aggregated_products = []
            for cat in category_config.keys():
                print(f"\n--- Extracting category: {cat} ---")
                extractor = AdidasExtractor(cat, self.num_pages)
                aggregated_products.extend(extractor.extract())
            return aggregated_products

        # Otherwise, proceed with the specified category.
        config = category_config.get(self.category_endpoint, {"gender": [], "age_group": ""})
        current_gender = config["gender"]
        current_age_group = config["age_group"]
        full_url = f"{BASE_URL}{self.category_endpoint}"
        product_list = []
        page_num = 0
        print(f"Starting extraction for category {self.category_endpoint} using Playwright...")

        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=[
                    "--disable-http2",
                    "--disable-quic",
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-setuid-sandbox"
                ]
            )
            context = browser.new_context(ignore_https_errors=True, viewport={"width": 1280, "height": 720})
            page = context.new_page()
            # Set extra headers to mimic a real browser
            page.set_extra_http_headers({
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
            })

            while True:
                start = page_num * 48
                paginated_url = f"{full_url}?start={start}"
                print(f"Fetching page: {paginated_url}")

                try:
                    page.goto(paginated_url, timeout=70000, wait_until="domcontentloaded")
                except Exception as e:
                    print(f"Error navigating to {paginated_url}: {e}")
                    break

                html = page.content()
                soup = BeautifulSoup(html, "html.parser")
                script_tag = soup.find("script", id="__NEXT_DATA__")
                if not script_tag:
                    print(f"No __NEXT_DATA__ JSON found on {paginated_url}!")
                    break

                try:
                    data = json.loads(script_tag.string)
                except Exception as e:
                    print(f"Error parsing JSON from {paginated_url}: {e}")
                    break

                products = data.get("props", {}).get("pageProps", {}).get("products", [])
                print(f"Found {len(products)} products on page {page_num+1} of {self.category_endpoint}.")

                if not products:
                    print("No products found. Ending pagination for this category.")
                    break

                for product in products:
                    prices = product.get("priceData", {}).get("prices", [])
                    price_sale = None
                    price_original = None
                    for price in prices:
                        if price.get("type") == "sale":
                            price_sale = price.get("value")
                        elif price.get("type") == "original":
                            price_original = price.get("value")

                    shoe = Shoe(
                        id=product.get("id", ""),
                        title=product.get("title", ""),
                        subTitle=product.get("subTitle"),
                        url=product.get("url", ""),
                        image=product.get("image"),
                        price_sale=price_sale if price_sale is not None else 0.0,
                        price_original=price_original,
                        gender=current_gender,
                        age_group=current_age_group
                    )
                    product_list.append(shoe)

                sleep_time = random.uniform(1, 8)
                print(f"Sleeping for {sleep_time:.2f} seconds...\n")
                time.sleep(sleep_time)
                page_num += 1
                if self.num_pages != -1 and page_num >= self.num_pages:
                    break

            browser.close()

        return product_list
