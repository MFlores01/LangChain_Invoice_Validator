import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))

from utils.db import DatabaseManager

# Test the get_invoice_by_po method
db = DatabaseManager()
invoice = db.get_invoice_by_po('2001321')
print(f"Invoice: {invoice}")  # Check if the method returns data

# Test the get_purchase_order_by_number method
po = db.get_purchase_order_by_number('PO-2001321')
print(f"PO: {po}")  # Check if the method returns data
