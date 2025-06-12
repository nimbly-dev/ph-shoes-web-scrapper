import time
import re
import requests
import concurrent.futures
import html
import json
import pandas as pd
from bs4 import BeautifulSoup
from typing import List
from dataclasses import dataclass
from typing import Optional

from .base import BaseShoe, BaseExtractor
from logger import get_logger

logger = get_logger(__name__, log_file="./logs/asics_poc.log")

BASE_URL = "https://www.asics.com/ph/en-ph"
PRODUCT_LISTS = [
    '/running013', '/sportstyle013', '/indoor013', '/volleyball013',
    '/tennis013', '/trailrunning013', '/basketball013', '/soccer013',
    '/cricket013', '/others013',
    '/running023', '/sportstyle023', '/indoor023', '/volleyball023',
    '/netball023', '/tennis023', '/trailrunning023', '/basketball023',
    '/soccer023',
    '/running033', '/kids-indoor-shoes', '/kids-tennis-shoes', '/casual033'
]
CATEGORY_CONFIG = {
    '/running013': {"gender": ["male"],   "age_group": "adult"},
    '/sportstyle013': {"gender": ["male"],   "age_group": "adult"},
    '/indoor013': {"gender": ["male"],   "age_group": "adult"},
    '/volleyball013': {"gender": ["male"],   "age_group": "adult"},
    '/tennis013': {"gender": ["male"],   "age_group": "adult"},
    '/trailrunning013': {"gender": ["male"],   "age_group": "adult"},
    '/basketball013': {"gender": ["male"],   "age_group": "adult"},
    '/soccer013': {"gender": ["male"],   "age_group": "adult"},
    '/cricket013': {"gender": ["male"],   "age_group": "adult"},
    '/others013': {"gender": ["male"],   "age_group": "adult"},
    '/running023': {"gender": ["female"], "age_group": "adult"},
    '/sportstyle023': {"gender": ["female"], "age_group": "adult"},
    '/indoor023': {"gender": ["female"], "age_group": "adult"},
    '/volleyball023': {"gender": ["female"], "age_group": "adult"},
    '/netball023': {"gender": ["female"], "age_group": "adult"},
    '/tennis023': {"gender": ["female"], "age_group": "adult"},
    '/trailrunning023': {"gender": ["female"], "age_group": "adult"},
    '/basketball023': {"gender": ["female"], "age_group": "adult"},
    '/soccer023': {"gender": ["female"], "age_group": "adult"},
    '/running033': {"gender": ["unisex"], "age_group": "youth"},
    '/kids-indoor-shoes': {"gender": ["unisex"], "age_group": "youth"},
    '/kids-tennis-shoes': {"gender": ["unisex"], "age_group": "youth"},
    '/casual033': {"gender": ["unisex"], "age_group": "youth"}
}
PAGE_SIZE = 24

@dataclass
class AsicsShoe(BaseShoe):
    brand: str = "asics"


