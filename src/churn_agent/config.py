"""Configuration and constants."""

import os

DEFAULT_SEED = 42
DEFAULT_N_USERS = 1000
DEFAULT_N_MONTHS = 12
DEFAULT_ANOMALY_MONTH = 8

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

# Prices in cents to avoid float drift.
PLANS = {
    "Basic": {"price_cents": 999, "share": 0.60},
    "Pro": {"price_cents": 1999, "share": 0.30},
    "Premium": {"price_cents": 3999, "share": 0.10},
}

MONTHLY_HAZARD = {
    2: 0.10,
    3: 0.09,
    4: 0.07,
    5: 0.06,
    6: 0.05,
    7: 0.05,
    8: 0.04,
    9: 0.04,
    10: 0.04,
    11: 0.03,
    12: 0.03,
}

BASE_FAIL_RATE = 0.03
ANOMALY_FAIL_RATE = 0.25
FAIL_TO_CHURN_RATE = 0.40

DATA_DIR = "data"
REPORTS_DIR = "reports"
USERS_CSV = f"{DATA_DIR}/users.csv"
METRICS_CSV = f"{REPORTS_DIR}/metrics.csv"
REPORT_MD = f"{REPORTS_DIR}/report.md"
MANIFEST_JSON = f"{REPORTS_DIR}/run_manifest.json"
