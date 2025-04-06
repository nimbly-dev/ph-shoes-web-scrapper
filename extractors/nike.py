import json
import re
import time
import requests
from typing import List, Optional
from .base import BaseShoe, BaseExtractor
from logger import get_logger
from dataclasses import dataclass

# Create a logger for this module. It will log to both console and file.
logger = get_logger(__name__, log_file="./logs/nike_poc.log")

@dataclass
class NikeShoe(BaseShoe):
    colordescription: Optional[str] = None
    out_of_stock: Optional[bool] = False
    best_seller: Optional[bool] = False

class NikeExtractor(BaseExtractor):
    BASE_URL = 'https://api.nike.com'
    SITE_BASE = 'https://www.nike.com/ph/w'
    API_BASE = 'https://api.nike.com'
    # Global session with default headers to mimic a browser
    SESSION = requests.Session()
    DEFAULT_HEADERS = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36",
        "nike-api-caller-id": "com.nike.commerce.nikedotcom.snkrs.web"
    }
    SESSION.headers.update(DEFAULT_HEADERS)

    # List of category endpoints to process
    PRODUCT_LISTS_URL = [
        '/mens-shoes-nik1zy7ok',
        '/womens-shoes-5e1x6zy7ok',
        '/older-kids-agibjzv4dh',
        '/little-kids-6dacezv4dh',
        '/baby-toddlers-kids-2j488zv4dh'
    ]
    # Category configuration
    CATEGORY_CONFIG = {
        '/mens-shoes-nik1zy7ok': {"gender": ["male"], "age_group": "adult"},
        '/womens-shoes-5e1x6zy7ok': {"gender": ["female"], "age_group": "adult"},
        '/older-kids-agibjzv4dh': {"gender": ["unisex"], "age_group": "youth"},
        '/little-kids-6dacezv4dh': {"gender": ["unisex"], "age_group": "kids"},
        '/baby-toddlers-kids-2j488zv4dh': {"gender": ["unisex"], "age_group": "toddlers"}
    }

    def __init__(self, category: str = "all", num_pages: int = -1):
        """
        :param category: Category path (e.g., '/mens-shoes-nik1zy7ok') or "all" to process all available categories.
        :param num_pages: Number of pages to process per category (not used here as Nike API uses lazy loading).
        """
        self.category = category
        self.num_pages = num_pages  # not used in this lazy-loaded API context

    def _get_products_from_groupings(self, stub: str, products: list) -> list:
        """
        Recursively request lazy-load API URL and extract products from 'productGroupings'.
        """
        response = self.SESSION.get(self.API_BASE + stub, headers=self.DEFAULT_HEADERS).json()
        groupings = response.get('productGroupings', [])
        for grouping in groupings:
            prod_list = grouping.get('products') or []
            products.extend(prod_list)
        next_page = response.get('pages', {}).get('next')
        if next_page:
            self._get_products_from_groupings(next_page, products)
        return products

    def _extract_product_data(self, product: dict) -> dict:
        """
        Extract product fields based on Nike API data.
        """
        return {
            'id': product.get('productCode'),
            'title': product.get('copy', {}).get('title'),
            'subTitle': product.get('copy', {}).get('subTitle'),
            'url': product.get('pdpUrl', {}).get('url'),
            'image': product.get('colorwayImages', {}).get('portraitURL'),
            'price_original': product.get('prices', {}).get('initialPrice'),
            'price_sale': product.get('prices', {}).get('currentPrice'),
            'colordescription': product.get('displayColors', {}).get('colorDescription'),
            'out_of_stock': any("OUT_OF_STOCK" in attr for attr in (product.get('featuredAttributes') or [])),
            'best_seller': any("BEST_SELLER" in attr for attr in (product.get('featuredAttributes') or []))
        }

    def _process_category(self, category_path: str, config: dict) -> List[NikeShoe]:
        """
        Process a single category:
          1. Build the category URL.
          2. Fetch HTML and extract the lazy-load API URL from __NEXT_DATA__.
          3. Recursively load products via the API.
          4. Extract product fields and build NikeShoe instances.
        """
        logger.info(f"Processing category: {category_path}")
        start_time = time.time()

        category_url = self.SITE_BASE + category_path
        html_data = self.SESSION.get(category_url, headers=self.DEFAULT_HEADERS).text

        # Extract __NEXT_DATA__ JSON from the HTML.
        match = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', html_data, re.DOTALL)
        if match:
            redux = json.loads(match.group(1))
        else:
            raise Exception("Could not find __NEXT_DATA__ in HTML for category: " + category_path)

        # Extract the lazy-load API URL.
        try:
            wall = redux['props']['pageProps']['initialState']['Wall']
            initial_api = re.sub('anchor=[0-9]+', 'anchor=0', wall['pageData']['next'])
            logger.info("Lazy-load API URL extracted: %s", initial_api)
        except KeyError as e:
            raise Exception("Could not locate lazy load API URL in JSON data for category: " + category_path) from e

        # Recursively load all products via the API.
        products = self._get_products_from_groupings(initial_api, [])
        logger.info(f"Total products extracted from API for {category_path}: {len(products)}")

        shoes = []
        for prod in products:
            prod_data = self._extract_product_data(prod)
            shoe = NikeShoe(
                id=prod_data.get('id', ''),
                title=prod_data.get('title', ''),
                subTitle=prod_data.get('subTitle'),
                url=prod_data.get('url', ''),
                image=prod_data.get('image'),
                price_sale=prod_data.get('price_sale', 0.0),
                price_original=prod_data.get('price_original'),
                gender=config.get("gender", []),
                age_group=config.get("age_group", ""),
                colordescription=prod_data.get('colordescription'),
                out_of_stock=prod_data.get('out_of_stock', False),
                best_seller=prod_data.get('best_seller', False)
            )
            shoes.append(shoe)

        elapsed = time.time() - start_time
        logger.info(f"Finished processing category: {category_path} in {elapsed:.2f} seconds.")
        return shoes

    def extract(self) -> List[NikeShoe]:
        """
        Process either a specific category or all defined Nike categories.
        """
        all_shoes = []
        if self.category.lower() == "all":
            for cat in self.PRODUCT_LISTS_URL:
                config = self.CATEGORY_CONFIG.get(cat, {})
                shoes = self._process_category(cat, config)
                all_shoes.extend(shoes)
        else:
            cat_path = "/" + self.category if not self.category.startswith("/") else self.category
            config = self.CATEGORY_CONFIG.get(cat_path)
            if not config:
                raise ValueError(f"Invalid or unsupported category: {self.category}")
            all_shoes = self._process_category(cat_path, config)
        return all_shoes