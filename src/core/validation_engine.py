from core.data_processor import PDFValidator, CSVValidator, XMLValidator, ImageValidator

class InvoiceValidationService:
    """
    Service class that encapsulates invoice validation.
    It selects the appropriate validator based on file extension and provides a reusable validate() method.
    """
    def __init__(self):
        self.validators = {
            "pdf": PDFValidator,
            "csv": CSVValidator,
            "xml": XMLValidator,
            "png": ImageValidator,
            "jpg": ImageValidator,
            "jpeg": ImageValidator
        }
    
    def validate(self, file_path: str, file_ext: str):
        file_ext = file_ext.lower()
        validator_class = self.validators.get(file_ext)
        if not validator_class:
            raise ValueError(f"Unsupported file format: {file_ext}")
        validator = validator_class()
        return validator.validate_invoice(file_path)
