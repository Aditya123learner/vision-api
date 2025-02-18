import json
import re
import frappe
from google.cloud import vision
from frappe.utils.file_manager import get_file_path

@frappe.whitelist()
def extract_document_data(docname, file_url):
    try:
        file_path = get_file_path(file_url)
        # Initialize Google Vision client
        google_credentials = json.loads(frappe.conf.get("google_application_credentials"))
        client = vision.ImageAnnotatorClient.from_service_account_info(google_credentials)
        
        # Read the image
        with open(file_path, "rb") as image_file:
            content = image_file.read()
        image = vision.Image(content=content)
        
        # Perform OCR
        response = client.text_detection(image=image)
        texts = response.text_annotations
        if not texts:
            return {"success": False, "error": "No text detected."}
            
        extracted_text = texts[0].description
        
        # Get the Purchase Receipt document
        doc = frappe.get_doc("Purchase Receipt", docname)
        
        # Extract product sections
        # Split text by product patterns to get sections
        product_sections = []
        current_section = ""
        for line in extracted_text.split('\n'):
            if "CREPE TISSUE" in line and "Credit" in line:
                if current_section:
                    product_sections.append(current_section)
                current_section = line + "\n"
            else:
                current_section += line + "\n"
        if current_section:
            product_sections.append(current_section)

        # Process each original item from Purchase Receipt
        new_items = []
        processed_items = set()  # Keep track of processed items

        for item in doc.items:
            # Skip if we've already processed this item description
            if item.description in processed_items:
                continue
                
            # Find matching product section
            matching_section = None
            for section in product_sections:
                # Clean and normalize descriptions for matching
                section_desc = re.sub(r'\s+', ' ', section.split('\n')[0].strip())
                item_desc = re.sub(r'\s+', ' ', item.description.strip())
                
                if item_desc in section_desc or section_desc in item_desc:
                    matching_section = section
                    break
            
            if matching_section:
                # Extract lot numbers and their positions
                lot_matches = re.finditer(r"(\d{6})\s+\d+\s+(\d{8})\s+(\d+\.?\d*)", matching_section)
                
                # Create new rows for each BSR number
                for match in lot_matches:
                    lot_no = match.group(1)
                    bsr_no = match.group(2)
                    weight = match.group(3)
                    
                    new_row = {
                        "item_code": item.item_code,
                        "item_name": item.item_name,
                        "description": item.description,
                        "uom": item.uom,
                        "warehouse": item.warehouse,
                        "custom_lot_no": lot_no,
                        "custom_reel_no": bsr_no,
                        "qty": float(weight),
                        "received_qty": float(weight),
                        "accepted_qty": float(weight),
                        "rejected_qty": 0,
                        "purchase_order": item.purchase_order,
                        "purchase_order_item": item.purchase_order_item,
                        "material_request": item.material_request,
                        "material_request_item": item.material_request_item
                    }
                    new_items.append(new_row)
                
                processed_items.add(item.description)
        
        if new_items:
            # Clear existing items
            doc.items = []
            
            # Add all new items
            for row_data in new_items:
                doc.append("items", row_data)
            
            doc.save(ignore_version=True)
            
            return {
                "success": True,
                "message": f"Successfully created {len(new_items)} rows with data",
                "rows_count": len(new_items)
            }
        else:
            return {
                "success": False,
                "error": "No matching products found in the image"
            }
        
    except Exception as e:
        frappe.log_error(f"Document OCR Error: {str(e)}\nRaw Text: {extracted_text if 'extracted_text' in locals() else 'No text extracted'}", 
                        "Document OCR Processing Error")
        return {"success": False, "error": f"OCR Processing failed: {str(e)}"}
