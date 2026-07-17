import os
import asyncio
from fastapi import FastAPI, UploadFile, File, HTTPException, Query
from fastapi.concurrency import run_in_threadpool
from typing import List, Optional
from pydantic import BaseModel, Field, model_validator
from llama_cloud import LlamaCloud

app = FastAPI(title="Textile & Material Inward & Transport Extraction Service")

# Initialize client
LLAMA_CLOUD_API_KEY = os.getenv(
    "LLAMA_CLOUD_API_KEY", 
    "llx-knaUlGzQqxYtuAe9FnOO2YrMrjP2GXvmVycN5dQOtTA49XMX"
)
client = LlamaCloud(api_key=LLAMA_CLOUD_API_KEY)

# Polling configuration constants
MAX_POLL_SECONDS = 300
POLL_INTERVAL_SECONDS = 2.0

# ==============================================================================
# SECTION 1: DATA SCHEMAS
# ==============================================================================

class FreightChargesSchema(BaseModel):
    freight: Optional[float] = Field(default=0.0, description="Freight charge value")
    bc: Optional[float] = Field(default=0.0, description="BC / Booking charge value")
    handling: Optional[float] = Field(default=0.0, description="Handling or loading charge value")
    door_del: Optional[float] = Field(default=0.0, description="Door delivery charge value")
    lf: Optional[float] = Field(default=0.0, description="LF / Lorry Freight charge value")
    sc: Optional[float] = Field(default=0.0, description="SC / Statistical charge value")
    lc: Optional[float] = Field(default=0.0, description="LC / Labor charge value")
    grc: Optional[float] = Field(default=0.0, description="GRC / Goods Receipt charge value")
    other: Optional[float] = Field(default=0.0, description="Any other miscellaneous charges listed")

class TransportLineItem(BaseModel):
    sl_no: Optional[int] = Field(default=None, description="Serial number of the item")
    quantity: Optional[str] = Field(default=None, description="Quantity or primary count packed (e.g., 01, 1)")
    package_type: Optional[str] = Field(default=None, description="Type of packaging (e.g., BALE, Bale)")
    description: str = Field(description="Description of the goods (e.g., CLOTH, One Bale of HLC)")
    weight_kg: Optional[float] = Field(default=None, description="Actual weight in KG")
    charged_weight: Optional[float] = Field(default=None, description="Charged weight in KG")

class TransportSlipSchema(BaseModel):
    """Transport Slip / Lorry Receipt Schema matching Batcotrans and Nagpur Golden Transport."""
    document_title: str = Field(description="The explicit header title of the logistics provider")
    challan_no: str = Field(description="Challan No, G.R. No, or Booking reference ID")
    invoice_no: Optional[str] = Field(default=None, description="Internal reference Invoice Number linked to the slip")
    invoice_value: Optional[float] = Field(default=None, description="Declared structural value of goods")
    date: str = Field(description="Execution or delivery date stamp")
    consignor: str = Field(description="Company profile sending out the materials")
    consignor_gst: Optional[str] = Field(default=None, description="GSTIN identifier of the sender party")
    consignee: str = Field(description="Target recipient or destination company profile")
    consignee_gst: Optional[str] = Field(default=None, description="GSTIN identifier of the recipient party")
    from_location: str = Field(alias="from", description="Origin city hub or branch location")
    to_location: str = Field(alias="to", description="Destination delivery point or drop zone")
    transport_details: Optional[str] = Field(default=None, description="Payment terms or structural carriage metadata")
    line_items: List[TransportLineItem]
    total_packages_count: Optional[str] = Field(default=None, description="Summary packages line label string")
    net_weight: Optional[float] = Field(default=None, description="Aggregated structural net weight value")
    freight_charges: Optional[FreightChargesSchema] = Field(default=None, description="Broken-down logistical charges mapped out perfectly")
    total_amount: float = Field(description="Final summary evaluation balance payable")
    handwritten_notes: Optional[List[str]] = Field(default=None, description="Any unmapped structural text or notes captured anywhere on the slip")

    class Config:
        populate_by_name = True


class InvoiceLineItem(BaseModel):
    sl_no: Optional[int] = Field(default=None, description="Serial number of the item")
    dc_no: Optional[str] = Field(default=None, description="Challan or DC number if present in table")
    description: str = Field(description="Full name, grade, or count description of goods")
    hsn_sac: Optional[str] = Field(default=None, description="HSN or SAC code string")
    pcs: Optional[int] = Field(default=None, description="Quantity in Pieces (Pcs) or in KGs")
    meters: Optional[float] = Field(default=None, description="Quantity in Meters if applicable")
    weight_kg: Optional[float] = Field(default=None, description="Quantity in Kilograms (KG) if applicable")
    rate: float = Field(description="Rate per unit")
    per_unit: Optional[str] = Field(default=None, description="The unit basis for the rate (e.g., KG, pcs)")
    amount: float = Field(description="Total line item amount value")

