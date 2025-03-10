import re
import json, hashlib
from abc import ABC, abstractmethod
import fitz
import pytesseract
from PIL import Image
import pandas as pd
import xml.etree.ElementTree as ET
from core.data_processor import CommonOCRErrors  # Reuse post-processing if needed
from utils.db import DatabaseManager
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from utils.vector_stores import po_vectorstore  # Import the centralized PO vector store

PO_KEYWORDS = [
    "purchase order", "po number", "vendor", "shipping address", "billing address",
    "order summary", "subtotal", "tax", "total"
]

db_manager = DatabaseManager()

class POValidator(ABC):
    """
    Abstract base class for PO extraction using an LLM and a centralized vector store.
    This version requires that line items have exactly these keys: { "description", "quantity", "unit_price", "amount" }.
    It also extracts fields using standardized names so that invoices and POs use the same field titles.
    """
    REQUIRED_FIELDS = [
        "po_number",
        "po_date",
        "supplier_name",       # Unified field name (instead of vendor)
        "billing_address",
        "shipping_address",
        "line_items",          # Each line item: { "description", "quantity", "unit_price", "amount" }
        "subtotal",
        "tax",
        "total"
    ]
    
    def __init__(self):
        self.llm = ChatOpenAI(temperature=0)
        self.embeddings = OpenAIEmbeddings()
        # Use the centralized vector store for purchase orders.
        self.vector_store = po_vectorstore
        self.base_prompt = (
            "First, determine if this text is actually a purchase order. If not, respond with:\n\n"
            "{\n"
            "  \"validation\": { \"valid_format\": false, \"missing_fields\": [], \"anomalies\": [\"Document not recognized as purchase order\"] },\n"
            "  \"extracted_fields\": {}\n"
            "}\n\n"
            "If it IS a purchase order, extract and validate the following fields (handle synonyms). "
            "If a mandatory field is not found, set it to 'N/A'. If an optional field is not found, omit it:\n\n"
            "Mandatory fields:\n"
            "1. po_number\n"
            "2. po_date\n"
            "3. supplier_name\n"
            "4. billing_address\n"
            "5. shipping_address\n"
            "6. line_items: an array of objects, each with exactly these keys: {\"description\", \"quantity\", \"unit_price\", \"amount\"}.\n\n"
            "Optional fields:\n"
            "7. subtotal\n"
            "8. tax\n"
            "9. total\n\n"
            "Handle synonyms such that, for example, 'vendor' is mapped to 'supplier_name' and any synonyms for addresses are unified accordingly.\n\n"
            "Return a valid JSON object with exactly two keys:\n"
            "\"validation\": { \"valid_format\": bool, \"missing_fields\": [], \"anomalies\": [] },\n"
            "\"extracted_fields\": { ...all fields above... }\n\n"
            "Your output must be valid JSON only, with no extra text."
        )
    
    @abstractmethod
    def extract_text(self, file_path: str) -> str:
        """Extract text from the file (to be implemented by subclasses)."""
        pass

    def build_rag_prompt(self, po_text, top_k=2):
        retrieved_docs = self.vector_store.similarity_search(po_text, k=top_k)
        context_snippets = [doc.page_content.strip() for doc in retrieved_docs]
        context_text = "\n\n".join(context_snippets)
        rag_prompt = (
            f"You have the following validated PO examples:\n"
            f"{context_text}\n\n"
            f"Now, here is a NEW PO text:\n"
            f"{po_text}\n\n"
            f"{self.base_prompt}"
        )
        return rag_prompt

    def store_po_context(self, po_text, extracted_fields):
        chunk = (
            "PAST VALIDATED PO EXAMPLE:\n\n"
            f"Raw PO Text:\n{po_text}\n\n"
            "Extracted Fields:\n"
            f"{json.dumps(extracted_fields, indent=2)}\n"
        )
        self.vector_store.add_texts([chunk])
        self.vector_store.persist()

    def validate_po(self, file_path: str) -> dict:
        validation_result = {
            "is_valid_format": False,
            "is_corrupted": False,
            "is_duplicate": False,
            "missing_fields": [],
            "extracted_fields": {},
            "anomalies": []
        }
        try:
            with open(file_path, "rb") as f:
                file_bytes = f.read()
            file_hash = hashlib.sha256(file_bytes).hexdigest()

            # Check for duplicate using the PO duplicate method.
            if db_manager.check_duplicate_po(file_hash):
                validation_result["is_duplicate"] = True
                validation_result["anomalies"].append("Duplicate purchase order detected.")

            po_text = self.extract_text(file_path)
            if not po_text or po_text.startswith("Error reading"):
                validation_result["is_corrupted"] = True
                validation_result["anomalies"].append("File extraction error: " + po_text)
                return validation_result

            text_lower = po_text.lower()
            if not any(keyword in text_lower for keyword in PO_KEYWORDS):
                validation_result["anomalies"].append("Document not recognized as purchase order (keyword check).")
                return validation_result

            try:
                results = self.vector_store.similarity_search_with_score(po_text, k=1)
                if results and results[0][1] < 0.2:
                    validation_result["is_duplicate"] = True
            except Exception as e:
                validation_result["anomalies"].append(f"Vector search error: {str(e)}")

            prompt_text = self.build_rag_prompt(po_text, top_k=2)
            llm_response = self.llm.invoke(prompt_text)
            raw_text = llm_response.content if hasattr(llm_response, "content") else str(llm_response)
            start_index = raw_text.find('{')
            end_index = raw_text.rfind('}') + 1
            json_str = raw_text[start_index:end_index] if start_index != -1 and end_index != -1 else raw_text

            try:
                parsed_result = json.loads(json_str)
                val = parsed_result.get("validation", {})
                validation_result["is_valid_format"] = val.get("valid_format", False)
                validation_result["missing_fields"] = val.get("missing_fields", [])
                validation_result["anomalies"] = val.get("anomalies", [])
                extracted = parsed_result.get("extracted_fields", {})
                final_fields = {}
                for field in self.REQUIRED_FIELDS:
                    final_fields[field] = extracted.get(field, "N/A")
                # Optional fields can be added if needed.
                validation_result["extracted_fields"] = final_fields
            except Exception as parse_error:
                validation_result["anomalies"].append(f"Failed to parse JSON: {str(parse_error)}")

            if validation_result["is_valid_format"]:
                try:
                    self.store_po_context(po_text, validation_result["extracted_fields"])
                    if not validation_result["is_duplicate"]:
                        db_manager.store_purchase_order(file_hash, validation_result["extracted_fields"])
                except Exception as e:
                    validation_result["anomalies"].append(f"Failed to store PO in DB: {str(e)}")
        except Exception as e:
            validation_result["anomalies"].append(str(e))
        return validation_result