class AsicsExtractor(BaseExtractor):
    def __init__(self, category: str = "all", num_pages: int = -1):
        self.category = category
        self.num_pages = num_pages

    def _fetch_page(self, url: str) -> str:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
        r = requests.get(url, headers=headers, timeout=30)
        r.raise_for_status()
        return r.text

    def _extract_image(self, prod) -> Optional[str]:
        img = prod.find("img", class_="product-tile__image")
        if img:
            src = img.get("data-src-load-more") or img.get("src")
            if src and not src.startswith("data:"):
                return src.strip()
        # fallback via data-alt-image
        if img and img.has_attr("data-alt-image"):
            try:
                alt = json.loads(html.unescape(img["data-alt-image"]))
                return alt.get("src", "").strip()
            except Exception:
                pass
        # final fallback template
        pid = prod.get("data-itemid")
        if pid:
            parts = pid.split("-")
            if len(parts) == 2:
                return f"https://images.asics.com/is/image/asics/{parts[0]}_{parts[1]}_SR_RT_AJP?$productlist$"
        return None

    def _extract_products(self, html: str, path: str) -> List[AsicsShoe]:
        soup  = BeautifulSoup(html, 'html.parser')
        tiles = soup.find_all('div', class_='product-tile')
        shoes = []

        for prod in tiles:
            try:
                # 1) product ID
                pid = prod.get("data-itemid")

                # 2) title & subTitle
                title_elem    = prod.find('div', class_='product-name')
                subtitle_elem = prod.select_one(".product-tile__text--small")
                title    = title_elem.text.strip()    if title_elem    else None
                subtitle = subtitle_elem.text.strip() if subtitle_elem else None

                # 3) URL (attach BASE_URL if needed)
                link = prod.find_parent("a", class_="product-tile__link")
                url  = link["href"].strip() if link and link.has_attr("href") else None
                if url and url.startswith("/"):
                    url = f"{BASE_URL}{url}"

                # 4) image URL (reuse your existing helper)
                image = self._extract_image(prod)

                # 5) sale vs. original price
                #    - sale_elem: any span whose "class" list contains "price-sales"
                #    - orig_elem: prefer "price-original" if present; otherwise anything with "price-standard"
                sale_elem = prod.find(
                    "span",
                    class_=lambda attr: attr and "price-sales" in attr
                )
                orig_elem = (
                    prod.find("span", class_=lambda attr: attr and "price-original" in attr)
                    or
                    prod.find("span", class_=lambda attr: attr and "price-standard" in attr)
                )

                def parse_price(tag):
                    """
                    Extract numeric portion from a <span> like "₱ 3,771.00" → 3771.00
                    """
                    if not tag:
                        return None
                    raw = tag.text if hasattr(tag, "text") else str(tag)
                    # Remove currency symbols, commas, anything not digit or dot
                    digits = re.sub(r"[^\d\.]", "", raw)
                    return float(digits) if digits else None

                ps = parse_price(sale_elem)       # sale price, if it exists
                po = parse_price(orig_elem) or ps  # original price; fallback to ps if parsing fails

                # 6) category config
                cfg = CATEGORY_CONFIG.get(path, {})

                # 7) build record
                rec = {
                    "id":             pid,
                    "title":          title,
                    "subTitle":       subtitle,
                    "url":            url,
                    "image":          image,
                    "price_sale":     ps if ps is not None else 0.0,
                    "price_original": po if po is not None else 0.0,
                    "gender":         cfg.get("gender", []),
                    "age_group":      cfg.get("age_group", ""),
                    "brand":          "asics"
                }
                shoes.append(AsicsShoe(**rec))

            except Exception as e:
                logger.error(f"Error extracting tile (PID={pid}): {e}")

        return shoes

    def _process_category(self, path: str) -> List[AsicsShoe]:
        url_base = f"{BASE_URL}{path}/"
        all_shoes = []
        start = 0
        while True:
            url = f"{url_base}?start={start}&sz={PAGE_SIZE}"
            logger.info(f"Fetching {url}")
            html = self._fetch_page(url)
            shoes = self._extract_products(html, path)
            logger.info(f"Found {len(shoes)} on start={start}")
            if not shoes:
                break
            all_shoes.extend(shoes)
            start += PAGE_SIZE
            if self.num_pages != -1 and start >= PAGE_SIZE * self.num_pages:
                break
            time.sleep(0.25)
        return all_shoes

    def _clean_data(self, df: pd.DataFrame) -> pd.DataFrame:
        df['price_sale'] = pd.to_numeric(df['price_sale'], errors='coerce').fillna(0).clip(lower=0)
        df['price_original'] = pd.to_numeric(df['price_original'], errors='coerce').fillna(0).clip(lower=0)
        df['gender'] = df['gender'].apply(lambda g: [x.lower() for x in g] if isinstance(g, list) else [])
        df = df.dropna(subset=['id'])
        df = df.drop_duplicates(subset=['id'], keep='first')
        df['image'] = df['image'].fillna("no_image.png")   
        return df

    def _run_data_quality_tests(self, df: pd.DataFrame) -> bool:
        ok = True
        # no nulls
        nulls = df.isnull().sum()[lambda x: x>0].to_dict()
        if nulls:
            logger.error(f"Nulls found: {nulls}")
            ok = False
        # prices numeric
        for col in ['price_sale','price_original']:
            if not pd.api.types.is_numeric_dtype(df[col]):
                logger.error(f"{col} not numeric")
                ok = False
        # unique id
        if not df['id'].is_unique:
            logger.error("Duplicate ids found")
            ok = False
        if ok:
            logger.info("Data quality tests passed")
        else:
            logger.error("Data quality tests failed")
        return ok

    def extract(self) -> List[AsicsShoe]:
        paths = PRODUCT_LISTS if self.category.lower() == "all" else [self.category]
        all_shoes: List[AsicsShoe] = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as ex:
            futures = {ex.submit(self._process_category, p): p for p in paths}
            for f in concurrent.futures.as_completed(futures):
                p = futures[f]
                try:
                    result = f.result()
                    logger.info(f"{p} → {len(result)} shoes")
                    all_shoes.extend(result)
                except Exception as e:
                    logger.error(f"Category {p} failed: {e}")

        df = pd.DataFrame([s.__dict__ for s in all_shoes])
        df_clean = self._clean_data(df)
        self._run_data_quality_tests(df_clean)
        return [AsicsShoe(**rec) for rec in df_clean.to_dict('records')]
