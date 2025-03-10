from langchain.chains.retrieval import create_retrieval_chain
from langchain.prompts import (
    ChatPromptTemplate,
    SystemMessagePromptTemplate,
    HumanMessagePromptTemplate,
)
from langchain_openai import ChatOpenAI
from langchain_community.utilities import SQLDatabase
from langchain.chains.sql_database.query import create_sql_query_chain
from utils.vector_stores import invoice_vectorstore, po_vectorstore
from langchain_core.output_parsers import StrOutputParser
from utils.db import DatabaseManager
# src/chatbot.py

def get_chatbot_response(query: str) -> dict:
    """
    Given a user query, this function:
      1. Uses vector retrieval (for invoice & PO docs),
      2. Queries your SQLite database via a SQL chain,
      3. Combines the 3 answers into a single plain-text answer.
      4. Identifies discrepancies between PO and invoice details.
    
    Returns a dictionary with only one key: {"answer": <unified string>} or an error message if something goes wrong.
    """

    if query.strip().lower() in {"hi", "hello", "hey"}:
        return {"answer": "Hello! How can I help you with your invoices and purchase orders today?"}

    llm = ChatOpenAI(model_name="gpt-4o", temperature=0)

    # 1) Vector Retrieval Chains
    system_msg = SystemMessagePromptTemplate.from_template(
        "You have full access to invoice and PO documents. Retrieve matching invoice and PO number, analyze discrepancies, and generate a detailed discrepancy report."
    )
    human_msg = HumanMessagePromptTemplate.from_template(
        "Context: {context}\n\nQuestion: {input}"
    )
    vector_prompt = ChatPromptTemplate.from_messages([system_msg, human_msg])
    combine_docs_chain = vector_prompt | llm

    invoice_retriever = invoice_vectorstore.as_retriever(search_kwargs={"k": 1})
    po_retriever = po_vectorstore.as_retriever(search_kwargs={"k": 1})

    invoice_chain = create_retrieval_chain(retriever=invoice_retriever, combine_docs_chain=combine_docs_chain)
    po_chain = create_retrieval_chain(retriever=po_retriever, combine_docs_chain=combine_docs_chain)

    invoice_vec_result = invoice_chain.invoke({"input": query})
    po_vec_result = po_chain.invoke({"input": query})

    invoice_text = invoice_vec_result.get("text", "").strip()
    po_text = po_vec_result.get("text", "").strip()

    # 2) SQL Query Chain
    db = DatabaseManager()

    # Debugging the database retrieval
    print(f"Retrieving invoice by PO: {query}")
    invoice_by_po = db.get_invoice_by_po(query)
    print(f"Invoice by PO: {invoice_by_po}")  # Add debug print
    
    print(f"Retrieving PO by number: {query}")
    po_by_number = db.get_purchase_order_by_number(query)
    print(f"PO by number: {po_by_number}")  # Add debug print

    # Check if the queries return data
    if not invoice_by_po:
        print("No invoice data found.")
    if not po_by_number:
        print("No purchase order data found.")

    sql_text = ""
    if invoice_by_po:
        sql_text += f"Found invoice with PO number {query}: {invoice_by_po}\n"
    if po_by_number:
        sql_text += f"Found PO number {query}: {po_by_number}\n"

    # 3) Construct Discrepancy Report
    discrepancies = []

    # Compare PO and Invoice data for discrepancies
    if po_by_number.get("total_amount") != invoice_by_po.get("total_amount"):
        discrepancies.append(f"Total Amount mismatch: PO has {po_by_number.get('total_amount')}, but invoice has {invoice_by_po.get('total_amount')}.")

    if po_by_number.get("quantity") != invoice_by_po.get("quantity"):
        discrepancies.append(f"Quantity mismatch: PO has {po_by_number.get('quantity')}, but invoice has {invoice_by_po.get('quantity')}.")

    severity = "High" if discrepancies else "Low"
    next_steps = [
        "Conduct a detailed review of the invoice and purchase order (PO) documents to identify any missing or incorrect information.",
        "Cross-verify the SQL database entries with the invoice and PO details to ensure data consistency.",
        "Contact the vendor to clarify any discrepancies found between the invoice and PO.",
        "Implement a temporary hold on payment processing until discrepancies are resolved.",
        "Schedule a meeting with the procurement and accounts payable teams to discuss findings and preventive measures."
    ]

    detailed_breakdown = "\n".join(discrepancies) if discrepancies else "No discrepancies found."

    # Constructing the plain-text table
    table = f"""
    Invoice Details:
    - Invoice ID: {invoice_by_po.get('invoice_id', 'N/A')}
    - Supplier: {invoice_by_po.get('supplier', 'N/A')}
    - PO Number: {invoice_by_po.get('po_number', 'N/A')}
    - Total Amount: {invoice_by_po.get('total_amount', 'N/A')}
    - Quantity: {invoice_by_po.get('quantity', 'N/A')}

    Discrepancy Analysis:
    {detailed_breakdown}

    Severity: {severity}

    Next Steps:
    1. {next_steps[0]}
    2. {next_steps[1]}
    3. {next_steps[2]}
    4. {next_steps[3]}
    5. {next_steps[4]}

    Detailed Breakdown:
    -------------------------------------------------
    | Description   | Invoice Value  | PO Value      | Match Status |
    -------------------------------------------------
    | Total Amount  | {invoice_by_po.get('total_amount', 'N/A')} | {po_by_number.get('total_amount', 'N/A')} | {'Match' if invoice_by_po.get('total_amount') == po_by_number.get('total_amount') else 'Mismatch'} |
    | Quantity      | {invoice_by_po.get('quantity', 'N/A')} | {po_by_number.get('quantity', 'N/A')} | {'Match' if invoice_by_po.get('quantity') == po_by_number.get('quantity') else 'Mismatch'} |
    -------------------------------------------------
    """

    return {"answer": table.strip()}
