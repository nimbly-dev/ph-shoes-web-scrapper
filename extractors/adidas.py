import json
import random
import time
import requests
from urllib.parse import urljoin
from typing import List
from .base import BaseShoe, BaseExtractor

# Global configuration for Adidas
BASE_URL = "https://www.adidas.com.ph"

# Updated category configuration keyed by search term.
category_config = {
    "men-shoes": {"gender": ["male"], "age_group": "adult"},
    "women-shoes": {"gender": ["female"], "age_group": "adult"},
    "boys-shoes": {"gender": ["male"], "age_group": "youth"},
    "girls-shoes": {"gender": ["female"], "age_group": "youth"},
    "infants-shoes": {"gender": ["male", "female"], "age_group": "toddlers"}
}

# Use a simple User-Agent that worked for you locally.
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
        
def get_api(language: str = "en", start_num: int = 0, search_item: str = "shoes") -> str:
    """
    Returns the API URL using the given language, start number, and search item.
    """
    return f"{BASE_URL}/api/plp/content-engine?sitePath={language}&query={search_item}&start={start_num}"

def get_json(api: str) -> dict:
    """
    Makes a GET request to the API and returns the JSON response.
    """
    try:
        response = requests.get(api, headers=HEADERS)
        print(f"Fetching API: {api}")
        if response.status_code != 200:
            raise Exception(f"Non-200 status code: {response.status_code}")
        if not response.text.strip():
            raise Exception("Empty response text")
        try:
            data = response.json()
        except json.JSONDecodeError as json_err:
            
            raise Exception(f"JSON decode error: {json_err}\nResponse text: {response.text}") from json_err
        return data
    except Exception as e:
        print(f"Error while requesting {api}: {e}")
        raise e

# @DeprecationWarning("AdidasExtractor is not working on FastAPI setup, a seperate repository is created for this.")
class AdidasExtractor(BaseExtractor):
    def __init__(self, category_endpoint: str, num_pages: int = -1):
        """
        :param category_endpoint: Either a specific search term (e.g. "men-shoes")
                                  or "all" to process all categories.
        :param num_pages: Number of pages to process (-1 means loop until no products found)
        """
        self.category_endpoint = category_endpoint.lower()
        self.num_pages = num_pages

    def extract_category(self, search_term: str, fixed_config: dict) -> List[BaseShoe]:
        """
        Extracts products for a given search term using the fixed configuration.
        """
        current_gender = fixed_config["gender"]
        current_age_group = fixed_config["age_group"]
        product_list = []
        page_num = 0
        print(f"Starting extraction for category '{search_term}' using API...")

        while True:
            start = page_num * 48
            api_url = get_api("en", start, search_term)
            data = get_json(api_url)
            # Parse products from the JSON; assumed structure is under "raw" -> "itemList" -> "items"
            products = data.get("raw", {}).get("itemList", {}).get("items", [])
            print(f"Found {len(products)} products on page {page_num+1} for category '{search_term}'.")

            if not products:
                print(f"No products found for '{search_term}'. Ending pagination.")
                break

            for product in products:
                shoe = BaseShoe(
                    id = product.get("productId", ""),
                    title = product.get("displayName", ""),
                    subTitle = product.get("subTitle"),
                    url = urljoin(BASE_URL, product.get("link", "")),
                    image = product.get("image", {}).get("src"),
                    price_sale = product.get("salePrice") if product.get("salePrice") is not None else 0.0,
                    price_original = product.get("price"),
                    gender = current_gender,
                    age_group = current_age_group
                )
                product_list.append(shoe)

            sleep_time = random.uniform(1, 8)
            print(f"Sleeping for {sleep_time:.2f} seconds...\n")
            time.sleep(sleep_time)
            page_num += 1
            if self.num_pages != -1 and page_num >= self.num_pages:
                break

        return product_list

    def extract(self) -> List[BaseShoe]:
        """
        If the search term is "all", iterates over every key in category_config.
        Otherwise, uses the provided search term.
        """
        if self.category_endpoint == "all":
            aggregated = []
            for search_term, fixed_config in category_config.items():
                aggregated.extend(self.extract_category(search_term, fixed_config))
            return aggregated
        else:
            fixed_config = category_config.get(
                self.category_endpoint, {"gender": ["unisex"], "age_group": "adult"}
            )
            return self.extract_category(self.category_endpoint, fixed_config)
