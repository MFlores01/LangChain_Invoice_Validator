import hashlib
import json
from abc import ABC, abstractmethod
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from utils.db import DatabaseManager  
from utils.vector_stores import invoice_vectorstore  # Import centralized vector store

INVOICE_KEYWORDS = [
    "invoice", "bill", "supplier", "due", "tax", "vat", "subtotal", "total",
    "line item", "payment", "amount", "qty", "balance", "remit"
]

db_manager = DatabaseManager()

class InvoiceValidator(ABC):
    """
    Abstract base class for invoice validation using an LLM and a centralized vector store.
    Uses a Retrieval Augmented Generation (RAG) approach to:
      - Retrieve previously validated invoices for context.
      - Store new invoices for future reference.
    """

    # Define mandatory fields (if missing, set to "N/A") and optional fields (if missing, omit)
    MANDATORY_FIELDS = [
        "invoice_number",
        "invoice_date",
        "total_amount",
        "line_items"
    ]
    OPTIONAL_FIELDS = [
        "due_date",
        "invoice_to",
        "supplier_name",
        "billing_address",
        "shipping_address",
        "discount",
        "tax_vat",
        "email",
        "phone_number"
    ]

    def __init__(self):
        self.llm = ChatOpenAI(temperature=0)
        self.embeddings = OpenAIEmbeddings()
        # Use the centralized invoice vector store
        self.vector_store = invoice_vectorstore

        # Updated prompt: Use the same field titles for both Invoice and PO.
        self.base_prompt = (
            "First, determine if this text is actually an invoice. If not, respond with:\n\n"
            "{\n"
            "  \"validation\": { \"valid_format\": false, \"missing_fields\": [], \"anomalies\": [\"Document not recognized as invoice\"] },\n"
            "  \"extracted_fields\": {}\n"
            "}\n\n"
            "If it IS an invoice, extract and validate the following fields. For mandatory fields, if not found, set them to 'N/A'. For optional fields, if not found, omit them entirely:\n\n"
            "Mandatory fields:\n"
            "1. invoice_number\n"
            "2. invoice_date\n"
            "3. total_amount\n"
            "4. line_items: an array of objects, each with exactly these keys: {\"description\", \"quantity\", \"unit_price\", \"amount\"}.\n\n"
            "Optional fields:\n"
            "5. due_date\n"
            "6. invoice_to (only the person's name)\n"
            "7. supplier_name\n"
            "8. billing_address\n"
            "9. shipping_address\n"
            "10. discount\n"
            "11. tax_vat\n"
            "12. email\n"
            "13. phone_number\n\n"
            "Handle synonyms (e.g., 'bill to' should map to billing_address, 'ship to' to shipping_address, "
            "'vendor address' to supplier_name, etc.).\n\n"
            "Return a valid JSON object with exactly two keys:\n"
            "\"validation\": { \"valid_format\": bool, \"missing_fields\": [], \"anomalies\": [] },\n"
            "\"extracted_fields\": { ...all fields above... }\n\n"
            "Your output must be valid JSON only, with no extra text."
        )

    @abstractmethod
    def extract_text(self, file_path):
        """Extract text from the file (to be implemented by subclasses)."""
        pass

    def build_rag_prompt(self, invoice_text, top_k=2):
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
        chunk = (
            "PAST VALIDATED INVOICE EXAMPLE:\n\n"
            f"Raw Invoice Text:\n{invoice_text}\n\n"
            "Extracted Fields:\n"
            f"{json.dumps(extracted_fields, indent=2)}\n"
        )
        self.vector_store.add_texts([chunk])
        self.vector_store.persist()

    def validate_invoice(self, file_path):
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

            # Check duplicates using dedicated method
            if db_manager.check_duplicate_invoice(file_hash):
                validation_result["is_duplicate"] = True
                validation_result["anomalies"].append("Duplicate invoice detected.")

            invoice_text = self.extract_text(file_path)
            if not invoice_text or invoice_text.startswith("Error reading"):
                validation_result["is_corrupted"] = True
                validation_result["anomalies"].append("File extraction error: " + invoice_text)
                return validation_result

            text_lower = invoice_text.lower()
            if not any(keyword in text_lower for keyword in INVOICE_KEYWORDS):
                validation_result["anomalies"].append("Document not recognized as invoice (keyword check).")
                return validation_result

            try:
                results = self.vector_store.similarity_search_with_score(invoice_text, k=1)
                if results and results[0][1] < 0.2:
                    validation_result["is_duplicate"] = True
            except Exception as e:
                validation_result["anomalies"].append(f"Vector search error: {str(e)}")

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
                extracted = parsed_result.get("extracted_fields", {})

                final_fields = {}
                for field in self.MANDATORY_FIELDS:
                    final_fields[field] = extracted.get(field, "N/A")
                for field in self.OPTIONAL_FIELDS:
                    if field in extracted:
                        final_fields[field] = extracted[field]
                validation_result["extracted_fields"] = final_fields

            except Exception as parse_error:
                validation_result["anomalies"].append(f"Failed to parse JSON: {str(parse_error)}")

            if validation_result["is_valid_format"]:
                try:
                    self.store_invoice_context(invoice_text, validation_result["extracted_fields"])
                    if not validation_result["is_duplicate"]:
                        db_manager.store_invoice(file_hash, validation_result["extracted_fields"])
                except Exception as e:
                    validation_result["anomalies"].append(f"Failed to store invoice in DB: {str(e)}")
        except Exception as e:
            validation_result["anomalies"].append(str(e))
        return validation_result
