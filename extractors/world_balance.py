import json
import random
import time
import re
import requests
from bs4 import BeautifulSoup
from typing import List
from dataclasses import dataclass
from .base import BaseShoe, BaseExtractor
from logger import get_logger

# Create a logger for this module.
logger = get_logger(__name__, log_file="./logs/world_balance_poc.log")

# Global configuration for World Balance
BASE_URL = 'https://worldbalance.com.ph/collections'

# List of category endpoints to process
product_lists_url = [
    '/performance',
    '/lifestyle-m',
    '/athleisure-m',
    '/classic-men-shoes',
    '/slipper-m',
    # WOMEN
    '/performance-l',
    '/lifestyle-l',
    '/classic-women-shoes',
    '/slippers-l',
    # KIDS
    '/performance-kids',
    '/lifestyle-kids',
    '/classic-children-shoes',
    '/slippers-kids',
    '/pe',
    '/athleisure-kids'
]

# Category configuration (includes extra details like subtitle)
category_config = {
    # MALE
    '/performance': {"gender": ["male"], "age_group": "adult", "subtitle": "performance"},
    '/lifestyle-m': {"gender": ["male"], "age_group": "adult", "subtitle": "lifestyle"},
    '/athleisure-m': {"gender": ["male"], "age_group": "adult", "subtitle": "athleisure"},
    '/classic-men-shoes': {"gender": ["male"], "age_group": "adult", "subtitle": "classic-shoes"},
    '/slipper-m': {"gender": ["male"], "age_group": "adult", "subtitle": "slipper"},
    # FEMALE
    '/performance-l': {"gender": ["female"], "age_group": "adult", "subtitle": "performance"},
    '/lifestyle-l': {"gender": ["female"], "age_group": "adult", "subtitle": "lifestyle"},
    '/classic-women-shoes': {"gender": ["female"], "age_group": "adult", "subtitle": "classic-shoes"},
    '/slippers-l': {"gender": ["female"], "age_group": "adult", "subtitle": "slipper"},
    # KIDS
    '/performance-kids': {"gender": ["unisex"], "age_group": "youth", "subtitle": "performance"},
    '/lifestyle-kids': {"gender": ["unisex"], "age_group": "youth", "subtitle": "lifestyle"},
    '/classic-children-shoes': {"gender": ["unisex"], "age_group": "youth", "subtitle": "classic-shoes"},
    '/slippers-kids': {"gender": ["unisex"], "age_group": "youth", "subtitle": "slipper"},
    '/pe': {"gender": ["unisex"], "age_group": "youth", "subtitle": "pe"},
    '/athleisure-kids': {"gender": ["unisex"], "age_group": "youth", "subtitle": "athleisure"}
}

# Request headers for World Balance
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
}

# Define the WorldBalanceShoe dataclass.
@dataclass
class WorldBalanceShoe(BaseShoe):
    pass  # Inherit all fields from BaseShoe; extra details (like subtitle) will be stored in subTitle

