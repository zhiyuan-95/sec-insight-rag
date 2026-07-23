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
            occurrence_count INTEGER NOT NULL DEFAULT 1,
            occurrence_references_json TEXT NOT NULL DEFAULT '[]',
            conflict_evidence_json TEXT NOT NULL DEFAULT '[]',
            identity_version INTEGER NOT NULL DEFAULT 2,
            source TEXT NOT NULL,
            quality_flags TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )
    connection.execute("CREATE INDEX IF NOT EXISTS idx_raw_xbrl_facts_cik ON raw_xbrl_facts (cik)")
    connection.execute("CREATE INDEX IF NOT EXISTS idx_raw_xbrl_facts_concept ON raw_xbrl_facts (concept)")
    _ensure_column(connection, "raw_xbrl_facts", "namespace_uri", "TEXT")
    _ensure_column(connection, "raw_xbrl_facts", "context_id", "TEXT")
    _ensure_column(
        connection,
        "raw_xbrl_facts",
        "dimensions_json",
        "TEXT NOT NULL DEFAULT '[]'",
    )
    _ensure_column(
        connection,
        "raw_xbrl_facts",
        "is_consolidated",
        "INTEGER NOT NULL DEFAULT 1",
    )
    _ensure_column(connection, "raw_xbrl_facts", "source_document", "TEXT")
    _ensure_column(connection, "raw_xbrl_facts", "balance", "TEXT")
    _ensure_column(connection, "raw_xbrl_facts", "is_numeric", "INTEGER")
    _ensure_column(
        connection,
        "raw_xbrl_facts",
        "occurrence_count",
        "INTEGER NOT NULL DEFAULT 1",
    )
    _ensure_column(
        connection,
        "raw_xbrl_facts",
        "occurrence_references_json",
        "TEXT NOT NULL DEFAULT '[]'",
    )
    _ensure_column(
        connection,
        "raw_xbrl_facts",
        "conflict_evidence_json",
        "TEXT NOT NULL DEFAULT '[]'",
    )
    _ensure_column(
        connection,
        "raw_xbrl_facts",
        "identity_version",
        "INTEGER NOT NULL DEFAULT 1",
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_raw_xbrl_facts_taxonomy_concept
        ON raw_xbrl_facts (taxonomy, concept)
        """
    )
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
        CREATE TABLE IF NOT EXISTS company_industry_labels (
            company_industry_label_id INTEGER PRIMARY KEY AUTOINCREMENT,
            company_id INTEGER NOT NULL,
            industry_label TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'approved',
            assignment_source TEXT NOT NULL,
            assignment_reason TEXT NOT NULL,
            confidence REAL,
            evidence_json TEXT NOT NULL DEFAULT '[]',
            classifier_version TEXT,
            reviewed_at TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE (company_id, industry_label),
            FOREIGN KEY (company_id) REFERENCES companies(company_id) ON DELETE CASCADE
        )
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_company_industry_labels_company
        ON company_industry_labels (company_id)
        """
    )
    _ensure_column(
        connection,
        "company_industry_labels",
        "status",
        "TEXT NOT NULL DEFAULT 'approved'",
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS company_industry_label_snapshots (
            company_industry_label_snapshot_id INTEGER PRIMARY KEY AUTOINCREMENT,
            company_id INTEGER NOT NULL,
            accession_number TEXT NOT NULL,
            fiscal_year INTEGER NOT NULL,
            fiscal_period TEXT NOT NULL,
            assigned_labels_json TEXT NOT NULL DEFAULT '[]',
            label_status TEXT NOT NULL,
            assignment_source TEXT NOT NULL,
            assignment_reason TEXT NOT NULL,
            confidence REAL,
            evidence_json TEXT NOT NULL DEFAULT '[]',
            classifier_version TEXT,
            reviewed_at TEXT,
            created_at TEXT NOT NULL,
            UNIQUE (
                company_id,
                accession_number,
                fiscal_year,
                fiscal_period
            ),
            FOREIGN KEY (company_id) REFERENCES companies(company_id) ON DELETE CASCADE
        )
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_company_industry_label_snapshots_period
        ON company_industry_label_snapshots (
            company_id,
            fiscal_year,
            fiscal_period
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS xbrl_concept_mappings (
            mapping_id INTEGER PRIMARY KEY AUTOINCREMENT,
            taxonomy TEXT NOT NULL,
            concept TEXT NOT NULL,
            namespace_uri TEXT,
            metric_name TEXT NOT NULL,
            statement_type TEXT NOT NULL,
            scope_type TEXT NOT NULL,
            scope_value TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL,
            confidence REAL,
            match_method TEXT NOT NULL,
            evidence_json TEXT NOT NULL DEFAULT '{}',
            reviewed_by TEXT,
            reviewed_at TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE (
                taxonomy,
                concept,
                metric_name,
                scope_type,
                scope_value
            )
        )
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_xbrl_concept_mappings_lookup
        ON xbrl_concept_mappings (taxonomy, concept, status)
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_xbrl_concept_mappings_scope
        ON xbrl_concept_mappings (scope_type, scope_value, status)
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS mapping_shadow_candidates (
            shadow_candidate_id INTEGER PRIMARY KEY AUTOINCREMENT,
            company_id INTEGER NOT NULL,
            raw_fact_id INTEGER NOT NULL,
            taxonomy TEXT NOT NULL,
            concept TEXT NOT NULL,
            metric_name TEXT NOT NULL,
            statement_type TEXT NOT NULL,
            fiscal_year INTEGER NOT NULL,
            fiscal_period TEXT NOT NULL,
            score REAL NOT NULL,
            match_method TEXT NOT NULL,
            evidence_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE (
                company_id,
                raw_fact_id,
                metric_name,
                match_method
            ),
            FOREIGN KEY (company_id)
                REFERENCES companies(company_id) ON DELETE CASCADE,
            FOREIGN KEY (raw_fact_id)
                REFERENCES raw_xbrl_facts(id) ON DELETE CASCADE
        )
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_mapping_shadow_candidates_period
        ON mapping_shadow_candidates (
            company_id,
            fiscal_year,
            fiscal_period,
            metric_name
        )
        """
    )
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
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS financial_indicators (
            indicator_id INTEGER PRIMARY KEY AUTOINCREMENT,
            company_id INTEGER NOT NULL,
            indicator_name TEXT NOT NULL,
            formula_name TEXT NOT NULL,
            formula_version TEXT NOT NULL,
            value_numeric TEXT,
            unit TEXT NOT NULL,
            period_type TEXT NOT NULL,
            fiscal_year INTEGER,
            fiscal_period TEXT,
            start_date TEXT,
            end_date TEXT,
            filing_date TEXT,
            source_metric_ids TEXT NOT NULL,
            source_raw_fact_ids TEXT NOT NULL,
            source_accession_numbers TEXT NOT NULL,
            is_active_window INTEGER NOT NULL DEFAULT 1,
            calculation_status TEXT NOT NULL,
            skip_reason TEXT,
            created_at TEXT NOT NULL,
            UNIQUE (
                company_id,
                indicator_name,
                period_type,
                fiscal_year,
                fiscal_period,
                formula_version
            ),
            FOREIGN KEY (company_id) REFERENCES companies(company_id)
        )
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_financial_indicators_company_active
        ON financial_indicators (company_id, is_active_window)
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_financial_indicators_lookup
        ON financial_indicators (company_id, indicator_name, fiscal_year, fiscal_period)
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS filing_chunks (
            chunk_id TEXT PRIMARY KEY,
            generation_id TEXT NOT NULL,
            company_id INTEGER NOT NULL,
            filing_id INTEGER NOT NULL,
            accession_number TEXT NOT NULL,
            section_name TEXT NOT NULL,
            section_title TEXT NOT NULL,
            section_order INTEGER NOT NULL,
            chunk_order INTEGER NOT NULL,
            text TEXT NOT NULL,
            text_sha256 TEXT NOT NULL,
            source_sha256 TEXT NOT NULL,
            source_path TEXT NOT NULL,
            token_count INTEGER NOT NULL,
            parser_version TEXT NOT NULL,
            splitter_version TEXT NOT NULL,
            is_active_window INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL,
            FOREIGN KEY (company_id) REFERENCES companies(company_id) ON DELETE CASCADE,
            FOREIGN KEY (filing_id) REFERENCES filings(filing_id) ON DELETE CASCADE
        )
        """
    )
    chunk_columns = {
        row[1] for row in connection.execute("PRAGMA table_info(filing_chunks)").fetchall()
    }
    if "source_path" not in chunk_columns:
        connection.execute("ALTER TABLE filing_chunks ADD COLUMN source_path TEXT")
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_filing_chunks_company_active
        ON filing_chunks (company_id, is_active_window)
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_filing_chunks_filing
        ON filing_chunks (filing_id, section_name, chunk_order)
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_filing_chunks_accession
        ON filing_chunks (accession_number)
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS retrieval_index_state (
            company_id INTEGER PRIMARY KEY,
            generation_id TEXT NOT NULL,
            source_fingerprint TEXT NOT NULL,
            parser_version TEXT NOT NULL,
            splitter_version TEXT NOT NULL,
            embedding_model TEXT NOT NULL,
            chunk_size INTEGER NOT NULL,
            chunk_overlap INTEGER NOT NULL,
            chunk_set_hash TEXT NOT NULL,
            filing_count INTEGER NOT NULL,
            chunk_count INTEGER NOT NULL,
            artifact_path TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (company_id) REFERENCES companies(company_id) ON DELETE CASCADE
        )
        """
    )
    connection.commit()


def _ensure_column(
    connection: sqlite3.Connection,
    table_name: str,
    column_name: str,
    definition: str,
) -> None:
    columns = {
        str(row[1])
        for row in connection.execute(f"PRAGMA table_info({table_name})").fetchall()
    }
    if column_name not in columns:
        connection.execute(
            f"ALTER TABLE {table_name} ADD COLUMN {column_name} {definition}"
        )
