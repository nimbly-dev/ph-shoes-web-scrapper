# main.py

import json
from fastapi import FastAPI
from extractors.adidas import AdidasExtractor
from extractors.nike import NikeExtractor
from extractors.world_balance import WorldBalanceExtractor
from extractors.new_balance import NewBalanceExtractor
from extractors.asics import AsicsExtractor
from extractors.hoka import HokaExtractor
from utils.csv_util import CSVUtil
from dataclasses import asdict

app = FastAPI()

# 1) Base fields in the exact order your RAW table expects:
BASE_COLUMNS = [
    "id", "title", "subTitle", "url", "image",
    "price_sale", "price_original", "gender", "age_group", "brand"
]

# 2) One catch-all extra column:
CSV_COLUMNS = BASE_COLUMNS + ["extra"]


def serialize_shoe(shoe) -> dict:
    d = asdict(shoe)

    # 3) Extract base values:
    record = {col: d.get(col) for col in BASE_COLUMNS}

    # 4) JSON-encode gender array:
    record["gender"] = json.dumps(d.get("gender", []))

    # 5) Everything else goes into `extra`:
    extras = {
        k: v
        for k, v in d.items()
        if k not in BASE_COLUMNS and v is not None
    }
    record["extra"] = json.dumps(extras) if extras else None

    return record


@app.get("/run-extract")
def run_extract(category: str, brand: str = "adidas", pages: int = -1, uploadToS3: bool = False):
    # pick the right extractor
    lookup = {
        "adidas": AdidasExtractor,
        "nike": NikeExtractor,
        "worldbalance": WorldBalanceExtractor,
        "newbalance_atmos": NewBalanceExtractor,
        "asics": AsicsExtractor,
        "hoka": HokaExtractor,
    }
    cls = lookup.get(brand.lower())
    if not cls:
        return {"error": f"Brand '{brand}' not implemented."}

    shoes = cls(category, pages).extract()
    rows  = [serialize_shoe(s) for s in shoes]
    file_name = f"{brand}_all_extracted.csv"

    if uploadToS3:
        s3_key = CSVUtil.upload_to_s3(rows, file_name)
        return {"extracted": rows, "s3_upload": f"successful: {s3_key}"}

    return {"extracted": rows}
