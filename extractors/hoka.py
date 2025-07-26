# hoka.py

import time
import re
import requests
import json
import html
from bs4 import BeautifulSoup
from typing import List, Optional, Dict, Any
from dataclasses import dataclass

import pandas as pd

from .base import BaseShoe, BaseExtractor
from logger import get_logger

logger = get_logger(__name__, log_file="./logs/hoka_poc.log")


BASE_URL = "https://www.hoka.com/en/ph"
PRODUCT_LISTS = [
    # MEN
    '/mens-road',
    '/mens-trail',
    '/mens-trail-hiking-shoes',
    '/mens-walking',
    '/mens-fitness',
    '/mens-recovery-comfort-shoes',
    '/mens-stability-shoes',
    '/mens-wides',
    '/mens-sandals',
    '/mens-lifestyle',
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
    # KIDS
    '/kids'
]
CATEGORY_CONFIG: Dict[str, Dict[str, Any]] = {
    '/mens-road':    {"gender": ["male"],   "age_group": "adult",   "subTitle": "road"},
    '/mens-trail':   {"gender": ["male"],   "age_group": "adult",   "subTitle": "trail"},
    '/mens-trail-hiking-shoes': {"gender": ["male"],   "age_group": "adult", "subTitle": "trail-hiking"},
    '/mens-walking': {"gender": ["male"],   "age_group": "adult",   "subTitle": "walking"},
    '/mens-fitness': {"gender": ["male"],   "age_group": "adult",   "subTitle": "fitness"},
    '/mens-recovery-comfort-shoes': {"gender": ["male"],   "age_group": "adult", "subTitle": "recovery-comfort"},
    '/mens-stability-shoes': {"gender": ["male"],   "age_group": "adult",   "subTitle": "stability"},
    '/mens-wides':   {"gender": ["male"],   "age_group": "adult",   "subTitle": "wides"},
    '/mens-sandals': {"gender": ["male"],   "age_group": "adult",   "subTitle": "sandals"},
    '/mens-lifestyle': {"gender": ["male"],   "age_group": "adult",   "subTitle": "lifestyle"},

    '/womens-road':    {"gender": ["female"], "age_group": "adult",   "subTitle": "road"},
    '/womens-trail':   {"gender": ["female"], "age_group": "adult",   "subTitle": "trail"},
    '/womens-trail-hiking-shoes': {"gender": ["female"], "age_group": "adult", "subTitle": "trail-hiking"},
    '/womens-walking': {"gender": ["female"], "age_group": "adult",   "subTitle": "walking"},
    '/womens-fitness': {"gender": ["female"], "age_group": "adult",   "subTitle": "fitness"},
    '/womens-recovery-comfort-shoes': {"gender": ["female"], "age_group": "adult", "subTitle": "recovery-comfort"},
    '/womens-stability-shoes': {"gender": ["female"], "age_group": "adult",   "subTitle": "stability"},
    '/womens-wides':   {"gender": ["female"], "age_group": "adult",   "subTitle": "wides"},
    '/womens-sandals': {"gender": ["female"], "age_group": "adult",   "subTitle": "sandals"},
    '/womens-lifestyle': {"gender": ["female"], "age_group": "adult",   "subTitle": "lifestyle"},

    '/kids': {"gender": ["unisex"], "age_group": "youth", "subTitle": "kids"}
}


@dataclass
class HokaShoe(BaseShoe):
    """
    Subclass of BaseShoe with brand preset to 'hoka'
    and an optional JSON‐encoded `extra` field.
    """
    brand: str = "hoka"
    extra: Optional[str] = None


