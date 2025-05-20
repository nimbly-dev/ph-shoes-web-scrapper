import json
import random
import time
import re
import requests
import pandas as pd
from urllib.parse import urljoin
from typing import List, Optional
from dataclasses import dataclass

from .base import BaseShoe, BaseExtractor

# --- Data class for Adidas shoes ---
@dataclass
class AdidasShoe(BaseShoe):
    # now accepts brand
    brand: Optional[str] = None

# --- Extractor ---
class AdidasExtractor(BaseExtractor):
    BASE_URL = "https://www.adidas.com.ph"
    HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    CATEGORY_CONFIG = {
        "men-shoes":     {"gender": ["male"],           "age_group": "adult"},
        "women-shoes":   {"gender": ["female"],         "age_group": "adult"},
        "boys-shoes":    {"gender": ["male"],           "age_group": "youth"},
        "girls-shoes":   {"gender": ["female"],         "age_group": "youth"},
        "infants-shoes": {"gender": ["male","female"],  "age_group": "toddlers"}
    }

    def __init__(self, category_endpoint: str, num_pages: int = -1):
        self.category_endpoint = category_endpoint.lower()
        self.num_pages = num_pages

    def _get_api_url(self, start: int, search_term: str) -> str:
        return (
            f"{self.BASE_URL}/api/plp/content-engine?"
            f"sitePath=en&query={search_term}&start={start}"
        )

    def _fetch_json(self, url: str) -> dict:
        r = requests.get(url, headers=self.HEADERS, timeout=30)
        r.raise_for_status()
        return r.json()

    def _extract_raw(self, search_term: str, config: dict) -> List[AdidasShoe]:
        shoes = []
        page = 0
        while True:
            start = page * 48
            api = self._get_api_url(start, search_term)
            data = self._fetch_json(api)
            items = data.get("raw", {}).get("itemList", {}).get("items", [])
            if not items or (self.num_pages != -1 and page >= self.num_pages):
                break
            for p in items:
                shoes.append(AdidasShoe(
                    id             = p.get("productId",""),
                    title          = p.get("displayName",""),
                    subTitle       = p.get("subTitle"),
                    url            = urljoin(self.BASE_URL, p.get("link","")),
                    image          = p.get("image",{}).get("src"),
                    price_sale     = p.get("salePrice") or 0.0,
                    price_original = p.get("price") or 0.0,
                    gender         = config["gender"],
                    age_group      = config["age_group"],
                    brand          = "adidas"              # set brand here directly
                ))
            time.sleep(random.uniform(1,3))
            page += 1
        return shoes

    def _clean_data(self, df: pd.DataFrame) -> pd.DataFrame:
        # normalize gender lists
        df["gender"] = df["gender"].apply(lambda g: [x.lower() for x in g] if isinstance(g,list) else [])
        # fill numeric nulls
        for col in ["price_sale","price_original"]:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).clip(lower=0)
        # merge duplicate IDs
        def merge_group(g):
            base = g.iloc[0].to_dict()
            genders = set(x for lst in g["gender"] for x in lst)
            base["gender"] = ["unisex"] if {"male","female"}.issubset(genders) else sorted(genders)
            return pd.Series(base)
        df = df.groupby("id", as_index=False).apply(merge_group)
        return df

    def _run_data_quality_tests(self, df: pd.DataFrame) -> bool:
        ok = True
        # no nulls in price columns
        for col in ["price_sale","price_original"]:
            n = df[col].isnull().sum()
            if n:
                print(f"DQ Fail: {col} has {n} nulls")
                ok = False
        # gender normalization
        for _,r in df.iterrows():
            g = r["gender"]
            if isinstance(g,list) and "male" in g and "female" in g and g!=["unisex"]:
                print(f"DQ Fail: id {r['id']} gender {g}")
                ok = False
        # non-negative
        for col in ["price_sale","price_original"]:
            neg = (df[col]<0).sum()
            if neg:
                print(f"DQ Fail: {neg} negative in {col}")
                ok = False
        print("DQ Passed" if ok else "DQ Failed")
        return ok

    def extract(self) -> List[AdidasShoe]:
        if self.category_endpoint == "all":
            terms = list(self.CATEGORY_CONFIG.keys())
        else:
            terms = [self.category_endpoint]

        all_shoes: List[AdidasShoe] = []
        for term in terms:
            cfg = self.CATEGORY_CONFIG.get(term, {"gender":[],"age_group":""})
            all_shoes.extend(self._extract_raw(term, cfg))

        # clean & test
        df = pd.DataFrame([s.__dict__ for s in all_shoes])
        df_clean = self._clean_data(df)
        self._run_data_quality_tests(df_clean)

        # reconstruct dataclasses (brand now accepted)
        return [AdidasShoe(**rec) for rec in df_clean.to_dict("records")]
