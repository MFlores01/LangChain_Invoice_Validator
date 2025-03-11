import streamlit as st
import hashlib
import json
from abc import ABC, abstractmethod
from langchain.prompts import PromptTemplate
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
import pymupdf  # PyMuPDF for PDF extraction
import pandas as pd
import xml.etree.ElementTree as ET
import tempfile
import os
from dotenv import load_dotenv

# For embeddings and vector DB
from langchain.vectorstores import Chroma

# For OCR
import pytesseract
pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"  # adjust the path as needed

from PIL import Image

# Load environment variables from .env file
load_dotenv()

class InvoiceValidator(ABC):
    """
    Base class for invoice validation using an LLM and a vector database (Chroma).
    Uses a RAG (Retrieval-Augmented Generation) approach:
      - Retrieves previously validated invoices to guide extraction.
      - After validation, stores the new invoice for future references.
    """

    # Define main invoice fields.
    # Note: "line_items" will be an array of objects.
    REQUIRED_FIELDS = [
        "invoice_number",
        "invoice_date",
        "due_date",
        "invoice_to",
        "supplier_name",
        "supplier_address",
        "total_amount",
        "line_items",     # An array of objects, each with {quantity, description, unit_price, amount}
        "discount",
        "tax_vat",
        "email",
        "phone_number"
    ]

    # Some simple invoice keywords for a heuristic check
    INVOICE_KEYWORDS = [
        "invoice", "bill", "supplier", "due", "tax", "vat", "subtotal", "total",
        "line item", "payment", "amount", "qty", "balance", "remit"
    ]

    def __init__(self):
        self.llm = ChatOpenAI(temperature=0)
        self.embeddings = OpenAIEmbeddings()
        try:
            self.vector_store = Chroma(
                persist_directory="invoice_db",
                embedding_function=self.embeddings,
                collection_name="invoices"
            )
        except Exception:
            self.vector_store = Chroma.from_texts(
                [],
                self.embeddings,
                collection_name="invoices",
                persist_directory="invoice_db"
            )

        # Base prompt instructs the LLM to first determine if the document is an invoice.
        # If so, it should output all the required fields and, importantly,
        # return line items as an array of objects with exactly these keys:
        # { "quantity", "description", "unit_price", "amount" }.
        self.base_prompt = (
            "First, determine if this text is actually an invoice. If not, respond with:\n\n"
            "{\n"
            "  \"validation\": {\n"
            "    \"valid_format\": false,\n"
            "    \"missing_fields\": [],\n"
            "    \"anomalies\": [\"Document not recognized as invoice\"]\n"
            "  },\n"
            "  \"extracted_fields\": {}\n"
            "}\n\n"
            "If it IS an invoice, extract and validate the following fields (handle synonyms). "
            "If any field is not found, set its value to 'N/A':\n\n"
            "1. invoice_number\n"
            "2. invoice_date\n"
            "3. due_date\n"
            "4. invoice_to (only the person's name)\n"
            "5. supplier_name\n"
            "6. supplier_address\n"
            "7. total_amount\n"
            "8. line_items: an array of objects, each with exactly these keys: {\"quantity\", \"description\", \"unit_price\", \"amount\"}.\n"
            "   - Do not combine multiple items into one; each item must be a separate object in the array.\n"
            "9. discount\n"
            "10. tax_vat\n"
            "11. email\n"
            "12. phone_number\n\n"
            "Return a valid JSON object with exactly two keys:\n"
            "\"validation\": {\n"
            "  \"valid_format\": bool,\n"
            "  \"missing_fields\": [],\n"
            "  \"anomalies\": []\n"
            "},\n"
            "\"extracted_fields\": {\n"
            "  ...all fields above...\n"
            "}\n\n"
            "Your output must be valid JSON only, with no extra text."
        )

    @abstractmethod
    def extract_text(self, file_path):
        """Extract text from the file (implemented by subclasses)."""
        pass

    def build_rag_prompt(self, invoice_text, top_k=2):
        """
        Retrieve top_k similar invoices from the DB and build a prompt that includes:
         - Prior validated examples,
         - The new invoice text,
         - And the base extraction instructions.
        """
        retrieved_docs = self.vector_store.similarity_search(invoice_text, k=top_k)
        context_snippets = [doc.page_content.strip() for doc in retrieved_docs]
        context_text = "\n\n".join(context_snippets)

        rag_prompt = (
            f"You have the following validated invoice examples:\n"
            f"{context_text}\n\n"
            f"Now, here is a NEW invoice text:\n"
            f"{invoice_text}\n\n"
            f"{self.base_prompt}"
        )
        return rag_prompt

    def store_invoice_context(self, invoice_text, extracted_fields):
        """
        Store the final validated invoice in the vector DB so future invoices
        can learn from it. Combines raw text and final extracted fields into a chunk.
        """
        chunk = (
            "PAST VALIDATED INVOICE EXAMPLE:\n\n"
            f"Raw Invoice Text:\n{invoice_text}\n\n"
            "Extracted Fields:\n"
            f"{json.dumps(extracted_fields, indent=2)}\n"
        )
        self.vector_store.add_texts([chunk])
        self.vector_store.persist()

    def validate_invoice(self, file_path):
        """
        1. Extract text from the invoice.
        2. Use a simple heuristic to check if the text appears to be an invoice.
        3. Check for duplicates using the vector DB.
        4. Build a RAG prompt and invoke the LLM for extraction.
        5. Parse the JSON output.
        6. If valid, store the invoice in the DB.
        7. Return the validation result.
        """
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

            invoice_text = self.extract_text(file_path)
            if not invoice_text or invoice_text.startswith("Error reading"):
                validation_result["is_corrupted"] = True
                validation_result["anomalies"].append("File extraction error: " + invoice_text)
                return validation_result

            # Heuristic check for invoice keywords
            text_lower = invoice_text.lower()
            if not any(keyword in text_lower for keyword in self.INVOICE_KEYWORDS):
                validation_result["anomalies"].append("Document not recognized as invoice (keyword check).")
                return validation_result

            # Duplicate check
            try:
                results = self.vector_store.similarity_search_with_score(invoice_text, k=1)
                if results and results[0][1] < 0.2:
                    validation_result["is_duplicate"] = True
            except Exception as e:
                validation_result["anomalies"].append(f"Vector search error: {str(e)}")

            # Build RAG prompt and invoke LLM
            prompt_text = self.build_rag_prompt(invoice_text, top_k=2)
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
                validation_result["extracted_fields"] = parsed_result.get("extracted_fields", {})
            except Exception as parse_error:
                validation_result["anomalies"].append(f"Failed to parse JSON: {str(parse_error)}")

            # Store the invoice if it was recognized as valid
            if validation_result["is_valid_format"]:
                try:
                    self.store_invoice_context(invoice_text, validation_result["extracted_fields"])
                except Exception as e:
                    validation_result["anomalies"].append(f"Failed to store invoice in DB: {str(e)}")

        except Exception as e:
            validation_result["anomalies"].append(str(e))

        return validation_result


