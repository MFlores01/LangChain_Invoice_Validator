# src/core/po_comparator.py

from langchain_openai import ChatOpenAI

class POComparator:
    def __init__(self, temperature: float = 0):
        self.llm = ChatOpenAI(model_name="gpt-4o", temperature=temperature)
    
    @staticmethod
    def parse_amount(amount_str: str) -> float:
        """Converts a string like '$1,899.00' to a float value."""
        try:
            return float(amount_str.replace("$", "").replace(",", ""))
        except Exception:
            return 0.0

    @staticmethod
    def get_item_key(item: dict) -> str:
        """
        Returns a key for the line item using the 'description' field (uppercased).
        """
        return item.get("description", "").strip().upper()

    def build_raw_analysis(self, invoice_fields: dict, po_fields: dict) -> str:
        raw_lines = []
    
        # --- Overall Extracted Details ---
        inv_id = invoice_fields.get("invoice_number", "N/A")
        supplier = invoice_fields.get("supplier_name", "N/A")
        po_number = po_fields.get("po_number", "N/A")
        inv_total = self.parse_amount(invoice_fields.get("total_amount", "0"))
        po_total = self.parse_amount(po_fields.get("total", "0"))
        inv_bill = invoice_fields.get("billing_address", "N/A")
        po_bill = po_fields.get("billing_address", "N/A")
        inv_ship = invoice_fields.get("shipping_address", "N/A")
        po_ship = po_fields.get("shipping_address", "N/A")
    
        raw_lines.append("=== Overall Extracted Details ===")
        raw_lines.append(f"Invoice ID: {inv_id}")
        raw_lines.append(f"Supplier: {supplier}")
        raw_lines.append(f"PO Number: {po_number}")
        raw_lines.append(f"Invoice Amount: ${inv_total:.2f}")
        raw_lines.append(f"PO Amount: ${po_total:.2f}")
        raw_lines.append(f"Billing Address: Invoice: {inv_bill} | PO: {po_bill}")
        raw_lines.append(f"Shipping Address: Invoice: {inv_ship} | PO: {po_ship}")
        raw_lines.append("")
    
        # --- Raw Discrepancy Analysis ---
        raw_lines.append("=== Raw Discrepancy Analysis ===")
        if inv_total != po_total:
            raw_lines.append(f"Total Discrepancy: Invoice total ${inv_total:.2f} vs PO total ${po_total:.2f}")
        
        # If both addresses exist but differ, note a discrepancy. 
        # If invoice address is "N/A" but PO has an address, or vice versa, treat it as a "missing" scenario.
        if inv_bill.lower() != po_bill.lower():
            raw_lines.append(f"Billing Address Discrepancy: Invoice '{inv_bill}' vs PO '{po_bill}'")
        if inv_ship.lower() != po_ship.lower():
            raw_lines.append(f"Shipping Address Discrepancy: Invoice '{inv_ship}' vs PO '{po_ship}'")
    
        # --- Detailed Line Item Comparison ---
        raw_lines.append("")
        raw_lines.append("=== Detailed Line Item Comparison ===")
        inv_items = invoice_fields.get("line_items", [])
        po_items = po_fields.get("line_items", [])
    
        inv_dict = {self.get_item_key(item): item for item in inv_items if self.get_item_key(item)}
        po_dict = {self.get_item_key(item): item for item in po_items if self.get_item_key(item)}
        all_keys = set(inv_dict.keys()) | set(po_dict.keys())
    
        for key in sorted(all_keys):
            inv_item = inv_dict.get(key)
            po_item = po_dict.get(key)
            raw_lines.append(f"Item: {key}")
            properties = [("quantity", "Quantity"), ("unit_price", "Unit Price"), ("amount", "Line Item Amount")]
            for prop_key, prop_label in properties:
                inv_val = inv_item.get(prop_key, "N/A") if inv_item else "N/A"
                po_val = po_item.get(prop_key, "N/A") if po_item else "N/A"
                status = "Match" if str(inv_val).strip() == str(po_val).strip() else "Mismatch"
                raw_lines.append(f"  {prop_label}: Invoice = {inv_val} | PO = {po_val} => {status}")
            if not inv_item:
                raw_lines.append("  --> Missing in Invoice")
            if not po_item:
                raw_lines.append("  --> Missing in PO")
            raw_lines.append("")
    
        return "\n".join(raw_lines)

    def build_prompt(self, raw_analysis: str) -> str:
        """
        Construct a detailed prompt instructing the LLM to generate a final discrepancy report in HTML.
        We explicitly restrict it to minimal tags so that we don't see raw <div> tags in the final output.
        """
        prompt = (
            "You are an expert in financial discrepancy analysis. Analyze the following raw discrepancy analysis "
            "between an Invoice and a Purchase Order. Generate a final discrepancy report in HTML format that "
            "when rendered, does not show raw HTML tags like <div>. Instead, use only these tags:\n\n"
            "- <h2>, <h3>, <p>, <ul>, <li>, <table>, <thead>, <tbody>, <tr>, <th>, <td>\n\n"
            "Your final report must include:\n\n"
            "1. <h2>Validation Status</h2>: A concise statement indicating documents are flagged for review.\n"
            "2. <h2>Invoice Details</h2>: A bullet list (<ul>) summarizing key invoice details (Invoice ID, Supplier, PO Number, etc.).\n"
            "3. <h2>Discrepancy Found</h2>: A bullet list of identified discrepancies.\n"
            "4. <h2>Next Steps</h2>: Actionable recommendations.\n"
            "5. <h2>Detailed Breakdown</h2>: For each line item, create an HTML table (<table>) with columns for Description, Invoice value, PO value, and match status (match or mistmatch).\n\n"
            "Important: If one document has an address while the other does not, do not automatically treat it as a severe discrepancy unless it's truly required. "
            "Use your best judgment. The final HTML must not contain <div> or extraneous tags.\n\n"
            "Below is the raw discrepancy analysis:\n"
            "----------------------------------------\n"
            f"{raw_analysis.replace(chr(10), '<br>')}\n"
            "----------------------------------------\n\n"
            "Final Report (HTML) using only <h2>, <h3>, <p>, <ul>, <li>, <table>, <thead>, <tbody>, <tr>, <th>, <td>:"
        )
        return prompt

    def compare(self, invoice_fields: dict, po_fields: dict) -> str:
        """
        Generate the final discrepancy report by building a raw analysis, constructing the prompt,
        invoking the LLM, and returning the final HTML
          report.
        """
        raw_analysis = self.build_raw_analysis(invoice_fields, po_fields)
        prompt = self.build_prompt(raw_analysis)
        llm_response = self.llm.invoke(prompt)
        final_report = llm_response.content if hasattr(llm_response, "content") else str(llm_response)
        return final_report
