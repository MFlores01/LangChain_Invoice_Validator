# src/core/po_validation_engine.py
from core.po_validator import PDFPOValidator, CSVPOValidator, XMLPOValidator, ImagePOValidator

class POValidationService:
    """
    Service class for purchase order validation.
    Selects the appropriate validator based on file extension.
    """
    def __init__(self):
        self.validators = {
            "pdf": PDFPOValidator,
            "csv": CSVPOValidator,
            "xml": XMLPOValidator,
            "png": ImagePOValidator,
            "jpg": ImagePOValidator,
            "jpeg": ImagePOValidator
        }
    
    def validate(self, file_path: str, file_ext: str):
        file_ext = file_ext.lower()
        validator_class = self.validators.get(file_ext)
        if not validator_class:
            raise ValueError(f"Unsupported PO file format: {file_ext}")
        validator = validator_class()
        return validator.validate_po(file_path)
