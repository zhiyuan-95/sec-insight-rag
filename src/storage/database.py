"""SQLite connection and schema helpers."""

from __future__ import annotations

import sqlite3
from pathlib import Path


def connect_sqlite(db_path: Path) -> sqlite3.Connection:
    """Connect to a SQLite database and create parent directories if needed."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def initialize_database(connection: sqlite3.Connection) -> None:
    """Initialize local SQLite tables used by the MVP."""
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS raw_xbrl_facts (
            id INTEGER PRIMARY KEY,
            unique_key TEXT NOT NULL UNIQUE,
            cik TEXT NOT NULL,
            entity_name TEXT,
            taxonomy TEXT NOT NULL,
            concept TEXT NOT NULL,
            label TEXT,
            description TEXT,
            unit TEXT NOT NULL,
            value_raw TEXT,
            value_numeric TEXT,
            start_date TEXT,
            end_date TEXT,
            period_type TEXT NOT NULL,
            fiscal_year INTEGER,
            fiscal_period TEXT,
            form TEXT,
            filed_date TEXT,
            accession_number TEXT,
            frame TEXT,
            source TEXT NOT NULL,
            quality_flags TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )
    connection.execute("CREATE INDEX IF NOT EXISTS idx_raw_xbrl_facts_cik ON raw_xbrl_facts (cik)")
    connection.execute("CREATE INDEX IF NOT EXISTS idx_raw_xbrl_facts_concept ON raw_xbrl_facts (concept)")
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS companies (
            company_id INTEGER PRIMARY KEY AUTOINCREMENT,
            cik TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            ticker TEXT,
            exchange TEXT,
            sic TEXT,
            sic_description TEXT,
            latest_10k_filing_date TEXT,
            latest_10q_filing_date TEXT,
            next_check_date_10k TEXT,
            next_check_date_10q TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    connection.execute("CREATE INDEX IF NOT EXISTS idx_companies_ticker ON companies (ticker)")
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS filings (
            filing_id INTEGER PRIMARY KEY AUTOINCREMENT,
            company_id INTEGER NOT NULL,
            accession_number TEXT UNIQUE NOT NULL,
            form_type TEXT NOT NULL,
            filing_date TEXT NOT NULL,
            report_date TEXT,
            fiscal_year INTEGER,
            fiscal_period TEXT,
            source TEXT NOT NULL DEFAULT 'SEC',
            document_url TEXT,
            local_path TEXT,
            is_active_window INTEGER NOT NULL DEFAULT 1,
            ingested_at TEXT NOT NULL,
            FOREIGN KEY (company_id) REFERENCES companies(company_id)
        )
        """
    )
    connection.execute("CREATE INDEX IF NOT EXISTS idx_filings_company ON filings (company_id)")
    connection.execute("CREATE INDEX IF NOT EXISTS idx_filings_accession ON filings (accession_number)")
    connection.execute("CREATE INDEX IF NOT EXISTS idx_filings_active ON filings (company_id, is_active_window)")
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS financial_metrics (
            metric_id INTEGER PRIMARY KEY AUTOINCREMENT,
            company_id INTEGER NOT NULL,
            filing_id INTEGER,
            accession_number TEXT NOT NULL,
            raw_fact_id INTEGER,
            statement_type TEXT NOT NULL,
            metric_name TEXT NOT NULL,
            value_numeric TEXT,
            value_raw TEXT,
            unit TEXT NOT NULL,
            period_type TEXT NOT NULL,
            fiscal_year INTEGER,
            fiscal_period TEXT,
            start_date TEXT,
            end_date TEXT,
            filing_date TEXT,
            is_active_window INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL,
            UNIQUE (
                company_id,
                metric_name,
                period_type,
                fiscal_year,
                fiscal_period,
                accession_number,
                raw_fact_id
            ),
            FOREIGN KEY (company_id) REFERENCES companies(company_id),
            FOREIGN KEY (filing_id) REFERENCES filings(filing_id),
            FOREIGN KEY (raw_fact_id) REFERENCES raw_xbrl_facts(id)
        )
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_financial_metrics_company_active
        ON financial_metrics (company_id, is_active_window)
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_financial_metrics_lookup
        ON financial_metrics (company_id, statement_type, metric_name)
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_financial_metrics_raw_fact
        ON financial_metrics (raw_fact_id)
        """
    )
    connection.commit()
