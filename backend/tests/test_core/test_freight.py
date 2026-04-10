"""Tests for app.core.freight — upload_freight_file, send_freight_request."""
import re
from unittest.mock import patch, MagicMock

from app.core.freight import upload_freight_file, send_freight_request, generate_reference_id


class TestGenerateReferenceId:
    def test_format(self):
        ref = generate_reference_id()
        assert ref.startswith("FRQ-")
        assert len(ref) == 12

    def test_unique(self):
        ids = {generate_reference_id() for _ in range(100)}
        assert len(ids) == 100


class TestUploadFreightFile:
    @patch("app.core.freight.get_supabase_client")
    def test_returns_signed_url(self, mock_client_fn):
        mock_client = MagicMock()
        mock_client_fn.return_value = mock_client
        mock_client.storage.from_.return_value.upload.return_value = None
        mock_client.storage.from_.return_value.create_signed_url.return_value = {
            "signedURL": "https://xyz.supabase.co/storage/v1/object/sign/freight-requests/FRQ-abc12345/test.xlsx?token=abc"
        }

        url = upload_freight_file(b"fake-file-content", "test.xlsx", "FRQ-abc12345")
        assert "supabase.co" in url
        assert "FRQ-abc12345" in url
        mock_client.storage.from_.assert_called_with("freight-requests")

    @patch("app.core.freight.get_supabase_client")
    def test_raises_on_client_none(self, mock_client_fn):
        mock_client_fn.return_value = None
        try:
            upload_freight_file(b"content", "test.xlsx", "FRQ-abc12345")
            assert False, "Should have raised"
        except RuntimeError as e:
            assert "unavailable" in str(e).lower()


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

    @patch("app.core.freight.requests.post")
    @patch("app.core.freight.get_secret", return_value="https://hooks.zapier.com/test")
    def test_successful_request(self, mock_secret, mock_post):
        mock_post.return_value = MagicMock(status_code=200)
        success, message = send_freight_request(
            file_url="https://storage.example.com/file.xlsx",
            filename="shipments.xlsx",
            reference_id="FRQ-abc12345",
            sender_address=self.SENDER,
            notes="urgente",
            contact_email="mario@example.com",
            contact_phone="0212345678",
        )
        assert success is True
        assert "inviata" in message.lower()
        payload = mock_post.call_args[1]["json"]
        assert payload["event_type"] == "freight_request"
        assert payload["reference_id"] == "FRQ-abc12345"
        assert payload["subject"] == "FREIGHT REQUEST - FRQ-abc12345"
        assert payload["file_url"] == "https://storage.example.com/file.xlsx"
        assert payload["filename"] == "shipments.xlsx"
        assert payload["from_company"] == "Acme Srl"
        assert payload["contact_email"] == "mario@example.com"
        assert payload["contact_phone"] == "0212345678"
        assert payload["notes"] == "urgente"
        assert payload["has_notes"] is True

    @patch("app.core.freight.requests.post")
    @patch("app.core.freight.get_secret", return_value="https://hooks.zapier.com/test")
    def test_null_notes_and_phone(self, mock_secret, mock_post):
        mock_post.return_value = MagicMock(status_code=200)
        success, _ = send_freight_request(
            file_url="https://example.com/f.xlsx", filename="f.xlsx",
            reference_id="FRQ-abc12345", sender_address=self.SENDER,
            notes=None, contact_email="test@example.com", contact_phone=None,
        )
        assert success is True
        payload = mock_post.call_args[1]["json"]
        assert payload["has_notes"] is False
        assert payload["notes"] == ""
        assert payload["contact_phone"] == ""

    @patch("app.core.freight.requests.post", side_effect=Exception("connection error"))
    @patch("app.core.freight.get_secret", return_value="https://hooks.zapier.com/test")
    def test_zapier_failure(self, mock_secret, mock_post):
        success, message = send_freight_request(
            file_url="https://example.com/f.xlsx", filename="f.xlsx",
            reference_id="FRQ-abc12345", sender_address=self.SENDER,
            notes=None, contact_email="test@example.com",
        )
        assert success is False

    @patch("app.core.freight.get_secret", return_value=None)
    def test_no_webhook_url(self, mock_secret):
        success, message = send_freight_request(
            file_url="https://example.com/f.xlsx", filename="f.xlsx",
            reference_id="FRQ-abc12345", sender_address=self.SENDER,
            notes=None, contact_email="test@example.com",
        )
        assert success is False
        assert "configurato" in message.lower()

    @patch("app.core.freight.requests.post")
    @patch("app.core.freight.get_secret", return_value="https://hooks.zapier.com/test")
    def test_timestamp_format(self, mock_secret, mock_post):
        mock_post.return_value = MagicMock(status_code=200)
        send_freight_request(
            file_url="https://example.com/f.xlsx", filename="f.xlsx",
            reference_id="FRQ-abc12345", sender_address=self.SENDER,
            notes=None, contact_email="test@example.com",
        )
        payload = mock_post.call_args[1]["json"]
        assert re.match(r"\d{2}/\d{2}/\d{4} \d{2}:\d{2}", payload["timestamp"])
