"""Tests for app.core.freight — send_freight_request with base64-encoded file."""
import base64
import re
from unittest.mock import patch, MagicMock

from app.core.freight import send_freight_request, generate_reference_id


class TestGenerateReferenceId:
    def test_format(self):
        ref = generate_reference_id()
        assert ref.startswith("FRQ-")
        assert len(ref) == 12

    def test_unique(self):
        ids = {generate_reference_id() for _ in range(100)}
        assert len(ids) == 100


class TestSendFreightRequest:
    SENDER = {
        "from_name": "Mario Rossi",
        "from_company": "Acme Srl",
        "from_street1": "Via Roma 1",
        "from_city": "Milano",
        "from_state": "MI",
        "from_zip": "20121",
        "from_country": "IT",
        "from_phone": "0212345678",
    }

    FILE_BYTES = b"fake-excel-content-here"

    @patch("app.core.freight.requests.post")
    @patch("app.core.freight.get_secret", return_value="https://hooks.zapier.com/test")
    def test_successful_request(self, mock_secret, mock_post):
        mock_post.return_value = MagicMock(status_code=200)
        success, message = send_freight_request(
            file_bytes=self.FILE_BYTES,
            filename="shipments.xlsx",
            reference_id="FRQ-abc12345",
            sender_address=self.SENDER,
            notes="urgente",
        )
        assert success is True
        assert "inviata" in message.lower()
        payload = mock_post.call_args[1]["json"]
        assert payload["event_type"] == "freight_request"
        assert payload["reference_id"] == "FRQ-abc12345"
        assert payload["subject"] == "FREIGHT REQUEST - FRQ-abc12345"
        assert payload["filename"] == "shipments.xlsx"
        assert payload["from_company"] == "Acme Srl"
        assert payload["notes"] == "urgente"
        assert payload["has_notes"] is True

    @patch("app.core.freight.requests.post")
    @patch("app.core.freight.get_secret", return_value="https://hooks.zapier.com/test")
    def test_file_is_base64_encoded(self, mock_secret, mock_post):
        mock_post.return_value = MagicMock(status_code=200)
        send_freight_request(
            file_bytes=self.FILE_BYTES,
            filename="test.xlsx",
            reference_id="FRQ-abc12345",
            sender_address=self.SENDER,
            notes=None,
        )
        payload = mock_post.call_args[1]["json"]
        assert "file_base64" in payload
        decoded = base64.b64decode(payload["file_base64"])
        assert decoded == self.FILE_BYTES

    @patch("app.core.freight.requests.post")
    @patch("app.core.freight.get_secret", return_value="https://hooks.zapier.com/test")
    def test_null_notes(self, mock_secret, mock_post):
        mock_post.return_value = MagicMock(status_code=200)
        success, _ = send_freight_request(
            file_bytes=self.FILE_BYTES, filename="f.xlsx",
            reference_id="FRQ-abc12345", sender_address=self.SENDER, notes=None,
        )
        assert success is True
        payload = mock_post.call_args[1]["json"]
        assert payload["has_notes"] is False
        assert payload["notes"] == ""

    @patch("app.core.freight.requests.post", side_effect=Exception("connection error"))
    @patch("app.core.freight.get_secret", return_value="https://hooks.zapier.com/test")
    def test_zapier_failure(self, mock_secret, mock_post):
        success, message = send_freight_request(
            file_bytes=self.FILE_BYTES, filename="f.xlsx",
            reference_id="FRQ-abc12345", sender_address=self.SENDER, notes=None,
        )
        assert success is False

    @patch("app.core.freight.get_secret", return_value=None)
    def test_no_webhook_url(self, mock_secret):
        success, message = send_freight_request(
            file_bytes=self.FILE_BYTES, filename="f.xlsx",
            reference_id="FRQ-abc12345", sender_address=self.SENDER, notes=None,
        )
        assert success is False
        assert "configurato" in message.lower()

    @patch("app.core.freight.requests.post")
    @patch("app.core.freight.get_secret", return_value="https://hooks.zapier.com/test")
    def test_timestamp_format(self, mock_secret, mock_post):
        mock_post.return_value = MagicMock(status_code=200)
        send_freight_request(
            file_bytes=self.FILE_BYTES, filename="f.xlsx",
            reference_id="FRQ-abc12345", sender_address=self.SENDER, notes=None,
        )
        payload = mock_post.call_args[1]["json"]
        assert re.match(r"\d{2}/\d{2}/\d{4} \d{2}:\d{2}", payload["timestamp"])
