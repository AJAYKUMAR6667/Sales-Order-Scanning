import os
import json
import httpx
from fastapi import FastAPI, UploadFile, File, HTTPException, Query
from typing import List, Optional
from pydantic import BaseModel, Field, model_validator, ConfigDict

app = FastAPI(title="Textile & Material Inward & Transport Extraction Service Fast")

# Using raw HTTP request to LlamaCloud inline API instead of the polling SDK client
LLAMA_CLOUD_API_KEY = os.getenv(
    "LLAMA_CLOUD_API_KEY", 
    "llx-knaUlGzQqxYtuAe9FnOO2YrMrjP2GXvmVycN5dQOtTA49XMX"
)

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
    
    model_config = ConfigDict(populate_by_name=True)

class TransportLineItem(BaseModel):
    sl_no: Optional[int] = Field(default=None, description="Serial number of the item")
    quantity: Optional[str] = Field(default=None, description="Quantity or primary count packed (e.g., 01, 1)")
    package_type: Optional[str] = Field(default=None, description="Type of packaging (e.g., BALE, Bale)")
    description: str = Field(description="Description of the goods (e.g., CLOTH, One Bale of HLC)")
    weight_kg: Optional[float] = Field(default=None, description="Actual weight in KG")
    charged_weight: Optional[float] = Field(default=None, description="Charged weight in KG")
    
    model_config = ConfigDict(populate_by_name=True)

class TransportSlipSchema(BaseModel):
    """Transport Slip / Lorry Receipt Schema matching Batcotrans and Nagpur Golden Transport."""
    document_title: str = Field(description="The explicit header title of the logistics provider")
    challan_no: str = Field(description="Challan No, G.R. No, or Booking reference ID")
    invoice_no: Optional[str] = Field(default=None, description="Internal reference Invoice Number linked to the slip")
    invoice_value: Optional[float] = Field(default=None, description="Declared structural value of goods")
    date: str = Field(description="Execution or delivery date stamp. CRITICAL CORRECTION: Standardize to YYYY-MM-DD format. Ensure that any year written as shorthand '26' or '.26' is strictly mapped to the four-digit century year '2026'. Never output '0026'.")
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

    # Fixed: Replaced class Config with V2 ConfigDict
    model_config = ConfigDict(populate_by_name=True)


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
    
    model_config = ConfigDict(populate_by_name=True)

class TaxInvoiceSchema(BaseModel):
    """Product Inward: covers Raw Material inward AND Finished Goods inward."""
    inward_category: str = Field(description="Classify as 'Raw Material' or 'Finished Goods'")
    vendor_name: str = Field(description="Company issuing the invoice")
    vendor_gstin: Optional[str] = Field(default=None, description="GSTIN of the supplier/vendor")
    billing_to: str = Field(description="The buyer/consignee name")
    buyer_gstin: Optional[str] = Field(default=None, description="GSTIN of the buyer")
    invoice_number: str = Field(description="Invoice No. found on the document")
    invoice_date: str = Field(description="The exact issuance date found on the invoice header. CRITICAL CORRECTION: Standardize to YYYY-MM-DD format. If the document lists a two-digit year like '26' (e.g., 06-07-26 or 11.07.2026), always interpret the century as 2026. Do not ever return '0026' or '0025'.")
    po_number: Optional[str] = Field(default=None, description="PO reference")
    line_items: List[InvoiceLineItem]
    sub_total: Optional[float] = Field(default=None, description="Subtotal amount before tax")
    cgst_amount: Optional[float] = Field(default=None, description="Extracted CGST tax value")
    sgst_amount: Optional[float] = Field(default=None, description="Extracted SGST tax value")
    igst_amount: Optional[float] = Field(default=None, description="Extracted IGST tax value")
    grand_total: float = Field(description="The absolute Grand Total due")
    bank_details: Optional[str] = Field(default=None, description="Bank accounts or branch info")
    
    model_config = ConfigDict(populate_by_name=True)


