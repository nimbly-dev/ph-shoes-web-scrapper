# hoka.py

import time
import re
import requests
import json
import html
from bs4 import BeautifulSoup
from typing import List, Optional
from dataclasses import dataclass

import pandas as pd

from .base import BaseShoe, BaseExtractor
from logger import get_logger

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
category_config = {
    '/mens-road':    {"gender": ["male"],   "age_group": "adult", "subTitle": "road"},
    '/mens-trail':   {"gender": ["male"],   "age_group": "adult", "subTitle": "trail"},
    '/mens-trail-hiking-shoes': {"gender": ["male"], "age_group": "adult", "subTitle": "trail-hiking"},
    '/mens-walking': {"gender": ["male"],   "age_group": "adult", "subTitle": "walking"},
    '/mens-fitness': {"gender": ["male"],   "age_group": "adult", "subTitle": "fitness"},
    '/mens-recovery-comfort-shoes': {"gender": ["male"], "age_group": "adult", "subTitle": "recovery-comfort"},
    '/mens-stability-shoes': {"gender": ["male"], "age_group": "adult", "subTitle": "stability"},
    '/mens-wides':   {"gender": ["male"],   "age_group": "adult", "subTitle": "wides"},
    '/mens-sandals': {"gender": ["male"],   "age_group": "adult", "subTitle": "sandals"},
    '/mens-lifestyle': {"gender": ["male"], "age_group": "adult", "subTitle": "lifestyle"},

    '/womens-road':    {"gender": ["female"], "age_group": "adult", "subTitle": "road"},
    '/womens-trail':   {"gender": ["female"], "age_group": "adult", "subTitle": "trail"},
    '/womens-trail-hiking-shoes': {"gender": ["female"], "age_group": "adult", "subTitle": "trail-hiking"},
    '/womens-walking': {"gender": ["female"], "age_group": "adult", "subTitle": "walking"},
    '/womens-fitness': {"gender": ["female"], "age_group": "adult", "subTitle": "fitness"},
    '/womens-recovery-comfort-shoes': {"gender": ["female"], "age_group": "adult", "subTitle": "recovery-comfort"},
    '/womens-stability-shoes': {"gender": ["female"], "age_group": "adult", "subTitle": "stability"},
    '/womens-wides':   {"gender": ["female"], "age_group": "adult", "subTitle": "wides"},
    '/womens-sandals': {"gender": ["female"], "age_group": "adult", "subTitle": "sandals"},
    '/womens-lifestyle': {"gender": ["female"], "age_group": "adult", "subTitle": "lifestyle"},

    '/kids': {"gender": ["unisex"], "age_group": "youth", "subTitle": "kids"}
}


@dataclass
class HokaShoe(BaseShoe):
    brand: str = "hoka"


def fetch_page(url: str) -> str:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/116.0.5845.97 Safari/537.36"
        )
    }
    resp = requests.get(url, headers=headers)
    resp.raise_for_status()
    return resp.text


def extract_image(prod) -> str:
    img = prod.find("img", class_="tile-image")
    if img and img.get("src"):
        return img["src"].strip()
    cont = prod.find("div", class_="image-container")
    if cont and cont.has_attr("data-images"):
        try:
            data = json.loads(cont["data-images"])
            for grp in data.values():
                if "default" in grp and "medium" in grp["default"]:
                    url = grp["default"]["medium"][0].get("url")
                    if url:
                        return url.strip()
        except:
            pass
    return ""


def parse_hoka_products(html: str) -> List[dict]:
    soup = BeautifulSoup(html, 'html.parser')
    elems = soup.find_all('div', class_='product', attrs={'data-pid': True})
    out = []
    for prod in elems:
        rec = {}
        rec["id"] = prod.get("data-pid")
        nm = prod.find("div", class_="tile-product-name")
        if nm and (a := nm.find("a", class_="link")):
            rec["title"] = a.get_text(strip=True)
        if (ln := prod.find("a", class_="js-pdp-link")) and ln.has_attr("href"):
            href = ln["href"].strip()
            rec["url"] = href if href.startswith("http") else "https://www.hoka.com" + href
        rec["image"] = extract_image(prod)
        sale = prod.find("span", class_="sales")
        rec["price_sale"] = float(sale.get_text(strip=True).replace("₱", "").replace(",", "")) if sale else None
        orig = prod.find("span", class_="original-price")
        rec["price_original"] = (
            float(orig.get_text(strip=True).replace("₱", "").replace(",", ""))
            if orig else rec["price_sale"]
        )
        if rec.get("id") and rec.get("title"):
            out.append(rec)
    return out


