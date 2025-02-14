# api.py

import json
import re
from typing import Dict, List, Tuple
import frappe
from google.cloud import vision
from frappe.utils.file_manager import get_file_path
from PIL import Image, ImageEnhance

def preprocess_image(file_path: str) -> str:
    """Preprocess the image using PIL to improve OCR quality."""
    try:
        # Open image
        image = Image.open(file_path)
        
        # Convert to grayscale
        image = image.convert('L')
        
        # Enhance contrast
        enhancer = ImageEnhance.Contrast(image)
        image = enhancer.enhance(2.0)
        
        # Enhance sharpness
        enhancer = ImageEnhance.Sharpness(image)
        image = enhancer.enhance(2.0)
        
        # Save processed image
        processed_path = file_path + "_processed.png"
        image.save(processed_path, 'PNG')
        
        return processed_path
    except Exception as e:
        frappe.log_error(f"Image preprocessing failed: {str(e)}", "OCR Error")
        return file_path

class DocumentProcessor:
    def __init__(self):
        self.client = None
        self.setup_vision_client()

    def setup_vision_client(self):
        """Initialize Google Vision client."""
        try:
            google_credentials = json.loads(frappe.conf.get("google_application_credentials"))
            self.client = vision.ImageAnnotatorClient.from_service_account_info(google_credentials)
        except Exception as e:
            frappe.log_error(f"Failed to initialize Vision client: {str(e)}", "OCR Error")
            raise

    def process_image(self, file_path: str) -> Dict:
        """Process a single image and extract data."""
        try:
            # Preprocess image
            processed_path = preprocess_image(file_path)
            
            # Read the image
            with open(processed_path, "rb") as image_file:
                content = image_file.read()
            image = vision.Image(content=content)
            
            # Perform OCR
            response = self.client.document_text_detection(image=image)
            texts = response.text_annotations
            
            if not texts:
                return {"success": False, "error": "No text detected in image"}
                
            extracted_text = texts[0].description
            
            # Process the extracted text
            result = self.process_extracted_text(extracted_text)
            result['extracted_text'] = extracted_text
            
            return result
            
        except Exception as e:
            frappe.log_error(f"Image processing failed: {str(e)}", "OCR Error")
            return {"success": False, "error": str(e)}

    def process_extracted_text(self, text: str) -> Dict:
        """Process extracted text and organize data."""
        try:
            lines = text.split('\n')
            
            products_data = []
            current_product = None
            current_lot = None
            current_data = []
            
            for line in lines:
                # Check for product name
                if 'GSM' in line:
                    if current_data:
                        products_data.append({
                            'product': current_product,
                            'lot_no': current_lot,
                            'data': current_data
                        })
                    current_product = line
                    current_data = []
                    current_lot = None
                
                # Look for lot number and size
                lot_size_match = re.search(r'(\d{6})\s+(\d+)', line)
                if lot_size_match:
                    current_lot = lot_size_match.group(1)
                
                # Look for BSR number and weight
                reel_weight_match = re.search(r'(\d{8})\s+(\d+(?:\.\d{2})?)', line)
                if reel_weight_match:
                    reel_no = reel_weight_match.group(1)
                    weight = reel_weight_match.group(2)
                    current_data.append((reel_no, weight))
            
            # Add the last product
            if current_data:
                products_data.append({
                    'product': current_product,
                    'lot_no': current_lot,
                    'data': current_data
                })
            
            return {
                "success": True,
                "products_data": products_data
            }
            
        except Exception as e:
            frappe.log_error(f"Text processing failed: {str(e)}", "OCR Error")
            return {"success": False, "error": str(e)}

@frappe.whitelist()
def process_multiple_documents(docname, file_urls):
    """Process multiple documents and combine their data."""
    if isinstance(file_urls, str):
        file_urls = [file_urls]  # Convert single URL to list
        
    try:
        processor = DocumentProcessor()
        all_products_data = []
        all_extracted_texts = []
        
        for file_url in file_urls:
            file_path = get_file_path(file_url)
            result = processor.process_image(file_path)
            
            if result["success"]:
                all_products_data.extend(result["products_data"])
                all_extracted_texts.append(result["extracted_text"])
            else:
                frappe.log_error(f"Failed to process file {file_url}: {result['error']}", "OCR Error")
        
        if not all_products_data:
            return {"success": False, "error": "No data could be extracted from any of the documents"}
        
        # Update the document
        doc = frappe.get_doc("Purchase Receipt", docname)
        
        # Store template data
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
        total_rows = 0
        for product in all_products_data:
            for reel_no, weight in product['data']:
                row_data = {
                    "custom_lot_no": product['lot_no'],
                    "custom_reel_no": reel_no,
                    "qty": float(weight),
                    "received_qty": float(weight),
                    "accepted_qty": float(weight),
                    "rejected_qty": 0
                }
                
                if template_data:
                    row_data.update(template_data)
                    
                doc.append("items", row_data)
                total_rows += 1
        
        doc.save(ignore_version=True)
        
        return {
            "success": True,
            "message": f"Successfully processed {len(file_urls)} documents",
            "total_files": len(file_urls),
            "total_rows": total_rows,
            "extracted_texts": all_extracted_texts,
            "products_data": all_products_data
        }
        
    except Exception as e:
        frappe.log_error(f"Multiple document processing failed: {str(e)}", "OCR Error")
        return {"success": False, "error": str(e)}

@frappe.whitelist()
def extract_document_data(docname: str, file_url: str) -> Dict:
    """Process a single document."""
    return process_multiple_documents(docname, [file_url])

@frappe.whitelist()
def extract_item_level_data(docname: str, item_idx: int) -> Dict:
    """Extract data for a single item row."""
    try:
        doc = frappe.get_doc("Purchase Receipt", docname)
        if not doc.items or len(doc.items) < item_idx:
            return {"success": False, "error": "Invalid item index"}
            
        item = doc.items[item_idx - 1]
        if not item.custom_attach_image:
            return {"success": False, "error": "No image attached to this item"}
            
        processor = DocumentProcessor()
        file_path = get_file_path(item.custom_attach_image)
        result = processor.process_image(file_path)
        
        if not result["success"]:
            return result
            
        if not result["products_data"]:
            return {"success": False, "error": "No data could be extracted from the image"}
            
        # Take the first reel data from the first product
        product = result["products_data"][0]
        if not product["data"]:
            return {"success": False, "error": "No reel data found in the image"}
            
        reel_no, weight = product["data"][0]
        
        return {
            "success": True,
            "lot_no": product["lot_no"],
            "reel_no": reel_no,
            "qty": float(weight)
        }
        
    except Exception as e:
        frappe.log_error(f"Item level data extraction failed: {str(e)}", "OCR Error")
        return {"success": False, "error": str(e)}
