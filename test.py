import asyncio
import base64
import json
from main import ai_client, InvoiceSchema

async def test_ai_extraction():
    print("Reading local test image...")
    try:
        # Load your local test image file
        with open("test.jpeg", "rb") as image_file:
            binary_content = image_file.read()
            
        b64_image = base64.b64encode(binary_content).decode("utf-8")
        
        print("Sending request to local Ollama instance...")
        # Target the exact model name variant we configured
        ai_res = ai_client.chat.completions.create(
            model="qwen2.5vl:3b-q4_K_M", 
            messages=[{
                "role": "user",
                "content": [
                    {"type": "text", "text": "Extract fields: vendor_name, grand_total, line_items (description, amount) from this unstructured invoice layout."},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64_image}"}}
                ]
            }],
            response_format={"type": "json_object"},
            temperature=0.0
        )
        
        raw_content = ai_res.choices[0].message.content
        print("\n--- Raw Response From Ollama ---")
        print(raw_content)
        
        # Test the Pydantic validator models and data cleansing logic
        parsed_raw = json.loads(raw_content)
        parsed_data = InvoiceSchema.model_validate(parsed_raw).model_dump()
        
        print("\n--- Validated Pydantic Output Data ---")
        print(json.dumps(parsed_data, indent=2))
        print("\nSUCCESS: AI extraction and data cleansing work perfectly!")
        
    except FileNotFoundError:
        print("ERROR: Please put a 'test_invoice.jpg' file in this folder to run the mock test.")
    except Exception as e:
        print(f"\nFAILURE: Something broke down in the pipeline: {str(e)}")

# Execute the test loop
asyncio.run(test_ai_extraction())