class HokaExtractor(BaseExtractor):
    def __init__(self, category: str = "all", num_pages: int = -1):
        self.category = category
        self.num_pages = num_pages

    def _scrape_category(self, path: str) -> List[dict]:
        first = f"{base_url}{path}/"
        logger.info(f"Fetching first page: {first}")
        html = fetch_page(first)
        first_prods = parse_hoka_products(html)
        page_size = len(first_prods) or 12

        sz = page_size
        prev = 0
        final = first_prods

        while True:
            url = first if sz == page_size else f"{base_url}{path}/?sz={sz}"
            logger.info(f"Fetching: {url}")
            html = fetch_page(url)
            prods = parse_hoka_products(html)
            cnt = len(prods)
            logger.info(f"sz={sz} → {cnt} products")
            if cnt == prev:
                break
            final = prods
            prev = cnt
            sz += page_size
            time.sleep(0.5)
            if self.num_pages != -1 and (sz / page_size) >= self.num_pages:
                break

        # enrich with category_config
        extras = category_config.get(path, {})
        for r in final:
            r.update(extras)
        return final

    def _clean_data(self, df: pd.DataFrame) -> pd.DataFrame:
        # null → None (except id)
        for c in df.columns:
            if c != "id":
                df[c] = df[c].where(df[c].notna(), None)
        # drop missing id
        df = df[df["id"].notna()].copy()
        # title‐based gender normalization
        df["gender"] = df.apply(
            lambda r: ["unisex"]
            if r.get("age_group") == "adult" and r.get("title") and "unisex" in r["title"].lower()
            else r.get("gender"),
            axis=1
        )
        # dedupe
        df = df.drop_duplicates(subset=["id"], keep="first")
        # prices numeric
        for col in ["price_sale", "price_original"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        # clean title text
        df["title"] = (
            df["title"]
            .str.replace(r"(?i)men's|women's|kid's", "", regex=True)
            .str.replace(r"\s+", " ", regex=True)
            .str.strip()
        )
        
        df['image'] = df['image'].fillna("no_image.png")   
        return df

    def _run_data_quality_tests(self, df: pd.DataFrame) -> bool:
        ok = True
        req = ["id", "title", "subTitle", "url", "image", "price_sale", "price_original", "gender", "age_group", "brand"]
        miss = [c for c in req if c not in df.columns]
        if miss:
            logger.error(f"Missing columns: {miss}")
            ok = False
        if df["id"].isnull().any():
            logger.error("Null id values")
            ok = False
        nulls = df.isnull().sum()[lambda x: x > 0].to_dict()
        if nulls:
            logger.error(f"Nulls present: {nulls}")
            ok = False
        for col in ["price_sale", "price_original"]:
            if not pd.api.types.is_numeric_dtype(df[col]):
                logger.error(f"{col} not numeric")
                ok = False
        if ok:
            logger.info("Data quality tests passed")
        else:
            logger.error("Data quality tests failed")
        return ok

    def extract(self) -> List[HokaShoe]:
        all_dicts = []
        paths = product_lists_url if self.category.lower() == "all" else [self.category]
        for p in paths:
            logger.info(f"Processing category {p}")
            all_dicts.extend(self._scrape_category(p))
            time.sleep(1)

        df = pd.DataFrame(all_dicts)
        df_clean = self._clean_data(df)
        self._run_data_quality_tests(df_clean)

        # now we can safely instantiate HokaShoe with brand present
        shoes = [HokaShoe(**rec) for rec in df_clean.to_dict(orient="records")]
        return shoes
