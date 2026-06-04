"""Common SEC XBRL constants and base-metric concept mappings."""

COMMON_GAAP_CONCEPTS = {
    "Assets",
    "AssetsCurrent",
    "CashAndCashEquivalentsAtCarryingValue",
    "CostOfRevenue",
    "GrossProfit",
    "Liabilities",
    "LiabilitiesCurrent",
    "NetCashProvidedByUsedInOperatingActivities",
    "NetIncomeLoss",
    "OperatingIncomeLoss",
    "PaymentsToAcquirePropertyPlantAndEquipment",
    "RevenueFromContractWithCustomerExcludingAssessedTax",
    "Revenues",
    "StockholdersEquity",
}

DEFAULT_TAXONOMIES = {"us-gaap"}
DEFAULT_FORMS = {"10-K", "10-Q"}
SUPPORTED_REPORT_FORMS = {"10-K", "10-Q"}
