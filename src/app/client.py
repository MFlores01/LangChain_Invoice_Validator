from fastapi import FastAPI, HTTPException
from utils.db import get_db, insert_invoice, get_invoice_by_id  # Adjust based on db.py

app = FastAPI()

@app.get("/")
def read_root():
    return {"message": "FastAPI Invoice Validator API is running"}

@app.get("/invoice/{invoice_id}")
def get_invoice(invoice_id: int):
    db = get_db()
    invoice = get_invoice_by_id(db, invoice_id)
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")
    return invoice

@app.post("/invoice/")
def add_invoice(data: dict):
    db = get_db()
    success = insert_invoice(db, data)
    if not success:
        raise HTTPException(status_code=400, detail="Failed to insert invoice")
    return {"message": "Invoice added successfully"}
