# Invoice Validator Project

This project validates invoices using a LangChain-based, Retrieval-Augmented Generation (RAG) approach.  
It supports multiple file types (PDF, CSV, XML, PNG/JPG images), uses Tesseract OCR as a fallback, and stores validated invoices in a vector database (Chroma) for duplication checking and context retrieval.

## Setup

1. Create a virtual environment and install dependencies:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows use: venv\Scripts\activate
   pip install -r requirements.txt
