from services.normalization import normalize_phone, normalize_text


def test_normalize_text_trims_casefolds_collapses_whitespace_and_strips_punctuation():
    assert normalize_text("  123 Elm Street,  Apt 4.  ") == "123 elm street apt 4"
    assert normalize_text("Jane") == normalize_text("  jane  ")
    assert normalize_text("O'Brien") == "obrien"


def test_normalize_text_does_not_expand_abbreviations():
    # Deliberately basic — "St" and "Street" are NOT treated as equivalent.
    assert normalize_text("123 Elm St") != normalize_text("123 Elm Street")


def test_normalize_phone_canonical_e164_digits():
    # 10 digits = NANP without the country code -> "1" added (stored customers are E.164)
    assert normalize_phone("(555) 123-4567") == "15551234567"
    assert normalize_phone("+1 555-123-4567") == "15551234567"
    assert normalize_phone("555.123.4567") == "15551234567"
    assert normalize_phone("1-555-123-4567") == "15551234567"
    assert normalize_phone("001 555 123 4567") == "15551234567"
    assert normalize_phone("+15551234567") == "15551234567"


def test_normalize_phone_keeps_other_country_codes():
    assert normalize_phone("+44 20 7946 0000") == "442079460000"
    assert normalize_phone("") == ""