# -------------- SUBCLASSES FOR FILE EXTRACTION --------------

class PDFValidator(InvoiceValidator):
    def extract_text(self, file_path):
        """Extract text from PDF (PyMuPDF). If no text, fallback to OCR."""
        try:
            doc = pymupdf.open(file_path)
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
            return text.strip() if text.strip() else "No readable text found in PDF."
        except Exception as e:
            return f"Error reading PDF: {str(e)}"


class CSVValidator(InvoiceValidator):
    def extract_text(self, file_path):
        """Extract text from CSV by reading into a pandas DataFrame, then converting to string."""
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
            text = pytesseract.image_to_string(img)
            return text.strip() if text.strip() else "No readable text found in image."
        except Exception as e:
            return f"Error reading image: {str(e)}"


def get_validator(file_ext):
    """Return the appropriate validator based on file extension."""
    if file_ext == "pdf":
        return PDFValidator()
    elif file_ext == "csv":
        return CSVValidator()
    elif file_ext == "xml":
        return XMLValidator()
    elif file_ext in ["png", "jpg", "jpeg"]:
        return ImageValidator()
    else:
        return None


# ------------------ STREAMLIT APP ------------------

def main():
    st.set_page_config(layout="wide")
    st.title("Invoice Validation System (RAG Powered)")

    uploaded_file = st.file_uploader(
        "Upload Invoice (PDF/CSV/XML/Image)",
        type=["pdf", "csv", "xml", "png", "jpg", "jpeg"]
    )
    if uploaded_file:
        file_ext = uploaded_file.name.split(".")[-1].lower()

        with tempfile.NamedTemporaryFile(delete=False, suffix=f".{file_ext}") as tmp_file:
            tmp_file.write(uploaded_file.getvalue())
            tmp_path = tmp_file.name

        validator = get_validator(file_ext)
        if validator is None:
            st.error("Unsupported file format")
            return

        with st.spinner("Validating invoice..."):
            result = validator.validate_invoice(tmp_path)

        os.unlink(tmp_path)

        # Print JSON result to terminal for debugging
        print(json.dumps(result, indent=2))

        # Display results in Streamlit
        st.subheader("Validation Results")
        col1, col2, col3 = st.columns(3)
        col1.metric("Valid Format", "✅" if result["is_valid_format"] else "❌")
        col2.metric("File Status", "Corrupted" if result["is_corrupted"] else "OK")
        col3.metric("Duplicate", "Yes" if result["is_duplicate"] else "No")

        st.subheader("Extracted Fields")
        extracted_fields = result.get("extracted_fields", {})
        if extracted_fields:
            # Separate main fields from line items
            line_items = extracted_fields.pop("line_items", [])
            if extracted_fields:
                df_main = pd.DataFrame([extracted_fields])
                st.write("**Main Invoice Fields**")
                st.dataframe(df_main, use_container_width=True)
            else:
                st.write("No main fields extracted.")
            if isinstance(line_items, list) and line_items:
                st.write("**Line Items**")
                df_items = pd.DataFrame(line_items)
                st.dataframe(df_items, use_container_width=True)
            else:
                st.write("No line items extracted.")
        else:
            st.write("No fields extracted.")

        if result.get("missing_fields"):
            st.error("Missing fields: " + ", ".join(result["missing_fields"]))

        if result.get("anomalies"):
            st.warning("Anomalies detected:")
            for anomaly in result["anomalies"]:
                st.write("- " + anomaly)


if __name__ == "__main__":
    main()