# Concrete implementations for different file types:

class PDFPOValidator(POValidator):
    def extract_text(self, file_path: str) -> str:
        try:
            doc = fitz.open(file_path)
            text = ""
            for page in doc:
                page_text = page.get_text().strip()
                if page_text:
                    text += page_text + "\n"
                else:
                    pix = page.get_pixmap(dpi=300)
                    img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                    ocr_text = pytesseract.image_to_string(img)
                    text += ocr_text + "\n"
            text = CommonOCRErrors.post_process_ocr_text(text)
            return text.strip() if text.strip() else "No readable text found in PDF."
        except Exception as e:
            return f"Error reading PO PDF: {str(e)}"

class CSVPOValidator(POValidator):
    def extract_text(self, file_path: str) -> str:
        try:
            df = pd.read_csv(file_path)
            return df.to_string()
        except Exception as e:
            return f"Error reading CSV PO: {str(e)}"

class XMLPOValidator(POValidator):
    def extract_text(self, file_path: str) -> str:
        try:
            tree = ET.parse(file_path)
            root = tree.getroot()
            return ET.tostring(root, encoding='unicode')
        except Exception as e:
            return f"Error reading XML PO: {str(e)}"

class ImagePOValidator(POValidator):
    def extract_text(self, file_path: str) -> str:
        try:
            img = Image.open(file_path)
            raw_text = pytesseract.image_to_string(img)
            return raw_text.strip() if raw_text.strip() else "No readable text found in image."
        except Exception as e:
            return f"Error reading PO image: {str(e)}"
