# src/core/chatbot.py

import re
import json
import streamlit as st
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
    """
    Classify the query into one of:
      - "discrepancy": for queries about mismatches,
      - "missing": for queries about missing mandatory fields,
      - "email": for drafting an email response,
      - "details": for a request for full details.
    """
    q = query.lower()
    if "draft" in q and "email" in q:
        return "email"
    if any(word in q for word in ["discrepancy", "mismatch", "difference"]):
        return "discrepancy"
    elif "missing" in q:
        return "missing"
    else:
        return "details"

def format_invoice_details(invoice_record: dict, invoice_line_items: list) -> str:
    """
    Build a plain-text summary of invoice-level fields (only including those that have data)
    and a markdown-formatted table for its line items.
    """
    summary_lines = []
    if invoice_record.get("invoice_number"):
        summary_lines.append(f"Invoice Number: {invoice_record.get('invoice_number')}")
    if invoice_record.get("invoice_date"):
        summary_lines.append(f"Invoice Date: {invoice_record.get('invoice_date')}")
    if invoice_record.get("total_amount"):
        summary_lines.append(f"Total Amount: {invoice_record.get('total_amount')}")
    if invoice_record.get("invoice_to"):
        summary_lines.append(f"Invoice To: {invoice_record.get('invoice_to')}")
    if invoice_record.get("email"):
        summary_lines.append(f"Email: {invoice_record.get('email')}")
    if invoice_record.get("phone_number"):
        summary_lines.append(f"Phone Number: {invoice_record.get('phone_number')}")
    summary = "\n\n".join(summary_lines)
    
    header = "| Description | Quantity | Unit Price | Amount |\n| --- | --- | --- | --- |\n"
    rows = []
    if invoice_line_items:
        for item in invoice_line_items:
            rows.append(
                f"| {item.get('description', 'N/A')} | {item.get('quantity', 'N/A')} | {item.get('unit_price', 'N/A')} | {item.get('amount', 'N/A')} |"
            )
    else:
        rows.append("| No line items found |")
    table = header + "\n".join(rows)
    return summary + "\n\n" + "**Line Items:**\n" + table

def format_po_details(po_record: dict, po_line_items: list) -> str:
    """
    Build a plain-text summary of PO-level fields (only including those that have data)
    and a markdown-formatted table for its line items.
    """
    summary_lines = []
    if po_record.get("po_number"):
        summary_lines.append(f"PO Number: {po_record.get('po_number')}")
    if po_record.get("po_date"):
        summary_lines.append(f"PO Date: {po_record.get('po_date')}")
    if po_record.get("total"):
        summary_lines.append(f"Total: {po_record.get('total')}")
    if po_record.get("supplier_name"):
        summary_lines.append(f"Supplier: {po_record.get('supplier_name')}")
    if po_record.get("billing_address"):
        summary_lines.append(f"Billing Address: {po_record.get('billing_address')}")
    if po_record.get("shipping_address"):
        summary_lines.append(f"Shipping Address: {po_record.get('shipping_address')}")
    summary = "\n\n".join(summary_lines)
    
    header = "| Description | Quantity | Unit Price | Amount |\n| --- | --- | --- | --- |\n"
    rows = []
    if po_line_items:
        for item in po_line_items:
            rows.append(
                f"| {item.get('description', 'N/A')} | {item.get('quantity', 'N/A')} | {item.get('unit_price', 'N/A')} | {item.get('amount', 'N/A')} |"
            )
    else:
        rows.append("| No line items found |")
    table = header + "\n".join(rows)
    return summary + "\n\n" + "**Line Items:**\n" + table

