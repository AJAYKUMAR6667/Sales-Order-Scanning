import time
from fastapi import FastAPI, UploadFile, File, HTTPException, Query
from pydantic import BaseModel, Field
from typing import List, Optional, Dict
from llama_cloud import LlamaCloud

app = FastAPI(title="Textile & Material Inward & Transport Extraction Service")

# Initialize client
client = LlamaCloud(api_key="llx-knaUlGzQqxYtuAe9FnOO2YrMrjP2GXvmVycN5dQOtTA49XMX")

# ==============================================================================
# SECTION 1: NEW DATA SCHEMAS (Transport Slips / Lorry Receipts)
# ==============================================================================

class FreightChargesSchema(BaseModel):
    # Defining explicit fields matches both Batcotrans and Nagpur Golden layouts
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
    
    # FIX: Replaced Dict[str, float] with explicit sub-schema model validation
    freight_charges: Optional[FreightChargesSchema] = Field(default=None, description="Broken-down logistical charges mapped out perfectly")
    
    total_amount: float = Field(description="Final summary evaluation balance payable")
    handwritten_notes: Optional[List[str]] = Field(default=None, description="Any unmapped structural text or notes captured anywhere on the slip")

    class Config:
        populate_by_name = True


# ==============================================================================
# SECTION 2: PREVIOUS DATA SCHEMAS (Tax Invoices, Packing Slips, Offer Forms)
# ==============================================================================

# --- FORMAT A: Raw Material / Product Inward (Tax Invoices) ---
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

# --- FORMAT B: Standard Delivery Slip (Packing Slips) ---
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

# --- FORMAT C: Product Request Form (Offer Sheets) ---
class OfferLineItem(BaseModel):
    description: str = Field(description="Item label (e.g., VIP, Hero)")
    dimension: Optional[str] = Field(default=None, description="Dimension size (e.g., 30x60)")
    quantity_bales: str = Field(description="Handwritten volume block")
    rate_rs: Optional[float] = Field(default=None, description="Rupees column rate element")
    rate_p: Optional[float] = Field(default=None, description="Paise column fraction element")

class OfferFormSchema(BaseModel):
    """Product Request Form (Indent Sheet)."""
    agency_or_broker: str = Field(description="Commission agent name")
    indent_number: str = Field(description="Indent No. or tracking ID")
    date: str = Field(description="Written document date")
    from_party: str = Field(description="Sender entity name")
    to_party: str = Field(description="Target recipient name")
    dispatch_instructions: Optional[str] = Field(default=None, description="Shipping route directions")
    line_items: List[OfferLineItem]
    handwritten_notes: Optional[List[str]] = Field(default=None, description="Any loose handwritten text")

# -------------------------------------------------------------
# 3. RUNTIME EXTRACTION ROUTING (Supports All Formats)
# -------------------------------------------------------------

@app.post("/extract")
async def extract_document(
    file: UploadFile = File(...),
    doc_type: str = Query(..., description="Schema selection: tax_invoice, packing_slip, offer_form, transport_slip")
):
    # Route matching for both Previous and New Schemas
    if doc_type == "tax_invoice":
        selected_schema = TaxInvoiceSchema.model_json_schema()
    elif doc_type == "packing_slip":
        selected_schema = PackingSlipSchema.model_json_schema()
    elif doc_type == "offer_form":
        selected_schema = OfferFormSchema.model_json_schema()
    elif doc_type == "transport_slip":
        selected_schema = TransportSlipSchema.model_json_schema()
    else:
        raise HTTPException(
            status_code=400, 
            detail="Invalid doc_type routing identifier. Choose: tax_invoice, packing_slip, offer_form, transport_slip."
        )

    # Determine Media Type
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
        
        # Create extraction upload file reference
        uploaded_file = client.files.create(
            file=(file.filename, file_bytes, media_type), 
            purpose="extract"
        )

        # Trigger extracting utilizing targeted schema profile
        job = client.extract.create(
            file_input=uploaded_file.id,
            configuration={
                "data_schema": selected_schema,
                "tier": "agentic",  # Essential for processing mixed digital and handwritten details!
            },
        )

        # Await extraction lifecycle status updates
        while job.status not in ("COMPLETED", "FAILED", "CANCELLED"):
            time.sleep(1.5)
            job = client.extract.get(job.id)

        if job.status == "COMPLETED":
            return job.extract_result
        else:
            raise HTTPException(status_code=500, detail=f"LlamaCloud task failed with status code: {job.status}")

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))