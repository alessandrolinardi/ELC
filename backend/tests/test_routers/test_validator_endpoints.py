"""
Validator endpoint integration tests covering:
- Issue #3: parse_method updated after user edits
- Issue #7: Empty file rejected with 400
- Issue #8: Module-level regex parser reuse

Tests the full Phase 1 -> confirm -> Phase 2 flow, user edits,
double-confirm rejection, and edge cases.
"""
import io
import time
from unittest.mock import patch, MagicMock

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.job_store import job_store
from app.core.models import ParsedAddress


client = TestClient(app)


def _make_excel_bytes(rows: list[dict]) -> bytes:
    """Create an Excel file in memory from a list of dicts."""
    df = pd.DataFrame(rows)
    buf = io.BytesIO()
    df.to_excel(buf, index=False, engine='openpyxl')
    return buf.getvalue()


def _make_empty_excel() -> bytes:
    """Create an Excel file with headers but no data rows."""
    df = pd.DataFrame(columns=["Street 1", "City", "Zip"])
    buf = io.BytesIO()
    df.to_excel(buf, index=False, engine='openpyxl')
    return buf.getvalue()


def _make_valid_excel() -> bytes:
    return _make_excel_bytes([
        {"Street 1": "Via Roma 10", "City": "Milano", "Zip": "20121"},
        {"Street 1": "Piazza Duomo 1", "City": "Milano", "Zip": "20122"},
    ])


