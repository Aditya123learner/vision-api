import pytesseract
import re
import frappe
from frappe.utils.file_manager import get_file_path
from PIL import Image, ImageEnhance, ImageFilter

@frappe.whitelist()
def extract_item_level_data(docname, item_idx):
    try:
        # Basic setup
        doc = frappe.get_doc("Purchase Receipt", docname)
        item_idx = int(item_idx)
        item = next((i for i in doc.items if i.idx == item_idx), None)
        
        if not item:
            return {"success": False, "error": "Item not found."}

        file_url = item.custom_attach_image
        if not file_url:
            return {"success": False, "error": "Please upload an image before extracting data."}

        file_path = get_file_path(file_url)
        
        # Enhanced image processing for camera captures
        with Image.open(file_path) as img:
            # Convert to grayscale
            img = img.convert("L")
            
            # Auto-rotate based on EXIF data if present
            try:
                import exifread
                with open(file_path, 'rb') as f:
                    tags = exifread.process_file(f)
                    if 'Image Orientation' in tags:
                        orientation = tags['Image Orientation'].values[0]
                        if orientation == 3:
                            img = img.rotate(180, expand=True)
                        elif orientation == 6:
                            img = img.rotate(270, expand=True)
                        elif orientation == 8:
                            img = img.rotate(90, expand=True)
            except:
                pass
            
            # Enhance image
            enhancer = ImageEnhance.Contrast(img)
            img = enhancer.enhance(3.0)
            
            brightness_enhancer = ImageEnhance.Brightness(img)
            img = brightness_enhancer.enhance(1.2)
            
            # Sharpen
            img = img.filter(ImageFilter.SHARPEN)
            
            # Resize for better OCR
            width, height = img.size
            scale_factor = 1.5
            new_size = (int(width * scale_factor), int(height * scale_factor))
            img = img.resize(new_size, Image.Resampling.LANCZOS)

        # Configure tesseract
        custom_config = r'--oem 3 --psm 6 -c tessedit_char_whitelist=0123456789:.()/ABCDEFGHIJKLMNOPQRSTUVWXYZ -c tessedit_do_invert=0'
        extracted_text = pytesseract.image_to_string(img, config=custom_config)
        
        # Store raw text for logging
        raw_text = extracted_text

        # Initialize variables
        lot_no = None
        reel_no = None
        weight = None
        missing_fields = []

        # Extract Lot No.
        lot_pattern = r"Lot\s*No\.\s*:\s*(\d{6,7})"
        lot_match = re.search(lot_pattern, extracted_text, re.IGNORECASE)
        if lot_match:
            lot_no = lot_match.group(1).strip()

        # Extract Reel No.
        reel_pattern = r"REEL\s*No\.\s*:\s*(\d{3}\s*\d{5})"
        reel_match = re.search(reel_pattern, extracted_text, re.IGNORECASE)
        if reel_match:
            reel_no = reel_match.group(1).replace(" ", "").strip()

        # Simplified weight extraction
        # First split text into lines
        lines = extracted_text.split('\n')
        for line in lines:
            # Look for line containing weight information
            if 'Wt' in line or 'KGS' in line.upper():
                # Extract the number from this line
                numbers = re.findall(r'\d+', line)
                if numbers:
                    # Take the last number in the line as weight
                    potential_weight = numbers[-1]
                    # Verify it's not the lot number or reel number
                    if potential_weight != lot_no and (not reel_no or potential_weight not in reel_no):
                        weight = potential_weight
                        break

        # Track missing fields
        if not lot_no:
            missing_fields.append("Lot No")
        if not reel_no:
            missing_fields.append("Reel No")
        if not weight:
            missing_fields.append("Weight")

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

        # Log the extracted text for debugging
        frappe.logger().debug(f"Raw OCR Text: {raw_text}")
        frappe.logger().debug(f"Extracted: Lot={lot_no}, Reel={reel_no}, Weight={weight}")

        if missing_fields:
    # Show message for each missing field
         frappe.msgprint(
            msg=f"Please manually enter the following fields: {', '.join(missing_fields)}",
            title='Missing Fields',
            indicator='orange'  # This will show an orange indicator
        )

        return {
            "success": True,
            "lot_no": lot_no,
            "reel_no": reel_no,
            "qty": weight,
            "raw_text": raw_text,
            "message": message,
            "missing_fields": missing_fields
        }

    except Exception as e:
        frappe.log_error(f"OCR Error: {str(e)}\nRaw Text: {extracted_text}", "OCR Processing Error")
        return {"success": False, "error": f"OCR Processing failed: {str(e)}"}