class PackingLineItem(BaseModel):
    sl_no: Optional[int] = None
    description: str = Field(description="Description of the packed item")
    alt_quantity: Optional[str] = Field(default=None, description="Alternative units measurement")
    quantity: str = Field(description="Primary count/quantity packed")
    rate: Optional[float] = Field(default=None, description="Rate value if listed")
    amount: Optional[float] = Field(default=None, description="Line amount value if listed")
    
    model_config = ConfigDict(populate_by_name=True)

class PackingSlipSchema(BaseModel):
    """Delivery Slip / Packing Slip."""
    document_title: str = Field(default="Packing Slip", description="The explicit header title")
    voucher_number: str = Field(description="Voucher No. or Packing Slip reference ID")
    date: str = Field(description="Dated reference field. CRITICAL CORRECTION: Standardize to YYYY-MM-DD format. Ensure that any year written as shorthand '26' or '.26' is strictly mapped to the four-digit century year '2026'. Never output '0026'.")
    buyer_bill_to: str = Field(description="Company billed to")
    destination: Optional[str] = Field(default=None, description="Delivery destination city")
    dispatched_through: Optional[str] = Field(default=None, description="Logistics provider name")
    line_items: List[PackingLineItem]
    total_packages_count: Optional[str] = Field(default=None, description="Aggregated total at the bottom")
    grand_total: Optional[float] = Field(default=None, description="Final evaluation balance value")
    
    model_config = ConfigDict(populate_by_name=True)


class OfferLineItem(BaseModel):
    description: str = Field(
        description=(
            "The clean product name text extracted from the main item column "
            "(e.g., 'Particulars', 'Description of Goods', 'Quality / Sort No.'). "
            "1. STRIP DIMENSIONS: Remove any size configurations found embedded or written inline "
            "with the name (e.g., convert '30/60- Diamond' to 'Diamond', 'Kingfisher 30X60' to 'Kingfisher', "
            "and '76X82 Silk vanaja' to 'Silk vanaja'). "
            "2. KEEP QUALITY MODIFIERS: Retain descriptive specifications, style codes, colors, or quality "
            "brackets that belong to the product identity (e.g., 'Blue Star (w)', 'Blue Star (c)', "
            "'VIP (600g)', 'Hero 700g', 'Plain white 3', 'Diamond col'). "
            "3. RESOLVE DITTO MARKS: If a row contains ditto marks ('\"', '“', ',,', '—'), inherit the base product parent "
            "name from the row immediately above, combining it cleanly with any explicit suffix modifiers written on the current line."
        )
    )

    dimension: str = Field(
        default="",
        description=(
            "The product size configuration from the 'Width Size' or 'Dimension' column. "
            "1. STANDARDIZE VALUE FORMAT: Normalize all layout variations—whether written as a raw number sequence "
            "('3060'), separated by dots ('30..60', '30.60'), slashes ('30/60'), or dashes ('36-72')—to "
            "always be formatted strictly as 'WIDTHxLENGTH' (e.g., '30X60', '36X72', '76X82'). Do not truncate zeros (e.g., '3060' is '30X60', not '30X6'). "
            "2. CASCADE/RESOLVE DITTO MARKS: If subsequent rows contain ditto marks (,,), quotes (\"), lines, or are blank, "
            "you MUST explicitly copy and populate the active dimension string (e.g., '30X60') into every single line item entry. "
            "Never omit this field or return null."
        )
    )

    quantity_bales: Optional[str] = Field(
        default="",
        description=(
            "Extracted from dedicated macro packaging columns (like 'Bales' or 'Delivery') or structural handwritten "
            "annotations specifying whole packaging units (e.g., '1 Bale', '2 Bale', '1 Bale mix'). "
            "Leave as an empty string if only localized pieces or dozens are being listed on that row."
        )
    )

    quantity_pieces_meters: Optional[str] = Field(
        default=None,
        description=(
            "The quantity or localized unit count (e.g., from 'Qty', 'Meters/Pcs', or 'Qnty Pcs.Mtr' columns). "
            "CRITICAL HANDWRITING CORRECTION: Carefully map varying abbreviated notation to standard terms. "
            "Convert handwritten cursive forms like 'd.', 'd2', 'doz', or 'Dozen' to dozens ('dz'), and raw numeric "
            "counts to pieces ('pcs'). Examples: '5 d.' -> '5 dz', '10 d2' -> '10 dz', '720.00' -> '720 pcs'."
        )
    )

    rate_rs: Optional[float] = Field(
        default=None,
        description="The base rate value before the decimal/fraction point. Leave null if blank.",
    )

    rate_p: Optional[float] = Field(
        default=0.0,
        description="The rate fraction/paisa balance (e.g., from a split column or suffix like '.50' or '=00').",
    )

    model_config = ConfigDict(populate_by_name=True)

    @model_validator(mode="after")
    def check_must_have_metrics(self) -> "OfferLineItem":
        """Ensures that structural divider rows or bottom totals are ignored."""
        if (
            not self.quantity_pieces_meters
            and not self.quantity_bales
            and self.rate_rs is None
        ):
            raise ValueError(
                "Row lacks clear quantity metrics or item rates; skipping."
            )
        return self


