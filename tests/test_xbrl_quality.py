from src.processing.quality import MISSING_VALUE, add_quality_flag


def test_add_quality_flag_does_not_duplicate_existing_flag() -> None:
    assert add_quality_flag((MISSING_VALUE,), MISSING_VALUE) == (MISSING_VALUE,)


def test_add_quality_flag_appends_new_flag() -> None:
    assert add_quality_flag((), MISSING_VALUE) == (MISSING_VALUE,)
