"""Named errors raised by the filing retrieval pipeline."""


class RetrievalError(RuntimeError):
    """Base class for retrieval-pipeline failures."""


class RetrievalConfigurationError(RetrievalError):
    """Retrieval storage or model configuration is unusable."""


class RetrievalCompanyNotFoundError(RetrievalError):
    """The requested company is not present in local storage."""


class ActiveFilingsNotFoundError(RetrievalError):
    """No active 10-K or 10-Q filings are available for indexing."""


class FilingSourceMissingError(RetrievalError):
    """A required active filing does not have a readable local source file."""


class FilingParseError(RetrievalError):
    """A local SEC filing could not be parsed into readable text."""


class EmptyFilingTextError(RetrievalError):
    """A parsed filing contained no indexable visible text."""


class InvalidRetrievalQueryError(RetrievalError):
    """A retrieval query is empty or outside supported limits."""


class RetrievalIndexNotFoundError(RetrievalError):
    """No successful retrieval generation exists for the company."""


class RetrievalIndexMismatchError(RetrievalError):
    """Stored chunks and index artifacts do not describe the same generation."""


class RetrievalIndexCorruptError(RetrievalError):
    """A persisted retrieval artifact could not be loaded."""
