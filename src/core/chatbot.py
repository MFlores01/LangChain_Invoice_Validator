# chatbot.py

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
def get_chatbot_response(query: str) -> dict:
    """
    Given a user query, this function:
      1. Uses vector retrieval (for invoice & PO docs),
      2. Queries your SQLite database via a SQL chain,
      3. Combines the 3 answers into a single plain-text answer.
    
    Returns a dictionary with only one key: {"answer": <unified string>}.
    """

    # If the user typed a simple greeting, return one greeting.
    if query.strip().lower() in {"hi", "hello", "hey"}:
        return {"answer": "Hello! How can I help you with your invoices and purchase orders today?"}

    # 1) Initialize the LLM (GPT-4o)
    llm = ChatOpenAI(model_name="gpt-4o", temperature=0)

    # 2) Vector Retrieval Chains
    #   - A prompt instructing the LLM to use the doc text internally, not verbatim
    system_msg = SystemMessagePromptTemplate.from_template(
        "You have full access to invoice and PO documents. Use them thoroughly, but do NOT reveal large excerpts. "
         "Return a concise plain-text answer."
    )
    human_msg = HumanMessagePromptTemplate.from_template(
        "Context: {context}\n\nQuestion: {input}"
    )
    vector_prompt = ChatPromptTemplate.from_messages([system_msg, human_msg])
    # Pipe operator for the chain
    combine_docs_chain = vector_prompt | llm

    # Retrievers from your centralized vector stores
    invoice_retriever = invoice_vectorstore.as_retriever(search_kwargs={"k": 1})
    po_retriever = po_vectorstore.as_retriever(search_kwargs={"k": 1})

    # Create retrieval chains
    invoice_chain = create_retrieval_chain(
        retriever=invoice_retriever,
        combine_docs_chain=combine_docs_chain
    )
    po_chain = create_retrieval_chain(
        retriever=po_retriever,
        combine_docs_chain=combine_docs_chain
    )

    # Run vector retrieval
    invoice_vec_result = invoice_chain.invoke({"input": query})
    po_vec_result = po_chain.invoke({"input": query})

    # Extract text answers
    invoice_text = invoice_vec_result.get("text", "").strip()
    po_text = po_vec_result.get("text", "").strip()

    # 3) SQL Query Chain
    db = SQLDatabase.from_uri("sqlite:///invoices.db")
    sql_chain = create_sql_query_chain(llm, db)
    sql_result = sql_chain.invoke({"question": query})
    if isinstance(sql_result, dict):
        sql_text = sql_result.get("answer", "").strip()
    else:
        sql_text = str(sql_result).strip()

    # 4) Merge All into One
    #   We build a final prompt to unify invoice_text, po_text, and sql_text.
    unify_system = SystemMessagePromptTemplate.from_template(
        "You are an expert financial assistant. Merge the following data from vector retrieval (invoice & PO) and a SQL query into a single, plain-text answer."
    )
    unify_human = HumanMessagePromptTemplate.from_template(
        "Invoice Info: {invoice}\n\n"
        "PO Info: {po}\n\n"
        "SQL Info: {sql}\n\n"
        "Please produce a single, concise plain-text answer without revealing raw doc text or raw SQL details."
    )
    unify_prompt = ChatPromptTemplate.from_messages([unify_system, unify_human])
    unify_chain = unify_prompt | llm

    unify_input = {
        "invoice": invoice_text,
        "po": po_text,
        "sql": sql_text
    }
    unify_result = unify_chain.invoke(unify_input)
    final_answer = ""
    if isinstance(unify_result, dict):
        final_answer = unify_result.get("text", "").strip()
    else:
        final_answer = str(unify_result).strip()

    return {"answer": final_answer}
