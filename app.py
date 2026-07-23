import os
import asyncio
import base64
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.concurrency import run_in_threadpool
from typing import List, Optional
from pydantic import BaseModel, Field, ConfigDict
from llama_cloud import LlamaCloud
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="Textile & Material Sales Order Extraction Service")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # For development
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize the official client SDK
LLAMA_CLOUD_API_KEY = os.getenv(
    "LLAMA_CLOUD_API_KEY", 
    "llx-Zpce1PZzndxZrHoLsSd9UoUMqngGFIsc2syvzxlJqzwNcHzm"
)
client = LlamaCloud(api_key=LLAMA_CLOUD_API_KEY)

# Optimized polling configuration for instant response needs
MAX_POLL_SECONDS = 30
POLL_INTERVAL_SECONDS = 0.5  # Check every 0.5s instead of 2.0s for speed

# ==============================================================================
# SECTION 1: SALES ORDER SCHEMAS
# ==============================================================================

class SalesOrderLineItem(BaseModel):
    sl_no: Optional[int] = Field(default=None, description="Serial number of the item")
    description: str = Field(description="Full name, grade, fabric count, or quality description of goods ordered")
    hsn_sac: Optional[str] = Field(default=None, description="HSN or SAC code string")
    quantity: float = Field(description="Ordered quantity amount")
    unit_of_measure: str = Field(description="Unit of measurement (e.g., Meters, KGs, Pcs, Rolls)")
    rate: float = Field(description="Price rate per unit specified")
    amount: float = Field(description="Total line item amount (quantity * rate)")
    
    model_config = ConfigDict(populate_by_name=True)

class SalesOrderSchema(BaseModel):
    """Extraction blueprint for official Sales Orders / Customer Orders."""
    customer_name: str = Field(description="Company or buyer placing the sales order")
    customer_gstin: Optional[str] = Field(default=None, description="GSTIN of the purchasing customer")
    seller_company: str = Field(description="The organization selling the materials/goods")
    order_number: str = Field(description="Sales Order Number or Reference ID found on the header")
    order_date: str = Field(description="The exact order date. CRITICAL CORRECTION: Standardize to YYYY-MM-DD format. If the document lists a two-digit year like '26' (e.g., 06-07-26), always map it to '2026'. Never output '0026'.")
    delivery_date_expected: Optional[str] = Field(default=None, description="Expected shipment or delivery date in YYYY-MM-DD format")
    payment_terms: Optional[str] = Field(default=None, description="Agreed payment timeline (e.g., Net 30, Advance)")
    line_items: List[SalesOrderLineItem] = Field(description="List of all textile/material rows ordered")
    sub_total: Optional[float] = Field(default=None, description="Total before taxes and shipping costs")
    tax_amount: Optional[float] = Field(default=None, description="Aggregated or calculated tax amounts if visible")
    grand_total: float = Field(description="The definitive final total value of the sales order")
    
    model_config = ConfigDict(populate_by_name=True)

# FIX: Moved out of SalesOrderSchema context and fixed field indentations
class Base64UploadSchema(BaseModel):
    filename: str
    file_data: str

# ==============================================================================
# SECTION 2: UTILITIES
# ==============================================================================

def _resolve_media_type(filename: str) -> str:
    filename_lower = filename.lower()
    if filename_lower.endswith(".pdf"):
        return "application/pdf"
    elif filename_lower.endswith(".png"):
        return "image/png"
    elif filename_lower.endswith((".jpg", ".jpeg")):
        return "image/jpeg"
    raise HTTPException(
        status_code=400,
        detail="Unsupported format type. Send PDF, PNG, or JPEG image assets.",
    )

# ==============================================================================
# SECTION 3: ENDPOINTS
# ==============================================================================

@app.post("/extract")
async def extract_sales_order(payload: Base64UploadSchema):
    """
    Submits a Base64-encoded Sales Order document to LlamaIndex production.
    """
    media_type = _resolve_media_type(payload.filename)
    
    try:
        # Decode the incoming string data back into raw binary bytes
        file_bytes = base64.b64decode(payload.file_data)
    except Exception:
        raise HTTPException(
            status_code=400, 
            detail="Failed to process document string. Invalid Base64 data."
        )

    try:
        # 1. Upload binary data to LlamaCloud using the native SDK
        uploaded_file = await run_in_threadpool(
            client.files.create,
            file=(payload.filename, file_bytes, media_type),
            purpose="extract",
        )

        # 2. Spawn extraction using your SalesOrderSchema
        job = await run_in_threadpool(
            client.extract.create,
            file_input=uploaded_file.id,
            configuration={
                "data_schema": SalesOrderSchema.model_json_schema(),
                "tier": "agentic",
            },
        )

        # 3. High-frequency polling loop
        elapsed = 0.0
        while job.status not in ("COMPLETED", "FAILED", "CANCELLED"):
            if elapsed >= MAX_POLL_SECONDS:
                raise HTTPException(
                    status_code=504,
                    detail=f"Sales Order extraction job {job.id} timed out."
                )
            
            await asyncio.sleep(POLL_INTERVAL_SECONDS)
            job = await run_in_threadpool(client.extract.get, job.id)
            elapsed += POLL_INTERVAL_SECONDS

        if job.status == "COMPLETED":
            return job.extract_result
        else:
            raise HTTPException(
                status_code=500, 
                detail=f"LlamaCloud extraction pipeline failed with status: {job.status}"
            )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Extraction runtime exception: {str(e)}")