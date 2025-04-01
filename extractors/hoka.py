import time
import re
import requests
import json
import html
from bs4 import BeautifulSoup
from typing import List
from dataclasses import dataclass
from .base import BaseShoe, BaseExtractor
from logger import get_logger

# Create a logger for this module.
logger = get_logger(__name__, log_file="./logs/hoka_poc.log")

# Global configuration for Hoka
base_url = "https://www.hoka.com/en/ph"

product_lists_url = [
    # MEN
    '/mens-road',
    '/mens-trail',
    '/mens-trail-hiking-shoes',
    '/mens-walking',
    '/mens-fitness',
    '/mens-trail-hiking-shoes',
    '/mens-recovery-comfort-shoes',
    '/mens-stability-shoes',
    '/mens-wides',
    '/mens-sandals',
    '/mens-lifestyle',
    '/mens-recovery-comfort-shoes',
    # WOMEN
    '/womens-road',
    '/womens-trail',
    '/womens-trail-hiking-shoes',
    '/womens-walking',
    '/womens-fitness',
    '/womens-recovery-comfort-shoes',
    '/womens-stability-shoes',
    '/womens-wides',
    '/womens-sandals',
    '/womens-lifestyle',
    '/womens-recovery-comfort-shoes',
    # KIDS
    '/kids'
]

category_config = {
    # MEN
    '/mens-road': {"gender": ["male"], "age_group": "adult", "subTitle": "road"},
    '/mens-trail': {"gender": ["male"], "age_group": "adult", "subTitle": "trail"},
    '/mens-trail-hiking-shoes': {"gender": ["male"], "age_group": "adult", "subTitle": "trail-hiking"},
    '/mens-walking': {"gender": ["male"], "age_group": "adult", "subTitle": "walking"},
    '/mens-fitness': {"gender": ["male"], "age_group": "adult", "subTitle": "fitness"},
    '/mens-recovery-comfort-shoes': {"gender": ["male"], "age_group": "adult", "subTitle": "recovery-comfort"},
    '/mens-stability-shoes': {"gender": ["male"], "age_group": "adult", "subTitle": "stability"},
    '/mens-wides': {"gender": ["male"], "age_group": "adult", "subTitle": "wides"},
    '/mens-sandals': {"gender": ["male"], "age_group": "adult", "subTitle": "sandals"},
    '/mens-lifestyle': {"gender": ["male"], "age_group": "adult", "subTitle": "lifestyle"},
    
    # WOMEN
    '/womens-road': {"gender": ["female"], "age_group": "adult", "subTitle": "road"},
    '/womens-trail': {"gender": ["female"], "age_group": "adult", "subTitle": "trail"},
    '/womens-trail-hiking-shoes': {"gender": ["female"], "age_group": "adult", "subTitle": "trail-hiking"},
    '/womens-walking': {"gender": ["female"], "age_group": "adult", "subTitle": "walking"},
    '/womens-fitness': {"gender": ["female"], "age_group": "adult", "subTitle": "fitness"},
    '/womens-recovery-comfort-shoes': {"gender": ["female"], "age_group": "adult", "subTitle": "recovery-comfort"},
    '/womens-stability-shoes': {"gender": ["female"], "age_group": "adult", "subTitle": "stability"},
    '/womens-wides': {"gender": ["female"], "age_group": "adult", "subTitle": "wides"},
    '/womens-sandals': {"gender": ["female"], "age_group": "adult", "subTitle": "sandals"},
    '/womens-lifestyle': {"gender": ["female"], "age_group": "adult", "subTitle": "lifestyle"},
    
    # KIDS
    '/kids': {"gender": ["unisex"], "age_group": "youth", "subTitle": "kids"}
}

# --- Define the HokaShoe dataclass ---
@dataclass
class HokaShoe(BaseShoe):
    pass

# --- Helper functions based on your PoC ---
def fetch_page(url: str) -> str:
    headers = {
        "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                       "AppleWebKit/537.36 (KHTML, like Gecko) "
                       "Chrome/116.0.5845.97 Safari/537.36"),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
        "Referer": "https://www.google.com/"
    }
    response = requests.get(url, headers=headers)
    response.raise_for_status()
    return response.text

def extract_image(prod) -> str:
    img_tag = prod.find("img", class_="tile-image")
    if img_tag and img_tag.get("src"):
        return img_tag.get("src").strip()
    image_container = prod.find("div", class_="image-container")
    if image_container and image_container.has_attr("data-images"):
        data_images = image_container["data-images"]
        try:
            images_data = json.loads(data_images)
            for key, group in images_data.items():
                if "default" in group and "medium" in group["default"]:
                    candidate = group["default"]["medium"][0].get("url")
                    if candidate:
                        return candidate.strip()
        except Exception:
            return ""
    return ""

