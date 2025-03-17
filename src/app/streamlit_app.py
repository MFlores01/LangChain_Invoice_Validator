import sys
import os
import base64
import streamlit as st
import json
import pandas as pd
from dotenv import load_dotenv
from streamlit_option_menu import option_menu

from core.validation_engine import InvoiceValidationService
from core.po_validation_engine import POValidationService
from core.po_comparator import POComparator
from utils.file_utils import save_temp_file, remove_temp_file
from styles.styles import CSS_STYLE  # Our advanced styling

# Import chatbot functionality from chatbot.py
from core.chatbot import get_chatbot_response

# Load environment variables: use Streamlit secrets (Cloud) if available; otherwise, load .env locally.
if "OPENAI_API_KEY" in st.secrets:
    os.environ["OPENAI_API_KEY"] = st.secrets["OPENAI_API_KEY"]
else:
    load_dotenv()

comparator = POComparator(temperature=0)

class InvoiceValidationApp:
    def __init__(self, logo_path: str):
        st.set_page_config(layout="wide")
        self.logo_b64 = self.load_logo_as_base64(logo_path)
        self.load_css()
        self.invoice_service = InvoiceValidationService()
        self.po_service = POValidationService()
        # Initialize session state to preserve file upload results and chat messages
        if "po_result" not in st.session_state:
            st.session_state["po_result"] = {}
        if "invoice_result" not in st.session_state:
            st.session_state["invoice_result"] = {}
        if "po_record" not in st.session_state:
            st.session_state["po_record"] = {}
        if "invoice_record" not in st.session_state:
            st.session_state["invoice_record"] = {}
        if "messages" not in st.session_state:
            st.session_state["messages"] = []

    def load_css(self):
        st.markdown(CSS_STYLE, unsafe_allow_html=True)

    def load_logo_as_base64(self, logo_path: str) -> str:
        if not os.path.exists(logo_path):
            st.warning(f"Logo not found at: {logo_path}")
            return ""
        with open(logo_path, "rb") as f:
            data = f.read()
        return base64.b64encode(data).decode()

    def run(self):
        st.markdown(
            f"""
            <div class="top-bar">
                <img src="data:image/png;base64,{self.logo_b64}" alt="Cloudstaff Logo"/>
                <h1>Invoice Validation</h1>
            </div>
            """,
            unsafe_allow_html=True
        )
        with st.sidebar:
            selected_page = option_menu(
                "CloudStaff Invoice Validator",
                ["Document Upload", "Invoice Chatbot"],
                icons=["cloud-upload", "robot"],
                menu_icon="briefcase",
                default_index=0,
                styles={
                    "container": {"padding": "0!important", "background-color": "#fafafa"},
                    "nav-link": {"font-size": "16px", "text-align": "left", "--hover-color": "#eee"},
                    "nav-link-selected": {"background": "linear-gradient(90deg, #005f73, #0a9396)", "color": "white"},
                }
            )
        if selected_page == "Document Upload":
            self.render_upload_page()
        else:
            self.render_chatbot_page()

    def render_upload_page(self):
        # File uploaders for PO and Invoice files
        col1, col2 = st.columns(2)
        with col1:
            st.markdown('<div class="upload-section">', unsafe_allow_html=True)
            uploaded_po = st.file_uploader(
                "Upload Purchase Order (PDF/CSV/XML/Image)",
                type=["pdf", "csv", "xml", "png", "jpg", "jpeg"],
                key="po_upload"
            )
            st.markdown('</div>', unsafe_allow_html=True)
        with col2:
            st.markdown('<div class="upload-section">', unsafe_allow_html=True)
            uploaded_invoice = st.file_uploader(
                "Upload Invoice (PDF/CSV/XML/Image)",
                type=["pdf", "csv", "xml", "png", "jpg", "jpeg"],
                key="invoice_upload"
            )
            st.markdown('</div>', unsafe_allow_html=True)

        # Process files only when both are uploaded
        if uploaded_po and uploaded_invoice:
            st.markdown("<hr>", unsafe_allow_html=True)
            # Process Purchase Order file
            po_ext = uploaded_po.name.split(".")[-1].lower()
            tmp_po_path = save_temp_file(uploaded_po, suffix=f".{po_ext}")
            try:
                po_result = self.po_service.validate(tmp_po_path, po_ext)
            except Exception as e:
                st.error(f"PO validation failed: {str(e)}")
                po_result = {}
            remove_temp_file(tmp_po_path)
            # Process Invoice file
            inv_ext = uploaded_invoice.name.split(".")[-1].lower()
            tmp_inv_path = save_temp_file(uploaded_invoice, suffix=f".{inv_ext}")
            try:
                invoice_result = self.invoice_service.validate(tmp_inv_path, inv_ext)
            except Exception as e:
                st.error(f"Invoice validation failed: {str(e)}")
                invoice_result = {}
            remove_temp_file(tmp_inv_path)

            # Store results in session state for later use by the chatbot
            st.session_state["po_result"] = po_result
            st.session_state["invoice_result"] = invoice_result
            st.session_state["po_record"] = po_result.get("extracted_fields", {})
            st.session_state["invoice_record"] = invoice_result.get("extracted_fields", {})

        # Display uploaded document details if available
        po_result = st.session_state["po_result"]
        invoice_result = st.session_state["invoice_result"]

        if po_result or invoice_result:
            combined_results_html = self.build_combined_validation_card(po_result, invoice_result)
            st.markdown(combined_results_html, unsafe_allow_html=True)
            if po_result.get("extracted_fields"):
                st.markdown("<hr>", unsafe_allow_html=True)
                st.markdown("<h2>Purchase Order Details</h2>", unsafe_allow_html=True)
                po_main_fields = po_result["extracted_fields"].copy()
                po_line_items = po_main_fields.pop("line_items", [])
                po_details_html = self.build_details_card(po_main_fields, title="PO Details")
                po_extracted_html = self.build_extracted_card(po_main_fields, po_line_items)
                col_po_left, col_po_right = st.columns(2)
                with col_po_left:
                    st.markdown(po_details_html, unsafe_allow_html=True)
                with col_po_right:
                    st.markdown(po_extracted_html, unsafe_allow_html=True)
            if invoice_result.get("extracted_fields"):
                st.markdown("<hr>", unsafe_allow_html=True)
                st.markdown("<h2>Invoice Details</h2>", unsafe_allow_html=True)
                invoice_main_fields = invoice_result["extracted_fields"].copy()
                invoice_line_items = invoice_main_fields.pop("line_items", [])
                inv_details_html = self.build_details_card(invoice_main_fields, title="Invoice Details")
                inv_extracted_html = self.build_extracted_card(invoice_main_fields, invoice_line_items)
                col_inv_left, col_inv_right = st.columns(2)
                with col_inv_left:
                    st.markdown(inv_details_html, unsafe_allow_html=True)
                with col_inv_right:
                    st.markdown(inv_extracted_html, unsafe_allow_html=True)
            if po_result and invoice_result:
                discrepancy_report = comparator.compare(
                    invoice_result.get("extracted_fields", {}),
                    po_result.get("extracted_fields", {})
                )
                if discrepancy_report.strip():
                    st.markdown("<hr>", unsafe_allow_html=True)
                    st.markdown(self.build_discrepancy_card(discrepancy_report), unsafe_allow_html=True)

    def render_chatbot_page(self):
        st.markdown("<h2>Invoice Chatbot</h2>", unsafe_allow_html=True)
        # Render chat history
        for msg in st.session_state["messages"]:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])
        query = st.chat_input("Ask about Invoices or Purchase Orders. For example: 'What is the information for invoice #1001329?'")
        if query:
            with st.chat_message("user"):
                st.markdown(query)
            st.session_state.messages.append({"role": "user", "content": query})
            # If the user requests a draft email, use stored records from session state
            if query.strip().lower().startswith("draft email"):
                if "invoice" in query.lower():
                    record = st.session_state.get("invoice_record", {})
                    if record:
                        email_response = self.draft_email_response(record, record_type="invoice")
                    else:
                        email_response = "No invoice record available to draft an email."
                elif "po" in query.lower() or "purchase order" in query.lower():
                    record = st.session_state.get("po_record", {})
                    if record:
                        email_response = self.draft_email_response(record, record_type="po")
                    else:
                        email_response = "No purchase order record available to draft an email."
                else:
                    email_response = "Please specify whether you want an invoice or purchase order email draft."
                with st.chat_message("assistant"):
                    st.markdown(email_response)
                st.session_state.messages.append({"role": "assistant", "content": email_response})
            else:
                with st.spinner("Thinking..."):
                    responses = get_chatbot_response(query)
                    assistant_response = responses.get("answer", "")
                    with st.chat_message("assistant"):
                        st.markdown(assistant_response)
                st.session_state.messages.append({"role": "assistant", "content": assistant_response})

    def draft_email_response(self, record: dict, record_type: str) -> str:
        if record_type == "invoice":
            email_body = (
                f"Dear {record.get('invoice_to', 'Customer')},\n\n"
                f"Regarding your invoice {record.get('invoice_number', 'N/A')} dated {record.get('invoice_date', 'N/A')},\n"
                f"we have reviewed the details as follows:\n"
                f"- Total Amount: {record.get('total_amount', 'N/A')}\n"
                f"- Invoice To: {record.get('invoice_to', 'N/A')}\n"
                f"- Email: {record.get('email', 'N/A')}\n"
                f"- Phone: {record.get('phone_number', 'N/A')}\n\n"
                "Please review these details and let us know if any corrections are required.\n\n"
                "Best regards,\n"
                "Finance Team"
            )
            return email_body
        elif record_type == "po":
            email_body = (
                f"Dear {record.get('supplier_name', 'Vendor')},\n\n"
                f"Regarding your purchase order {record.get('po_number', 'N/A')} dated {record.get('po_date', 'N/A')},\n"
                f"we have reviewed the details as follows:\n"
                f"- Total: {record.get('total', 'N/A')}\n"
                f"- Supplier: {record.get('supplier_name', 'N/A')}\n"
                f"- Billing Address: {record.get('billing_address', 'N/A')}\n"
                f"- Shipping Address: {record.get('shipping_address', 'N/A')}\n\n"
                "Please review these details and let us know if any corrections are required.\n\n"
                "Best regards,\n"
                "Finance Team"
            )
            return email_body
        else:
            return "Invalid record type specified."

    def build_combined_validation_card(self, po_result: dict, invoice_result: dict) -> str:
        if not po_result and not invoice_result:
            return ""
        po_valid = "✅" if po_result.get("is_valid_format") else "❌"
        po_dup = "Yes" if po_result.get("is_duplicate") else "No"
        po_status = "OK" if not po_result.get("is_corrupted") else "Corrupted"
        inv_valid = "✅" if invoice_result.get("is_valid_format") else "❌"
        inv_dup = "Yes" if invoice_result.get("is_duplicate") else "No"
        inv_status = "OK" if not invoice_result.get("is_corrupted") else "Corrupted"
        return f"""
        <div class="card-elevated" style="width:80%; margin:20px auto;">
          <div class="card-header">Combined Validation Results</div>
          <div class="card-body" style="display:flex; gap:20px; justify-content:center; flex-wrap: wrap;">
            <div style="min-width: 300px; margin:10px;">
              <h4>Purchase Order</h4>
              <p><strong>Valid Format:</strong> {po_valid}</p>
              <p><strong>File Status:</strong> {po_status}</p>
              <p><strong>Duplicate:</strong> {po_dup}</p>
            </div>
            <div style="min-width: 300px; margin:10px;">
              <h4>Invoice</h4>
              <p><strong>Valid Format:</strong> {inv_valid}</p>
              <p><strong>File Status:</strong> {inv_status}</p>
              <p><strong>Duplicate:</strong> {inv_dup}</p>
            </div>
          </div>
        </div>
        """

    def build_details_card(self, fields: dict, title: str = "Details") -> str:
        if not fields:
            return "<p>No data extracted.</p>"
        lines = []
        for k, v in fields.items():
            lines.append(f"<p><strong>{k.replace('_', ' ').title()}:</strong> {v}</p>")
        lines_html = "".join(lines)
        return f"""
        <div class="card-elevated">
          <div class="card-header">{title}</div>
          <div class="card-body">
            {lines_html}
          </div>
        </div>
        """

    def build_extracted_card(self, fields: dict, line_items: list) -> str:
        if not line_items:
            return "<p>No line items extracted.</p>"
        headers = list(line_items[0].keys())
        thead = "<thead><tr>" + "".join([f"<th>{h}</th>" for h in headers]) + "</tr></thead>"
        tbody_rows = []
        for item in line_items:
            row_cells = [f"<td>{item.get(h, '')}</td>" for h in headers]
            row_html = "<tr>" + "".join(row_cells) + "</tr>"
            tbody_rows.append(row_html)
        tbody = "<tbody>" + "".join(tbody_rows) + "</tbody>"
        table_html = f"<table class='table-custom'>{thead}{tbody}</table>"
        csv_link = self.build_csv_download_link(fields, line_items)
        return f"""
        <div class="card-elevated">
          <div class="card-header">Extracted Details</div>
          <div class="card-body">
            {table_html}
            {csv_link}
          </div>
        </div>
        """

    def build_csv_download_link(self, fields: dict, line_items: list) -> str:
        if not fields and not line_items:
            return ""
        if line_items:
            df_items = pd.DataFrame(line_items)
            for key, value in fields.items():
                if key not in df_items.columns:
                    df_items[key] = value
            df_combined = df_items
        else:
            df_combined = pd.DataFrame([fields])
        csv_bytes = df_combined.to_csv(index=False).encode('utf-8')
        b64 = base64.b64encode(csv_bytes).decode()
        return f"""
        <a href="data:text/csv;base64,{b64}" download="extracted_data.csv" class="download-link">
            Extract into CSV
        </a>
        """

    def build_discrepancy_card(self, report: str) -> str:
        return f"""
        <div class="card-elevated" style="width:80%; margin:20px auto;">
          <div class="card-header">Discrepancy Report</div>
          <div class="card-body">
            {report}
          </div>
        </div>
        """

if __name__ == "__main__":
    logo_path = os.path.join(os.path.dirname(__file__), "..", "assets", "logo.png")
    app = InvoiceValidationApp(logo_path)
    app.run()
