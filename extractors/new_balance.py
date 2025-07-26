# extractors/new_balance.py

import re
import time
import json
from dataclasses import dataclass
from typing import List, Dict, Any
from urllib.parse import urlparse, parse_qs

import pandas as pd
import requests
from bs4 import BeautifulSoup

from .base import BaseShoe, BaseExtractor
from logger import get_logger

logger = get_logger(__name__, log_file="./logs/new_balance_poc.log")


# 1) Build the list of filtered endpoints for Atmos New Balance
male_sizes = [ "4", "4.5", "5", "5.5", "6", "6.5", "7", "7.5",
               "8", "8.5", "9", "9.5", "10", "10.5", "11",
               "11.5", "12", "12.5", "13" ]
female_sizes = [ "5", "5.5", "6", "6.5", "7", "7.5",
                 "8", "8.5", "9", "9.5", "10" ]

product_lists_url: List[str] = []
for size in male_sizes:
    product_lists_url.append(f"/collections/new-balance?filter.v.option.size=US+M+{size}")
for size in female_sizes:
    product_lists_url.append(f"/collections/new-balance?filter.v.option.size=US+W+{size}")

# Gender‐filtered URLs
product_lists_url.append("/collections/new-balance?filter.p.tag=All+Mens")
product_lists_url.append("/collections/new-balance?filter.p.tag=All+Womens")


# 2) Map each URL fragment to metadata (gender, age_group, subTitle)
category_config: Dict[str, Dict[str, Any]] = {}
for size in male_sizes:
    key = f"/collections/new-balance?filter.v.option.size=US+M+{size}"
    category_config[key] = {
        "gender": ["male"],
        "age_group": "adult",
        "subTitle": f"size US M {size}"
    }
for size in female_sizes:
    key = f"/collections/new-balance?filter.v.option.size=US+W+{size}"
    category_config[key] = {
        "gender": ["female"],
        "age_group": "adult",
        "subTitle": f"size US W {size}"
    }
category_config["/collections/new-balance?filter.p.tag=All+Mens"] = {
    "gender": ["male"],   "age_group": "adult", "subTitle": "All Mens"
}
category_config["/collections/new-balance?filter.p.tag=All+Womens"] = {
    "gender": ["female"], "age_group": "adult", "subTitle": "All Womens"
}


BASE_PREFIX = "https://atmos.ph"


@dataclass
class NewBalanceShoe(BaseShoe):
    """
    Subclass of BaseShoe for New Balance; `extra` will hold sizes.
    """
    brand: str = "newbalance"
    # no separate sizes field—use BaseShoe.extra


