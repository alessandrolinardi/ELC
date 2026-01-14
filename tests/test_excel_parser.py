"""
Test per il modulo excel_parser.
"""

import pytest
import sys
import os

# Aggiungi il path del progetto
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.excel_parser import ExcelParser


class TestExcelParser:
    """Test per la classe ExcelParser."""

    def setup_method(self):
        """Setup per ogni test."""
        self.parser = ExcelParser()

    # Test normalizzazione tracking
    def test_normalize_tracking_removes_spaces(self):
        """Verifica rimozione spazi."""
        assert self.parser.normalize_tracking("63 3270 2261") == "6332702261"

    def test_normalize_tracking_uppercase(self):
        """Verifica uppercase."""
        assert self.parser.normalize_tracking("abc123") == "ABC123"

    def test_normalize_tracking_nan(self):
        """Verifica gestione NaN."""
        import pandas as pd
        assert self.parser.normalize_tracking(pd.NA) == ""

    def test_normalize_tracking_none(self):
        """Verifica gestione None."""
        assert self.parser.normalize_tracking(None) == ""


class TestNumericSuffixExtraction:
    """Test per l'estrazione del suffisso numerico."""

    def setup_method(self):
        """Setup per ogni test."""
        self.parser = ExcelParser()

    def test_extract_suffix_standard(self):
        """Formato standard: ID_BRAND_NUM."""
        result = self.parser.extract_numeric_suffix("3501512414_ORIGINS_99")
        assert result == 99

    def test_extract_suffix_multi_underscore(self):
        """Multipli underscore."""
        result = self.parser.extract_numeric_suffix("A_B_C_D_123")
        assert result == 123

    def test_extract_suffix_no_underscore(self):
        """Nessun underscore, numero alla fine."""
        result = self.parser.extract_numeric_suffix("ORDER123")
        assert result == 123

    def test_extract_suffix_no_number(self):
        """Nessun numero alla fine."""
        result = self.parser.extract_numeric_suffix("ORDER_ABC")
        assert result is None

    def test_extract_suffix_empty(self):
        """Stringa vuota."""
        result = self.parser.extract_numeric_suffix("")
        assert result is None

    def test_extract_suffix_nan(self):
        """Valore NaN."""
        import pandas as pd
        result = self.parser.extract_numeric_suffix(pd.NA)
        assert result is None

    def test_extract_suffix_only_numbers(self):
        """Solo numeri."""
        result = self.parser.extract_numeric_suffix("12345")
        assert result == 12345

    def test_extract_suffix_mixed(self):
        """Formato misto."""
        result = self.parser.extract_numeric_suffix("3501512414_BOBBI BROWN_100")
        assert result == 100


class TestColumnMapping:
    """Test per il mapping delle colonne."""

    def setup_method(self):
        """Setup per ogni test."""
        self.parser = ExcelParser()

    def test_find_column_exact_match(self):
        """Match esatto nome colonna."""
        import pandas as pd
        df = pd.DataFrame(columns=["ID Ordine Marketplace", "Tracking", "Corriere"])
        assert self.parser._find_column(df, "order_id") == "ID Ordine Marketplace"

    def test_find_column_case_insensitive(self):
        """Match case insensitive."""
        import pandas as pd
        df = pd.DataFrame(columns=["id ordine marketplace", "tracking", "corriere"])
        assert self.parser._find_column(df, "order_id") == "id ordine marketplace"

    def test_find_column_alternative_name(self):
        """Match nome alternativo."""
        import pandas as pd
        df = pd.DataFrame(columns=["Order ID", "Tracking Number", "Carrier"])
        assert self.parser._find_column(df, "order_id") == "Order ID"

    def test_find_column_not_found(self):
        """Colonna non trovata."""
        import pandas as pd
        df = pd.DataFrame(columns=["Col1", "Col2", "Col3"])
        assert self.parser._find_column(df, "order_id") is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