def get_chatbot_response(query: str) -> dict:
    """
    1) Uses vector retrieval (for optional context) and direct SQLite queries (via DatabaseManager)
       to produce a unified answer.
    2) The answer is tailored based on the query type:
         - "discrepancy": compares totals and line-item quantities.
         - "missing": identifies missing mandatory fields.
         - "email": drafts an email response using full details.
         - "details": returns a plain-text summary of main fields plus a markdown table for line items,
                      then asks if the user would like a draft email.
    3) Returns a dict {"answer": <final unified text>} for display.
    """
    # --- Guardrail ---
    if not any(term in query.lower() for term in ["invoice", "po", "purchase order"]):
        return {"answer": "Please ask a question related to invoices or purchase orders."}
    if query.strip().lower() in {"hi", "hello", "hey"}:
        return {"answer": "Hello! How can I help you with your invoices and purchase orders today?"}

    # --- Step 1: Extract invoice and PO references ---
    invoice_number = None
    inv_match = re.search(r"(?:invoice\s*(?:number)?[:#]?\s*)(\d+)", query, re.IGNORECASE)
    if inv_match:
        invoice_number = inv_match.group(1)
    po_number = None
    # Updated regex to catch various PO formats
    po_match = re.search(r"(?:po(?:\s*number)?[:\s\-]*)([\d\w]+)", query, re.IGNORECASE)
    if not po_match:
        po_match = re.search(r"(?:purchase\s+order(?:\s*number)?[:\s\-]*)([\d\w]+)", query, re.IGNORECASE)
    if po_match:
        po_number = po_match.group(1)
    print(f"[DEBUG] Extracted Invoice Number: {invoice_number}")
    print(f"[DEBUG] Extracted PO Number: {po_number}")

    # --- Step 2: Optional vector retrieval for context (context used internally only) ---
    llm = ChatOpenAI(model_name="gpt-4o", temperature=0)
    system_msg = SystemMessagePromptTemplate.from_template(
        "You are an expert financial assistant with access to invoice and PO documents. "
        "You are also skilled at drafting email responses based on document details. "
        "Use any retrieved context internally to inform your answer, but do not reveal raw document text."
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
    # Prime chains (context used internally)
    invoice_chain.invoke({"input": query})
    po_chain.invoke({"input": query})

    # --- Step 3: Retrieve records from session state (if available) or DB ---
    db = DatabaseManager()
    invoice_record = {}
    po_record = {}
    # Assume that your main app keeps a session dictionary of uploaded records:
    invoice_records = st.session_state.get("invoice_records", {})
    po_records = st.session_state.get("po_records", {})

    if invoice_number and invoice_number in invoice_records:
        invoice_record = invoice_records[invoice_number]
        print(f"[DEBUG] Retrieved invoice from session state: {invoice_record}")
    if po_number and po_number in po_records:
        po_record = po_records[po_number]
        print(f"[DEBUG] Retrieved PO from session state: {po_record}")

    if not invoice_record and invoice_number:
        invoice_record = db.get_invoice_by_number(invoice_number)
        print(f"[DEBUG] Retrieved invoice from DB: {invoice_record}")
    if not po_record and po_number:
        po_record = db.get_purchase_order_by_number(po_number)
        print(f"[DEBUG] Retrieved PO from DB: {po_record}")

    if not invoice_record and not po_record:
        return {"answer": "No matching invoice or purchase order data found in the database. Please check your reference."}

    invoice_line_items = []
    if invoice_record and "id" in invoice_record:
        invoice_line_items = db.get_invoice_line_items(invoice_record["id"])
        print(f"[DEBUG] Invoice line items: {invoice_line_items}")
    po_line_items = []
    if po_record and "id" in po_record:
        po_line_items = db.get_purchase_order_line_items(po_record["id"])
        print(f"[DEBUG] PO line items: {po_line_items}")

    # --- Step 4: Determine query type ---
    query_type = determine_query_type(query)
    print(f"[DEBUG] Determined query type: {query_type}")

    # --- Step 5: Build unified answer based on query type ---
    if query_type == "discrepancy":
        discrepancies = []
        inv_total = invoice_record.get("total_amount", "N/A") if invoice_record else "N/A"
        po_total = po_record.get("total", "N/A") if po_record else "N/A"
        if invoice_record and po_record and inv_total != po_total and inv_total != "N/A" and po_total != "N/A":
            discrepancies.append(f"Total amount mismatch: Invoice total is {inv_total} vs. PO total is {po_total}.")
        def sum_quantities(items):
            total = 0.0
            for it in items:
                try:
                    total += float(it.get("quantity", 0))
                except:
                    pass
            return total
        inv_qty = sum_quantities(invoice_line_items)
        po_qty = sum_quantities(po_line_items)
        if invoice_record and po_record and inv_qty and po_qty and inv_qty != po_qty:
            discrepancies.append(f"Line item quantity mismatch: Invoice total qty is {inv_qty}, PO total qty is {po_qty}.")
        discrepancy_text = "\n".join(discrepancies) if discrepancies else "No discrepancies found."
        final_answer = (
            f"**Invoice Details:**\n"
            f"- Invoice Number: {invoice_record.get('invoice_number', 'N/A')}\n"
            f"- Invoice Date: {invoice_record.get('invoice_date', 'N/A')}\n"
            f"- Total Amount: {invoice_record.get('total_amount', 'N/A')}\n"
            f"- Invoice To: {invoice_record.get('invoice_to', 'N/A')}\n"
            f"- Email: {invoice_record.get('email', 'N/A')}\n"
            f"- Phone: {invoice_record.get('phone_number', 'N/A')}\n\n"
            f"**Purchase Order Details:**\n"
            f"- PO Number: {po_record.get('po_number', 'N/A')}\n"
            f"- PO Date: {po_record.get('po_date', 'N/A')}\n"
            f"- Total: {po_record.get('total', 'N/A')}\n\n"
            f"**Discrepancy Analysis:**\n{discrepancy_text}"
        )
        return {"answer": final_answer}

    elif query_type == "missing":
        missing_fields = []
        for field in ["invoice_number", "invoice_date", "total_amount"]:
            val = invoice_record.get(field, "").strip() if invoice_record.get(field) else ""
            if not val:
                missing_fields.append(field)
        if missing_fields:
            return {"answer": f"The following mandatory fields appear to be missing in the invoice: {', '.join(missing_fields)}."}
        else:
            return {"answer": "No missing mandatory fields detected in the invoice."}

    elif query_type == "email":
        # For email drafting, use the detailed info for the relevant record.
        # Determine whether the query is about an invoice or a PO.
        if invoice_record and ("invoice" in query.lower() or not po_record):
            details = format_invoice_details(invoice_record, invoice_line_items)
            email_body = (
                f"Dear {invoice_record.get('invoice_to', 'Customer')},\n\n"
                f"Regarding your invoice {invoice_record.get('invoice_number', 'N/A')} dated {invoice_record.get('invoice_date', 'N/A')},\n"
                f"we have reviewed the following details:\n\n"
                f"{details}\n\n"
                "Please review these details and let us know if any corrections are required.\n\n"
                "Best regards,\n"
                "Finance Team"
            )
            return {"answer": email_body}
        elif po_record and ("po" in query.lower()):
            details = format_po_details(po_record, po_line_items)
            email_body = (
                f"Dear {po_record.get('supplier_name', 'Vendor')},\n\n"
                f"Regarding your purchase order {po_record.get('po_number', 'N/A')} dated {po_record.get('po_date', 'N/A')},\n"
                f"we have reviewed the following details:\n\n"
                f"{details}\n\n"
                "Please review these details and let us know if any corrections are required.\n\n"
                "Best regards,\n"
                "Finance Team"
            )
            return {"answer": email_body}
        elif invoice_record:
            details = format_invoice_details(invoice_record, invoice_line_items)
            email_body = (
                f"Dear {invoice_record.get('invoice_to', 'Customer')},\n\n"
                f"Regarding your invoice {invoice_record.get('invoice_number', 'N/A')} dated {invoice_record.get('invoice_date', 'N/A')},\n"
                f"we have reviewed the following details:\n\n"
                f"{details}\n\n"
                "Please review these details and let us know if any corrections are required.\n\n"
                "Best regards,\n"
                "Finance Team"
            )
            return {"answer": email_body}
        else:
            return {"answer": "No invoice or purchase order record available for drafting an email."}

    else:  # query_type == "details"
        # If the query is about details, show full information in a plain-text summary and a markdown table.
        if invoice_record:
            summary = "Invoice Details\n\n"
            if invoice_record.get("invoice_number"):
                summary += f"Invoice Number: {invoice_record.get('invoice_number')}\n\n"
            if invoice_record.get("invoice_date"):
                summary += f"Invoice Date: {invoice_record.get('invoice_date')}\n\n"
            if invoice_record.get("total_amount"):
                summary += f"Total Amount: {invoice_record.get('total_amount')}\n\n"
            if invoice_record.get("invoice_to"):
                summary += f"Invoice To: {invoice_record.get('invoice_to')}\n\n"
            if invoice_record.get("email"):
                summary += f"Email: {invoice_record.get('email')}\n\n"
            if invoice_record.get("phone_number"):
                summary += f"Phone Number: {invoice_record.get('phone_number')}\n\n"
            details_table = ""
            header = "| Description | Quantity | Unit Price | Amount |\n| --- | --- | --- | --- |\n"
            rows = []
            if invoice_line_items:
                for item in invoice_line_items:
                    rows.append(
                        f"| {item.get('description', 'N/A')} | {item.get('quantity', 'N/A')} | {item.get('unit_price', 'N/A')} | {item.get('amount', 'N/A')} |"
                    )
            else:
                rows.append("| No line items found |")
            details_table = header + "\n".join(rows)
            email_prompt = "\n\nWould you like me to draft an email response regarding these details? (Reply with 'draft email invoice [invoice number]' to request a draft.)"
            final_answer = summary + "\n" + "**Line Items:**\n" + details_table + email_prompt
            return {"answer": final_answer}
        elif po_record:
            summary = "Purchase Order Details\n\n"
            if po_record.get("po_number"):
                summary += f"PO Number: {po_record.get('po_number')}\n\n"
            if po_record.get("po_date"):
                summary += f"PO Date: {po_record.get('po_date')}\n\n"
            if po_record.get("total"):
                summary += f"Total: {po_record.get('total')}\n\n"
            if po_record.get("supplier_name"):
                summary += f"Supplier: {po_record.get('supplier_name')}\n\n"
            if po_record.get("billing_address"):
                summary += f"Billing Address: {po_record.get('billing_address')}\n\n"
            if po_record.get("shipping_address"):
                summary += f"Shipping Address: {po_record.get('shipping_address')}\n\n"
            details_table = ""
            header = "| Description | Quantity | Unit Price | Amount |\n| --- | --- | --- | --- |\n"
            rows = []
            if po_line_items:
                for item in po_line_items:
                    rows.append(
                        f"| {item.get('description', 'N/A')} | {item.get('quantity', 'N/A')} | {item.get('unit_price', 'N/A')} | {item.get('amount', 'N/A')} |"
                    )
            else:
                rows.append("| No line items found |")
            details_table = header + "\n".join(rows)
            email_prompt = "\n\nWould you like me to draft an email response regarding these details? (Reply with 'draft email po [PO number]' to request a draft.)"
            final_answer = summary + "\n" + "**Line Items:**\n" + details_table + email_prompt
            return {"answer": final_answer}
        else:
            return {"answer": "No matching invoice or purchase order data found."}
