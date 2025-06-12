# extractors/new_balance.py

import re
import time
from dataclasses import dataclass
from typing import List, Dict
from urllib.parse import urlparse, parse_qs

import pandas as pd
import requests
from bs4 import BeautifulSoup

from .base import BaseShoe, BaseExtractor
from logger import get_logger

logger = get_logger(__name__, log_file="./logs/new_balance_poc.log")

# 1) Build the list of filtered endpoints for Atmos New Balance
male_sizes = [
    "4", "4.5", "5", "5.5", "6", "6.5", "7", "7.5",
    "8", "8.5", "9", "9.5", "10", "10.5", "11",
    "11.5", "12", "12.5", "13"
]
female_sizes = [
    "5", "5.5", "6", "6.5", "7", "7.5",
    "8", "8.5", "9", "9.5", "10"
]

product_lists_url: List[str] = []

# Size‐filtered URLs (Men’s sizes)
for size in male_sizes:
    product_lists_url.append(
        f"/collections/new-balance?filter.v.option.size=US+M+{size}"
    )

# Size‐filtered URLs (Women’s sizes)
for size in female_sizes:
    product_lists_url.append(
        f"/collections/new-balance?filter.v.option.size=US+W+{size}"
    )

# Gender‐filtered URLs
product_lists_url.append("/collections/new-balance?filter.p.tag=All+Mens")
product_lists_url.append("/collections/new-balance?filter.p.tag=All+Womens")


# 2) Map each URL fragment to metadata (gender + age_group + “subTitle” marker)
category_config: Dict[str, Dict] = {}
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
    "gender": ["male"],
    "age_group": "adult",
    "subTitle": "All Mens"
}
category_config["/collections/new-balance?filter.p.tag=All+Womens"] = {
    "gender": ["female"],
    "age_group": "adult",
    "subTitle": "All Womens"
}

BASE_PREFIX = "https://atmos.ph"


@dataclass
class NewBalanceShoe(BaseShoe):
    # All BaseShoe fields come first (each already has a default).
    # Now add `brand` *with* a default, to avoid the “non-default after default” error:
    brand: str = "newbalance"

    # Then the extra field `sizes` (also defaulted):
    sizes: List[str] = None


