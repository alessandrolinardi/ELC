"""
Italian municipalities database for address validation.
Loads gi_comuni_cap.json for exact CAP-per-comune validation.
"""
import json
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_db = None  # singleton


class ItalianDB:
    """Lookup service for Italian municipalities, CAPs, and provinces."""

    def __init__(self):
        self._comuni_by_name: dict[str, list[dict]] = {}  # lowercase name → list of records
        self._caps_by_comune: dict[str, set[str]] = {}    # "nome|provincia" → set of CAPs
        self._all_caps: set[str] = set()                   # all valid Italian CAPs
        self._cap_to_comuni: dict[str, list[dict]] = {}    # CAP → list of comuni with that CAP
        self._province: dict[str, dict] = {}               # sigla → province info
        self._loaded = False

    def load(self):
        """Load the database from JSON files."""
        if self._loaded:
            return

        data_dir = Path(__file__).parent.parent.parent / "data"

        # Load comuni + CAP
        comuni_file = data_dir / "gi_comuni_cap.json"
        try:
            with open(comuni_file, 'r') as f:
                records = json.load(f)

            for r in records:
                cap = r.get("cap", "")
                nome = r.get("denominazione_ita", "")
                nome_alt = r.get("denominazione_ita_altra", "")
                provincia = r.get("sigla_provincia", "")

                if not cap or not nome:
                    continue

                self._all_caps.add(cap)

                # Index by name (lowercase), avoid duplicates
                names_to_index = {nome.lower()}
                if nome_alt and nome_alt.lower() != nome.lower():
                    names_to_index.add(nome_alt.lower())
                for name in names_to_index:
                    if name:
                        if name not in self._comuni_by_name:
                            self._comuni_by_name[name] = []
                        self._comuni_by_name[name].append(r)

                # Index CAPs by comune+provincia
                key = f"{nome.lower()}|{provincia.upper()}"
                if key not in self._caps_by_comune:
                    self._caps_by_comune[key] = set()
                self._caps_by_comune[key].add(cap)

                # Also index with alternate name
                if nome_alt and nome_alt.lower() != nome.lower():
                    key_alt = f"{nome_alt.lower()}|{provincia.upper()}"
                    if key_alt not in self._caps_by_comune:
                        self._caps_by_comune[key_alt] = set()
                    self._caps_by_comune[key_alt].add(cap)

                # Index comuni by CAP
                if cap not in self._cap_to_comuni:
                    self._cap_to_comuni[cap] = []
                self._cap_to_comuni[cap].append(r)

            logger.info(f"Loaded {len(records)} comuni/CAP records, "
                        f"{len(self._all_caps)} unique CAPs, "
                        f"{len(self._comuni_by_name)} unique names")

        except (json.JSONDecodeError, IOError, FileNotFoundError) as e:
            logger.error(f"Could not load comuni database: {e}")

        # Load province
        province_file = data_dir / "gi_province.json"
        try:
            with open(province_file, 'r') as f:
                provinces = json.load(f)
            for p in provinces:
                sigla = p.get("sigla_provincia", "")
                if sigla:
                    self._province[sigla.upper()] = p
            logger.info(f"Loaded {len(self._province)} provinces")
        except (json.JSONDecodeError, IOError, FileNotFoundError) as e:
            logger.warning(f"Could not load province database: {e}")

        self._loaded = True

    def is_valid_cap(self, cap: str) -> bool:
        """Check if a CAP exists in Italy."""
        self.load()
        return cap in self._all_caps

    def get_valid_caps_for_comune(self, comune: str, provincia: str = "") -> set[str]:
        """Get all valid CAPs for a given comune (and optionally provincia)."""
        self.load()

        comune_lower = comune.lower().strip()

        if provincia:
            key = f"{comune_lower}|{provincia.upper().strip()}"
            if key in self._caps_by_comune:
                return self._caps_by_comune[key].copy()

        # Try without provincia — collect all CAPs for comuni with this name
        records = self._comuni_by_name.get(comune_lower, [])
        caps = set()
        for r in records:
            caps.add(r.get("cap", ""))
        return caps

    def validate_cap_for_comune(self, cap: str, comune: str,
                                  provincia: str = "") -> tuple[bool, str]:
        """
        Validate if a CAP is correct for a given comune.

        Returns:
            (is_valid, message)
        """
        self.load()

        if not cap or not comune:
            return True, ""  # can't validate, assume OK

        valid_caps = self.get_valid_caps_for_comune(comune, provincia)

        if not valid_caps:
            # Comune not found in database — can't validate
            return True, f"Comune '{comune}' not in database"

        if cap in valid_caps:
            return True, f"CAP {cap} valid for {comune}"

        # CAP not valid — suggest correct ones
        if len(valid_caps) == 1:
            correct = next(iter(valid_caps))
            return False, f"CAP {cap} not valid for {comune} (should be {correct})"
        else:
            sorted_caps = sorted(valid_caps)
            return False, f"CAP {cap} not valid for {comune} (valid: {', '.join(sorted_caps[:5])})"

    def validate_cap_for_provincia(self, cap: str, provincia: str) -> tuple[bool, str]:
        """
        Validate if a CAP belongs to a given provincia.
        More accurate than the old prefix-based check.
        """
        self.load()

        if not cap or not provincia:
            return True, ""

        # Find all comuni with this CAP
        comuni = self._cap_to_comuni.get(cap, [])
        if not comuni:
            if cap in self._all_caps:
                return True, ""  # CAP exists but no province match data
            return False, f"CAP {cap} does not exist in Italy"

        # Check if any comune with this CAP is in the given provincia
        for r in comuni:
            if r.get("sigla_provincia", "").upper() == provincia.upper().strip():
                return True, f"CAP {cap} matches province {provincia}"

        # CAP exists but belongs to different provincia
        actual_provinces = set(r.get("sigla_provincia", "") for r in comuni)
        return False, f"CAP {cap} belongs to province {', '.join(sorted(actual_provinces))}, not {provincia}"

    def get_comune_info(self, comune: str) -> list[dict]:
        """Get all records for a comune name."""
        self.load()
        return list(self._comuni_by_name.get(comune.lower().strip(), []))

    def get_comuni_for_cap(self, cap: str) -> list[dict]:
        """Get all comuni that have a given CAP."""
        self.load()
        return list(self._cap_to_comuni.get(cap, []))

    def get_province_info(self, sigla: str) -> Optional[dict]:
        """Get province info by sigla."""
        self.load()
        return self._province.get(sigla.upper().strip())


def get_italian_db() -> ItalianDB:
    """Get singleton instance of the Italian DB."""
    global _db
    if _db is None:
        _db = ItalianDB()
    return _db