class HokaExtractor(BaseExtractor):
    """
    Extractor for Hoka shoes. Crawls each category,
    normalizes into BaseShoe shape, and bundles any
    site-specific bits into `extra`.
    """

    def __init__(self, category: str = "all", num_pages: int = -1):
        self.category = category
        self.num_pages = num_pages

    def _fetch_page(self, url: str) -> str:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
        resp = requests.get(url, headers=headers, timeout=30)
        resp.raise_for_status()
        return resp.text

    def _extract_image(self, prod) -> str:
        # Try <img> tag, then data-images JSON, else blank
        img = prod.find("img", class_="tile-image")
        if img and img.get("src"):
            return img["src"].strip()
        cont = prod.find("div", class_="image-container")
        if cont and cont.has_attr("data-images"):
            try:
                data = json.loads(html.unescape(cont["data-images"]))
                for grp in data.values():
                    if "default" in grp and "medium" in grp["default"]:
                        url = grp["default"]["medium"][0].get("url")
                        if url:
                            return url.strip()
            except Exception:
                pass
        return ""

    def _parse_price(self, tag) -> Optional[float]:
        if not tag:
            return None
        text = tag.get_text(strip=True).replace("₱", "").replace(",", "")
        try:
            return float(text) if text else None
        except ValueError:
            logger.warning(f"Could not parse price from: '{text}'")
            return None

    def _extract_products(self, html_str: str, path: str) -> List[dict]:
        """
        Parse one page of HTML, return a list of dicts
        with canonical BaseShoe fields plus `extra`.
        """
        soup = BeautifulSoup(html_str, 'html.parser')
        tiles = soup.find_all('div', class_='product', attrs={'data-pid': True})
        shoes: List[dict] = []
        cfg = CATEGORY_CONFIG.get(path, {})

        for prod in tiles:
            pid = prod.get("data-pid")
            # title
            nm = prod.find("div", class_="tile-product-name")
            title = nm.get_text(strip=True) if nm else ""
            # URL
            ln = prod.find("a", class_="js-pdp-link")
            href = ln["href"].strip() if ln and ln.has_attr("href") else ""
            url = href if href.startswith("http") else f"{BASE_URL}{href}"
            # image
            image = self._extract_image(prod)
            # prices
            sale_tag = prod.find("span", class_="sales")
            orig_tag = prod.find("span", class_="original-price")
            ps = self._parse_price(sale_tag) or 0.0
            po = self._parse_price(orig_tag) or ps

            rec: Dict[str, Any] = {
                "id":             pid,
                "title":          title,
                "subTitle":       cfg.get("subTitle"),
                "url":            url,
                "image":          image,
                "price_sale":     ps,
                "price_original": po,
                "gender":         cfg.get("gender", []),
                "age_group":      cfg.get("age_group", ""),
                "brand":          "hoka",
            }

            # bundle any site‐specific bits into `extra`
            extras = {"category": path}
            rec["extra"] = json.dumps(extras, ensure_ascii=False) if extras else None

            shoes.append(rec)

        return shoes

    def _scrape_category(self, path: str) -> List[dict]:
        """
        Fetch pages in one category until no new items,
        returning a deduped list of raw dicts.
        """
        first_url = f"{BASE_URL}{path}/"
        logger.info(f"Fetching first page: {first_url}")
        html_str = self._fetch_page(first_url)
        first_batch = self._extract_products(html_str, path)

        page_size = len(first_batch) or 12
        final = first_batch
        prev_count = 0
        sz = page_size

        # increase ?sz= until count stabilizes
        while True:
            url = first_url if sz == page_size else f"{BASE_URL}{path}/?sz={sz}"
            logger.info(f"Fetching: {url}")
            html_str = self._fetch_page(url)
            batch = self._extract_products(html_str, path)
            count = len(batch)
            if count == prev_count:
                break
            final = batch
            prev_count = count
            sz += page_size
            if 0 <= self.num_pages <= (sz // page_size):
                break
            time.sleep(0.5)

        return final

    def _clean_data(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Normalize price columns, lowercase gender,
        drop null/duplicates, ensure image not null.
        """
        df["price_sale"]     = pd.to_numeric(df["price_sale"], errors="coerce").fillna(0).clip(lower=0)
        df["price_original"] = pd.to_numeric(df["price_original"], errors="coerce").fillna(0).clip(lower=0)
        df["gender"]         = df["gender"].apply(lambda g: [x.lower() for x in g] if isinstance(g, list) else [])
        df = df.dropna(subset=["id"]).drop_duplicates(subset=["id"], keep="first")
        df["image"] = df["image"].fillna("")
        return df.reset_index(drop=True)

    def _run_data_quality_tests(self, df: pd.DataFrame) -> bool:
        """
        Basic sanity checks: required columns exist, prices are numeric & non-null,
        IDs are unique. Returns True if all pass.
        """
        ok = True
        
        required = [
            "id", "title", "subTitle", "url", "image",
            "price_sale", "price_original", "gender", "age_group", "brand", "extra"
        ]
        missing = [c for c in required if c not in df.columns]
        if missing:
            logger.error(f"[DQ Fail] Missing columns: {missing}")
            ok = False

        for col in ["price_sale", "price_original"]:
            if df[col].isnull().any():
                logger.error(f"[DQ Fail] {col} has nulls")
                ok = False
            if not pd.api.types.is_numeric_dtype(df[col]):
                logger.error(f"[DQ Fail] {col} is not numeric")
                ok = False

        if not df["id"].is_unique:
            dupes = df[df.duplicated("id", keep=False)]["id"].unique().tolist()
            logger.error(f"[DQ Fail] Duplicate id(s) found: {dupes}")
            ok = False

        if ok:
            logger.info("[DQ] Data quality tests passed")
        else:
            logger.error("[DQ] Data quality tests **failed**")
        return ok

    def extract(self) -> List[HokaShoe]:
        """
        Entry point: scrape all (or one) category,
        clean + QA, and return dataclass instances.
        """
        paths = PRODUCT_LISTS if self.category.lower() == "all" else [self.category]
        raw: List[dict] = []
        for p in paths:
            logger.info(f"Processing category {p}")
            raw.extend(self._scrape_category(p))
            time.sleep(1)

        df = pd.DataFrame(raw)
        df_clean = self._clean_data(df)
        self._run_data_quality_tests(df_clean)

        return [HokaShoe(**rec) for rec in df_clean.to_dict(orient="records")]
