import pytesseract
import re
import frappe
from frappe.utils.file_manager import get_file_path
from PIL import Image, ImageEnhance, ImageFilter

@frappe.whitelist()
def extract_item_level_data(docname, item_idx):
    try:
        # Fetch the Purchase Receipt document
        doc = frappe.get_doc("Purchase Receipt", docname)
        item_idx = int(item_idx)
        item = next((i for i in doc.items if i.idx == item_idx), None)
        
        if not item:
            return {"success": False, "error": "Item not found."}

        file_url = item.custom_attach_image
        if not file_url:
            return {"success": False, "error": "Please upload an image before extracting data."}

        file_path = get_file_path(file_url)
        
        # 🔹 Enhanced Image Processing for Camera Captured Images
        with Image.open(file_path) as img:
            img = img.convert("L")  # Convert to grayscale
            img = img.filter(ImageFilter.MedianFilter(size=3))  # Reduce noise
            img = img.filter(ImageFilter.SHARPEN)  # Sharpen the text
            enhancer = ImageEnhance.Contrast(img)
            img = enhancer.enhance(2.5)  # Boost contrast for better OCR
            img = img.resize((1600, 1600))  # Resize for consistent OCR accuracy

        # Configure Tesseract for printed text OCR
        extracted_text = pytesseract.image_to_string(img)
        
        # Store raw text for logging
        raw_text = extracted_text

        # 🔹 Extract Lot No.
        lot_pattern = r"Lot\s*No\.\s*:\s*(\d{6,7})"
        lot_match = re.search(lot_pattern, extracted_text, re.IGNORECASE)
        lot_no = lot_match.group(1).strip() if lot_match else None

        # 🔹 Extract Reel No.
        reel_pattern = r"REEL\s*No\.\s*:\s*(\d{3}\s*\d{5})"
        reel_match = re.search(reel_pattern, extracted_text, re.IGNORECASE)
        reel_no = reel_match.group(1).replace(" ", "").strip() if reel_match else None

        # 🔹 Extract Weight (Only keeping direct pattern match)
        weight_pattern = r"Wt\s*\(In\s*Kgs\)\s*:\s*(\d{2,3})"
        weight_match = re.search(weight_pattern, extracted_text, re.IGNORECASE)
        weight = weight_match.group(1).strip() if weight_match else None

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

        # Log extracted details
        frappe.logger().debug(f"Raw OCR Text: {raw_text}")
        frappe.logger().debug(f"Extracted: Lot={lot_no}, Reel={reel_no}, Weight={weight}")

        return {
            "success": True,
            "lot_no": lot_no,
            "reel_no": reel_no,
            "qty": weight,
            "raw_text": raw_text
        }

    except Exception as e:
        frappe.log_error(f"OCR Error: {str(e)}\nRaw Text: {extracted_text}", "OCR Processing Error")
        return {"success": False, "error": f"OCR Processing failed: {str(e)}"}