class NewBalanceExtractor(BaseExtractor):
    def __init__(self, category: str, num_pages: int = -1):
        """
        :param category: ignored (we loop through all product_lists_url)
        :param num_pages: -1 → fetch until two consecutive empty pages; otherwise limit
        """
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
        if variant:
            return f"{slug}?variant={variant}"
        return slug

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
        srcset = img.get("srcset") or img.get("data-srcset") or ""
        if srcset:
            candidates = [p.strip() for p in srcset.split(",") if p.strip()]
            for cand in candidates:
                url_part = cand.split()[0]
                if "_400x" in url_part:
                    return url_part if url_part.startswith("http") else f"https:{url_part}"
            first = candidates[0].split()[0]
            return first if first.startswith("http") else f"https:{first}"
        for attr in ("src", "data-src"):
            raw = img.get(attr)
            if raw:
                return raw if raw.startswith("http") else f"https:{raw}"
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
        html: str,
        metadata: Dict[str, List[str]]
    ) -> List[dict]:
        soup = BeautifulSoup(html, "html.parser")
        cards = soup.select("div.ProductItem")
        logger.info(f"[Parse] Found {len(cards)} ProductItem cards")

        gender_list = metadata["gender"]
        age_group_val = metadata["age_group"]
        sub_title_marker = metadata["subTitle"]

        results: List[dict] = []
        for card in cards:
            try:
                # 1) Title & URL
                a_tag = card.select_one("h2.ProductItem__Title a")
                href = a_tag.get("href", "") if a_tag else ""
                product_url = f"{BASE_PREFIX}{href}" if href.startswith("/") else href
                title = a_tag.text.strip() if a_tag else ""
                norm_id = cls._normalize_id(href)

                # 2) Prices
                sale_el = card.select_one("span.Price--highlight")
                price_sale = 0.0
                if sale_el and sale_el.text.strip():
                    price_sale = float(sale_el.text.strip().replace("₱", "").replace(",", ""))
                orig_el = card.select_one("span.Price--compareAt")
                price_original = price_sale
                if orig_el and orig_el.text.strip():
                    price_original = float(orig_el.text.strip().replace("₱", "").replace(",", ""))

                # 3) Image
                image_url = cls._extract_image(card)

                # 4) Sizes
                if sub_title_marker.startswith("size "):
                    sizes_list = [sub_title_marker.replace("size ", "")]
                else:
                    sizes_list = cls._fetch_sizes_from_detail(product_url)

                # 5) Build a dict that matches exactly BaseShoe’s fields + brand + sizes
                rec = {
                    # ---- BaseShoe’s fields (in the same order BaseShoe declares) ----
                    "id":             norm_id,
                    "title":          title,
                    "subTitle":       "",              # Atmos New Balance always leaves subTitle blank
                    "url":            product_url,
                    "image":          image_url,
                    "price_sale":     price_sale,
                    "price_original": price_original,
                    "gender":         gender_list.copy(),
                    "age_group":      age_group_val,

                    # ---- Now `brand` (defaulted in dataclass) ----
                    "brand":          "newbalance",

                    # ---- Finally, the extra `sizes` field ----
                    "sizes":         sizes_list
                }
                results.append(rec)
            except Exception as exc:
                logger.error(f"[Parse] Error parsing ProductItem: {exc}")
        return results

    def extract(self) -> List[NewBalanceShoe]:
        logger.info("[Extract] Starting extraction for Atmos New Balance")
        all_raw: List[dict] = []

        for fragment in product_lists_url:
            metadata = category_config.get(fragment, {})
            page = 1
            empty_count = 0

            while True:
                if self.max_pages != -1 and page > self.max_pages:
                    break

                full_url = self._build_url(fragment, page)
                try:
                    html = self._fetch_html(full_url)
                except Exception as exc:
                    logger.error(f"[Fetch] {fragment} page {page} failed: {exc}")
                    break

                page_recs = self._parse_page(html, metadata)
                if not page_recs:
                    empty_count += 1
                    if empty_count >= 2:
                        break
                else:
                    empty_count = 0
                    all_raw.extend(page_recs)

                page += 1
                time.sleep(1.5)

        logger.info(f"[Extract] Raw items before merging: {len(all_raw)}")
        if not all_raw:
            return []

        # 3) Merge duplicates by normalized 'id'
        df = pd.DataFrame(all_raw)
        merged: List[dict] = []
        for item_id, group in df.groupby("id"):
            base = group.iloc[0].to_dict()

            # Combine all size lists
            all_sizes = set()
            for sz_list in group["sizes"]:
                all_sizes.update(sz_list if isinstance(sz_list, list) else [sz_list])
            base["sizes"] = sorted(all_sizes)

            # Combine gender (if both ["male"] & ["female"], force ["unisex"])
            all_genders = set()
            for g_list in group["gender"]:
                all_genders.update(g_list if isinstance(g_list, list) else [g_list])
            base["gender"] = ["unisex"] if len(all_genders) > 1 else list(all_genders)

            merged.append(base)

        # Drop Prices that are 0
        df = df[~((df["price_sale"] == 0.0) & (df["price_original"] == 0.0))].reset_index(drop=True)
        logger.info(f"[Extract] Items after merging: {len(merged)}")
        
        df['image'] = df['image'].fillna("no_image.png")   

        # Convert to NewBalanceShoe (BaseShoe fields first, then brand, then sizes)
        return [
            NewBalanceShoe(
                id=rec["id"],
                title=rec["title"],
                subTitle=rec["subTitle"],
                url=rec["url"],
                image=rec["image"],
                price_sale=rec["price_sale"],
                price_original=rec["price_original"],
                gender=rec["gender"],
                age_group=rec["age_group"],
                sizes=rec["sizes"],    # extra field
            )
            for rec in merged
        ]
