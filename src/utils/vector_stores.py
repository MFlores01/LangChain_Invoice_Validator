# utils/vector_stores.py

from langchain_openai import OpenAIEmbeddings
from langchain.vectorstores import Chroma

# Initialize the embeddings only once.
embeddings = OpenAIEmbeddings()

# Initialize the vector store for invoices.
invoice_vectorstore = Chroma(
    persist_directory="invoice_db",
    embedding_function=embeddings,
    collection_name="invoices"
)

# Initialize the vector store for purchase orders.
po_vectorstore = Chroma(
    persist_directory="po_db",
    embedding_function=embeddings,
    collection_name="purchase_orders"
)
