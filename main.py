# main.py

from fastapi import FastAPI
from extractors.adidas_playwright import AdidasExtractor

app = FastAPI()

@app.get("/run-extract")
def run_extract(brand: str = "adidas", category: str = "/men-shoes", pages: int = 1):
    if brand.lower() == "adidas":
        extractor = AdidasExtractor(category, pages)
        print("asdasd")
        results = extractor.extract()
        # Serialize each Shoe instance to a dict
        return {"extracted": [shoe.__dict__ for shoe in results]}
    else:
        return {"error": f"Brand '{brand}' not implemented."}
