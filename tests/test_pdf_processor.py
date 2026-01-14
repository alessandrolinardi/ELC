"""
Test per il modulo pdf_processor.
"""

import pytest
import sys
import os

# Aggiungi il path del progetto
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.pdf_processor import PDFProcessor


class TestPDFProcessor:
    """Test per la classe PDFProcessor."""

    def setup_method(self):
        """Setup per ogni test."""
        self.processor = PDFProcessor()

    # Test normalizzazione tracking
    def test_normalize_tracking_removes_spaces(self):
        """Verifica che gli spazi vengano rimossi."""
        assert self.processor.normalize_tracking("1Z FC2 577 68") == "1ZFC257768"

    def test_normalize_tracking_uppercase(self):
        """Verifica conversione a uppercase."""
        assert self.processor.normalize_tracking("1z fc2 577") == "1ZFC2577"

    def test_normalize_tracking_empty(self):
        """Verifica gestione stringa vuota."""
        assert self.processor.normalize_tracking("") == ""

    # Test estrazione UPS
    def test_extract_ups_tracking(self):
        """Verifica estrazione tracking UPS."""
        text = "TRACKING #: 1Z FC2 577 68 0034 1731"
        tracking, carrier = self.processor.extract_tracking_from_text(text)
        assert tracking == "1ZFC25776800341731"
        assert carrier == "UPS"

    def test_extract_ups_tracking_alt_format(self):
        """Verifica estrazione tracking UPS formato alternativo."""
        text = "Some text 1Z AB1 234 56 7890 1234 more text"
        tracking, carrier = self.processor.extract_tracking_from_text(text)
        assert tracking is not None
        assert tracking.startswith("1Z")
        assert carrier == "UPS"

    # Test estrazione FedEx
    def test_extract_fedex_tracking(self):
        """Verifica estrazione tracking FedEx."""
        text = "TRK# [0881] 8878 9864 4283"
        tracking, carrier = self.processor.extract_tracking_from_text(text)
        assert tracking == "887898644283"
        assert carrier == "FedEx"

    def test_extract_fedex_tracking_no_box(self):
        """Verifica estrazione FedEx senza box."""
        text = "TRK# 8878 9864 4283"
        tracking, carrier = self.processor.extract_tracking_from_text(text)
        assert tracking == "887898644283"
        assert carrier == "FedEx"

    # Test estrazione DHL
    def test_extract_dhl_tracking(self):
        """Verifica estrazione tracking DHL."""
        text = "WAYBILL 63 3270 4114"
        tracking, carrier = self.processor.extract_tracking_from_text(text)
        assert tracking == "6332704114"
        assert carrier == "DHL"

    # Test casi limite
    def test_extract_no_tracking_found(self):
        """Verifica quando non c'è tracking."""
        text = "Some random text without any tracking number"
        tracking, carrier = self.processor.extract_tracking_from_text(text)
        assert tracking is None
        assert carrier is None

    def test_extract_empty_text(self):
        """Verifica gestione testo vuoto."""
        tracking, carrier = self.processor.extract_tracking_from_text("")
        assert tracking is None
        assert carrier is None


class TestTrackingValidation:
    """Test per la validazione dei tracking."""

    def setup_method(self):
        """Setup per ogni test."""
        self.processor = PDFProcessor()

    def test_validate_ups_valid(self):
        """UPS valido."""
        assert self.processor._validate_tracking("1ZFC25776800341731", "UPS") is True

    def test_validate_ups_invalid_prefix(self):
        """UPS con prefisso sbagliato."""
        assert self.processor._validate_tracking("2ZFC25776800341731", "UPS") is False

    def test_validate_ups_too_short(self):
        """UPS troppo corto."""
        assert self.processor._validate_tracking("1ZFC2577", "UPS") is False

    def test_validate_fedex_valid(self):
        """FedEx valido."""
        assert self.processor._validate_tracking("887898644283", "FedEx") is True

    def test_validate_fedex_not_numeric(self):
        """FedEx non numerico."""
        assert self.processor._validate_tracking("88789864ABCD", "FedEx") is False

    def test_validate_dhl_valid(self):
        """DHL valido."""
        assert self.processor._validate_tracking("6332704114", "DHL") is True

    def test_validate_dhl_too_short(self):
        """DHL troppo corto."""
        assert self.processor._validate_tracking("633270", "DHL") is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
