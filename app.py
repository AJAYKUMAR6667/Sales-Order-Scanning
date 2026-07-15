import time
from fastapi import FastAPI, UploadFile, File, HTTPException
from pydantic import BaseModel, Field
from typing import List
from llama_cloud import LlamaCloud
import os

app = FastAPI(title="Invoice Extraction Service")

# The SDK automatically checks for the LLAMA_CLOUD_API_KEY env variable
client = LlamaCloud(api_key="llx-knaUlGzQqxYtuAe9FnOO2YrMrjP2GXvmVycN5dQOtTA49XMX")

class LineItem(BaseModel):
    description: str
    quantity: int
    unit_price: float
    amount: float

class InvoiceSchema(BaseModel):
    vendor_name: str
    invoice_number: str
    invoice_date: str
    line_items: List[LineItem]
    total_tax: float
    grand_total: float

@app.post("/extract-invoice")
async def extract_invoice(file: UploadFile = File(...)):
    if not file.filename.endswith('.pdf'):
        raise HTTPException(status_code=400, detail="Only PDF files are supported.")
    
    try:
        # Read file contents into memory bytes
        file_bytes = await file.read()
        
        # 1. Upload the raw byte stream directly to LlamaCloud
        uploaded_file = client.files.create(
            file=(file.filename, file_bytes, "application/pdf"), 
            purpose="extract"
        )

        # 2. Trigger the extraction job
        job = client.extract.create(
            file_input=uploaded_file.id,
            configuration={
                "data_schema": InvoiceSchema.model_json_schema(),
                "tier": "agentic", 
            },
        )

        # 3. Poll for completion
        while job.status not in ("COMPLETED", "FAILED", "CANCELLED"):
            time.sleep(1.5)
            job = client.extract.get(job.id)

        if job.status == "COMPLETED":
            return job.extract_result
        else:
            raise HTTPException(status_code=500, detail=f"Extraction failed with status: {job.status}")

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))