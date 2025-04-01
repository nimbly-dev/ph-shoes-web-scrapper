import json
import random
import time
from bs4 import BeautifulSoup
from typing import List
from .base import BaseShoe, BaseExtractor
from utils.fetch_html import fetch_html
from dataclasses import dataclass
from typing import Optional, List as TypedList

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

# Define AdidasShoe with additional fields.
@dataclass
class AdidasShoe(BaseShoe):
    rating: Optional[float] = None
    ratingCount: Optional[int] = None
    colourVariations: TypedList = None

class AdidasExtractor(BaseExtractor):
    def __init__(self, category_endpoint: str, num_pages: int = -1):
        """
        :param category_endpoint: Category endpoint (e.g., "/men-shoes") or "all" to scrape all categories.
        :param num_pages: Number of pages to process per category (-1 means loop until no products found).
        """
        self.category_endpoint = category_endpoint
        self.num_pages = num_pages

    def extract(self) -> List[AdidasShoe]:
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
        print(f"Starting extraction for category {self.category_endpoint} using plain GET requests...")

        while True:
            start = page_num * 48
            paginated_url = f"{full_url}?start={start}"
            print(f"Fetching page: {paginated_url}")

            html = fetch_html(paginated_url)
            if not html:
                print(f"Failed to load {paginated_url} after retries.")
                break

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

                # If sale price is missing or 0, assign original price.
                if not price_sale:
                    price_sale = price_original if price_original is not None else 0.0

                shoe = AdidasShoe(
                    id=product.get("id", ""),
                    title=product.get("title", ""),
                    subTitle=product.get("subTitle"),
                    url=product.get("url", ""),
                    image=product.get("image"),
                    price_sale=price_sale,
                    price_original=price_original,
                    gender=current_gender,
                    age_group=current_age_group,
                    rating=product.get("rating"),
                    ratingCount=product.get("ratingCount"),
                    colourVariations=product.get("colourVariations", [])
                )
                
                product_list.append(shoe)

            sleep_time = random.uniform(1, 8)
            print(f"Sleeping for {sleep_time:.2f} seconds...\n")
            time.sleep(sleep_time)
            page_num += 1
            if self.num_pages != -1 and page_num >= self.num_pages:
                break

        return product_list
