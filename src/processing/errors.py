"""XBRL processing error types."""


class XbrlProcessingError(Exception):
    """Base class for XBRL processing failures."""


class XbrlPayloadError(XbrlProcessingError):
    """Raised when a companyfacts payload cannot be normalized."""


class InlineXbrlExtractionError(XbrlProcessingError):
    """Raised when an Inline XBRL filing cannot be loaded or extracted."""
