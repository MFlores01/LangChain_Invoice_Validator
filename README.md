# **Invoice Validator** 🧾✅  

An AI-powered **invoice validation system** using **LangChain-based Retrieval-Augmented Generation (RAG)**.  
It supports **PDF, CSV, XML, PNG/JPG** invoices, uses **Tesseract OCR** for text extraction, and stores validated invoices in a **vector database (Chroma)** for duplication detection and context retrieval.  

## 🚀 **Features**  

- ✅ **Multi-format Support** – Processes invoices in **PDF, CSV, XML, and image formats**  
- 🧠 **AI-Powered Validation** – Uses **LangChain + RAG** for structured document validation  
- 🔍 **Field Extraction** – Extracts key invoice details (e.g., invoice number, date, total amount)  
- 🛑 **Duplicate & Corruption Detection** – Prevents duplicate invoices and verifies file integrity  
- 📜 **Tesseract OCR Integration** – Reads invoice text from scanned images  
- 📊 **Purchase Order (PO) Comparison** – Validates invoices **against purchase orders (POs)**  
- 📌 **Discrepancy Reporting** – Highlights mismatches between invoices and POs  

---

## ⚙️ How It Works  

### 1️⃣ Invoice Format Check  
✔ Ensures the invoice follows a **standard format** (PDF, XML, CSV, etc.).  

### 2️⃣ Field Validation  
✔ Extracts and verifies required fields:  
   - **Invoice Number**  
   - **Date**  
   - **Supplier Details**  
   - **Total Amount**  

### 3️⃣ Duplicate & Integrity Check  
✔ Ensures the file is **not corrupted** or **previously processed** using **ChromaDB**.  

### 4️⃣ PO-Invoice Comparison  
✔ Cross-checks **invoice details** against the **purchase order database** to detect discrepancies.  

### 5️⃣ Discrepancy Report  
✔ Generates a **report** highlighting **inconsistencies** between invoices and purchase orders.  

## 📂 Project Structure  

```plaintext
📦 Invoice_Validator
 ┣ 📂 invoice_db/                # Database for storing validated invoices
 ┣ 📂 po_db/                     # Database for storing purchase orders
 ┣ 📂 src/                        # Source code directory
 ┃ ┣ 📂 app/
 ┃ ┃ ┗ 📜 __init__.py              # App initialization
 ┃ ┃ ┗ 📜 streamlit_app.py         # Streamlit UI for invoice validation
 ┃ ┣ 📂 assets/
 ┃ ┃ ┗ 📜 logo.png                 # Project logo
 ┃ ┣ 📂 core/
 ┃ ┃ ┣ 📜 __init__.py              # Core module initialization
 ┃ ┃ ┣ 📜 chatbot.py               # AI-powered chatbot (if applicable)
 ┃ ┃ ┣ 📜 data_processor.py        # Handles invoice data extraction
 ┃ ┃ ┣ 📜 file_validator.py        # Validates file formats & structures
 ┃ ┃ ┣ 📜 po_comparator.py         # Compares invoices with purchase orders
 ┃ ┃ ┣ 📜 po_validation_engine.py  # Validates POs
 ┃ ┃ ┣ 📜 po_validator.py          # Purchase Order validation logic
 ┃ ┃ ┗ 📜 validation_engine.py     # Core validation logic for invoices
 ┃ ┣ 📂 styles/
 ┃ ┃ ┗ 📜 styles.py                # Custom styling for the UI
 ┃ ┣ 📂 utils/
 ┃ ┃ ┣ 📜 __init__.py              # Utility module initialization
 ┃ ┃ ┣ 📜 db.py                    # Database handling functions
 ┃ ┃ ┣ 📜 file_utils.py            # File handling utilities
 ┃ ┃ ┣ 📜 logger.py                # Logging setup and utilities
 ┃ ┃ ┗ 📜 vector_stores.py         # Handles vector database (ChromaDB)

 ┣ 📜 .env                        # Environment variables (API keys, DB configs)
 ┣ 📜 .gitignore                   # Files to be ignored by Git
 ┣ 📜 project.toml                 # Project metadata and dependencies
 ┣ 📜 README.md                    # Project documentation
 ┣ 📜 requirements.txt              # Required dependencies
 ┣ 📜 setup.py                      # Installation script
 ┣ 📜 try.py                        # Test script
```

## 📝 To-Do List  
✅ Add support for additional document formats  
✅ Implement real-time invoice verification via an API  
✅ Improve OCR accuracy with additional pre-processing  
✅ Expand discrepancy reporting with detailed insights  

## 🤝 Contributing  
Contributions are welcome! Follow these steps:  

1️⃣ **Fork** the repository  
2️⃣ **Create a new branch** (`feature/new-feature`)  
3️⃣ **Commit your changes**  
   ```bash
   git commit -m "Added new feature"
   ```
4️⃣ **Push to your branch**

## 📜 License
This project is licensed under the MIT License.

## 🛠️ **Setup**  
### **Create a Virtual Environment**  

   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```
1. Create a virtual environment and install dependencies:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows use: venv\Scripts\activate
   pip install -r requirements.txt
   ```
2. Run the app
   ```bash
   streamlit run src/app/streamlit_app.py
   ```
   
