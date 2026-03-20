from app.core.models import ParsedAddress, ValidationOutcome


def test_parsed_address_street_with_number():
    addr = ParsedAddress(
        street_prefix="Via",
        street_name="Roma",
        house_number="11/A",
        location_info="",
        country_code="IT",
        confidence="high"
    )
    assert addr.street_with_number == "Via Roma 11/A"


def test_parsed_address_street_without_number():
    addr = ParsedAddress(
        street_prefix="Via",
        street_name="Roma",
        house_number="11/A",
        location_info="",
        country_code="IT",
        confidence="high"
    )
    assert addr.street_without_number == "Via Roma"


def test_parsed_address_full_street_with_location():
    addr = ParsedAddress(
        street_prefix="Via",
        street_name="Roma",
        house_number="1",
        location_info="C.C. Le Grange",
        country_code="IT",
        confidence="high"
    )
    assert addr.full_street == "C.C. Le Grange Via Roma 1"


def test_parsed_address_empty_house_number():
    addr = ParsedAddress(
        street_prefix="Via",
        street_name="Roma",
        house_number="",
        location_info="",
        country_code="IT",
        confidence="high"
    )
    assert addr.street_with_number == "Via Roma"
    assert addr.street_without_number == "Via Roma"


def test_parsed_address_snc():
    addr = ParsedAddress(
        street_prefix="Via",
        street_name="Roma",
        house_number="SNC",
        location_info="",
        country_code="IT",
        confidence="high"
    )
    assert addr.street_with_number == "Via Roma SNC"


def test_validation_outcome_defaults():
    outcome = ValidationOutcome(
        status="valid",
        action="ACCEPT",
        input_zip="20121",
        output_zip="20121",
        zip_confirmed=True,
        zip_corrected=False,
        input_street="Via Roma 10",
        output_street="Via Roma",
        street_confirmed=True,
        street_corrected=False,
        silent_correction=False,
        house_number="10",
        granularity="PREMISE",
        address_complete=True,
        reasons=[],
        formatted_address="Via Roma, 10, 20121 Milano MI, Italia",
        location_info=""
    )
    assert outcome.status == "valid"
    assert outcome.zip_corrected is False
