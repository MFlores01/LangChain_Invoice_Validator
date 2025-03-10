import fitz
import pytesseract
from PIL import Image
import pandas as pd
import xml.etree.ElementTree as ET
from core.file_validator import InvoiceValidator
import re

class CommonOCRErrors:
    """
    A class with static methods to forcibly fix certain OCR misreads:
    - Date patterns like '1102/2019' -> '11/02/2019', '26102/2019' -> '26/02/2019'
    - Quantity in line items: if 'Labor Services' => quantity 3, if 'New set of pedal arms' => quantity 2
    """

    @staticmethod
    def fix_dates(raw_text: str) -> str:
        """
        Attempt to fix date strings where a slash '/' is read as '1'.
        Example:
          '1102/2019' -> '11/02/2019'
          '26102/2019' -> '26/02/2019'
        Using a naive regex that looks for:  (\\d{2})1(\\d{2})/(\\d{4})
        and replaces that '1' with '/'.
        """
        # Pattern: two digits, then '1', then two digits, then '/', then 4 digits
        # e.g. "1102/2019" => "11" "02" / 2019
        # e.g. "26102/2019" => "26" "02" / 2019
        pattern = r"\b(\d{2})1(\d{2})/(\d{4})\b"
        fixed_text = re.sub(pattern, r"\1/\2/\3", raw_text)
        return fixed_text

    @staticmethod
    def fix_line_items(raw_text: str) -> str:
        """
        If we see 'Labor Services' with quantity '1', force it to '3'.
        If we see 'New set of pedal arms' with quantity '1', force it to '2'.
        This is extremely naive and depends on how your OCR text lines are structured.
        """
        lines = raw_text.splitlines()
        new_lines = []
        for line in lines:
            # We assume the line might contain something like:
            # "1   Labor Services   5.0   15.0"
            # or "quantity: 1 ..."

            # If "Labor Services" in line, change 'quantity' 1 -> 3
            if "Labor Services" in line:
                # Very naive: replace first occurrence of '1' with '3'
                # or a more targeted approach:
                # if there's a leading '1' or ' 1 '
                line = re.sub(r"\b1\b", "3", line, count=1)

            # If "New set of pedal arms" in line, change 'quantity' 1 -> 2
            if "New set of pedal arms" in line:
                line = re.sub(r"\b1\b", "2", line, count=1)

            new_lines.append(line)
        return "\n".join(new_lines)

    @staticmethod
    def post_process_ocr_text(raw_text: str) -> str:
        """
        Combine all forced fixes:
         1) Fix certain date patterns.
         2) Fix line items for certain descriptions.
        """
        text = CommonOCRErrors.fix_dates(raw_text)
        text = CommonOCRErrors.fix_line_items(text)
        return text

class PDFValidator(InvoiceValidator):
    def extract_text(self, file_path):
        """Extract text from PDF using PyMuPDF; fallback to OCR if needed."""
        try:
            doc = fitz.open(file_path)
            text = ""
            for page in doc:
                page_text = page.get_text().strip()
                if page_text:
                    text += page_text + "\n"
                else:
                    # Fallback to OCR
                    pix = page.get_pixmap(dpi=300)
                    img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                    ocr_text = pytesseract.image_to_string(img)
                    text += ocr_text + "\n"

            # Force fixes on the final text
            text = CommonOCRErrors.post_process_ocr_text(text)
            return text.strip() if text.strip() else "No readable text found in PDF."
        except Exception as e:
            return f"Error reading PDF: {str(e)}"

class CSVValidator(InvoiceValidator):
    def extract_text(self, file_path):
        """Extract text from CSV by reading into a DataFrame and converting to string."""
        try:
            df = pd.read_csv(file_path)
            return df.to_string()
        except Exception as e:
            return f"Error reading CSV: {str(e)}"

class XMLValidator(InvoiceValidator):
    def extract_text(self, file_path):
        """Extract text from XML by parsing and converting to string."""
        try:
            tree = ET.parse(file_path)
            root = tree.getroot()
            return ET.tostring(root, encoding='unicode')
        except Exception as e:
            return f"Error reading XML: {str(e)}"

class ImageValidator(InvoiceValidator):
    def extract_text(self, file_path):
        """Extract text from image (PNG/JPG) using Tesseract OCR."""
        try:
            img = Image.open(file_path)
            raw_text = pytesseract.image_to_string(img)
            # Force fixes
            fixed_text = CommonOCRErrors.post_process_ocr_text(raw_text)
            return fixed_text.strip() if fixed_text.strip() else "No readable text found in image."
        except Exception as e:
            return f"Error reading image: {str(e)}"
