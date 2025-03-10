import os
import pytest
from src.core.validation_engine import InvoiceValidationService

def test_validation_service_with_invalid_file():
    service = InvoiceValidationService()
    with pytest.raises(ValueError):
        service.validate("nonexistent_file.txt", "txt")
