import pytest
import pandas as pd

from app.core.security import validate_excel_content, sanitize_filename


class TestValidateExcelContent:

    def test_valid_dataframe(self):
        df = pd.DataFrame({"name": ["Alice", "Bob"], "city": ["Roma", "Milano"]})
        is_valid, error = validate_excel_content(df)
        assert is_valid is True
        assert error is None

    def test_formula_injection_detected(self):
        df = pd.DataFrame({"col": ["=CMD(malicious)"]})
        is_valid, error = validate_excel_content(df)
        assert is_valid is False
        assert "col" in error

    def test_cell_exceeding_max_length(self):
        df = pd.DataFrame({"long": ["x" * 1001]})
        is_valid, error = validate_excel_content(df)
        assert is_valid is False
        assert "long" in error
        assert "1000" in error

    def test_empty_dataframe(self):
        df = pd.DataFrame()
        is_valid, error = validate_excel_content(df)
        assert is_valid is True
        assert error is None


class TestSanitizeFilename:

    def test_normal_filename(self):
        assert sanitize_filename("report.xlsx") == "report.xlsx"

    def test_path_traversal(self):
        result = sanitize_filename("../../etc/passwd")
        assert "/" not in result
        assert "\\" not in result
        # Slashes replaced with underscores, leading dots stripped — no traversal possible
        assert not result.startswith(".")

    def test_empty_filename(self):
        result = sanitize_filename("")
        assert result == "unnamed"
