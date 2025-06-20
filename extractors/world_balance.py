# extractors/world_balance.py

import random
import re
import time
from dataclasses import dataclass
from typing import List, Tuple, Dict

import pandas as pd
import requests
from bs4 import BeautifulSoup
from logger import get_logger
from .base import BaseShoe, BaseExtractor

logger = get_logger(__name__, log_file="./logs/world_balance_poc.log")

BASE_URL = 'https://worldbalance.com.ph'
COLLECTION_PATH = '/collections'
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://worldbalance.com.ph/"
}

product_lists_url = [
    '/performance',
    '/lifestyle-m',
    '/athleisure-m',
    '/classic-men-shoes',
    '/slipper-m',
    '/performance-l',
    '/lifestyle-l',
    '/classic-women-shoes',
    '/slippers-l',
    '/performance-kids',
    '/lifestyle-kids',
    '/classic-children-shoes',
    '/slippers-kids',
    '/pe',
    '/athleisure-kids'
]

category_config: Dict[str, Dict] = {
    '/performance':            {"gender": ["male"],   "age_group": "adult", "subtitle": "performance"},
    '/lifestyle-m':            {"gender": ["male"],   "age_group": "adult", "subtitle": "lifestyle"},
    '/athleisure-m':           {"gender": ["male"],   "age_group": "adult", "subtitle": "athleisure"},
    '/classic-men-shoes':      {"gender": ["male"],   "age_group": "adult", "subtitle": "classic-shoes"},
    '/slipper-m':              {"gender": ["male"],   "age_group": "adult", "subtitle": "slipper"},
    '/performance-l':          {"gender": ["female"], "age_group": "adult", "subtitle": "performance"},
    '/lifestyle-l':            {"gender": ["female"], "age_group": "adult", "subtitle": "lifestyle"},
    '/classic-women-shoes':    {"gender": ["female"], "age_group": "adult", "subtitle": "classic-shoes"},
    '/slippers-l':             {"gender": ["female"], "age_group": "adult", "subtitle": "slipper"},
    '/performance-kids':       {"gender": ["unisex"], "age_group": "youth", "subtitle": "performance"},
    '/lifestyle-kids':         {"gender": ["unisex"], "age_group": "youth", "subtitle": "lifestyle"},
    '/classic-children-shoes': {"gender": ["unisex"], "age_group": "youth", "subtitle": "classic-shoes"},
    '/slippers-kids':          {"gender": ["unisex"], "age_group": "youth", "subtitle": "slipper"},
    '/pe':                     {"gender": ["unisex"], "age_group": "youth", "subtitle": "pe"},
    '/athleisure-kids':        {"gender": ["unisex"], "age_group": "youth", "subtitle": "athleisure"},
}


@dataclass
class WorldBalanceShoe(BaseShoe):
    brand: str = "worldbalance"


def parse_price(raw: str) -> Tuple[float, float]:
    """
    Extract sale & original prices from a raw string like "₱1,234.00 ₱1,499.00".
    Returns (sale, original). If only one price found, both become that value.
    """
    nums = [m.replace(',', '') for m in re.findall(r'\d{1,3}(?:,\d{3})*\.\d{2}', raw)]
    if len(nums) >= 2:
        orig, sale = float(nums[0]), float(nums[1])
        return sale, orig
    if nums:
        v = float(nums[0])
        return v, v
    return 0.0, 0.0