class TaxInvoiceSchema(BaseModel):
    """Product Inward: covers Raw Material inward AND Finished Goods inward."""
    inward_category: str = Field(description="Classify as 'Raw Material' or 'Finished Goods'")
    vendor_name: str = Field(description="Company issuing the invoice")
    vendor_gstin: Optional[str] = Field(default=None, description="GSTIN of the supplier/vendor")
    billing_to: str = Field(description="The buyer/consignee name")
    buyer_gstin: Optional[str] = Field(default=None, description="GSTIN of the buyer")
    invoice_number: str = Field(description="Invoice No. found on the document")
    invoice_date: str = Field(description="Date the invoice was generated")
    po_number: Optional[str] = Field(default=None, description="PO reference")
    line_items: List[InvoiceLineItem]
    sub_total: Optional[float] = Field(default=None, description="Subtotal amount before tax")
    cgst_amount: Optional[float] = Field(default=None, description="Extracted CGST tax value")
    sgst_amount: Optional[float] = Field(default=None, description="Extracted SGST tax value")
    igst_amount: Optional[float] = Field(default=None, description="Extracted IGST tax value")
    grand_total: float = Field(description="The absolute Grand Total due")
    bank_details: Optional[str] = Field(default=None, description="Bank accounts or branch info")


class PackingLineItem(BaseModel):
    sl_no: Optional[int] = None
    description: str = Field(description="Description of the packed item")
    alt_quantity: Optional[str] = Field(default=None, description="Alternative units measurement")
    quantity: str = Field(description="Primary count/quantity packed")
    rate: Optional[float] = Field(default=None, description="Rate value if listed")
    amount: Optional[float] = Field(default=None, description="Line amount value if listed")

class PackingSlipSchema(BaseModel):
    """Delivery Slip / Packing Slip."""
    document_title: str = Field(default="Packing Slip", description="The explicit header title")
    voucher_number: str = Field(description="Voucher No. or Packing Slip reference ID")
    date: str = Field(description="Dated reference field")
    buyer_bill_to: str = Field(description="Company billed to")
    destination: Optional[str] = Field(default=None, description="Delivery destination city")
    dispatched_through: Optional[str] = Field(default=None, description="Logistics provider name")
    line_items: List[PackingLineItem]
    total_packages_count: Optional[str] = Field(default=None, description="Aggregated total at the bottom")
    grand_total: Optional[float] = Field(default=None, description="Final evaluation balance value")



class OfferLineItem(BaseModel):
    description: str = Field(
        description=(
            "The clean product name text extracted from the main item column "
            "(e.g., 'Particulars', 'Description of Goods', 'Quality / Sort No.'). "
            "1. STRIP DIMENSIONS: Remove any size configurations found embedded or written inline "
            "with the name (e.g., convert '30/60- Diamond' to 'Diamond', 'Kingfisher 30x60' to 'Kingfisher', "
            "and '76x82 Silk vanaja' to 'Silk vanaja'). "
            "2. KEEP QUALITY MODIFIERS: Retain descriptive specifications or style numbers that belong to "
            "the product identity (e.g., 'VIP (600g)', 'Hero 700g', 'Plain white 3', 'Diamond col'). "
            "3. RESOLVE DITTO MARKS: If ditto marks ('\"', '“', ',,', '—') are present, inherit the product name "
            "from the row directly above, combining it with any new explicit suffix text written on the line."
        )
    )
    dimension: Optional[str] = Field(
        default=None, 
        description=(
            "The isolated product size configuration. Scan both the designated 'Size' column "
            "and the description text string to isolate this value. "
            "STANDARDIZE VALUE FORMAT: Normalize all layout variations—whether written as a raw number sequence "
            "('3060'), separated by dots ('30..60', '30.60'), slashes ('30/60'), or dashes ('36-72')—to "
            "always be formatted strictly as 'WIDTHxLENGTH' (e.g., '30x60', '36x72', '76x82'). "
            "RESOLVE DITTO MARKS: Carry down and explicitly fill the resolved string value from the row above "
            "if subsequent rows use ditto marks or lines."
        )
    )
    quantity_bales: Optional[str] = Field(
        default="", 
        description=(
            "Extracted from dedicated macro packaging columns (like 'Bales') or structural handwritten "
            "annotations specifying whole packaging units (e.g., '1 Bale', '2 Bale', '1 Bale mix'). "
            "Leave as an empty string if only localized pieces or dozens are being listed."
        )
    )
    quantity_pieces_meters: Optional[str] = Field(
        default=None,
        description=(
            "The quantity or localized unit count (e.g., from 'Qty', 'Meters/Pcs', or 'No. of Bales' columns). "
            "STANDARDIZE HANDWRITING: Carefully map varying abbreviated notation to standard terms. "
            "Convert handwritten cursive forms like 'd.', 'd2', 'doz', or 'Dozen' to dozens ('dz'), and raw numeric "
            "counts to pieces ('pcs'). Examples: '5 d.' -> '5 dz', '10 d2' -> '10 dz', '720.00' -> '720 pcs'."
        )
    )
    rate_rs: Optional[float] = Field(
        default=None, 
        description="The base rate value before the decimal/fraction point. Leave null if blank."
    )
    rate_p: Optional[float] = Field(
        default=0.0, 
        description="The rate fraction/paisa balance (e.g., from a split column or suffix like '.50' or '=00')."
    )

    @model_validator(mode="after")
    def check_must_have_metrics(self) -> "OfferLineItem":
        """Ensures that structural divider rows or bottom totals are ignored."""
        if not self.quantity_pieces_meters and not self.quantity_bales and self.rate_rs is None:
            raise ValueError("Row lacks clear quantity metrics or item rates; skipping.")
        return self

