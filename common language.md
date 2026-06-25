data lineage view : shows where a value came from, how the system translated it, and whether it is available for the calculation or report being inspected.

raw XBRL fact : one reported fact from SEC/XBRL, stored in `raw_xbrl_facts`.

XBRL concept / SEC tag : the raw tag name from SEC/XBRL, such as `Revenues`, `NetIncomeLoss`, or `RevenueFromContractWithCustomerExcludingAssessedTax`.

observed XBRL concept : an XBRL concept that was actually found in a company's ingested filing data.

unknown XBRL concept : an observed XBRL concept that the system does not currently map to a system financial metric and does not currently treat as a target XBRL concept.

system financial metric : the internal metric name the system understands, such as `revenue`, `net_income`, `inventory`, or `operating_cash_flow`. Use this term in system design instead of `financial matrix`.

target XBRL concept : an SEC/XBRL tag that the system intentionally looks for because it may map to a system financial metric or support an indicator.

candidate XBRL concept : one possible SEC/XBRL tag for a system financial metric. Example: `RevenueFromContractWithCustomerExcludingAssessedTax`, `Revenues`, and `SalesRevenueNet` are candidate XBRL concepts for `revenue`.

approved mapping : a trusted mapping from an XBRL concept to a system financial metric. Only approved mappings can populate `financial_metrics`.

semantic mapping candidate : a possible mapping suggested by vector similarity. It requires review and must not populate `financial_metrics` automatically.

missing target XBRL concept : a target or candidate XBRL concept expected for the company's approved industry labels but not found after Round 1 hard mapping.

hard industry label : one of the fixed 11 industry tags assigned to a company: Energy, Materials, Industrials, Consumer Discretionary, Consumer Staples, Health Care, Financials, Information Technology, Communication Services, Utilities, Real Estate.

target XBRL concept set : the union of common base candidate XBRL concepts plus industry-specific candidate XBRL concepts for the company's approved hard industry labels.

Round 1 hard mapping : direct deterministic matching from known candidate XBRL concept names to observed XBRL concepts.

Round 2 semantic mapping : vector comparison between missing target XBRL concept vectors and unknown company XBRL concept vectors.

canonical mapping flow : candidate XBRL concept -> observed XBRL concept -> raw XBRL fact -> approved mapping -> system financial metric.

semantic review flow : unknown XBRL concept -> semantic mapping candidate -> reviewed approved mapping.