def parse_hoka_products(html_content: str) -> List[dict]:
    soup = BeautifulSoup(html_content, 'html.parser')
    product_elements = soup.find_all('div', class_='product', attrs={'data-pid': True})
    products = []
    for prod in product_elements:
        record = {}
        record["id"] = prod.get("data-pid")
        name_container = prod.find("div", class_="tile-product-name")
        if name_container:
            a_tag = name_container.find("a", class_="link")
            if a_tag:
                record["title"] = a_tag.get_text(strip=True)
        a_link = prod.find("a", class_="js-pdp-link")
        if a_link and a_link.has_attr("href"):
            raw_url = a_link["href"].strip()
            if not raw_url.startswith("http"):
                record["url"] = "https://www.hoka.com" + raw_url
            else:
                record["url"] = raw_url
        record["image"] = extract_image(prod)
        sale_span = prod.find("span", class_="sales")
        if sale_span:
            sale_text = sale_span.get_text(strip=True).replace("₱", "").replace(",", "").strip()
            try:
                record["price_sale"] = float(sale_text)
            except ValueError:
                record["price_sale"] = None
        else:
            record["price_sale"] = None
        orig_span = prod.find("span", class_="original-price")
        if orig_span:
            orig_text = orig_span.get_text(strip=True).replace("₱", "").replace(",", "").strip()
            try:
                record["price_original"] = int(float(orig_text))
            except ValueError:
                record["price_original"] = None
        else:
            record["price_original"] = record.get("price_sale")
        if record.get("id") and record.get("title"):
            products.append(record)
    return products

# --- HokaExtractor Class (plain Python version) ---
class HokaExtractor(BaseExtractor):
    def __init__(self, category: str = "all", num_pages: int = -1):
        """
        :param category: Category endpoint (e.g., '/running013') or 'all' for all categories.
        :param num_pages: Number of pages per category (-1 means loop until product count stops increasing).
        """
        self.category = category
        self.num_pages = num_pages

    def _scrape_category(self, cat_path: str) -> List[dict]:
        # Determine page size dynamically by fetching the first page.
        first_url = f"{base_url}{cat_path}/"
        logger.info(f"Fetching first page: {first_url}")
        try:
            html_first = fetch_page(first_url)
        except Exception as e:
            logger.error(f"Error fetching {first_url}: {e}")
            return []
        first_products = parse_hoka_products(html_first)
        page_size = len(first_products) if first_products else 12
        logger.info(f"Determined page_size = {page_size} for {cat_path}")
        
        sz = page_size
        prev_count = 0
        final_products = first_products  # start with first page results
        
        while True:
            if sz == page_size:
                url_to_fetch = first_url
            else:
                url_to_fetch = f"{base_url}{cat_path}/?sz={sz}"
            logger.info(f"Fetching: {url_to_fetch}")
            try:
                html_content = fetch_page(url_to_fetch)
            except Exception as e:
                logger.error(f"Error fetching {url_to_fetch}: {e}")
                break
            products = parse_hoka_products(html_content)
            current_count = len(products)
            logger.info(f"With sz={sz}, found {current_count} product(s)")
            if current_count == prev_count:
                break
            final_products = products
            prev_count = current_count
            sz += page_size
            time.sleep(1)
            if self.num_pages != -1 and (sz / page_size) >= self.num_pages:
                break
        return final_products

    def extract(self) -> List[HokaShoe]:
        all_products = []
        if self.category.lower() == "all":
            paths = product_lists_url
        else:
            paths = [self.category]
        for path in paths:
            logger.info(f"Processing category: {path}")
            products = self._scrape_category(path)
            # Merge extra fields from category_config.
            if path in category_config:
                extra_fields = category_config[path]
                for product in products:
                    product.update(extra_fields)
            else:
                inferred = path.lstrip("/").split("-")[-1]
                for product in products:
                    product["subTitle"] = inferred
            all_products.extend(products)
            time.sleep(2.5)
        shoes = []
        def parse_price(p):
            try:
                return float(re.sub(r'[^\d.]', '', str(p)))
            except Exception:
                return None
        for rec in all_products:
            rec["price_sale"] = parse_price(rec.get("price_sale"))
            rec["price_original"] = parse_price(rec.get("price_original"))
            if rec["price_sale"] is None:
                rec["price_sale"] = rec["price_original"]
            try:
                shoe = HokaShoe(**rec)
                shoes.append(shoe)
            except Exception as ex:
                logger.error(f"Error creating HokaShoe: {ex}")
        return shoes
