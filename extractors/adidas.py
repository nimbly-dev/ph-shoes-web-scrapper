import json
import random
import time
import requests
import pandas as pd
from urllib.parse import urljoin
from typing import List, Optional
from dataclasses import dataclass

from .base import BaseShoe, BaseExtractor

@dataclass
class AdidasShoe(BaseShoe):
    """
    Subclass of BaseShoe with brand preset to 'adidas'
    and an optional JSON‐encoded extra blob.
    """
    brand: str = "adidas"
    extra: Optional[str] = None


class AdidasExtractor(BaseExtractor):
    """
    Extractor for adidas shoes, returns a list of AdidasShoe instances.
    Bundles any site‐specific fields into `extra`.
    """
    BASE_URL    = "https://www.adidas.com.ph"
    CONTENT_URL = "https://www.adidas.com.ph/api/plp/content-engine/search"
    HEADERS     = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    PAGE_SIZE   = 48

    CATEGORY_CONFIG = {
        "men-shoes":     {"gender": ["male"],           "age_group": "adult"},
        "women-shoes":   {"gender": ["female"],         "age_group": "adult"},
        "boys-shoes":    {"gender": ["male"],           "age_group": "youth"},
        "girls-shoes":   {"gender": ["female"],         "age_group": "youth"},
        "infants-shoes": {"gender": ["male", "female"], "age_group": "toddlers"},
    }

    def __init__(self, category_endpoint: str, num_pages: int = -1):
        self.category_endpoint = category_endpoint.lower().strip()
        self.num_pages = num_pages

    def _taxonomy_term(self, original_key: str) -> str:
        # ensure we hit the "originals" endpoint
        if original_key.endswith("-originals-shoes"):
            return original_key
        if original_key.endswith("-shoes"):
            return original_key.replace("-shoes", "-originals-shoes")
        return f"{original_key}-originals-shoes"

    def _fetch_page(self, start: int, taxonomy_term: str) -> dict:
        params = {
            "sitePath": "ph",
            "query":     taxonomy_term,
            "start":     start,
            "rows":      self.PAGE_SIZE
        }
        resp = requests.get(
            self.CONTENT_URL,
            headers=self.HEADERS,
            params=params,
            timeout=30
        )
        resp.raise_for_status()
        return resp.json()

    def _extract_raw(self, taxonomy_term: str, config: dict) -> List[AdidasShoe]:
        """
        Paginate through the PLP API, extract canonical fields into BaseShoe,
        bundle any extras into a JSON string, and return AdidasShoe instances.
        """
        shoes: List[AdidasShoe] = []
        page = 0

        while True:
            if 0 <= self.num_pages <= page:
                break

            start = page * self.PAGE_SIZE
            data = self._fetch_page(start, taxonomy_term)
            items = data.get("raw", {}) \
                        .get("itemList", {}) \
                        .get("items", [])
            if not items:
                break

            for p in items:
                # Canonical fields
                base = {
                    "id":             p.get("productId", ""),
                    "title":          p.get("displayName", ""),
                    "subTitle":       p.get("subtitle"),
                    "url":            urljoin(self.BASE_URL, p.get("link", "")),
                    "image":          p.get("thumbnail", ""),
                    "price_sale":     p.get("priceSale", 0.0) or 0.0,
                    "price_original": p.get("price", 0.0)    or 0.0,
                    "gender":         config["gender"],
                    "age_group":      config["age_group"],
                    "brand":          "adidas",
                }

                # Any additional site‐specific fields
                extras = {
                    # e.g. ribbon text or badges, if present
                    "ribbons": p.get("ribbons"),
                    "badges":  p.get("badges"),
                }
                # prune None or empty
                extras = {k: v for k, v in extras.items() if v not in (None, "", [], {})}

                # JSON‐encode if nonempty, else None
                extra_blob = json.dumps(extras, ensure_ascii=False) if extras else None

                shoes.append(AdidasShoe(**base, extra=extra_blob))

            if len(items) < self.PAGE_SIZE:
                break

            page += 1
            time.sleep(random.uniform(1, 3))

        return shoes

    def _clean_data(self, df: pd.DataFrame) -> pd.DataFrame:
        # lowercase gender
        df["gender"] = df["gender"].apply(
            lambda g: [x.lower() for x in g] if isinstance(g, list) else []
        )
        # coerce prices
        for col in ["price_sale", "price_original"]:
            df[col] = pd.to_numeric(df[col], errors="coerce") \
                        .fillna(0).clip(lower=0)

        # dedupe, merging gender sets
        def merge_group(group_df: pd.DataFrame) -> pd.Series:
            base = group_df.iloc[0].to_dict()
            genders = {x for sub in group_df["gender"] for x in sub}
            base["gender"] = (["unisex"]
                              if {"male", "female"}.issubset(genders)
                              else sorted(genders))
            return pd.Series(base)

        if not df.empty:
            df = df.groupby("id", as_index=False).apply(merge_group)

        # ensure image is never null
        df["image"] = df["image"].fillna("")

        return df.reset_index(drop=True)

    def _run_data_quality_tests(self, df: pd.DataFrame) -> bool:
        ok = True
        for col in ["price_sale", "price_original"]:
            n_null = df[col].isnull().sum()
            if n_null:
                print(f"[DQ Fail] {col} has {n_null} nulls")
                ok = False
            neg = (df[col] < 0).sum()
            if neg:
                print(f"[DQ Fail] {neg} negative values in {col}")
                ok = False

        for _, row in df.iterrows():
            g = row["gender"]
            if isinstance(g, list) and {"male", "female"}.issubset(g) and g != ["unisex"]:
                print(f"[DQ Fail] id {row['id']} gender not normalized: {g}")
                ok = False

        print("DQ Passed" if ok else "DQ Failed")
        return ok

    def extract(self) -> List[AdidasShoe]:
        """
        Entry point: fetch all configured categories (or a single one),
        clean + QA, and return a list of AdidasShoe instances.
        """
        if self.category_endpoint == "all":
            keys = list(self.CATEGORY_CONFIG.keys())
        else:
            keys = [self.category_endpoint]

        all_shoes: List[AdidasShoe] = []
        for key in keys:
            cfg = self.CATEGORY_CONFIG.get(key, {"gender": [], "age_group": ""})
            term = self._taxonomy_term(key)
            all_shoes.extend(self._extract_raw(term, cfg))

        # normalize & dedupe via DataFrame
        df = pd.DataFrame([shoe.__dict__ for shoe in all_shoes])
        df_clean = self._clean_data(df)
        self._run_data_quality_tests(df_clean)

        # convert back to dataclasses
        return [AdidasShoe(**rec) for rec in df_clean.to_dict("records")]
