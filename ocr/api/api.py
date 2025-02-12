import json
import re
import frappe
from google.cloud import vision
from frappe.utils.file_manager import get_file_path
from PIL import Image

@frappe.whitelist()
def extract_item_level_data(docname, item_idx):
    try:
        # Fetch Purchase Receipt document
        doc = frappe.get_doc("Purchase Receipt", docname)
        item_idx = int(item_idx)
        item = next((i for i in doc.items if i.idx == item_idx), None)
        
        if not item:
            return {"success": False, "error": "Item not found."}
        
        file_url = item.custom_attach_image
        if not file_url:
            return {"success": False, "error": "Please upload an image before extracting data."}
            
        file_path = get_file_path(file_url)
        
        # Load Google Vision Credentials
        google_credentials = json.loads(frappe.conf.get("google_application_credentials"))
        # Initialize Google Vision API Client
        client = vision.ImageAnnotatorClient.from_service_account_info(google_credentials)
        
        # Read the image
        with open(file_path, "rb") as image_file:
            content = image_file.read()
        image = vision.Image(content=content)
        
        # Perform OCR using Google Vision
        response = client.text_detection(image=image)
        texts = response.text_annotations
        
        if not texts:
            return {"success": False, "error": "No text detected."}
            
        extracted_text = texts[0].description
        frappe.log_error(f"Extracted Text:\n{extracted_text}", "OCR Debug Log")
        
        # Extract Lot No.
        lot_pattern = re.search(r"Lot\s*No\.\s*:\s*(\d{6})", extracted_text, re.IGNORECASE)
        lot_no = lot_pattern.group(1) if lot_pattern else None
        
        # Fallback: Find first 6-7 digit number in the text
        if not lot_no:
            lot_fallback = re.findall(r"\b\d{6}\b", extracted_text)
            lot_no = lot_fallback[0] if lot_fallback else None
            
        # Extract Reel No.
        reel_pattern = re.search(r"REEL\s*No\.\s*:\s*(\d{3}\s*\d{5})", extracted_text, re.IGNORECASE)
        reel_no = reel_pattern.group(1).replace(" ", "") if reel_pattern else None
        
        # Fallback: Find first 8-9 digit number
        if not reel_no:
            reel_fallback = re.findall(r"\b\d{8,9}\b", extracted_text)
            reel_no = reel_fallback[0] if reel_fallback else None
            
        # Extract Weight (Wt in Kgs)
        weight_pattern = re.search(r"Wt\s*\(In\s*Kgs\)\s*:\s*(\d{2,3})", extracted_text, re.IGNORECASE)
        weight = weight_pattern.group(1) if weight_pattern else None
        
        # Fallback: Extract last 2-3 digit number
        if not weight:
            weight_fallback = re.findall(r"\b\d{2,3}\b", extracted_text)
            weight = weight_fallback[-1] if weight_fallback else None
            
        # Update document fields
        if lot_no:
            item.custom_lot_no = lot_no
        if reel_no:
            item.custom_reel_no = reel_no
        if weight:
            item.qty = float(weight)
            item.received_qty = float(weight)
            item.rejected_qty = 0
            
        doc.save(ignore_version=True)
        
        return {
            "success": True,
            "lot_no": lot_no,
            "reel_no": reel_no,
            "qty": weight,
            "raw_text": extracted_text
        }
        
    except Exception as e:
        frappe.log_error(f"OCR Error: {str(e)}\nRaw Text: {extracted_text if 'extracted_text' in locals() else 'No text extracted'}", 
                        "OCR Processing Error")
        return {"success": False, "error": f"OCR Processing failed: {str(e)}"}

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
        frappe.log_error(f"Extracted Text:\n{extracted_text}", "OCR Debug Log")
        
        # Extract lot number (common for all rows)
        lot_pattern = re.search(r"Lot\s*No\.\s*:\s*(\d{6})", extracted_text, re.IGNORECASE)
        lot_no = lot_pattern.group(1) if lot_pattern else None
        
        # Extract all BSR numbers and weights
        reel_weight_pairs = re.findall(r'(\d{8})\s+(\d{2,3}(?:\.\d{0,2})?)', extracted_text)
        
        if not reel_weight_pairs:
            return {"success": False, "error": "No reel numbers and weights found."}
            
        # Get the document
        doc = frappe.get_doc("Purchase Receipt", docname)
        
        # Store template row data before clearing
        template_data = None
        if doc.items:
            template_data = {
                "item_code": doc.items[0].item_code,
                "item_name": doc.items[0].item_name,
                "description": doc.items[0].description,
                "uom": doc.items[0].uom,
                "warehouse": doc.items[0].warehouse
            }
        
        # Clear existing items
        doc.items = []
        
        # Add all extracted rows
        for reel_no, weight in reel_weight_pairs:
            row_data = {
                "custom_lot_no": lot_no,
                "custom_reel_no": reel_no,
                "qty": float(weight),
                "received_qty": float(weight),
                "accepted_qty": float(weight),
                "rejected_qty": 0
            }
            
            # Add template data if available
            if template_data:
                row_data.update(template_data)
                
            doc.append("items", row_data)
        
        doc.save(ignore_version=True)
        
        return {
            "success": True,
            "message": f"Successfully created {len(reel_weight_pairs)} rows with data",
            "rows_count": len(reel_weight_pairs)
        }
        
    except Exception as e:
        frappe.log_error(f"Document OCR Error: {str(e)}\nRaw Text: {extracted_text if 'extracted_text' in locals() else 'No text extracted'}", 
                        "Document OCR Processing Error")
        return {"success": False, "error": f"OCR Processing failed: {str(e)}"}
