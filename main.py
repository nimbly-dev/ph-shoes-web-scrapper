# main.py

from fastapi import FastAPI
from extractors.adidas_playwright import AdidasExtractor

app = FastAPI()

@app.get("/run-extract")
def run_extract(category: str, brand: str = "adidas", pages: int = -1):
    results = []

    if brand.lower() == "adidas":
        extractor = AdidasExtractor(category, pages)
        results = extractor.extract()
        return {"extracted": [shoe.__dict__ for shoe in results]}
    
    return {"error": f"Brand '{brand}' not implemented."}