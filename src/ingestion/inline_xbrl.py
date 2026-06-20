"""Load SEC Inline XBRL filings and hand models to processing code."""

from __future__ import annotations

import logging
from datetime import date

from arelle import Cntlr

from src.processing.errors import InlineXbrlExtractionError
from src.processing.inline_xbrl import (
    InlineXbrlExtractionResult,
    normalize_inline_xbrl_model,
)


def get_inline_xbrl_facts(
    document_url: str,
    *,
    cik: str,
    entity_name: str | None,
    form: str,
    filing_date: date,
    accession_number: str,
    fiscal_year: int | None,
    fiscal_period: str | None,
    sec_user_agent: str,
) -> InlineXbrlExtractionResult:
    """Load one SEC filing with Arelle and return normalized extension facts."""
    if not document_url.strip():
        raise InlineXbrlExtractionError("Inline XBRL document URL is required")
    controller = Cntlr.Cntlr(
        logFileName="logToBuffer",
        disable_persistent_config=True,
    )
    controller.webCache.httpUserAgent = sec_user_agent
    arelle_logger = logging.getLogger("arelle")
    logger_was_disabled = arelle_logger.disabled
    arelle_logger.disabled = True
    model_xbrl = None
    try:
        model_xbrl = controller.modelManager.load(document_url)
        if model_xbrl is None:
            raise InlineXbrlExtractionError(
                f"Arelle did not load Inline XBRL document: {document_url}"
            )
        return normalize_inline_xbrl_model(
            model_xbrl,
            cik=cik,
            entity_name=entity_name,
            form=form,
            filing_date=filing_date,
            accession_number=accession_number,
            fiscal_year=fiscal_year,
            fiscal_period=fiscal_period,
            source_document=document_url,
        )
    except InlineXbrlExtractionError:
        raise
    except Exception as exc:
        raise InlineXbrlExtractionError(
            f"Could not extract Inline XBRL from {document_url}: {exc}"
        ) from exc
    finally:
        if model_xbrl is not None:
            model_xbrl.close()
        controller.close()
        arelle_logger.disabled = logger_was_disabled
