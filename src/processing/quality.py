"""Quality flag constants for normalized XBRL facts."""

AMBIGUOUS_UNIT = "ambiguous_unit"
DUPLICATE_FACT = "duplicate_fact"
INCONSISTENT_PERIOD = "inconsistent_period"
INVALID_DATE = "invalid_date"
MISSING_ACCESSION_NUMBER = "missing_accession_number"
MISSING_END_DATE = "missing_end_date"
MISSING_FORM = "missing_form"
MISSING_VALUE = "missing_value"
NON_NUMERIC_VALUE = "non_numeric_value"
UNSUPPORTED_FORM = "unsupported_form"


def add_quality_flag(flags: tuple[str, ...], flag: str) -> tuple[str, ...]:
    """Append a quality flag without duplicating it."""
    if flag in flags:
        return flags
    return (*flags, flag)
