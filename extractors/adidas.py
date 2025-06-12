# adidas.py

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
    brand: str = "adidas"

class AdidasExtractor(BaseExtractor):
    BASE_URL = "https://www.adidas.com.ph"
    HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

    # Keep original keys; we convert to "-originals-shoes" at runtime
    CATEGORY_CONFIG = {
        "men-shoes":     {"gender": ["male"],           "age_group": "adult"},
        "women-shoes":   {"gender": ["female"],         "age_group": "adult"},
        "boys-shoes":    {"gender": ["male"],           "age_group": "youth"},
        "girls-shoes":   {"gender": ["female"],         "age_group": "youth"},
        "infants-shoes": {"gender": ["male", "female"], "age_group": "toddlers"},
    }

    PAGE_SIZE = 48

    def __init__(self, category_endpoint: str, num_pages: int = -1):
        self.category_endpoint = category_endpoint.lower().strip()
        self.num_pages = num_pages

    def _taxonomy_term(self, original_key: str) -> str:
        if original_key.endswith("-originals-shoes"):
            return original_key
        if original_key.endswith("-shoes"):
            return original_key.replace("-shoes", "-originals-shoes")
        return f"{original_key}-originals-shoes"

    def _get_api_url(self, start: int, taxonomy_term: str) -> str:
        base_path = f"{self.BASE_URL}/plp-app/api/taxonomy/{taxonomy_term}"
        return base_path if start == 0 else f"{base_path}?start={start}"

    def _fetch_json(self, url: str) -> List[dict]:
        attempts = 0
        max_attempts = 3
        backoff = 1.0

        while attempts < max_attempts:
            try:
                resp = requests.get(url, headers=self.HEADERS, timeout=30)
                resp.raise_for_status()
                print(f"JSON content: {resp.json()}")
                return resp.json()
            except (requests.exceptions.ReadTimeout, requests.exceptions.ConnectionError):
                attempts += 1
                if attempts >= max_attempts:
                    raise
                time.sleep(backoff)
                backoff *= 2
            except requests.exceptions.HTTPError:
                raise

    def _extract_raw(self, taxonomy_term: str, config: dict) -> List[AdidasShoe]:
        shoes: List[AdidasShoe] = []
        page = 0

        while True:
            if self.num_pages != -1 and page >= self.num_pages:
                break

            start_index = page * self.PAGE_SIZE
            api_url = self._get_api_url(start_index, taxonomy_term)
            data = self._fetch_json(api_url)
            items = data if isinstance(data, list) else data.get("products", [])

            if not items:
                break

            for p in items:
                price_info = p.get("priceData", {})
                shoes.append(
                    AdidasShoe(
                        id             = p.get("id", ""),
                        title          = p.get("title", ""),
                        subTitle       = p.get("subTitle"),
                        url            = urljoin(self.BASE_URL, p.get("url", "")),
                        image          = p.get("image", ""),
                        price_sale     = price_info.get("salePrice", 0.0) or 0.0,
                        price_original = price_info.get("price", 0.0) or 0.0,
                        gender         = config["gender"],
                        age_group      = config["age_group"],
                        brand          = "adidas"
                    )
                )

            # If fewer than PAGE_SIZE items returned, this is the last page
            if len(items) < self.PAGE_SIZE:
                break

            page += 1
            time.sleep(random.uniform(1, 3))

        return shoes

    def _clean_data(self, df: pd.DataFrame) -> pd.DataFrame:
        df["gender"] = df["gender"].apply(
            lambda g: [x.lower() for x in g] if isinstance(g, list) else []
        )

        for col in ["price_sale", "price_original"]:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).clip(lower=0)

        def merge_group(group_df: pd.DataFrame) -> pd.Series:
            base = group_df.iloc[0].to_dict()
            genders = {x for sub in group_df["gender"] for x in sub}
            base["gender"] = (["unisex"] if {"male", "female"}.issubset(genders)
                              else sorted(genders))
            return pd.Series(base)

        if not df.empty:
            df = df.groupby("id", as_index=False).apply(merge_group)

        df['image'] = df['image'].fillna("no_image.png")   
        return df.reset_index(drop=True)

    def _run_data_quality_tests(self, df: pd.DataFrame) -> bool:
        ok = True

        for col in ["price_sale", "price_original"]:
            n_null = df[col].isnull().sum()
            if n_null:
                print(f"[DQ Fail] {col} has {n_null} nulls")
                ok = False

        for _, row in df.iterrows():
            g = row["gender"]
            if isinstance(g, list) and "male" in g and "female" in g and g != ["unisex"]:
                print(f"[DQ Fail] id {row['id']} gender not normalized: {g}")
                ok = False

        for col in ["price_sale", "price_original"]:
            neg_count = (df[col] < 0).sum()
            if neg_count:
                print(f"[DQ Fail] {neg_count} negative values in {col}")
                ok = False

        print("DQ Passed" if ok else "DQ Failed")
        return ok

    def extract(self) -> List[AdidasShoe]:
        if self.category_endpoint == "all":
            keys = list(self.CATEGORY_CONFIG.keys())
        else:
            keys = [self.category_endpoint]

        all_shoes: List[AdidasShoe] = []
        for key in keys:
            cfg = self.CATEGORY_CONFIG.get(key, {"gender": [], "age_group": ""})
            taxonomy_term = self._taxonomy_term(key)
            all_shoes.extend(self._extract_raw(taxonomy_term, cfg))

        df = pd.DataFrame([shoe.__dict__ for shoe in all_shoes])
        df_clean = self._clean_data(df)
        self._run_data_quality_tests(df_clean)

        return [AdidasShoe(**rec) for rec in df_clean.to_dict("records")]
