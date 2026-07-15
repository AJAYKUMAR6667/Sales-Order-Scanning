import time
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from pydantic import BaseModel, Field
from typing import List, Optional, Union
from llama_cloud import LlamaCloud

app = FastAPI(title="Textile & Material Inward Extraction Service")

client = LlamaCloud(api_key="llx-knaUlGzQqxYtuAe9FnOO2YrMrjP2GXvmVycN5dQOtTA49XMX")

# -------------------------------------------------------------
# 1. SCHEMAS BASED ON YOUR IMAGES
# -------------------------------------------------------------

# --- FORMAT 1: Raw Material / Product Inward (Tax Invoices) ---
class InvoiceLineItem(BaseModel):
    sl_no: Optional[int] = Field(description="Serial number of the item")
    dc_no: Optional[str] = Field(description="Challan or DC number if present in table")
    description: str = Field(description="Full name, grade, or count description of goods (e.g., 30 X 60 NICE, 10S COTTON CONE YARN)")
    hsn_sac: Optional[str] = Field(description="HSN or SAC code string")
    pcs: Optional[int] = Field(description="Quantity in Pieces (Pcs) if applicable")
    meters: Optional[float] = Field(description="Quantity in Meters if applicable")
    weight_kg: Optional[float] = Field(description="Quantity in Kilograms (KG) if applicable")
    rate: float = Field(description="Rate per unit")
    per_unit: Optional[str] = Field(description="The unit basis for the rate (e.g., KG, pcs, meters)")
    amount: float = Field(description="Total line item amount value")

class TaxInvoiceSchema(BaseModel):
    vendor_name: str = Field(description="Company issuing the invoice (e.g., LALIT TEXTILE TRADING, SRI BHAGYALAKSHMI YARN STORES)")
    vendor_gstin: Optional[str] = Field(description="GSTIN of the supplier/vendor")
    billing_to: str = Field(description="The buyer/consignee name (e.g., R.GIRIDHAR ENTERPRISES)")
    buyer_gstin: Optional[str] = Field(description="GSTIN of the buyer")
    invoice_number: str = Field(description="Invoice No. found on the document")
    invoice_date: str = Field(description="Date the invoice was generated")
    po_number: Optional[str] = Field(description="Handwritten or printed PO reference (e.g., PO-43, PO-33)")
    line_items: List[InvoiceLineItem]
    sub_total: Optional[float] = Field(description="Subtotal amount before tax additions")
    cgst_amount: Optional[float] = Field(description="Extracted CGST total tax value")
    sgst_amount: Optional[float] = Field(description="Extracted SGST total tax value")
    igst_amount: Optional[float] = Field(description="Extracted IGST total tax value")
    grand_total: float = Field(description="The absolute Net Total or Grand Total due")
    bank_details: Optional[str] = Field(description="Any visible Bank accounts, IFSC codes, or branch information listed")

# --- FORMAT 2: Packing Slip ---
class PackingLineItem(BaseModel):
    sl_no: Optional[int]
    description: str = Field(description="Description of the packed item (e.g., Kingfisher 30x60)")
    alt_quantity: Optional[str] = Field(description="Alternative units measurement (e.g., 25 dz)")
    quantity: str = Field(description="Primary count/quantity packed (e.g., 300 pcs)")
    rate: Optional[float] = Field(description="Rate value if listed on the slip")
    amount: Optional[float] = Field(description="Line amount value if listed")

class PackingSlipSchema(BaseModel):
    document_title: str = Field(default="Packing Slip", description="The explicit header title of the document")
    voucher_number: str = Field(description="Voucher No. or Packing Slip reference ID")
    date: str = Field(description="Dated reference field")
    buyer_bill_to: str = Field(description="Company billed to (e.g., K K Trading Company)")
    destination: Optional[str] = Field(description="Delivery destination city or hub (e.g., JAIPUR)")
    dispatched_through: Optional[str] = Field(description="Logistics provider or courier name (e.g., MRL)")
    line_items: List[PackingLineItem]
    total_packages_count: Optional[str] = Field(description="The aggregated total volume at the bottom of table columns (e.g., 28 dz / 336 pcs)")
    grand_total: Optional[float] = Field(description="Final evaluation balance value if present")

# --- FORMAT 3: Offer Form / Indent Sheet ---
class OfferLineItem(BaseModel):
    description: str = Field(description="Item label (e.g., VIP, Hero, Jumbo)")
    dimension: Optional[str] = Field(description="Dimension size bounds (e.g., 30x60, 36x72)")
    quantity_bales: str = Field(description="Handwritten volume block (e.g., 10 doz, 15 doz)")
    rate_rs: Optional[float] = Field(description="Rupees column rate element")
    rate_p: Optional[float] = Field(description="Paise column fraction element")

class OfferFormSchema(BaseModel):
    agency_or_broker: str = Field(description="Commission agent or header name (e.g., Ajay Textile Agency)")
    indent_number: str = Field(description="Indent No. or unique red stamped form counter tracking ID (e.g., 61069)")
    date: str = Field(description="Written document execution date")
    from_party: str = Field(description="Sender entity name written next to From field")
    to_party: str = Field(description="Target recipient name written next to To field")
    dispatch_instructions: Optional[str] = Field(description="Shipping route directions (e.g., NGT To Bhilai)")
    line_items: List[OfferLineItem]
    handwritten_notes: Optional[List[str]] = Field(description="Any loose text descriptions captured on the face layout (e.g., 'Cash discount 2% for WA payment only')")

# -------------------------------------------------------------
# 2. RUNTIME EXTRACTION ROUTING
# -------------------------------------------------------------

@app.post("/extract")
async def extract_invoice(
    file: UploadFile = File(...),
    doc_type: str = None  # Changed from Form(...) to a clean Query parameter
):
    if not doc_type:
        raise HTTPException(status_code=400, detail="Missing doc_type query parameter.")
    # Dynamic schema selection matching the requested format blueprint
    if doc_type == "tax_invoice":
        selected_schema = TaxInvoiceSchema.model_json_schema()
    elif doc_type == "packing_slip":
        selected_schema = PackingSlipSchema.model_json_schema()
    elif doc_type == "offer_form":
        selected_schema = OfferFormSchema.model_json_schema()
    else:
        raise HTTPException(
            status_code=400, 
            detail="Invalid doc_type routing identifier provided."
        )

    filename_lower = file.filename.lower()
    if filename_lower.endswith('.pdf'):
        media_type = "application/pdf"
    elif filename_lower.endswith('.png'):
        media_type = "image/png"
    elif filename_lower.endswith(('.jpg', '.jpeg')):
        media_type = "image/jpeg"
    else:
        raise HTTPException(
            status_code=400, 
            detail="Unsupported format type. Send PDF, PNG, or JPEG image assets."
        )
    
    try:
        file_bytes = await file.read()
        
        uploaded_file = client.files.create(
            file=(file.filename, file_bytes, media_type), 
            purpose="extract"
        )

        job = client.extract.create(
            file_input=uploaded_file.id,
            configuration={
                "data_schema": selected_schema,
                "tier": "agentic",  # Crucial for reading handwritten forms and stamped data!
            },
        )

        while job.status not in ("COMPLETED", "FAILED", "CANCELLED"):
            time.sleep(1.5)
            job = client.extract.get(job.id)

        if job.status == "COMPLETED":
            return job.extract_result
        else:
            raise HTTPException(status_code=500, detail=f"LlamaCloud task failed with status code: {job.status}")

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))