class WorldBalanceExtractor(BaseExtractor):
    def __init__(self, category: str = "all", num_pages: int = -1):
        """
        :param category: Category endpoint (e.g., '/performance') or 'all' for all categories.
        :param num_pages: Number of pages per category (-1 means loop until no products are found).
        """
        self.category = category
        self.num_pages = num_pages

    def _extract_products_from_html(self, html: str, category_path: str) -> List[WorldBalanceShoe]:
        """
        Extract product details from the HTML of a category page.
        Returns a list of WorldBalanceShoe instances.
        """
        soup = BeautifulSoup(html, 'html.parser')
        shoes = []
        # Locate product cards (the cards have class "grid-product")
        product_cards = soup.select('div.grid-product')
        for card in product_cards:
            try:
                product_id = card.get('data-product-id', '').strip()
                title_elem = card.select_one('div.grid-product__title')
                product_name = title_elem.get_text(strip=True) if title_elem else ''
                link_elem = card.select_one('a.grid-product__link')
                url_val = link_elem.get('href', '').strip() if link_elem else ''
                if url_val.startswith('/'):
                    url_val = 'https://worldbalance.com.ph' + url_val
                img_elem = card.select_one('img.image-element')
                image_url = img_elem.get('src', '').strip() if img_elem else ''
                if image_url.startswith('//'):
                    image_url = 'https:' + image_url

                # Process price information.
                price_container = card.select_one('div.grid-product__price')
                price_original = None
                price_sale = None
                if price_container:
                    original_elem = price_container.select_one('span.grid-product__price--original')
                    if original_elem:
                        orig_text = original_elem.get_text(strip=True)
                        # Loop over siblings to find the sale price text.
                        sale_text = ""
                        for sibling in original_elem.next_siblings:
                            if isinstance(sibling, str) and sibling.strip():
                                sale_text = sibling.strip()
                                break
                        price_original = float(re.sub(r'[^\d.]', '', orig_text)) if orig_text else None
                        price_sale = float(re.sub(r'[^\d.]', '', sale_text)) if sale_text else price_original
                    else:
                        # Non-sale case: the price container has a single price.
                        price_text = price_container.get_text(strip=True)
                        price_original = float(re.sub(r'[^\d.]', '', price_text)) if price_text else None
                        price_sale = price_original
                else:
                    price_original = price_sale = None

                # Merge in the category details.
                cat_details = category_config.get(category_path, {})
                product_data = {
                    "id": product_id,
                    "title": product_name,
                    "subTitle": cat_details.get("subtitle", ""),  # store the category subtitle
                    "url": url_val,
                    "image": image_url,
                    "price_sale": price_sale if price_sale is not None else 0.0,
                    "price_original": price_original,
                    "gender": cat_details.get("gender", []),
                    "age_group": cat_details.get("age_group", "")
                }
                shoe = WorldBalanceShoe(**product_data)
                shoes.append(shoe)
            except Exception as ex:
                logger.error(f"Error extracting product details: {ex}")
        return shoes

    def _process_category(self, category_path: str) -> List[WorldBalanceShoe]:
        """
        Process a single category:
          1. Build the category URL.
          2. Fetch the HTML.
          3. Extract product details.
        """
        category_url = BASE_URL + category_path
        logger.info(f"Processing {category_url} ...")
        start_time = time.time()
        response = requests.get(category_url, headers=headers)
        if response.status_code == 200:
            html = response.text
            shoes = self._extract_products_from_html(html, category_path)
        else:
            logger.error(f"Failed to fetch {category_url}. Status code: {response.status_code}")
            shoes = []
        elapsed = time.time() - start_time
        logger.info(f"Time taken for {category_path}: {elapsed:.2f} seconds")
        return shoes

    def extract(self) -> List[WorldBalanceShoe]:
        """
        Process either a specific category or all World Balance categories using ?page pagination.
        Pagination is based on the page number (1-indexed).
        """
        all_shoes = []
        if self.category.lower() == "all":
            paths = product_lists_url
        else:
            paths = [self.category]
        for path in paths:
            page_num = 0  # We'll use page_num+1 for ?page=
            while True:
                paginated_url = BASE_URL + path + f"?page={page_num+1}"
                logger.info(f"Fetching page: {paginated_url}")
                response = requests.get(paginated_url, headers=headers)
                if response.status_code != 200:
                    logger.error(f"Failed to fetch {paginated_url}. Status code: {response.status_code}")
                    break
                html = response.text
                shoes = self._extract_products_from_html(html, path)
                if not shoes:
                    logger.info(f"No products found on page {page_num+1} for {path}. Ending pagination.")
                    break
                all_shoes.extend(shoes)
                page_num += 1
                if self.num_pages != -1 and page_num >= self.num_pages:
                    break
                sleep_time = random.uniform(1, 2)
                logger.info(f"Sleeping for {sleep_time:.2f} seconds...")
                time.sleep(sleep_time)
        return all_shoes
