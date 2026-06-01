"""Shared SEC ingestion error types."""


class SecIngestionError(Exception):
    """Base class for SEC ingestion failures."""


class SecConfigurationError(SecIngestionError):
    """Raised when SEC ingestion is missing required configuration."""


class SecHttpError(SecIngestionError):
    """Raised when an SEC HTTP request fails."""

    def __init__(self, message: str, *, status_code: int | None = None, url: str | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.url = url


class SecJsonError(SecIngestionError):
    """Raised when an SEC response cannot be parsed as JSON."""


class SecPayloadError(SecIngestionError):
    """Raised when an SEC payload is missing expected fields."""


class TickerNotFoundError(SecIngestionError):
    """Raised when a ticker cannot be resolved to a CIK."""


class FilingNotFoundError(SecIngestionError):
    """Raised when a requested SEC filing cannot be found."""
