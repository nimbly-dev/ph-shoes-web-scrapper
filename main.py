# main.py

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

@app.get("/run-extract")
def run_extract(category: str, brand: str = "adidas", pages: int = -1, uploadToS3: bool = False):
    if brand.lower() == "adidas":
        extractor = AdidasExtractor(category, pages)
    elif brand.lower() == "nike":
        extractor = NikeExtractor(category, pages)
    elif brand.lower() == "worldbalance":
        extractor = WorldBalanceExtractor(category, pages)
    elif brand.lower() == "newbalance":
        extractor = NewBalanceExtractor(category, pages)
    elif brand.lower() == "asics":
        extractor = AsicsExtractor(category, pages)
    elif brand.lower() == "hoka":
        extractor = HokaExtractor(category, pages)
    else:
        return {"error": f"Brand '{brand}' not implemented."}
    
    results = extractor.extract()
    
    file_name = f"{brand}_extracted.csv"

    if uploadToS3:
        s3_key = CSVUtil.upload_to_s3(results, file_name)
        return {
            "extracted": [asdict(shoe) for shoe in results],
            "s3_upload": f"successful: {s3_key}"
        }
        print("TEST")
    else:
        local_file_path = f".data/{file_name}"
        CSVUtil.write_to_csv(results, local_file_path)
        return {"extracted": [asdict(shoe) for shoe in results]}