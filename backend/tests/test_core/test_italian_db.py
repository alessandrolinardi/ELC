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


class TestIsGenericCap:

    def setup_method(self):
        self.db = ItalianDB()
        self.db.load()

    def test_genova_generic(self):
        assert self.db._is_generic_cap("16100") is True

    def test_milano_generic(self):
        assert self.db._is_generic_cap("20100") is True

    def test_not_generic_pattern(self):
        """12300 ends in 00 but not 100, so it is not a generic CAP."""
        assert self.db._is_generic_cap("12300") is False

    def test_no_specific_caps_with_prefix(self):
        """99100 has the right suffix but no specific CAPs share prefix 99."""
        assert self.db._is_generic_cap("99100") is False

    def test_specific_cap_not_generic(self):
        assert self.db._is_generic_cap("20121") is False


class TestValidateCapForProvinciaWithRegions:

    def setup_method(self):
        self.db = ItalianDB()
        self.db.load()

    def test_region_name_lombardia(self):
        valid, _ = self.db.validate_cap_for_provincia("20123", "Lombardia")
        assert valid is True

    def test_region_name_typo(self):
        """Fuzzy match should handle a single-char typo like 'Lombrardia'."""
        valid, _ = self.db.validate_cap_for_provincia("20123", "Lombrardia")
        assert valid is True

    def test_region_emilia_romagna_space(self):
        """Space vs hyphen should not matter thanks to normalisation."""
        valid, _ = self.db.validate_cap_for_provincia("40125", "Emilia Romagna")
        assert valid is True

    def test_region_friuli_venezia_giulia(self):
        valid, _ = self.db.validate_cap_for_provincia("34121", "Friuli Venezia Giulia")
        assert valid is True

    def test_region_valle_daosta_bilingual(self):
        valid, _ = self.db.validate_cap_for_provincia("11100", "Valle d'Aosta")
        assert valid is True

    def test_wrong_region(self):
        valid, _ = self.db.validate_cap_for_provincia("20123", "Toscana")
        assert valid is False


class TestValidateCapForComuneGeneric:

    def setup_method(self):
        self.db = ItalianDB()
        self.db.load()

    def test_generic_cap_genova(self):
        valid, _ = self.db.validate_cap_for_comune("16100", "Genova", "GE")
        assert valid is True

    def test_generic_cap_milano(self):
        valid, _ = self.db.validate_cap_for_comune("20100", "Milano", "MI")
        assert valid is True

    def test_generic_cap_wrong_city(self):
        valid, _ = self.db.validate_cap_for_comune("16100", "Milano", "MI")
        assert valid is False
