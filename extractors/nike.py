# nike.py

import json
import re
import time
import requests
from typing import List, Optional
from dataclasses import dataclass

import pandas as pd

from .base import BaseShoe, BaseExtractor
from logger import get_logger

logger = get_logger(__name__, log_file="./logs/nike_poc.log")


@dataclass
class NikeShoe(BaseShoe):
    brand: str = "nike"
    colordescription: Optional[str] = None
    out_of_stock: Optional[bool] = False
    best_seller: Optional[bool] = False


class NikeExtractor(BaseExtractor):
    BASE_URL = 'https://api.nike.com'
    SITE_BASE = 'https://www.nike.com/ph/w'
    API_BASE = 'https://api.nike.com'

    SESSION = requests.Session()
    DEFAULT_HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36"
        ),
        "nike-api-caller-id": "com.nike.commerce.nikedotcom.snkrs.web"
    }
    SESSION.headers.update(DEFAULT_HEADERS)

    PRODUCT_LISTS_URL = [
        '/mens-shoes-nik1zy7ok',
        '/womens-shoes-5e1x6zy7ok',
        '/older-kids-agibjzv4dh',
        '/little-kids-6dacezv4dh',
        '/baby-toddlers-kids-2j488zv4dh'
    ]
    CATEGORY_CONFIG = {
        '/mens-shoes-nik1zy7ok':         {"gender": ["male"],    "age_group": "adult"},
        '/womens-shoes-5e1x6zy7ok':       {"gender": ["female"],  "age_group": "adult"},
        '/older-kids-agibjzv4dh':         {"gender": ["unisex"],  "age_group": "youth"},
        '/little-kids-6dacezv4dh':        {"gender": ["unisex"],  "age_group": "kids"},
        '/baby-toddlers-kids-2j488zv4dh': {"gender": ["unisex"],  "age_group": "toddlers"},
    }

    def __init__(self, category: str = "all", num_pages: int = -1):
        self.category = category
        self.num_pages = num_pages

    def _get_products_from_groupings(self, stub: Optional[str], products: list) -> list:
        # If stub is None or empty, nothing to load
        if not stub:
            return products

        resp = self.SESSION.get(self.API_BASE + stub, headers=self.DEFAULT_HEADERS).json()
        groupings = resp.get('productGroupings', []) or []
        for grouping in groupings:
            prod_list = grouping.get('products') or []
            products.extend(prod_list)

        next_page = None
        pages = resp.get('pages')
        if isinstance(pages, dict):
            next_page = pages.get('next')

        if next_page:
            return self._get_products_from_groupings(next_page, products)
        return products

    def _extract_product_data(self, product: dict) -> dict:
        return {
            'id':                product.get('productCode', ''),
            'title':             product.get('copy', {}).get('title', ''),
            'subTitle':          product.get('copy', {}).get('subTitle'),
            'url':               product.get('pdpUrl', {}).get('url', ''),
            'image':             product.get('colorwayImages', {}).get('portraitURL'),
            'price_original':    product.get('prices', {}).get('initialPrice', 0.0),
            'price_sale':        product.get('prices', {}).get('currentPrice', 0.0),
            'brand':             product.get('brand', {}).get('name', 'nike').lower(),
            'colordescription':  product.get('displayColors', {}).get('colorDescription'),
            'out_of_stock':      any("OUT_OF_STOCK" in a for a in (product.get('featuredAttributes') or [])),
            'best_seller':       any("BEST_SELLER"  in a for a in (product.get('featuredAttributes') or []))
        }

    def _process_category(self, category_path: str, config: dict) -> List[NikeShoe]:
        logger.info(f"Processing category: {category_path}")
        start = time.time()
        html = self.SESSION.get(self.SITE_BASE + category_path, headers=self.DEFAULT_HEADERS).text

        m = re.search(
            r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>',
            html, re.DOTALL
        )
        if not m:
            raise Exception(f"__NEXT_DATA__ not found for {category_path}")
        redux = json.loads(m.group(1))

        try:
            wall = redux['props']['pageProps']['initialState']['Wall']
            api_stub = re.sub(r'anchor=\d+', 'anchor=0', wall['pageData']['next'])
        except KeyError:
            raise Exception(f"Lazy-load URL missing in JSON for {category_path}")

        products = self._get_products_from_groupings(api_stub, [])
        logger.info(f"Found {len(products)} raw products in {category_path}")

        shoes = []
        for p in products:
            d = self._extract_product_data(p)
            shoes.append(NikeShoe(
                id=d['id'],
                title=d['title'],
                subTitle=d['subTitle'],
                url=d['url'],
                image=d['image'],
                price_sale=d['price_sale'],
                price_original=d['price_original'],
                gender=config.get("gender", []),
                age_group=config.get("age_group", ""),
                brand=d['brand'],
                colordescription=d['colordescription'],
                out_of_stock=d['out_of_stock'],
                best_seller=d['best_seller']
            ))

        logger.info(f"Category {category_path} done in {time.time() - start:.2f}s")
        return shoes

    def _clean_data(self, df: pd.DataFrame) -> pd.DataFrame:
        df['brand'] = df['brand'].str.lower().str.strip()
        df['image'] = df['image'].fillna("")   

        
        # 1) Filter out any row where title OR subTitle contains "sportswear" or "tshirt"
        pattern = r"(sportswear|tshirt|drifit|t-shirt|cap|shorts|short|jacket|hoodie|backpack|socks|trousers|bag)"
        mask_title    = ~df["title"].str.contains(pattern, case=False, na=False)
        mask_subtitle = ~df["subTitle"].str.contains(pattern, case=False, na=False)
        df = df[mask_title & mask_subtitle]

        # 2) Existing null‐and‐negative‐price handling
        df["price_sale"]     = df["price_sale"].fillna(0)
        df["price_original"] = df["price_original"].fillna(0)

        def norm_gender(g):
            if isinstance(g, list) and 'male' in g and 'female' in g:
                return ['unisex']
            return g

        if 'gender' in df:
            df['gender'] = df['gender'].apply(norm_gender)

        df[['price_sale', 'price_original']] = df[['price_sale', 'price_original']].clip(lower=0)
        return df.drop_duplicates(subset=['id'], keep='first')

    def _run_data_quality_tests(self, df: pd.DataFrame) -> bool:
        ok = True
        for col in ['price_sale', 'price_original']:
            n = df[col].isnull().sum()
            if n:
                logger.error(f"{col} has {n} null(s)")
                ok = False

        for _, row in df.iterrows():
            g = row['gender']
            if isinstance(g, list) and 'male' in g and 'female' in g and g != ['unisex']:
                logger.error(f"{row['id']} gender not normalized: {g}")
                ok = False

            for col in ['price_sale', 'price_original']:
                if row[col] < 0:
                    logger.error(f"{row['id']} has negative {col}: {row[col]}")
                    ok = False

        if ok:
            logger.info("Data quality tests passed")
        else:
            logger.error("Data quality tests failed")
        return ok

    def extract(self) -> List[NikeShoe]:
        all_shoes = []
        if self.category.lower() == "all":
            for cat in self.PRODUCT_LISTS_URL:
                cfg = self.CATEGORY_CONFIG.get(cat, {})
                all_shoes += self._process_category(cat, cfg)
        else:
            path = self.category if self.category.startswith("/") else f"/{self.category}"
            cfg = self.CATEGORY_CONFIG.get(path)
            if not cfg:
                raise ValueError(f"Unsupported category: {self.category}")
            all_shoes = self._process_category(path, cfg)

        df = pd.DataFrame([s.__dict__ for s in all_shoes])
        df_clean = self._clean_data(df)
        self._run_data_quality_tests(df_clean)

        cleaned_shoes = []
        for rec in df_clean.to_dict(orient='records'):
            cleaned_shoes.append(NikeShoe(**rec))

        return cleaned_shoes
