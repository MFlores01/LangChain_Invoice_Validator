# src/utils/db.py
import sqlite3
import json
import sys
import sqlite3
sys.modules["sqlite3"] = sqlite3

class DatabaseManager:
    DB_PATH = "invoices.db"

    def __init__(self):
        self.init_db()

    def init_db(self):
        conn = sqlite3.connect(DatabaseManager.DB_PATH)
        cursor = conn.cursor()
        # Enable foreign keys support
        cursor.execute("PRAGMA foreign_keys = ON;")
        # Create the purchase_orders table.
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS purchase_orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_hash TEXT UNIQUE,
                po_number TEXT UNIQUE,
                po_date TEXT,
                vendor TEXT,
                extracted_fields TEXT
            )
        """)
        # Create the invoices table.
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS invoices (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_hash TEXT UNIQUE,
                invoice_number TEXT,
                invoice_date TEXT,
                supplier_name TEXT,
                po_number TEXT,
                extracted_fields TEXT,
                FOREIGN KEY(po_number) REFERENCES purchase_orders(po_number)
            )
        """)
        conn.commit()
        conn.close()

    # Invoices methods
    def check_duplicate_invoice(self, file_hash: str) -> bool:
        conn = sqlite3.connect(DatabaseManager.DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM invoices WHERE file_hash = ?", (file_hash,))
        result = cursor.fetchone()
        conn.close()
        return result is not None

    def store_invoice(self, file_hash: str, extracted_fields: dict):
        conn = sqlite3.connect(DatabaseManager.DB_PATH)
        cursor = conn.cursor()
        invoice_number = extracted_fields.get("invoice_number", "")
        invoice_date = extracted_fields.get("invoice_date", "")
        supplier_name = extracted_fields.get("supplier_name", "")
        po_number = extracted_fields.get("po_number", "")
        json_fields = json.dumps(extracted_fields)
        try:
            cursor.execute(
                "INSERT INTO invoices (file_hash, invoice_number, invoice_date, supplier_name, po_number, extracted_fields) VALUES (?, ?, ?, ?, ?, ?)",
                (file_hash, invoice_number, invoice_date, supplier_name, po_number, json_fields)
            )
            conn.commit()
        except sqlite3.IntegrityError:
            pass
        conn.close()

    # Purchase Orders methods
    def check_duplicate_po(self, file_hash: str) -> bool:
        conn = sqlite3.connect(DatabaseManager.DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM purchase_orders WHERE file_hash = ?", (file_hash,))
        result = cursor.fetchone()
        conn.close()
        return result is not None

    def store_purchase_order(self, file_hash: str, extracted_fields: dict):
        conn = sqlite3.connect(DatabaseManager.DB_PATH)
        cursor = conn.cursor()
        po_number = extracted_fields.get("po_number", "")
        po_date = extracted_fields.get("po_date", "")
        vendor = extracted_fields.get("vendor", "")
        json_fields = json.dumps(extracted_fields)
        try:
            cursor.execute(
                "INSERT INTO purchase_orders (file_hash, po_number, po_date, vendor, extracted_fields) VALUES (?, ?, ?, ?, ?)",
                (file_hash, po_number, po_date, vendor, json_fields)
            )
            conn.commit()
        except sqlite3.IntegrityError:
            pass
        conn.close()

    def get_invoice_by_po(self, po_number: str):
        conn = sqlite3.connect(DatabaseManager.DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM invoices WHERE po_number = ?", (po_number,))
        result = cursor.fetchone()  # Use fetchone() instead of fetchall()
        conn.close()

        if result:
            columns = [column[0] for column in cursor.description]
            return dict(zip(columns, result))  # Return the result as a dictionary
        return {}

    def get_purchase_order_by_number(self, po_number: str):
        conn = sqlite3.connect(DatabaseManager.DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM purchase_orders WHERE po_number = ?", (po_number,))
        result = cursor.fetchone()  # Use fetchone() instead of fetchall()
        conn.close()

        if result:
            columns = [column[0] for column in cursor.description]
            return dict(zip(columns, result))  # Return the result as a dictionary
        return {}


    # Methods to clear the tables (for testing purposes)
    def clear_invoices(self):
        conn = sqlite3.connect(DatabaseManager.DB_PATH)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM invoices")
        conn.commit()
        conn.close()

    def clear_purchase_orders(self):
        conn = sqlite3.connect(DatabaseManager.DB_PATH)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM purchase_orders")
        conn.commit()
        conn.close()
