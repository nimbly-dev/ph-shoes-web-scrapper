# extractors/world_balance.py

import random
import re
import time
import json
from dataclasses import dataclass
from typing import List, Dict, Any, Optional

import pandas as pd
import requests
from bs4 import BeautifulSoup

from .base import BaseShoe, BaseExtractor
from logger import get_logger

logger = get_logger(__name__, log_file="./logs/world_balance_poc.log")

BASE_URL       = 'https://worldbalance.com.ph'
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

category_config: Dict[str, Dict[str, Any]] = {
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
    """
    Subclass of BaseShoe with brand preset to 'worldbalance'
    and optional JSON‐encoded `extra` field.
    """
    brand: str = "worldbalance"
    extra: Optional[str] = None


def parse_price(raw: str) -> (float, float):
    """
    Extract sale & original prices from text like "₱1,234.00 ₱1,499.00".
    Returns (sale, original).
    """
    nums = [m.replace(',', '') for m in re.findall(r'\d{1,3}(?:,\d{3})*\.\d{2}', raw)]
    if len(nums) >= 2:
        return float(nums[0]), float(nums[1])
    if nums:
        v = float(nums[0])
        return v, v
    return 0.0, 0.0


class WorldBalanceExtractor(BaseExtractor):
    """
    Extractor for World Balance PH.  
    Crawls each collection path, scrapes product cards,
    normalizes into BaseShoe shape, bundles category into `extra`.
    """

    def __init__(self, category: str = "all", num_pages: int = -1):
        self.category = category
        self.num_pages = num_pages

    def _extract_products_from_html(self, html: str, path: str) -> List[WorldBalanceShoe]:
        soup  = BeautifulSoup(html, 'html.parser')
        cards = soup.select('div.grid__item[data-product-id]')
        logger.info(f"[Parse] Found {len(cards)} cards in {path}")

        shoes: List[WorldBalanceShoe] = []
        cfg = category_config.get(path, {})

        for c in cards:
            try:
                pid = c['data-product-id'].strip()

                # Title & URL
                link    = c.select_one('a.grid-product__link')
                name_el = c.select_one('div.grid-product__title')
                title   = name_el.get_text(strip=True) if name_el else ''
                href    = link['href'] if link and link.has_attr('href') else ''
                url     = href if href.startswith('http') else f"{BASE_URL}{href}"

                # Image
                img_el = c.select_one('img.grid-product__image')
                img_url = ''
                if img_el and img_el.has_attr('src'):
                    img_url = img_el['src']
                    if img_url.startswith('//'):
                        img_url = 'https:' + img_url
                    elif img_url.startswith('/'):
                        img_url = BASE_URL + img_url

                # Prices
                price_el = c.select_one('div.grid-product__price')
                raw_price = price_el.get_text(separator=' ', strip=True) if price_el else ''
                sale, orig = parse_price(raw_price)

                # Build the dataclass
                extras = {'category': path}
                shoes.append(WorldBalanceShoe(
                    id=pid,
                    title=title,
                    subTitle=cfg.get('subtitle', ''),
                    url=url,
                    image=img_url,
                    price_sale=sale,
                    price_original=orig,
                    gender=cfg.get('gender', []),
                    age_group=cfg.get('age_group', ''),
                    brand="worldbalance",
                    extra=json.dumps(extras, ensure_ascii=False)
                ))

            except Exception as e:
                logger.error(f"[Parse] Error on {path}: {e}")

        return shoes

    def _get_total_pages(self, html: str) -> int:
        soup = BeautifulSoup(html, 'html.parser')
        nums = [int(a.get_text()) for a in soup.select('div.pagination a') if a.get_text().isdigit()]
        return max(nums) if nums else 1

    def _clean_data(self, df: pd.DataFrame) -> pd.DataFrame:
        # Ensure all canonical columns exist
        for col in ['price_sale','price_original','gender','extra']:
            if col not in df.columns:
                df[col] = None
        df['image'] = df['image'].fillna("no_image.png")
        df['price_sale']     = pd.to_numeric(df['price_sale'], errors='coerce').fillna(0).clip(lower=0)
        df['price_original'] = pd.to_numeric(df['price_original'], errors='coerce').fillna(0).clip(lower=0)
        df['gender'] = df['gender'].apply(lambda g: [x.lower() for x in g] if isinstance(g, list) else [])
        return df.drop_duplicates(subset=['id'], keep='first').reset_index(drop=True)

    def _run_data_quality_tests(self, df: pd.DataFrame) -> bool:
        ok = True
        required = [
            "id","title","subTitle","url","image",
            "price_sale","price_original",
            "gender","age_group","brand","extra"
        ]
        missing = [c for c in required if c not in df.columns]
        if missing:
            logger.error(f"[DQ Fail] Missing columns: {missing}")
            ok = False

        for col in ["price_sale","price_original"]:
            if df[col].isnull().any():
                logger.error(f"[DQ Fail] {col} has nulls")
                ok = False
            if not pd.api.types.is_numeric_dtype(df[col]):
                logger.error(f"[DQ Fail] {col} is not numeric")
                ok = False

        if not df["id"].is_unique:
            dupes = df[df.duplicated("id", keep=False)]["id"].unique().tolist()
            logger.error(f"[DQ Fail] Duplicate id(s): {dupes}")
            ok = False

        if ok:
            logger.info("[DQ] Data quality tests passed")
        else:
            logger.error("[DQ] Data quality tests **failed**")
        return ok

    def extract(self) -> List[WorldBalanceShoe]:
        all_shoes: List[WorldBalanceShoe] = []
        paths = product_lists_url if self.category.lower() == "all" else [self.category]

        for p in paths:
            first_url = f"{BASE_URL}{COLLECTION_PATH}{p}"
            logger.info(f"[Fetch] GET {first_url}")
            r1 = requests.get(first_url, headers=HEADERS)
            if r1.status_code != 200:
                logger.error(f"[Fetch] {p} failed: {r1.status_code}")
                continue

            total_pages = self._get_total_pages(r1.text)
            logger.info(f"[Info] {p} has {total_pages} page(s)")

            for i in range(1, total_pages + 1):
                page_url = f"{BASE_URL}{COLLECTION_PATH}{p}?page={i}"
                logger.info(f"[Fetch] GET {page_url}")
                resp = requests.get(page_url, headers=HEADERS)
                if resp.status_code != 200:
                    logger.error(f"[Fetch] {page_url} failed: {resp.status_code}")
                    break

                batch = self._extract_products_from_html(resp.text, p)
                if not batch:
                    logger.info("[Info] No items on this page—stopping pagination.")
                    break

                all_shoes.extend(batch)

                if 0 <= self.num_pages == i:
                    break
                time.sleep(random.uniform(1, 2))

        # Build DataFrame, clean, DQ, and return dataclasses
        df = pd.DataFrame([s.__dict__ for s in all_shoes])
        df_clean = self._clean_data(df)
        self._run_data_quality_tests(df_clean)
        return [WorldBalanceShoe(**rec) for rec in df_clean.to_dict('records')]