class OfferFormSchema(BaseModel):
    """Product Request Form (Indent Sheet / Order Form / Order Confirmation)."""
    agency_or_broker: str = Field(description="Commission agent or organization profile banner (e.g., 'SHUKLA AGENCIES', 'SURYA AGENCIES')")
    indent_number: str = Field(description="Tracking identity string (e.g., Indent No., Order No., Reference Code)")
    date: str = Field(description="Document execution date stamp. Leave empty string if blank.")
    from_party: str = Field(description="Buyer / Purchaser customer profile name and regional city location details")
    to_party: str = Field(description="Seller / Supplier company profile designation")
    dispatch_instructions: Optional[str] = Field(default=None, description="Transport guidelines, transit stations, or booking routes (e.g., 'NGT to Bhilai')")
    line_items: List[OfferLineItem] = Field(description="List of valid structural item rows extracted from the main contents grid table.")
    handwritten_notes: Optional[List[str]] = Field(default=None, description="Loose terms, miscellaneous structural footer text remarks, or discount terms (e.g., 'Cash discount 2%')")


SCHEMA_MAP = {
    "tax_invoice": TaxInvoiceSchema,
    "packing_slip": PackingSlipSchema,
    "offer_form": OfferFormSchema,
    "transport_slip": TransportSlipSchema,
}

# ==============================================================================
# SECTION 2: UTILITIES & ROUTING
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
async def extract_document(
    file: UploadFile = File(...),
    doc_type: str = Query(..., description="Schema selection: tax_invoice, packing_slip, offer_form, transport_slip")
):
    """
    Kicks off extraction and safely polls via non-blocking async loops.
    """
    schema_cls = SCHEMA_MAP.get(doc_type)
    if schema_cls is None:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid doc_type routing identifier. Choose from: {list(SCHEMA_MAP.keys())}",
        )

    media_type = _resolve_media_type(file.filename)

    try:
        file_bytes = await file.read()

        # Run client synchronous code inside the threadpool to protect event loop
        uploaded_file = await run_in_threadpool(
            client.files.create,
            file=(file.filename, file_bytes, media_type),
            purpose="extract",
        )

        job = await run_in_threadpool(
            client.extract.create,
            file_input=uploaded_file.id,
            configuration={
                "data_schema": schema_cls.model_json_schema(),
                "tier": "agentic",  # Essential for processing mixed details!
            },
        )

        # Polling block with timeout logic that doesn't halt framework requests
        elapsed = 0.0
        while job.status not in ("COMPLETED", "FAILED", "CANCELLED"):
            if elapsed >= MAX_POLL_SECONDS:
                raise HTTPException(
                    status_code=504,
                    detail=f"Extraction job {job.id} exceeded maximum threshold of {MAX_POLL_SECONDS}s."
                )
            
            await asyncio.sleep(POLL_INTERVAL_SECONDS)  # Non-blocking async sleep
            job = await run_in_threadpool(client.extract.get, job.id)
            elapsed += POLL_INTERVAL_SECONDS

        if job.status == "COMPLETED":
            return job.extract_result
        else:
            raise HTTPException(status_code=500, detail=f"LlamaCloud task failed with status code: {job.status}")

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))