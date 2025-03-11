# src/core/chatbot.py

import re
import json
from langchain.chains.retrieval import create_retrieval_chain
from langchain.prompts import (
    ChatPromptTemplate,
    SystemMessagePromptTemplate,
    HumanMessagePromptTemplate,
)
from langchain_openai import ChatOpenAI
from utils.vector_stores import invoice_vectorstore, po_vectorstore
from utils.db import DatabaseManager

def determine_query_type(query: str) -> str:
    """Classify query into 'discrepancy', 'missing', or 'details' based on keywords."""
    q = query.lower()
    if any(word in q for word in ["discrepancy", "mismatch", "difference"]):
        return "discrepancy"
    elif "missing" in q:
        return "missing"
    else:
        return "details"

def get_chatbot_response(query: str) -> dict:
    """
    This function uses vector retrieval (for context) and direct SQLite queries (partial match)
    to return a single 'answer' string with either a discrepancy analysis, missing fields,
    or a markdown table of details.
    """

    # --- Guardrail: Must mention invoice or purchase order in the question ---
    if not any(term in query.lower() for term in ["invoice", "po", "purchase order"]):
        return {"answer": "Please ask a question related to invoices or purchase orders."}

    # --- Simple greeting ---
    if query.strip().lower() in {"hi", "hello", "hey"}:
        return {"answer": "Hello! How can I help you with your invoices and purchase orders today?"}

    # --- Step 1: Extract possible invoice/PO references from the query ---

    # Attempt to capture invoice number if user typed e.g. "invoice 1001329" or "invoice number: 1001329"
    invoice_number = None
    inv_match = re.search(r"(?:invoice\s*(?:number)?[:#]?\s*)(\d+)", query, re.IGNORECASE)
    if inv_match:
        invoice_number = inv_match.group(1)
    # Attempt to capture PO reference if user typed e.g. "po 1001329" or "po-1001329" or "purchase order 1001329"
    po_number = None
    # First try "po-xxxx"
    po_match = re.search(r"(?:po[-\s]+)([\d\w-]+)", query, re.IGNORECASE)
    if not po_match:
        # If that didn't match, try "purchase order 1234"
        po_match = re.search(r"(?:purchase\s+order\s+)([\d\w-]+)", query, re.IGNORECASE)
    if po_match:
        po_number = po_match.group(1)

    print(f"[DEBUG] Extracted Invoice Number: {invoice_number}")
    print(f"[DEBUG] Extracted PO Number: {po_number}")

    # --- Step 2: Vector retrieval for context (optional, not displayed verbatim) ---
    llm = ChatOpenAI(model_name="gpt-4o", temperature=0)
    system_msg = SystemMessagePromptTemplate.from_template(
        "You are an expert financial assistant with access to invoice and PO documents. "
        "Use any retrieved context internally to help answer the user's query, but do not output large verbatim excerpts."
    )
    human_msg = HumanMessagePromptTemplate.from_template(
        "Context: {context}\n\nUser Query: {input}"
    )
    vector_prompt = ChatPromptTemplate.from_messages([system_msg, human_msg])
    combine_docs_chain = vector_prompt | llm

    invoice_retriever = invoice_vectorstore.as_retriever(search_kwargs={"k": 1})
    po_retriever = po_vectorstore.as_retriever(search_kwargs={"k": 1})

    invoice_chain = create_retrieval_chain(retriever=invoice_retriever, combine_docs_chain=combine_docs_chain)
    po_chain = create_retrieval_chain(retriever=po_retriever, combine_docs_chain=combine_docs_chain)

    invoice_chain.invoke({"input": query})
    po_chain.invoke({"input": query})

    # --- Step 3: Retrieve records from DB (using partial match) ---
    db = DatabaseManager()

    invoice_record = {}
    po_record = {}

    # If user gave something that looks like an invoice number:
    if invoice_number:
        invoice_record = db.get_invoice_by_number(invoice_number)
        print(f"[DEBUG] Retrieved invoice by partial match: {invoice_record}")

    # If user gave something that looks like a PO reference:
    if po_number:
        po_record = db.get_purchase_order_by_number(po_number)
        print(f"[DEBUG] Retrieved PO by partial match: {po_record}")

    # If we still have no records, let's see if user typed "invoice #1001329" but also typed "PO # 1001329"
    # or they typed a partial. If no record found at all, fallback.
    if not invoice_record and not po_record:
        return {"answer": "No matching invoice or purchase order data found in the database. Please check the reference."}

    # --- Step 4: Retrieve line items if we found a record ---
    invoice_line_items = []
    if invoice_record and "id" in invoice_record:
        invoice_line_items = db.get_invoice_line_items(invoice_record["id"])
        print(f"[DEBUG] Invoice line items: {invoice_line_items}")

    po_line_items = []
    if po_record and "id" in po_record:
        po_line_items = db.get_purchase_order_line_items(po_record["id"])
        print(f"[DEBUG] PO line items: {po_line_items}")

    # --- Step 5: Determine the user's query type (discrepancy, missing, details) ---
    query_type = determine_query_type(query)

    # --- Step 6: Build the unified answer ---
    if query_type == "discrepancy":
        # Build discrepancy analysis if we have both invoice and PO
        # or if we only have invoice or only have PO, we just mention no mismatch possible
        discrepancies = []
        inv_total = invoice_record.get("total_amount", "N/A") if invoice_record else "N/A"
        po_total = po_record.get("total", "N/A") if po_record else "N/A"
        if invoice_record and po_record and inv_total != po_total and inv_total != "N/A" and po_total != "N/A":
            discrepancies.append(f"Total amount mismatch: Invoice total is {inv_total} vs. PO total is {po_total}.")

        # Compare line item sums if both exist
        def sum_quantities(items):
            total_q = 0.0
            for it in items:
                try:
                    total_q += float(it.get("quantity", 0))
                except:
                    pass
            return total_q
        inv_qty = sum_quantities(invoice_line_items) if invoice_line_items else 0
        po_qty = sum_quantities(po_line_items) if po_line_items else 0
        if invoice_record and po_record and inv_qty and po_qty and inv_qty != po_qty:
            discrepancies.append(f"Line item quantity mismatch: Invoice total qty {inv_qty}, PO total qty {po_qty}.")

        severity = "High" if discrepancies else "Low"
        if not discrepancies:
            discrepancy_text = "No discrepancies found."
        else:
            discrepancy_text = "\n".join(discrepancies)

        next_steps = (
            "Please review these discrepancies and coordinate with the vendor or supplier. "
            "Adjust records as necessary."
            if discrepancies else
            "No discrepancies detected; no further action is required."
        )

        answer = (
            f"**Invoice Details:**\n"
            f"- Invoice Number: {invoice_record.get('invoice_number', 'N/A')}\n"
            f"- Supplier: {invoice_record.get('supplier_name', 'N/A')}\n"
            f"- Total Amount: {invoice_record.get('total_amount', 'N/A')}\n\n"
            f"**Purchase Order Details:**\n"
            f"- PO Number: {po_record.get('po_number', 'N/A')}\n"
            f"- Supplier: {po_record.get('supplier_name', 'N/A')}\n"
            f"- Total: {po_record.get('total', 'N/A')}\n\n"
            f"**Discrepancy Analysis:**\n{discrepancy_text}\n\n"
            f"**Severity:** {severity}\n\n"
            f"**Next Steps:** {next_steps}"
        )
        return {"answer": answer}

    elif query_type == "missing":
        # Check if invoice has missing mandatory fields
        missing_fields = []
        mandatory_fields = ["invoice_number", "invoice_date", "total_amount"]
        if invoice_record:
            for field in mandatory_fields:
                val = invoice_record.get(field, "").strip()
                if not val:
                    missing_fields.append(field)
            if missing_fields:
                return {
                    "answer": (
                        f"The following mandatory fields appear to be missing in the invoice record: "
                        f"{', '.join(missing_fields)}.\nPlease review the source document."
                    )
                }
            else:
                return {"answer": "No missing mandatory fields detected in the invoice record."}
        else:
            return {"answer": "No invoice record found to check missing fields."}

    else:
        # "details" query => show a markdown table for whichever record we found
        if invoice_record:
            # Build a markdown table for invoice
            header = (
                "| Description | Quantity | Unit Price | Amount | Invoice Number | Invoice Date | Total Amount | Invoice To | Email | Phone Number |\n"
                "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |\n"
            )
            rows = []
            if invoice_line_items:
                for item in invoice_line_items:
                    rows.append(
                        f"| {item.get('description', '')} | {item.get('quantity', '')} | {item.get('unit_price', '')} | {item.get('amount', '')} | "
                        f"{invoice_record.get('invoice_number', 'N/A')} | {invoice_record.get('invoice_date', 'N/A')} | {invoice_record.get('total_amount', 'N/A')} | "
                        f"{invoice_record.get('invoice_to', 'N/A')} | {invoice_record.get('email', 'N/A')} | {invoice_record.get('phone_number', 'N/A')} |"
                    )
            else:
                # If no line items, show a single row with just invoice-level data
                rows.append(
                    f"|  |  |  |  | {invoice_record.get('invoice_number', 'N/A')} | {invoice_record.get('invoice_date', 'N/A')} | "
                    f"{invoice_record.get('total_amount', 'N/A')} | {invoice_record.get('invoice_to', 'N/A')} | "
                    f"{invoice_record.get('email', 'N/A')} | {invoice_record.get('phone_number', 'N/A')} |"
                )
            table = header + "\n".join(rows)
            return {"answer": f"**Invoice Details:**\n\n{table}"}

        elif po_record:
            # Build a markdown table for PO
            header = (
                "| Description | Quantity | Unit Price | Amount | PO Number | PO Date | Total | Supplier Name | Billing Address | Shipping Address |\n"
                "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |\n"
            )
            rows = []
            if po_line_items:
                for item in po_line_items:
                    rows.append(
                        f"| {item.get('description', '')} | {item.get('quantity', '')} | {item.get('unit_price', '')} | {item.get('amount', '')} | "
                        f"{po_record.get('po_number', 'N/A')} | {po_record.get('po_date', 'N/A')} | {po_record.get('total', 'N/A')} | "
                        f"{po_record.get('supplier_name', 'N/A')} | {po_record.get('billing_address', 'N/A')} | {po_record.get('shipping_address', 'N/A')} |"
                    )
            else:
                # If no line items, show a single row with just PO-level data
                rows.append(
                    f"|  |  |  |  | {po_record.get('po_number', 'N/A')} | {po_record.get('po_date', 'N/A')} | "
                    f"{po_record.get('total', 'N/A')} | {po_record.get('supplier_name', 'N/A')} | "
                    f"{po_record.get('billing_address', 'N/A')} | {po_record.get('shipping_address', 'N/A')} |"
                )
            table = header + "\n".join(rows)
            return {"answer": f"**Purchase Order Details:**\n\n{table}"}

        else:
            # Should not happen if we found something
            return {"answer": "No matching invoice or PO data found."}
