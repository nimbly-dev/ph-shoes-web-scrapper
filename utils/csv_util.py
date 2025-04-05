import os
import csv
import io 
from datetime import datetime
import boto3
from dataclasses import asdict, is_dataclass
from typing import List, Union, Dict, Any

class CSVUtil:
    @staticmethod
    def write_to_csv(data: List[Union[Dict[str, Any], object]], filename: str, fieldnames: List[str] = None):
        """
        Write a list of dictionaries or dataclass objects to a CSV file.
        
        :param data: A list of dictionaries or dataclass instances.
        :param filename: The path of the CSV file to write to.
        :param fieldnames: (Optional) A list of field names (columns) to write. 
                           If not provided, keys from the first dictionary will be used.
        """
        dict_data = []
        for item in data:
            if is_dataclass(item):
                dict_data.append(asdict(item))
            elif isinstance(item, dict):
                dict_data.append(item)
            else:
                raise ValueError("Data must be either a dictionary or a dataclass instance")
        
        if not dict_data:
            raise ValueError("No data provided to write.")
        
        if not fieldnames:
            fieldnames = list(dict_data[0].keys())
        
        with open(filename, mode="w", newline="", encoding="utf-8") as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            for row in dict_data:
                writer.writerow(row)


    @staticmethod
    def upload_to_s3(results, file_name: str):
        # Create CSV content in memory
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(results[0].__dict__.keys())
        for shoe in results:
            writer.writerow(shoe.__dict__.values())
        csv_content = output.getvalue()
        output.close()

        # Format S3 key as /raw/{year}/{month}/{day}/{file_name}
        now = datetime.utcnow()
        s3_key = f"raw/{now.year}/{now.month:02d}/{now.day:02d}/{file_name}"

        # Initialize S3 client using environment variables
        s3_client = boto3.client(
            "s3",
            aws_access_key_id=os.getenv("AWS_S3_DATA_LAKE_UPLOADER_ACCESS_KEY_ID"),
            aws_secret_access_key=os.getenv("AWS_S3_DATA_LAKE_UPLOADER_SECRET_ACCESS_KEY"),
            region_name=os.getenv("AWS_REGION"),
        )
        s3_bucket = os.getenv("S3_BUCKET")
        
        # S3 doesn't require explicit folder creation. Uploading to the key automatically creates the prefix.
        s3_client.put_object(Bucket=s3_bucket, Key=s3_key, Body=csv_content)
        
        return s3_key
