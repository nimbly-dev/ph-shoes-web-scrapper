import time
import re
import json
from bs4 import BeautifulSoup
from typing import List
from dataclasses import dataclass

import pandas as pd

from .base import BaseShoe, BaseExtractor
from logger import get_logger
from playwright.sync_api import sync_playwright

logger = get_logger(__name__, log_file="./logs/new_balance_poc.log")

BASE_SEARCH_URL = "https://www.lazada.com.ph/new-alance-st-re/?q=All-Products&from=wangpu&langFlag=en&pageTypeId=2"

@dataclass
class NewBalanceShoe(BaseShoe):
    sold: str = None
    reviews: str = None
    location: str = None
    gender: List[str] = None
    age_group: str = None
    brand: str = None

class NewBalanceExtractor(BaseExtractor):
    def __init__(self, category: str = "all", num_pages: int = -1):
        self.category = category
        self.num_pages = num_pages

    def _fetch_page(self, page: int) -> str:
        url = BASE_SEARCH_URL + (f"&page={page}" if page > 1 else "")
        logger.info(f"Fetching: {url}")
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page_obj = browser.new_page()
            page_obj.goto(url, wait_until="domcontentloaded", timeout=60000)
            time.sleep(6)
            html = page_obj.content()
            browser.close()
        return html

    def _extract_image_url(self, prod) -> str:
        images = prod.find_all("img")
        for img in images:
            src = img.get("src") or img.get("data-src")
            if src and src.startswith("https://img.lazcdn.com/"):
                return src.strip()
        for img in images:
            src = img.get("src") or img.get("data-src")
            if src and not src.startswith("data:"):
                return src.strip()
        return ""

    def _parse_products(self, html: str) -> List[dict]:
        soup = BeautifulSoup(html, 'html.parser')
        elems = soup.select("div.Bm3ON[data-qa-locator='product-item']")
        prods = []
        for prod in elems:
            try:
                rec = {}
                rec["id"] = prod.get("data-item-id")
                a = prod.select_one("div.RfADt a")
                if a:
                    rec["title"] = a.get("title") or a.text.strip()
                    href = a.get("href", "")
                    rec["url"] = ("https:" + href) if href.startswith("//") else href
                else:
                    rec["title"] = rec["url"] = ""
                rec["subTitle"] = "running"
                sale = prod.select_one("div.aBrP0 span.ooOxS")
                rec["price_sale"] = sale.text if sale else None
                orig = prod.select_one("div.WNoq3 span._1m41m del.ooOxS")
                rec["price_original"] = orig.text if orig else rec["price_sale"]
                sold = prod.select_one("div._6uN7R span._1cEkb span")
                rec["sold"] = sold.text.strip() if sold else "N/A"
                rev = prod.select_one("div._6uN7R div.mdmmT._32vUv span.qzqFw")
                rec["reviews"] = rev.text.strip() if rev else "N/A"
                loc = prod.select_one("div._6uN7R span.oa6ri")
                rec["location"] = (loc.get("title") or loc.text.strip()) if loc else "N/A"
                rec["image"] = self._extract_image_url(prod)
                prods.append(rec)
            except Exception as e:
                logger.error(f"Error parsing product: {e}")
        return prods

    def _clean_data(self, df: pd.DataFrame) -> pd.DataFrame:
        # convert price strings → floats
        df["price_sale"] = df["price_sale"].astype(str).str.replace(r"[₱,]", "", regex=True).astype(float).fillna(0).clip(lower=0)
        df["price_original"] = df["price_original"].astype(str).str.replace(r"[₱,]", "", regex=True).astype(float).fillna(0).clip(lower=0)
        # add static attrs
        df["gender"] = [['unisex'] for _ in range(len(df))]
        df["age_group"] = "adult"
        df["brand"] = "new balance"
        # dedupe
        return df.drop_duplicates(subset=["id"], keep="first")

    def _run_data_quality_tests(self, df: pd.DataFrame) -> bool:
        ok = True
        # required columns
        req = ["id","title","url","price_sale","price_original","sold","reviews","location","gender","age_group","brand"]
        missing = [c for c in req if c not in df.columns]
        if missing:
            logger.error(f"Missing columns: {missing}")
            ok = False
        # id not null
        if df["id"].isnull().any():
            logger.error("Null id values found")
            ok = False
        # no nulls
        nulls = df.isnull().sum()[lambda x: x>0].to_dict()
        if nulls:
            logger.error(f"Nulls present: {nulls}")
            ok = False
        # price numeric
        for col in ["price_sale","price_original"]:
            if not pd.api.types.is_float_dtype(df[col]):
                logger.error(f"{col} not float dtype")
                ok = False
        if ok:
            logger.info("Data quality tests passed")
        else:
            logger.error("Data quality tests failed")
        return ok

    def extract(self) -> List[NewBalanceShoe]:
        all_recs = []
        page = 1
        prev = 0
        while True:
            try:
                html = self._fetch_page(page)
            except Exception as e:
                logger.error(f"Fetch error page {page}: {e}")
                break
            recs = self._parse_products(html)
            if not recs or len(recs) == prev:
                break
            all_recs.extend(recs)
            prev = len(recs)
            page += 1
            if self.num_pages != -1 and page > self.num_pages:
                break
            time.sleep(2)

        df = pd.DataFrame(all_recs)
        df_clean = self._clean_data(df)
        self._run_data_quality_tests(df_clean)

        shoes = []
        for rec in df_clean.to_dict(orient="records"):
            shoes.append(NewBalanceShoe(**rec))
        return shoes