class NewBalanceExtractor(BaseExtractor):
    """
    Extractor for Atmos New Balance.  
    Loops through the filtered product_list fragments, scrapes pages,
    normalizes into BaseShoe shape, and bundles sizes into `extra`.
    """

    def __init__(self, category: str = "all", num_pages: int = -1):
        self.max_pages = num_pages

    def _build_url(self, fragment: str, page: int) -> str:
        return f"{BASE_PREFIX}{fragment}&page={page}"

    def _fetch_html(self, full_url: str) -> str:
        logger.info(f"[Fetch] GET {full_url}")
        resp = requests.get(full_url, timeout=30)
        resp.raise_for_status()
        return resp.text

    @staticmethod
    def _normalize_id(href: str) -> str:
        parsed = urlparse(href)
        slug = parsed.path.rstrip("/").split("/")[-1]
        qs = parse_qs(parsed.query)
        variant = qs.get("variant", [None])[0]
        return f"{slug}?variant={variant}" if variant else slug

    @staticmethod
    def _extract_image(prod_tag: BeautifulSoup) -> str:
        img = prod_tag.select_one("img.ProductItem__Image")
        if not img:
            return ""
        for attr in ("src", "data-src"):
            raw = img.get(attr)
            if raw and "{width}" in raw:
                fixed = raw.replace("{width}", "400")
                return fixed if fixed.startswith("http") else f"https:{fixed}"
        # fallback to srcset
        srcset = img.get("srcset") or img.get("data-srcset") or ""
        for part in srcset.split(","):
            url_part = part.strip().split()[0]
            if "_400x" in url_part:
                return url_part if url_part.startswith("http") else f"https:{url_part}"
        return ""

    @staticmethod
    def _fetch_sizes_from_detail(product_url: str) -> List[str]:
        try:
            resp = requests.get(product_url, timeout=30)
            resp.raise_for_status()
            detail_soup = BeautifulSoup(resp.text, "html.parser")
            size_elems = detail_soup.find_all(
                lambda tag: tag.name in ("button", "label")
                and re.match(r"^US [MW] \d+(\.\d+)?$", tag.get_text(strip=True))
            )
            return sorted({elem.get_text(strip=True) for elem in size_elems})
        except Exception:
            return []

    @classmethod
    def _parse_page(
        cls,
        html_str: str,
        metadata: Dict[str, Any]
    ) -> List[dict]:
        soup = BeautifulSoup(html_str, "html.parser")
        cards = soup.select("div.ProductItem")
        logger.info(f"[Parse] Found {len(cards)} ProductItem cards")

        gender_list    = metadata["gender"]
        age_group_val  = metadata["age_group"]
        sub_title_mark = metadata["subTitle"]

        results: List[dict] = []
        for card in cards:
            try:
                # 1) Title & URL
                a_tag = card.select_one("h2.ProductItem__Title a")
                href = a_tag["href"] if a_tag and a_tag.has_attr("href") else ""
                product_url = (f"{BASE_PREFIX}{href}"
                               if href.startswith("/") else href)
                title = a_tag.get_text(strip=True) if a_tag else ""
                norm_id = cls._normalize_id(href)

                # 2) Prices
                orig_el   = card.select_one("span.Price--compareAt")
                sale_el   = card.select_one("span.Price--highlight")
                default_el= card.select_one("span.ProductItem__Price.Text--subdued")

                if orig_el and sale_el:
                    po = float(orig_el.text.strip().replace("₱","").replace(",",""))
                    ps = float(sale_el.text.strip().replace("₱","").replace(",",""))
                elif default_el:
                    p = float(default_el.text.strip().replace("₱","").replace(",",""))
                    po = ps = p
                else:
                    continue

                # 3) Image
                image_url = cls._extract_image(card)

                # 4) Sizes
                if sub_title_mark.startswith("size "):
                    sizes_list = [ sub_title_mark.replace("size ", "") ]
                else:
                    sizes_list = cls._fetch_sizes_from_detail(product_url)

                # 5) Build canonical record
                rec = {
                    "id":             norm_id,
                    "title":          title,
                    "subTitle":       sub_title_mark,
                    "url":            product_url,
                    "image":          image_url,
                    "price_sale":     ps,
                    "price_original": po,
                    "gender":         gender_list,
                    "age_group":      age_group_val,
                    "brand":          "newbalance",
                }
                # bundle sizes into `extra`
                extras = {"sizes": sizes_list}
                rec["extra"] = json.dumps(extras, ensure_ascii=False) if extras else None

                results.append(rec)
            except Exception as exc:
                logger.error(f"[Parse] Error parsing ProductItem: {exc}")
        return results

    def _run_data_quality_tests(self, df: pd.DataFrame) -> bool:
        """
        Sanity checks: required columns, numeric prices, unique IDs.
        """
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

    def extract(self) -> List[NewBalanceShoe]:
        """
        Entry point: fetch all fragments, parse pages until empty,
        merge duplicates, run DQ, and return dataclasses.
        """
        all_raw: List[dict] = []

        for fragment in product_lists_url:
            metadata = category_config.get(fragment, {})
            page = 1
            empty_runs = 0

            while True:
                if self.max_pages != -1 and page > self.max_pages:
                    break
                url = self._build_url(fragment, page)
                try:
                    html_str = self._fetch_html(url)
                except Exception as e:
                    logger.error(f"[Fetch] {fragment} page {page} failed: {e}")
                    break

                page_items = self._parse_page(html_str, metadata)
                if not page_items:
                    empty_runs += 1
                    if empty_runs >= 2:
                        break
                else:
                    empty_runs = 0
                    all_raw.extend(page_items)

                page += 1
                time.sleep(1.5)

        #  Early exit if nothing found
        if not all_raw:
            return []

        # Merge duplicates by `id`
        df = pd.DataFrame(all_raw)
        merged: List[dict] = []
        for item_id, group in df.groupby("id"):
            base = group.iloc[0].to_dict()

            # merge sizes
            all_sizes = set()
            for blob in group["extra"].dropna():
                all_sizes.update(json.loads(blob)["sizes"])
            base["extra"] = json.dumps({"sizes": sorted(all_sizes)}, ensure_ascii=False)

            # normalize gender
            genders = set(sum(group["gender"].tolist(), []))
            base["gender"] = ["unisex"] if genders == {"male","female"} else sorted(genders)

            merged.append(base)

        # clean numeric & image
        df_clean = pd.DataFrame(merged)
        df_clean["image"] = df_clean["image"].fillna("")
        for col in ["price_sale","price_original"]:
            df_clean[col] = pd.to_numeric(df_clean[col], errors="coerce").fillna(0).clip(lower=0)

        # run your data quality checks
        self._run_data_quality_tests(df_clean)

        # return dataclasses
        return [NewBalanceShoe(**rec) for rec in df_clean.to_dict("records")]
