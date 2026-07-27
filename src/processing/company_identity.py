"""Shared company-identity comparisons for SEC CIK values."""


def same_cik(left: str, right: str) -> bool:
    """Compare CIKs while tolerating SEC leading-zero formatting."""
    return left.lstrip("0") == right.lstrip("0")
