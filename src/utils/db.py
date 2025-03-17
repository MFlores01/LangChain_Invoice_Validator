# src/utils/db.py

import sqlite3
import json
import sys
sys.modules["sqlite3"] = sqlite3

class DatabaseManager:
    DB_PATH = "invoices.db"

    def __init__(self):
        self.init_db()

    def init_db(self):
        conn = sqlite3.connect(DatabaseManager.DB_PATH)
        cursor = conn.cursor()

        # Enable foreign key support
        cursor.execute("PRAGMA foreign_keys = ON;")

        # ===========================================
        # purchase_orders Table
        # ===========================================
        # Contains main PO-level info. 
        #   - line_items are NOT stored here; they go into purchase_order_line_items
        #   - If you want to store entire LLM-extracted JSON, keep extracted_fields
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS purchase_orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_hash TEXT UNIQUE,
                po_number TEXT UNIQUE,
                po_date TEXT,
                supplier_name TEXT,
                billing_address TEXT,
                shipping_address TEXT,
                subtotal TEXT,
                tax TEXT,
                total TEXT,
                extracted_fields TEXT
            )
        """)

        # ===========================================
        # purchase_order_line_items Table
        # ===========================================
        # Each line item is a separate row, referencing purchase_orders(id).
        # If you want numeric calculations, consider REAL or DECIMAL columns for quantity/amount.
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS purchase_order_line_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                purchase_order_id INTEGER,
                description TEXT,
                quantity REAL,
                unit_price REAL,
                amount REAL,
                FOREIGN KEY(purchase_order_id) REFERENCES purchase_orders(id)
            )
        """)

        # ===========================================
        # invoices Table
        # ===========================================
        # Contains main Invoice-level info.
        #   - line_items are NOT stored here; they go into invoice_line_items
        #   - If you want entire LLM JSON, keep extracted_fields
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS invoices (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_hash TEXT UNIQUE,
                invoice_number TEXT UNIQUE,
                invoice_date TEXT,
                total_amount TEXT,
                due_date TEXT,
                invoice_to TEXT,
                supplier_name TEXT,
                billing_address TEXT,
                shipping_address TEXT,
                discount TEXT,
                tax_vat TEXT,
                email TEXT,
                phone_number TEXT,
                po_number TEXT,    -- references purchase_orders(po_number) if you prefer
                extracted_fields TEXT,
                FOREIGN KEY(po_number) REFERENCES purchase_orders(po_number)
            )
        """)

        # ===========================================
        # invoice_line_items Table
        # ===========================================
        # Each line item is a separate row, referencing invoices(id).
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS invoice_line_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                invoice_id INTEGER,
                description TEXT,
                quantity REAL,
                unit_price REAL,
                amount REAL,
                FOREIGN KEY(invoice_id) REFERENCES invoices(id)
            )
        """)

        conn.commit()
        conn.close()

    # ---------------------------------------------------------------------
    #                   INVOICE METHODS
    # ---------------------------------------------------------------------
    def check_duplicate_invoice(self, file_hash: str) -> bool:
        """
        Returns True if an invoice with the same file_hash is already in the DB.
        """
        conn = sqlite3.connect(DatabaseManager.DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM invoices WHERE file_hash = ?", (file_hash,))
        result = cursor.fetchone()
        conn.close()
        return result is not None
    
    def get_invoice_by_number(self, invoice_number: str):
        """
        Returns the first invoice whose 'invoice_number' contains the given text
        (partial match) or an empty dict if none.
        """
        conn = sqlite3.connect(self.DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM invoices WHERE invoice_number LIKE ?", (f"%{invoice_number}%",))
        row = cursor.fetchone()
        columns = [col[0] for col in cursor.description] if row else []
        conn.close()

        if row:
            return dict(zip(columns, row))
        return {}


    def store_invoice(self, file_hash: str, extracted_fields: dict):
        """
        Inserts a new invoice record into invoices. 
        Then inserts line items into invoice_line_items.
        """
        conn = sqlite3.connect(DatabaseManager.DB_PATH)
        cursor = conn.cursor()

        invoice_number = extracted_fields.get("invoice_number", "")
        invoice_date = extracted_fields.get("invoice_date", "")
        total_amount = extracted_fields.get("total_amount", "")
        due_date = extracted_fields.get("due_date", "")
        invoice_to = extracted_fields.get("invoice_to", "")
        supplier_name = extracted_fields.get("supplier_name", "")
        billing_address = extracted_fields.get("billing_address", "")
        shipping_address = extracted_fields.get("shipping_address", "")
        discount = extracted_fields.get("discount", "")
        tax_vat = extracted_fields.get("tax_vat", "")
        email = extracted_fields.get("email", "")
        phone_number = extracted_fields.get("phone_number", "")
        po_number = extracted_fields.get("po_number", "")  # Link to PO if present
        raw_json = json.dumps(extracted_fields)

        try:
            cursor.execute("""
                INSERT INTO invoices (
                    file_hash,
                    invoice_number,
                    invoice_date,
                    total_amount,
                    due_date,
                    invoice_to,
                    supplier_name,
                    billing_address,
                    shipping_address,
                    discount,
                    tax_vat,
                    email,
                    phone_number,
                    po_number,
                    extracted_fields
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                file_hash,
                invoice_number,
                invoice_date,
                total_amount,
                due_date,
                invoice_to,
                supplier_name,
                billing_address,
                shipping_address,
                discount,
                tax_vat,
                email,
                phone_number,
                po_number,
                raw_json
            ))
            invoice_id = cursor.lastrowid  # Get the newly inserted invoice's ID
            conn.commit()
        except sqlite3.IntegrityError:
            # Duplicate or constraint violation
            conn.close()
            return

        # Now insert line items into invoice_line_items
        line_items = extracted_fields.get("line_items", [])
        for item in line_items:
            description = item.get("description", "")
            quantity = float(item.get("quantity", 0) or 0)
            # unit_price & amount might be strings with '$', parse if needed
            # For now, we store them as float, ignoring currency symbols
            def parse_money(val):
                try:
                    return float(val.replace("$", "").replace(",", ""))
                except:
                    return 0.0

            unit_price = parse_money(item.get("unit_price", "0"))
            amount = parse_money(item.get("amount", "0"))

            cursor.execute("""
                INSERT INTO invoice_line_items (
                    invoice_id,
                    description,
                    quantity,
                    unit_price,
                    amount
                ) VALUES (?, ?, ?, ?, ?)
            """, (
                invoice_id,
                description,
                quantity,
                unit_price,
                amount
            ))
        conn.commit()
        conn.close()

    # ---------------------------------------------------------------------
    #                 PURCHASE ORDER METHODS
    # ---------------------------------------------------------------------
    def check_duplicate_po(self, file_hash: str) -> bool:
        """
        Returns True if a purchase order with the same file_hash is already in the DB.
        """
        conn = sqlite3.connect(DatabaseManager.DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM purchase_orders WHERE file_hash = ?", (file_hash,))
        result = cursor.fetchone()
        conn.close()
        return result is not None

    def store_purchase_order(self, file_hash: str, extracted_fields: dict):
        """
        Inserts a new purchase order record into purchase_orders,
        then inserts line items into purchase_order_line_items.
        """
        conn = sqlite3.connect(DatabaseManager.DB_PATH)
        cursor = conn.cursor()

        po_number = extracted_fields.get("po_number", "")
        po_date = extracted_fields.get("po_date", "")
        supplier_name = extracted_fields.get("supplier_name", "")
        billing_address = extracted_fields.get("billing_address", "")
        shipping_address = extracted_fields.get("shipping_address", "")
        subtotal = extracted_fields.get("subtotal", "")
        tax = extracted_fields.get("tax", "")
        total = extracted_fields.get("total", "")
        raw_json = json.dumps(extracted_fields)

        try:
            cursor.execute("""
                INSERT INTO purchase_orders (
                    file_hash,
                    po_number,
                    po_date,
                    supplier_name,
                    billing_address,
                    shipping_address,
                    subtotal,
                    tax,
                    total,
                    extracted_fields
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                file_hash,
                po_number,
                po_date,
                supplier_name,
                billing_address,
                shipping_address,
                subtotal,
                tax,
                total,
                raw_json
            ))
            purchase_order_id = cursor.lastrowid  # newly inserted PO ID
            conn.commit()
        except sqlite3.IntegrityError:
            # Duplicate or constraint violation
            conn.close()
            return

        # Insert line items into purchase_order_line_items
        line_items = extracted_fields.get("line_items", [])
        for item in line_items:
            description = item.get("description", "")
            quantity = float(item.get("quantity", 0) or 0)

            def parse_money(val):
                try:
                    return float(val.replace("$", "").replace(",", ""))
                except:
                    return 0.0

            unit_price = parse_money(item.get("unit_price", "0"))
            amount = parse_money(item.get("amount", "0"))

            cursor.execute("""
                INSERT INTO purchase_order_line_items (
                    purchase_order_id,
                    description,
                    quantity,
                    unit_price,
                    amount
                ) VALUES (?, ?, ?, ?, ?)
            """, (
                purchase_order_id,
                description,
                quantity,
                unit_price,
                amount
            ))
        conn.commit()
        conn.close()

    # ---------------------------------------------------------------------
    #                    HELPER QUERIES
    # ---------------------------------------------------------------------
    def get_invoice_by_po(self, po_number: str):
        """
        Return the first invoice that matches the given po_number as a dict, or empty if none.
        """
        conn = sqlite3.connect(DatabaseManager.DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM invoices WHERE po_number = ?", (po_number,))
        row = cursor.fetchone()
        columns = [col[0] for col in cursor.description] if row else []
        conn.close()

        if row:
            return dict(zip(columns, row))
        return {}

    def get_invoice_line_items(self, invoice_id: int):
        """
        Return all line items for the given invoice_id as a list of dicts.
        """
        conn = sqlite3.connect(DatabaseManager.DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT description, quantity, unit_price, amount FROM invoice_line_items WHERE invoice_id = ?", (invoice_id,))
        rows = cursor.fetchall()
        conn.close()

        line_items = []
        for r in rows:
            line_items.append({
                "description": r[0],
                "quantity": r[1],
                "unit_price": r[2],
                "amount": r[3]
            })
        return line_items

    def get_purchase_order_by_number(self, po_number: str):
        """
        Returns the first PO whose 'po_number' contains the given text
        (partial match) or an empty dict if none.
        """
        conn = sqlite3.connect(self.DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM purchase_orders WHERE po_number LIKE ?", (f"%{po_number}%",))
        row = cursor.fetchone()
        columns = [col[0] for col in cursor.description] if row else []
        conn.close()

        if row:
            return dict(zip(columns, row))
        return {}


    def get_purchase_order_line_items(self, purchase_order_id: int):
        """
        Return all line items for the given purchase_order_id as a list of dicts.
        """
        conn = sqlite3.connect(DatabaseManager.DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT description, quantity, unit_price, amount FROM purchase_order_line_items WHERE purchase_order_id = ?", (purchase_order_id,))
        rows = cursor.fetchall()
        conn.close()

        line_items = []
        for r in rows:
            line_items.append({
                "description": r[0],
                "quantity": r[1],
                "unit_price": r[2],
                "amount": r[3]
            })
        return line_items

    # ---------------------------------------------------------------------
    #    CLEAR TABLES (FOR TESTING/RESEEDING)
    # ---------------------------------------------------------------------
    def clear_invoices(self):
        conn = sqlite3.connect(DatabaseManager.DB_PATH)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM invoice_line_items")
        cursor.execute("DELETE FROM invoices")
        conn.commit()
        conn.close()

    def clear_purchase_orders(self):
        conn = sqlite3.connect(DatabaseManager.DB_PATH)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM purchase_order_line_items")
        cursor.execute("DELETE FROM purchase_orders")
        conn.commit()
        conn.close()