class WorldBalanceExtractor(BaseExtractor):
    def __init__(self, category: str = "all", num_pages: int = -1):
        """
        :param category: "all" to scrape every path; otherwise a single category path like '/performance'
        :param num_pages: -1 → fetch until two consecutive empty pages per path; else limit pages
        """
        self.category = category
        self.num_pages = num_pages

    def _extract_products_from_html(self, html: str, path: str) -> List[WorldBalanceShoe]:
        """
        Given HTML for a collection page and its path (e.g. '/performance'),
        parse all <div class="grid__item" data-product-id="..."> cards.
        Returns a list of WorldBalanceShoe objects.
        """
        soup = BeautifulSoup(html, 'html.parser')
        cards = soup.select('div.grid__item[data-product-id]')
        logger.info(f"Found {len(cards)} cards in {path}")

        shoes: List[WorldBalanceShoe] = []
        cfg = category_config.get(path, {})

        for c in cards:
            try:
                pid = c['data-product-id'].strip()

                # Title & link
                link = c.select_one('a.grid-product__link')
                name_el = c.select_one('div.grid-product__title')
                title = name_el.get_text(strip=True) if name_el else ''

                href = link['href'] if link and link.has_attr('href') else ''
                url = href if href.startswith('http') else f"{BASE_URL}{href}"

                # Image
                img_el = c.select_one('img.grid-product__image')
                img_url = ''
                if img_el and img_el.has_attr('src'):
                    img_url = img_el['src']
                    if img_url.startswith('//'):
                        img_url = 'https:' + img_url
                    elif img_url.startswith('/'):
                        img_url = BASE_URL + img_url

                # Price text
                price_el = c.select_one('div.grid-product__price')
                raw_price = price_el.get_text(separator=' ', strip=True) if price_el else ''
                sale, orig = parse_price(raw_price)

                shoes.append(WorldBalanceShoe(
                    id=pid,
                    title=title,
                    subTitle=cfg.get("subtitle", ""),
                    url=url,
                    image=img_url,
                    price_sale=sale,
                    price_original=orig,
                    gender=cfg.get("gender", []),
                    age_group=cfg.get("age_group", ""),
                    brand="worldbalance",
                ))
            except Exception as e:
                logger.error(f"Error on {path}: {e}")

        return shoes

    def _get_total_pages(self, html: str) -> int:
        """
        Inspect pagination links like <div class="pagination"><a>1</a> <a>2</a> …</div>
        and return the highest page number. Defaults to 1 if none found.
        """
        soup = BeautifulSoup(html, 'html.parser')
        nums = [
            int(a.get_text())
            for a in soup.select('div.pagination a')
            if a.get_text().isdigit()
        ]
        return max(nums) if nums else 1

    def _clean_data(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Ensure 'price_sale', 'price_original', and 'gender' columns exist.
        Cast prices to float ≥ 0, normalize 'gender' lists to lowercase,
        drop duplicates by 'id'.
        """
        # Guarantee required columns exist
        if 'price_original' not in df.columns:
            df['price_original'] = 0.0
        if 'price_sale' not in df.columns:
            df['price_sale'] = 0.0
        if 'gender' not in df.columns:
            df['gender'] = [[] for _ in range(len(df))]

        df['image'] = df['image'].fillna("no_image.png")   
        df['price_original'] = df['price_original'].fillna(0).astype(float).clip(lower=0)
        df['price_sale']     = df['price_sale'].fillna(0).astype(float).clip(lower=0)
        df['gender'] = df['gender'].apply(lambda g: [x.lower() for x in g] if isinstance(g, list) else [])
        return df.drop_duplicates(subset=['id'], keep='first').reset_index(drop=True)

    def _run_data_quality_tests(self, df: pd.DataFrame) -> bool:
        """
        Basic checks:
         - No nulls in 'price_sale' or 'price_original'
         - No negative prices
         - If both 'male' and 'female' appear in gender list, it must be ['unisex']
        """
        ok = True

        for col in ['price_original', 'price_sale']:
            null_count = df[col].isnull().sum()
            if null_count:
                logger.error(f"{col} has {null_count} null(s)")
                ok = False

        for _, row in df.iterrows():
            if row['price_original'] < 0 or row['price_sale'] < 0:
                logger.error(
                    f"{row['id']} has negative price(s): "
                    f"sale={row['price_sale']}, original={row['price_original']}"
                )
                ok = False

            genders = row['gender']
            if 'male' in genders and 'female' in genders and genders != ['unisex']:
                logger.error(f"{row['id']} gender not normalized: {genders}")
                ok = False

        if ok:
            logger.info("Data quality tests passed")
        else:
            logger.error("Data quality tests failed")

        return ok

    def extract(self) -> List[WorldBalanceShoe]:
        """
        1. Determine which collection paths to process (all or one).
        2. For each path:
             a. GET page=1 (with HEADERS), determine total pages via _get_total_pages.
             b. Loop pages 1..total_pages:
                - Fetch HTML with HEADERS.
                - Parse product cards via _extract_products_from_html.
                - If page yields no cards, break.
                - Sleep 1–2s between requests.
        3. Build DataFrame from collected shoes, clean & QC.
        4. Return a list of WorldBalanceShoe dataclasses.
        """
        all_shoes: List[WorldBalanceShoe] = []
        paths = product_lists_url if self.category.lower() == "all" else [self.category]

        for p in paths:
            first_url = f"{BASE_URL}{COLLECTION_PATH}{p}"
            logger.info(f"→ Fetching {first_url}")
            r1 = requests.get(first_url, headers=HEADERS)
            if r1.status_code != 200:
                logger.error(f"{p} fetch failed: {r1.status_code}")
                continue

            total_pages = self._get_total_pages(r1.text)
            logger.info(f"{p} has {total_pages} page(s)")

            for i in range(1, total_pages + 1):
                page_url = f"{BASE_URL}{COLLECTION_PATH}{p}?page={i}"
                logger.info(f"  · page {i}")
                resp = requests.get(page_url, headers=HEADERS)
                if resp.status_code != 200:
                    logger.error(f"Page {i} failed: {resp.status_code}")
                    break

                shoes = self._extract_products_from_html(resp.text, p)
                if not shoes:
                    logger.info("No items; stopping pages loop.")
                    break

                all_shoes.extend(shoes)
                if 0 <= self.num_pages == i:
                    break

                time.sleep(random.uniform(1, 2))

        # Build DataFrame and run cleaning/QC
        df = pd.DataFrame([s.__dict__ for s in all_shoes])
        df_clean = self._clean_data(df)
        self._run_data_quality_tests(df_clean)

        # Rebuild dataclasses from clean DataFrame
        results: List[WorldBalanceShoe] = []
        for rec in df_clean.to_dict('records'):
            results.append(WorldBalanceShoe(**rec))

        return results