class OfferFormSchema(BaseModel):
    """Product Request Form (Indent Sheet / Order Form / Order Confirmation)."""

    agency_or_broker: str = Field(
        description="Commission agent or organization profile banner (e.g., 'DILIP TEXTILE AGENCY', 'SHUKLA AGENCIES', 'SURYA AGENCIES')"
    )
    indent_number: str = Field(
        description="Tracking identity string (e.g., Indent No., Order No., Reference Code)"
    )
    date: str = Field(
        description="Document execution date stamp. CRITICAL CORRECTION: Standardize to YYYY-MM-DD format. Ensure that any year written as shorthand '26' or '.26' is strictly mapped to the four-digit century year '2026'. Never output '0026'."
    )
    from_party: str = Field(
        description="Buyer / Purchaser customer profile name and regional city location details"
    )
    to_party: str = Field(
        description="Seller / Supplier company profile designation"
    )
    dispatch_instructions: Optional[str] = Field(
        default=None,
        description="Transport guidelines, transit stations, destination, or booking routes (e.g., 'NGT to Bhilai', 'Destination: mata Samastipur')",
    )
    line_items: List[OfferLineItem] = Field(
        description="List of valid structural item rows extracted from the main contents grid table."
    )
    handwritten_notes: Optional[List[str]] = Field(
        default=None,
        description="Loose terms, miscellaneous structural footer text remarks, phone numbers, or discount terms (e.g., 'Cash discount 2%')",
    )

    model_config = ConfigDict(populate_by_name=True)

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
    Executes instant inline extraction to bypass background processing queues.
    """
    schema_cls = SCHEMA_MAP.get(doc_type)
    if schema_cls is None:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid doc_type routing identifier. Choose from: {list(SCHEMA_MAP.keys())}",
        )

    media_type = _resolve_media_type(file.filename)
    file_bytes = await file.read()

    # Make a direct synchronous round-trip request to LlamaCloud's inline extraction API
    async with httpx.AsyncClient(timeout=60.0) as http_client:
        try:
            headers = {"Authorization": f"Bearer {LLAMA_CLOUD_API_KEY}"}
            
            # Convert the active Pydantic code model directly to a JSON Schema string payload
            data = {"data_schema": json.dumps(schema_cls.model_json_schema())}
            files = {"file": (file.filename, file_bytes, media_type)}
            
            # Calling the /inline endpoint drops response latency down to 1-3 seconds
            response = await http_client.post(
                "https://api.llamacloud.com/v1/extract/inline",
                headers=headers,
                data=data,
                files=files
            )
            
            if response.status_code != 200:
                raise HTTPException(status_code=response.status_code, detail=response.text)
            
            # Extract and return the structure payload directly back to Zoho Deluge script
            result_json = response.json()
            return result_json.get("extract_result", result_json)
            
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Inline execution failed: {str(e)}")