import pytest
from app.core.italian_db import ItalianDB, get_italian_db


class TestItalianDB:

    def setup_method(self):
        self.db = ItalianDB()
        self.db.load()

    def test_loads_data(self):
        assert len(self.db._all_caps) > 4000

    def test_milano_caps(self):
        caps = self.db.get_valid_caps_for_comune("Milano", "MI")
        assert "20121" in caps
        assert "20122" in caps
        assert len(caps) >= 30  # Milano has 38 CAPs

    def test_roma_caps(self):
        caps = self.db.get_valid_caps_for_comune("Roma", "RM")
        assert "00187" in caps
        assert "00118" in caps
        assert len(caps) >= 50  # Roma has 73 CAPs

    def test_small_town_single_cap(self):
        caps = self.db.get_valid_caps_for_comune("Casalpusterlengo", "LO")
        assert "26841" in caps
        assert len(caps) == 1

    def test_assago_cap(self):
        caps = self.db.get_valid_caps_for_comune("Assago", "MI")
        assert "20057" in caps

    def test_is_valid_cap(self):
        assert self.db.is_valid_cap("20121") is True
        assert self.db.is_valid_cap("00187") is True
        assert self.db.is_valid_cap("99999") is False
        assert self.db.is_valid_cap("20199") is False

    def test_validate_cap_correct(self):
        valid, msg = self.db.validate_cap_for_comune("20121", "Milano", "MI")
        assert valid is True

    def test_validate_cap_wrong_for_comune(self):
        valid, msg = self.db.validate_cap_for_comune("20199", "Milano", "MI")
        assert valid is False
        assert "not valid" in msg.lower() or "20121" in msg

    def test_validate_cap_wrong_comune(self):
        """20057 is Assago, not Milano centro."""
        valid, msg = self.db.validate_cap_for_comune("20057", "Milano", "MI")
        assert valid is False

    def test_validate_cap_for_provincia_correct(self):
        valid, msg = self.db.validate_cap_for_provincia("20121", "MI")
        assert valid is True

    def test_validate_cap_for_provincia_wrong(self):
        valid, msg = self.db.validate_cap_for_provincia("10121", "MI")
        assert valid is False
        assert "TO" in msg  # 10121 is Torino

    def test_validate_nonexistent_cap(self):
        valid, msg = self.db.validate_cap_for_provincia("99999", "MI")
        assert valid is False
        assert "does not exist" in msg.lower()

    def test_validate_empty_inputs(self):
        valid, _ = self.db.validate_cap_for_comune("", "Milano")
        assert valid is True  # can't validate, assume OK
        valid, _ = self.db.validate_cap_for_comune("20121", "")
        assert valid is True

    def test_get_comuni_for_cap(self):
        comuni = self.db.get_comuni_for_cap("20121")
        names = [c["denominazione_ita"] for c in comuni]
        assert "Milano" in names

    def test_alternate_name(self):
        """Comuni with alternate names should be findable by both."""
        caps = self.db.get_valid_caps_for_comune("Abano Terme", "PD")
        assert len(caps) >= 1

    def test_singleton(self):
        db1 = get_italian_db()
        db2 = get_italian_db()
        assert db1 is db2


class TestProvinceValidation:

    def setup_method(self):
        self.db = ItalianDB()
        self.db.load()

    def test_rome_province(self):
        valid, _ = self.db.validate_cap_for_provincia("00187", "RM")
        assert valid is True

    def test_torino_province(self):
        valid, _ = self.db.validate_cap_for_provincia("10123", "TO")
        assert valid is True

    def test_cross_province(self):
        """Torino CAP should not validate for Milano province."""
        valid, msg = self.db.validate_cap_for_provincia("10121", "MI")
        assert valid is False
