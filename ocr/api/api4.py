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

        #  Enhanced Image Processing
        with Image.open(file_path) as img:
            img = img.convert("L")  # Convert to grayscale
            img = img.filter(ImageFilter.MedianFilter(size=3))  # Reduce noise
            img = img.filter(ImageFilter.SHARPEN)  # Sharpen text
            enhancer = ImageEnhance.Contrast(img)
            img = enhancer.enhance(2.5)  # Boost contrast
            img = img.resize((1600, 1600))  # Resize for better OCR accuracy

        # Custom Tesseract Configuration
        custom_config = r'--oem 3 --psm 6 -c tessedit_char_whitelist=0123456789:.()/ABCDEFGHIJKLMNOPQRSTUVWXYZ '
        
        # Initialize variables
        lot_no, reel_no, weight = None, None, None

        ###  **1. Try `image_to_string()` First (Full Text OCR)**
        full_text = pytesseract.image_to_string(img, config=custom_config)
        frappe.logger().debug(f"OCR Full Text Output: {full_text}")

        if not lot_no:
            match = re.search(r'Lot\s*No\.\s*:\s*(\d{6,7})', full_text, re.IGNORECASE)
            lot_no = match.group(1) if match else None
        
        if not reel_no:
            match = re.search(r'REEL\s*No\.\s*:\s*(\d{3}\s*\d{5})', full_text, re.IGNORECASE)
            reel_no = match.group(1) if match else None
        
        if not weight:
            match = re.search(r'Wt\s*\(In\s*Kgs\)\s*:\s*(\d{2,3})', full_text, re.IGNORECASE)
            weight = match.group(1) if match else None

        ###  **2. If Any Field is Missing, Use `image_to_data()` (Word-Based OCR)**
        if not lot_no or not reel_no or not weight:
            ocr_data = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT)
            words = [w.strip() for w in ocr_data['text'] if w.strip()]
            frappe.logger().debug(f"OCR Extracted Words: {words}")

            for i, word in enumerate(words):
                if not lot_no and "lot" in word.lower() and i + 1 < len(words):
                    lot_no = words[i + 1] if words[i + 1].isdigit() else lot_no
                if not reel_no and "reel" in word.lower() and i + 1 < len(words):
                    reel_no = words[i + 1].replace(" ", "") if words[i + 1].isdigit() else reel_no
                if not weight and ("wt" in word.lower() or "kgs" in word.lower()) and i + 1 < len(words):
                    possible_weight = words[i + 1]
                    if re.match(r"^\d+(\.\d+)?$", possible_weight):  # Allow decimal values
                        weight = possible_weight

        ###  **3. If Data Still Missing, Apply Alternative OCR Settings**
        if not lot_no or not reel_no or not weight:
            alternative_config = r'--oem 3 --psm 11'  # Sparse text mode
            alt_text = pytesseract.image_to_string(img, config=alternative_config)
            frappe.logger().debug(f"Alternative OCR Output: {alt_text}")

            if not lot_no:
                match = re.search(r'Lot\s*No[:\-]?\s*(\d+)', alt_text, re.IGNORECASE)
                lot_no = match.group(1) if match else lot_no

            if not reel_no:
                match = re.search(r'REEL\s*No[:\-]?\s*(\d+)', alt_text, re.IGNORECASE)
                reel_no = match.group(1) if match else reel_no

            if not weight:
                match = re.search(r'(\d+(\.\d+)?)\s*Kgs', alt_text, re.IGNORECASE)
                weight = match.group(1) if match else weight

        ### 🔹 **Final Validations & Document Update**
        if lot_no:
            item.custom_lot_no = lot_no
        if reel_no:
            item.custom_reel_no = reel_no
        if weight:
            item.qty = float(weight)
            item.received_qty = float(weight)
            item.rejected_qty = 0

        doc.save(ignore_version=True)

        frappe.logger().debug(f"Extracted: Lot={lot_no}, Reel={reel_no}, Weight={weight}")

        return {
            "success": True,
            "lot_no": lot_no,
            "reel_no": reel_no,
            "qty": weight,
        }

    except Exception as e:
        frappe.log_error(f"OCR Error: {str(e)}", "OCR Processing Error")
        return {"success": False, "error": f"OCR Processing failed: {str(e)}"}
