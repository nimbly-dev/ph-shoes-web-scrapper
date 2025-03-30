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
        :param category_endpoint: Endpoint for a specific category (e.g., "/men-shoes") or "all" to scrape all categories.
        :param num_pages: Number of pages to process per category (-1 means loop until no products found)
        """
        self.category_endpoint = category_endpoint
        self.num_pages = num_pages

    def extract(self) -> List[Shoe]:
        # If category is "all", iterate over all defined categories and aggregate results.
        if self.category_endpoint.lower() == "all":
            aggregated_products = []
            for cat in category_config.keys():
                print(f"\n--- Extracting category: {cat} ---")
                extractor = AdidasExtractor(cat, self.num_pages)
                aggregated_products.extend(extractor.extract())
            return aggregated_products

        # Otherwise, scrape the specified category.
        config = category_config.get(self.category_endpoint, {"gender": [], "age_group": ""})
        current_gender = config["gender"]
        current_age_group = config["age_group"]
        full_url = f"{BASE_URL}{self.category_endpoint}"
        product_list = []
        page_num = 0
        print(f"Starting extraction for category {self.category_endpoint}...")

        while True:
            start = page_num * 48
            paginated_url = f"{full_url}?start={start}"
            print(f"Fetching page: {paginated_url}")

            html = fetch_html(paginated_url, retries=5, timeout=70)
            if not html:
                print(f"Failed to load {paginated_url} after retries.")
                break

            soup = BeautifulSoup(html, "html.parser")
            script_tag = soup.find("script", id="__NEXT_DATA__")
            if script_tag:
                data = json.loads(script_tag.string)
                products = data.get("props", {}).get("pageProps", {}).get("products", [])
                print(f"Found {len(products)} products on page {page_num+1} of {self.category_endpoint}.")

                if not products:
                    print("No products found. Ending pagination.")
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
            else:
                print(f"No __NEXT_DATA__ JSON found on {paginated_url}!")
                break

            sleep_time = random.uniform(1, 8)
            print(f"Sleeping for {sleep_time:.2f} seconds...\n")
            time.sleep(sleep_time)
            page_num += 1
            if self.num_pages != -1 and page_num >= self.num_pages:
                break

        return product_list