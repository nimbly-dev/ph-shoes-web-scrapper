import json
import random
import time
import re
import requests
from bs4 import BeautifulSoup
from typing import List
from dataclasses import dataclass

import pandas as pd

from .base import BaseShoe, BaseExtractor
from logger import get_logger

logger = get_logger(__name__, log_file="./logs/world_balance_poc.log")


@dataclass
class WorldBalanceShoe(BaseShoe):
    pass


class WorldBalanceExtractor(BaseExtractor):
    BASE_URL = 'https://worldbalance.com.ph/collections'
    HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    PRODUCT_LISTS = [
        '/performance', '/lifestyle-m', '/athleisure-m', '/classic-men-shoes', '/slipper-m',
        '/performance-l', '/lifestyle-l', '/classic-women-shoes', '/slippers-l',
        '/performance-kids', '/lifestyle-kids', '/classic-children-shoes', '/slippers-kids',
        '/pe', '/athleisure-kids'
    ]
    CATEGORY_CONFIG = {
        '/performance':            {"gender": ["male"],   "age_group": "adult",   "subtitle": "performance"},
        '/lifestyle-m':            {"gender": ["male"],   "age_group": "adult",   "subtitle": "lifestyle"},
        '/athleisure-m':           {"gender": ["male"],   "age_group": "adult",   "subtitle": "athleisure"},
        '/classic-men-shoes':      {"gender": ["male"],   "age_group": "adult",   "subtitle": "classic-shoes"},
        '/slipper-m':              {"gender": ["male"],   "age_group": "adult",   "subtitle": "slipper"},
        '/performance-l':          {"gender": ["female"], "age_group": "adult",   "subtitle": "performance"},
        '/lifestyle-l':            {"gender": ["female"], "age_group": "adult",   "subtitle": "lifestyle"},
        '/classic-women-shoes':    {"gender": ["female"], "age_group": "adult",   "subtitle": "classic-shoes"},
        '/slippers-l':             {"gender": ["female"], "age_group": "adult",   "subtitle": "slipper"},
        '/performance-kids':       {"gender": ["unisex"], "age_group": "youth",   "subtitle": "performance"},
        '/lifestyle-kids':         {"gender": ["unisex"], "age_group": "youth",   "subtitle": "lifestyle"},
        '/classic-children-shoes': {"gender": ["unisex"], "age_group": "youth",   "subtitle": "classic-shoes"},
        '/slippers-kids':          {"gender": ["unisex"], "age_group": "youth",   "subtitle": "slipper"},
        '/pe':                     {"gender": ["unisex"], "age_group": "youth",   "subtitle": "pe"},
        '/athleisure-kids':        {"gender": ["unisex"], "age_group": "youth",   "subtitle": "athleisure"},
    }

    def __init__(self, category: str = "all", num_pages: int = -1):
        self.category = category
        self.num_pages = num_pages

    def _extract_products_from_html(self, html: str, category_path: str) -> List[WorldBalanceShoe]:
        soup = BeautifulSoup(html, 'html.parser')
        cards = soup.select('div.grid__item[data-product-id]')
        logger.info(f"Found {len(cards)} cards in {category_path}")

        shoes = []
        for card in cards:
            try:
                pid = card['data-product-id']
                link = card.select_one('a.grid-product__link')
                name_el = card.select_one('div.grid-product__title')
                price_el = card.select_one('div.grid-product__price')
                img_el = card.select_one('img.grid-product__image')

                name = name_el.get_text(strip=True) if name_el else ''
                href = link['href'] if link and link.has_attr('href') else ''
                url = href if href.startswith('http') else f'https://worldbalance.com.ph{href}'

                img_url = ''
                if img_el and img_el.has_attr('src'):
                    img_url = img_el['src']
                    if img_url.startswith('//'):
                        img_url = 'https:' + img_url
                    elif img_url.startswith('/'):
                        img_url = 'https://worldbalance.com.ph' + img_url

                def clean(x: str) -> float:
                    return float(re.sub(r'[^\d.]', '', x)) if x else 0.0

                price = clean(price_el.get_text()) if price_el else 0.0

                details = self.CATEGORY_CONFIG[category_path]
                data = {
                    "id": pid,
                    "title": name,
                    "subTitle": details["subtitle"],
                    "url": url,
                    "image": img_url,
                    "price_sale": price,
                    "price_original": price,
                    "gender": details["gender"],
                    "age_group": details["age_group"]
                }
                shoes.append(WorldBalanceShoe(**data))
            except Exception as ex:
                logger.error(f"Error extracting product card: {ex}")
        return shoes

    def _get_total_pages(self, html: str) -> int:
        soup = BeautifulSoup(html, 'html.parser')
        nums = [
            int(a.text.strip())
            for a in soup.select('div.pagination a')
            if a.text.strip().isdigit()
        ]
        return max(nums) if nums else 1

    def _clean_data(self, df: pd.DataFrame) -> pd.DataFrame:
        df['price_original'] = df['price_original'].fillna(0).astype(float).clip(lower=0)
        df['price_sale']     = df['price_sale'].fillna(0).astype(float).clip(lower=0)
        df['gender'] = df['gender'].apply(lambda g: [x.lower() for x in g] if isinstance(g, list) else [])
        return df.drop_duplicates(subset=['id'], keep='first')

    def _run_data_quality_tests(self, df: pd.DataFrame) -> bool:
        ok = True
        for col in ['price_original','price_sale']:
            n = df[col].isnull().sum()
            if n:
                logger.error(f"{col} has {n} null(s)")
                ok = False
        for idx,row in df.iterrows():
            for col in ['price_original','price_sale']:
                if row[col] < 0:
                    logger.error(f"{row['id']} negative {col}: {row[col]}")
                    ok = False
        for idx,row in df.iterrows():
            g = row['gender']
            if 'male' in g and 'female' in g and g != ['unisex']:
                logger.error(f"{row['id']} gender not normalized: {g}")
                ok = False
        if ok:
            logger.info("Data quality tests passed")
        else:
            logger.error("Data quality tests failed")
        return ok

    def extract(self) -> List[WorldBalanceShoe]:
        all_shoes: List[WorldBalanceShoe] = []
        paths = self.PRODUCT_LISTS if self.category.lower() == "all" else [self.category]
        for path in paths:
            first_url = f"{self.BASE_URL}{path}"
            r1 = requests.get(first_url, headers=self.HEADERS)
            if r1.status_code != 200:
                logger.error(f"Failed to fetch {first_url}: {r1.status_code}")
                continue
            total = self._get_total_pages(r1.text)
            for page in range(1, total+1):
                url = f"{self.BASE_URL}{path}?page={page}"
                r = requests.get(url, headers=self.HEADERS)
                if r.status_code != 200:
                    logger.error(f"Failed to fetch {url}: {r.status_code}")
                    break
                shoes = self._extract_products_from_html(r.text, path)
                if not shoes:
                    break
                all_shoes.extend(shoes)
                if 0 <= self.num_pages == page:
                    break
                time.sleep(random.uniform(1,2))

        df = pd.DataFrame([s.__dict__ for s in all_shoes])
        df_clean = self._clean_data(df)
        self._run_data_quality_tests(df_clean)
        return [WorldBalanceShoe(**rec) for rec in df_clean.to_dict('records')]
