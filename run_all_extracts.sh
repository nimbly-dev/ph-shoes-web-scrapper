#!/bin/bash

# Endpoint and common params
BASE_URL="http://localhost:10000/run-extract"
CATEGORY="all"
PAGES="-1"
UPLOAD="True"

# List of supported brands
BRANDS=("adidas" "nike" "worldbalance" "newbalance_atmos" "asics" "hoka")

# Loop through each brand and trigger extraction
for BRAND in "${BRANDS[@]}"; do
    echo "Triggering extraction for: $BRAND"
    curl -X GET "${BASE_URL}?brand=${BRAND}&category=${CATEGORY}&pages=${PAGES}&uploadToS3=${UPLOAD}"
    echo -e "\nDone: $BRAND"
done