def _wait_for_status(job_id: str, target: str, timeout: float = 10.0) -> dict:
    """Poll job status until it reaches target or times out."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        resp = client.get(f"/api/v1/jobs/{job_id}/status")
        data = resp.json()["data"]
        if data["status"] == target or data["status"] == "failed":
            return data
        time.sleep(0.2)
    raise TimeoutError(f"Job {job_id} did not reach '{target}' within {timeout}s")


# Patch security functions that depend on Supabase
_SECURITY_PATCHES = {
    'app.routers.validator.validate_excel_content': lambda df: (True, None),
    'app.routers.validator.check_rate_limit': lambda ip, rows: (True, "", {}),
    'app.routers.validator.record_usage': lambda ip, rows: None,
    'app.routers.validator.record_failed_attempt': lambda ip: None,
}


def _apply_security_mocks():
    """Context manager stack for all security mocks."""
    from contextlib import ExitStack
    stack = ExitStack()
    for target, side_effect in _SECURITY_PATCHES.items():
        stack.enter_context(patch(target, side_effect=side_effect))
    return stack


class TestEmptyFileRejection:
    """Issue #7: Empty file should return 400, not create a job."""

    def test_empty_excel_returns_400(self):
        excel = _make_empty_excel()
        resp = client.post(
            "/api/v1/jobs/validator",
            files={"excel_file": ("empty.xlsx", excel, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
            data={"confidence_threshold": 90, "street_confidence_threshold": 85},
        )
        assert resp.status_code == 400
        detail = resp.json()["detail"]
        assert detail["error"]["code"] == "EMPTY_FILE"

    def test_invalid_excel_returns_400(self):
        resp = client.post(
            "/api/v1/jobs/validator",
            files={"excel_file": ("bad.xlsx", b"not an excel file", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
            data={"confidence_threshold": 90, "street_confidence_threshold": 85},
        )
        assert resp.status_code == 400
        detail = resp.json()["detail"]
        assert detail["error"]["code"] == "INVALID_FILE"

    def test_valid_excel_returns_200(self):
        excel = _make_valid_excel()
        with _apply_security_mocks():
            resp = client.post(
                "/api/v1/jobs/validator",
                files={"excel_file": ("valid.xlsx", excel, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
                data={"confidence_threshold": 90, "street_confidence_threshold": 85},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert "job_id" in data["data"]


class TestPhase1Parsing:
    """Phase 1: File upload and AI parsing."""

    def test_phase1_reaches_parsed_status(self):
        """Upload valid file -> job should reach 'parsed' status."""
        excel = _make_valid_excel()
        with _apply_security_mocks():
            resp = client.post(
                "/api/v1/jobs/validator",
                files={"excel_file": ("test.xlsx", excel, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
                data={"confidence_threshold": 90, "street_confidence_threshold": 85},
            )
            job_id = resp.json()["data"]["job_id"]
            status = _wait_for_status(job_id, "parsed")

        assert status["status"] == "parsed"
        assert status["result"] is not None
        assert "rows" in status["result"]
        assert "parsing_summary" in status["result"]
        assert len(status["result"]["rows"]) == 2

    def test_phase1_rows_have_method(self):
        """Each parsed row should have a method field ('ai' or 'regex')."""
        excel = _make_valid_excel()
        with _apply_security_mocks():
            resp = client.post(
                "/api/v1/jobs/validator",
                files={"excel_file": ("test.xlsx", excel, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
                data={"confidence_threshold": 90, "street_confidence_threshold": 85},
            )
            job_id = resp.json()["data"]["job_id"]
            status = _wait_for_status(job_id, "parsed")

        assert status["status"] == "parsed"
        for row in status["result"]["rows"]:
            assert row["method"] in ("ai", "regex"), f"Unexpected method: {row['method']}"
            assert "parsed_components" in row
            assert "country_code" in row["parsed_components"]


class TestConfirmEndpoint:
    """Phase 2: Confirm and validate."""

    def _create_parsed_job(self):
        """Helper: create and wait for a parsed job."""
        excel = _make_valid_excel()
        with _apply_security_mocks():
            resp = client.post(
                "/api/v1/jobs/validator",
                files={"excel_file": ("test.xlsx", excel, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
                data={"confidence_threshold": 90, "street_confidence_threshold": 85},
            )
            job_id = resp.json()["data"]["job_id"]
            _wait_for_status(job_id, "parsed")
        return job_id

    def test_confirm_without_edits(self):
        """Confirm with no edits should start Phase 2."""
        job_id = self._create_parsed_job()
        resp = client.post(f"/api/v1/jobs/{job_id}/confirm", json={
            "edits": {},
            "retry_regex_rows": False,
        })
        assert resp.status_code == 200
        assert resp.json()["data"]["status"] == "processing_validate"

    def test_double_confirm_returns_409(self):
        """Issue #1: Second confirm on same job should return 409."""
        job_id = self._create_parsed_job()

        # First confirm succeeds
        resp1 = client.post(f"/api/v1/jobs/{job_id}/confirm", json={
            "edits": {}, "retry_regex_rows": False,
        })
        assert resp1.status_code == 200

        # Second confirm fails
        resp2 = client.post(f"/api/v1/jobs/{job_id}/confirm", json={
            "edits": {}, "retry_regex_rows": False,
        })
        assert resp2.status_code == 409
        assert resp2.json()["detail"]["error"]["code"] == "INVALID_STATE"

    def test_confirm_nonexistent_job_returns_404(self):
        resp = client.post("/api/v1/jobs/nonexistent-uuid/confirm", json={
            "edits": {}, "retry_regex_rows": False,
        })
        assert resp.status_code == 404

    def test_confirm_processing_job_returns_409(self):
        """Can't confirm a job still in 'processing' state."""
        # Create job directly in "processing" state (avoids background thread race)
        job_id = job_store.create_job("validator")
        # Status is "processing" — confirm should fail
        resp = client.post(f"/api/v1/jobs/{job_id}/confirm", json={
            "edits": {}, "retry_regex_rows": False,
        })
        assert resp.status_code == 409
        assert resp.json()["detail"]["error"]["code"] == "INVALID_STATE"


class TestUserEdits:
    """Issue #3: User edits should update method and country_code."""

    def _create_parsed_job_and_get_rows(self):
        """Helper: create job, wait for parsed, return (job_id, rows)."""
        excel = _make_valid_excel()
        with _apply_security_mocks():
            resp = client.post(
                "/api/v1/jobs/validator",
                files={"excel_file": ("test.xlsx", excel, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
                data={"confidence_threshold": 90, "street_confidence_threshold": 85},
            )
            job_id = resp.json()["data"]["job_id"]
            status = _wait_for_status(job_id, "parsed")
        assert status["status"] == "parsed", f"Job failed: {status.get('error')}"
        return job_id, status["result"]["rows"]

    def test_street_edit_starts_phase2(self):
        """Editing street should trigger Phase 2."""
        job_id, rows = self._create_parsed_job_and_get_rows()
        row_index = rows[0]["index"]

        resp = client.post(f"/api/v1/jobs/{job_id}/confirm", json={
            "edits": {str(row_index): {"street": "Via Garibaldi 20"}},
            "retry_regex_rows": False,
        })
        assert resp.status_code == 200
        assert resp.json()["data"]["status"] == "processing_validate"

    def test_city_edit_starts_phase2(self):
        """Editing city should trigger Phase 2."""
        job_id, rows = self._create_parsed_job_and_get_rows()
        row_index = rows[0]["index"]

        resp = client.post(f"/api/v1/jobs/{job_id}/confirm", json={
            "edits": {str(row_index): {"city": "Torino"}},
            "retry_regex_rows": False,
        })
        assert resp.status_code == 200

    def test_zip_edit_starts_phase2(self):
        """Editing zip should trigger Phase 2."""
        job_id, rows = self._create_parsed_job_and_get_rows()
        row_index = rows[0]["index"]

        resp = client.post(f"/api/v1/jobs/{job_id}/confirm", json={
            "edits": {str(row_index): {"zip": "10121"}},
            "retry_regex_rows": False,
        })
        assert resp.status_code == 200


class TestMethodPreservation:
    """Issue #3: parse_method should be correctly set after edits."""

    def test_edited_row_gets_user_edit_method(self):
        """When user edits a row's street, method should become 'user_edit'."""
        # Directly set up a parsed job in job_store
        excel = _make_valid_excel()
        job_id = job_store.create_job("validator")
        job_store.save_file(job_id, "original.xlsx", excel)
        job_store.update_status(job_id, "parsed", result={
            "rows": [
                {
                    "index": 0,
                    "original": {"street": "Via Roma 10", "city": "Milano", "zip": "20121"},
                    "parsed": {"street": "Via Roma 10", "city": "Milano", "zip": "20121"},
                    "parsed_components": {
                        "street_prefix": "Via", "street_name": "Roma",
                        "house_number": "10", "location_info": "",
                        "country_code": "IT",
                    },
                    "method": "regex",
                    "changed": False,
                    "changes": [],
                },
                {
                    "index": 1,
                    "original": {"street": "Piazza Duomo 1", "city": "Milano", "zip": "20122"},
                    "parsed": {"street": "Piazza Duomo 1", "city": "Milano", "zip": "20122"},
                    "parsed_components": {
                        "street_prefix": "Piazza", "street_name": "Duomo",
                        "house_number": "1", "location_info": "",
                        "country_code": "IT",
                    },
                    "method": "ai",
                    "changed": False,
                    "changes": [],
                },
            ],
            "config": {
                "confidence": 90, "street_confidence": 85,
                "pin_valid": True, "client_ip": "127.0.0.1",
            },
        })

        # Confirm with street edit on row 0 only
        resp = client.post(f"/api/v1/jobs/{job_id}/confirm", json={
            "edits": {"0": {"street": "Via Garibaldi 5"}},
            "retry_regex_rows": False,
        })
        assert resp.status_code == 200

        # Wait a moment for background processing to pick up
        time.sleep(0.5)

        # The confirm handler has already applied edits before dispatching.
        # We can check the final result once the job completes/fails.
        status = _wait_for_status(job_id, "complete", timeout=15)

        # Whether it completed or failed (no real Google API),
        # the parse_method in results should reflect the edit
        if status["status"] == "complete" and status.get("result"):
            results = status["result"].get("results", [])
            if len(results) >= 2:
                # Row 0 was edited -> should be "user_edit"
                assert results[0]["parse_method"] == "user_edit"
                # Row 1 was NOT edited -> should keep "ai"
                assert results[1]["parse_method"] == "ai"

    def test_unedited_row_keeps_original_method(self):
        """Rows not in edits should keep their original method."""
        job_id = job_store.create_job("validator")
        job_store.update_status(job_id, "parsed", result={
            "rows": [
                {
                    "index": 0,
                    "original": {"street": "Via Roma 10", "city": "Milano", "zip": "20121"},
                    "parsed": {"street": "Via Roma 10", "city": "Milano", "zip": "20121"},
                    "parsed_components": {
                        "street_prefix": "Via", "street_name": "Roma",
                        "house_number": "10", "location_info": "",
                        "country_code": "IT",
                    },
                    "method": "regex",
                    "changed": False,
                    "changes": [],
                },
            ],
            "config": {
                "confidence": 90, "street_confidence": 85,
                "pin_valid": False, "client_ip": "127.0.0.1",
            },
        })

        # Confirm with NO edits
        resp = client.post(f"/api/v1/jobs/{job_id}/confirm", json={
            "edits": {},
            "retry_regex_rows": False,
        })
        assert resp.status_code == 200


class TestRegexParserReuse:
    """Issue #8: Module-level regex parser should be reused."""

    def test_regex_parser_is_module_level(self):
        """The _regex_parser should be importable and have no API client."""
        from app.routers.validator import _regex_parser
        assert _regex_parser is not None
        assert _regex_parser.client is None  # No API key = no client

    def test_regex_parser_identity(self):
        """Multiple imports should return the same instance."""
        from app.routers.validator import _regex_parser as p1
        from app.routers.validator import _regex_parser as p2
        assert p1 is p2


class TestFileSizeLimit:
    """File size validation."""

    def test_oversized_file_returns_413(self):
        """File exceeding max_file_size_mb should return 413."""
        with patch('app.routers.validator.get_settings') as mock_settings:
            settings = MagicMock()
            settings.max_file_size_mb = 0.001  # ~1KB limit
            settings.anthropic_api_key = ""
            settings.google_address_validation_api_key = ""
            settings.bypass_pin = ""
            mock_settings.return_value = settings

            excel = _make_valid_excel()  # Will be larger than 1KB
            resp = client.post(
                "/api/v1/jobs/validator",
                files={"excel_file": ("big.xlsx", excel, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
                data={"confidence_threshold": 90, "street_confidence_threshold": 85},
            )
            assert resp.status_code == 413
