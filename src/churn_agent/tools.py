"""Tools for the agent and deterministic pipeline."""

import hashlib
import json
import logging
import os
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from churn_agent.config import (
    DATA_DIR,
    DEFAULT_ANOMALY_MONTH,
    DEFAULT_N_MONTHS,
    DEFAULT_N_USERS,
    DEFAULT_SEED,
    GEN_META_JSON,
    MANIFEST_JSON,
    METRICS_CSV,
    OPENAI_MODEL,
    REPORTS_DIR,
    USERS_CSV,
)
from churn_agent.data_generation import generate_users
from churn_agent.metrics import compute_monthly_metrics, metrics_to_dollars
from churn_agent.validation import ValidationResult, validate

logger = logging.getLogger(__name__)
_metrics_cache: pd.DataFrame | None = None


def _file_hash(path: str) -> str:
    """Return SHA-256 hex digest of a file."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()[:16]


def generate_data(
    n_users: int = DEFAULT_N_USERS,
    n_months: int = DEFAULT_N_MONTHS,
    seed: int = DEFAULT_SEED,
    inject_anomaly: bool = True,
    anomaly_month: int = DEFAULT_ANOMALY_MONTH,
    output_path: str = USERS_CSV,
) -> pd.DataFrame:
    """Generate synthetic data, write CSV in dollars, return cent DataFrame."""
    df = generate_users(
        n_users=n_users,
        n_months=n_months,
        seed=seed,
        inject_anomaly=inject_anomaly,
        anomaly_month=anomaly_month,
    )
    Path(DATA_DIR).mkdir(parents=True, exist_ok=True)
    df_out = df.copy()
    df_out["monthly_price"] = df_out["monthly_price"] / 100.0
    df_out["amount_paid"] = df_out["amount_paid"] / 100.0
    df_out.to_csv(output_path, index=False)
    active_total = int(df["is_active"].sum())
    logger.info(
        "Generated %s rows (%s users x %s months) seed=%s anomaly=%s active_months=%s",
        len(df),
        n_users,
        n_months,
        seed,
        inject_anomaly,
        active_total,
    )
    # Save generation params for downstream auditability
    meta = {
        "seed": seed,
        "n_users": n_users,
        "n_months": n_months,
        "inject_anomaly": inject_anomaly,
        "anomaly_month": anomaly_month,
    }
    with open(GEN_META_JSON, "w", encoding="utf-8") as f:
        json.dump(meta, f)
    return df


def compute_metrics(
    df: pd.DataFrame | None = None,
    input_path: str = USERS_CSV,
    output_path: str = METRICS_CSV,
) -> tuple[pd.DataFrame, str]:
    """Compute metrics from raw DataFrame or CSV, write CSV in dollars, return cent DataFrame and markdown table."""
    global _metrics_cache
    if df is None:
        df = pd.read_csv(input_path)
        df["monthly_price"] = (df["monthly_price"] * 100).round().astype(int)
        df["amount_paid"] = (df["amount_paid"] * 100).round().astype(int)

    metrics = compute_monthly_metrics(df)
    Path(REPORTS_DIR).mkdir(parents=True, exist_ok=True)
    metrics_to_dollars(metrics).to_csv(output_path, index=False)
    _metrics_cache = metrics
    logger.info("Metrics written to %s", output_path)

    # Build markdown table from dollar display
    disp = metrics_to_dollars(metrics)
    lines = [
        "| month | active_users | paid_users | churned_users | monthly_revenue | churn_rate | arpu |"
    ]
    lines.append(
        "|-------|-------------|------------|---------------|-----------------|------------|------|"
    )
    for _, row in disp.iterrows():
        lines.append(
            f"| {int(row['month'])} | {int(row['active_users'])} | {int(row['paid_users'])} | "
            f"{int(row['churned_users'])} | {row['monthly_revenue']:.2f} | {row['churn_rate']:.4f} | {row['arpu']:.2f} |"
        )
    return metrics, "\n".join(lines)


def run_validation(
    raw_df: pd.DataFrame | None = None,
    metrics_df: pd.DataFrame | None = None,
    raw_path: str = USERS_CSV,
    metrics_path: str = METRICS_CSV,
) -> ValidationResult:
    """Run full validation suite on raw data and metrics."""
    if raw_df is None:
        raw_df = pd.read_csv(raw_path)
        raw_df["monthly_price"] = (raw_df["monthly_price"] * 100).round().astype(int)
        raw_df["amount_paid"] = (raw_df["amount_paid"] * 100).round().astype(int)
    if metrics_df is None:
        metrics_df = pd.read_csv(metrics_path)
        for col in ["monthly_revenue", "arpu", "mrr"]:
            if col in metrics_df.columns:
                metrics_df[col] = (metrics_df[col] * 100).round().astype(int)
    return validate(raw_df, metrics_df)


def lookup_metric(month: int, name: str) -> float:
    """Return a single metric value by month and column name (in display units)."""
    global _metrics_cache
    if _metrics_cache is None:
        if not os.path.exists(METRICS_CSV):
            raise FileNotFoundError(f"Metrics file not found: {METRICS_CSV}")
        _metrics_cache = pd.read_csv(METRICS_CSV)
    row = _metrics_cache[_metrics_cache["month"] == month]
    if row.empty:
        raise ValueError(f"Month {month} not found in metrics")
    if name not in row.columns:
        raise ValueError(f"Metric '{name}' not found. Available: {list(row.columns)}")
    val = float(row[name].iloc[0])
    # Return display units (dollars for monetary columns)
    if name in ("monthly_revenue", "arpu", "mrr"):
        return round(val, 2)
    return val


def write_manifest(
    seed: int,
    n_users: int,
    n_months: int,
    inject_anomaly: bool,
    anomaly_month: int,
    model: str | None,
    system_fingerprint: str | None,
    passed: bool,
    output_path: str = MANIFEST_JSON,
) -> None:
    """Write a run manifest for auditability."""
    manifest = {
        "timestamp": datetime.now(UTC).isoformat(),
        "seed": seed,
        "n_users": n_users,
        "n_months": n_months,
        "inject_anomaly": inject_anomaly,
        "anomaly_month": anomaly_month,
        "model": model or OPENAI_MODEL,
        "system_fingerprint": system_fingerprint,
        "validation_passed": passed,
        "users_hash": _file_hash(USERS_CSV) if os.path.exists(USERS_CSV) else None,
        "metrics_hash": _file_hash(METRICS_CSV) if os.path.exists(METRICS_CSV) else None,
    }
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)
    logger.info("Run manifest written to %s", output_path)
