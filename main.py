import base64
import json
import requests
from fastapi import FastAPI, BackgroundTasks, Form
from openai import OpenAI
from pydantic import BaseModel, Field, field_validator
from typing import List

app = FastAPI()

# Configuration Settings (Preserved from your code)
ZOHO_CLIENT_ID = "1000.M0HJA9QPN866PF1E6KNFKOZQ60SPMN"
ZOHO_CLIENT_SECRET = "ba50e395c263aa587afe7c581470fba756848635dc"
ZOHO_REFRESH_TOKEN = "1000.f38a3a5ffa1a57e1535af66ba0b93c22.6b9e0ea927654671deaff8b2b50012cc"
ZOHO_ACCOUNT_OWNER = "traqmetrixsolutions"
ZOHO_APP_LINK_NAME = "giridharan-enterprises"
ZOHO_DOMAIN = "https://www.zohoapis.com" 

# Target the lightweight local Ollama engine running natively on Windows
ai_client = OpenAI(base_url="http://localhost:11434/v1", api_key="ollama")

# --- Schemas with String-to-Float Cleaning ---
class LineItem(BaseModel):
    description: str = Field(description="Item or service text line")
    amount: float = Field(description="Final numerical cost line value")

    @field_validator('amount', mode='before')
    def clean_amount(cls, v):
        if isinstance(v, str):
            cleaned = v.replace("INR", "").replace("Rs", "").replace(",", "").strip()
            return float(cleaned)
        return v

class InvoiceSchema(BaseModel):
    vendor_name: str
    grand_total: float
    line_items: List[LineItem]

    @field_validator('grand_total', mode='before')
    def clean_total(cls, v):
        if isinstance(v, str):
            cleaned = v.replace("INR", "").replace("Rs", "").replace(",", "").strip()
            return float(cleaned)
        return v


def get_fresh_zoho_token():
    url = f"https://accounts.zoho.com/oauth/v2/token"
    params = {
        "refresh_token": ZOHO_REFRESH_TOKEN,
        "client_id": ZOHO_CLIENT_ID,
        "client_secret": ZOHO_CLIENT_SECRET,
        "grant_type": "refresh_token" # Confirmed refresh parameter hook
    }
    res = requests.post(url, data=params).json()
    return res["access_token"]


def async_extraction_pipeline(record_id: str, field_name: str, report_name: str):
    try:
        access_token = get_fresh_zoho_token()
        headers = {"Authorization": f"Zoho-oauthtoken {access_token}"}
        
        # 1. Stream the file directly out of Zoho's storage
        dl_url = f"{ZOHO_DOMAIN}/creator/v2.1/data/{ZOHO_ACCOUNT_OWNER}/{ZOHO_APP_LINK_NAME}/report/{report_name}/{record_id}/{field_name}/download"
        file_res = requests.get(dl_url, headers=headers)
        
        if file_res.status_code != 200:
            print(f"Failed to download image from Zoho. Status: {file_res.status_code}")
            return
        
        # Convert raw binary to base64 format string
        b64_image = base64.b64encode(file_res.content).decode("utf-8")
        
        # 2. Extract values instantly using the lightweight Ollama endpoint
        ai_res = ai_client.chat.completions.create(
            model="qwen2.5vl:3b",
            messages=[{
                "role": "user",
                "content": [
                    {"type": "text", "text": "Extract fields: vendor_name, grand_total, line_items (description, amount) from this unstructured invoice layout."},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64_image}"}}
                ]
            }],
            response_format={"type": "json_object"}, # Hardware-level JSON structural constraint
            temperature=0.0
        )
        
        # Parse output string via Pydantic validator models
        parsed_raw = json.loads(ai_res.choices[0].message.content)
        parsed_data = InvoiceSchema.model_validate(parsed_raw).model_dump()
        
        # 3. Format payload to update the main fields and Subform tables in Zoho
        zoho_update_payload = {
            "data": {
                "Vendor_Name": parsed_data["vendor_name"],
                "Total_Amount": str(parsed_data["grand_total"]),
                "Extraction_Status": "Ready for Review",
                "Invoice_Line_Items": [
                    {
                        "Item_Description": item["description"], 
                        "Amount": str(item["amount"])
                    }
                    for item in parsed_data["line_items"]
                ]
            }
        }
        
        # 4. Push data back into the original record ID row
        update_url = f"{ZOHO_DOMAIN}/creator/v2.1/data/{ZOHO_ACCOUNT_OWNER}/{ZOHO_APP_LINK_NAME}/report/{report_name}/{record_id}"
        update_res = requests.patch(update_url, json=zoho_update_payload, headers=headers)
        print(f"Zoho update sent. Status: {update_res.status_code}")
        
    except Exception as e:
        print(f"Extraction Error: {str(e)}")


@app.post("/api/v1/parse-invoice")
async def handle_webhook(
    background_tasks: BackgroundTasks,
    record_id: str = Form(...),
    field_name: str = Form(...),
    report_name: str = Form(...)
):
    background_tasks.add_task(async_extraction_pipeline, record_id, field_name, report_name)
    return {"status": "processing_queued"}