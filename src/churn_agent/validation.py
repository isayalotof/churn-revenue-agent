"""Data and metric validation with hard invariants and soft anomalies."""

from dataclasses import dataclass

import pandas as pd


@dataclass
class Check:
    name: str
    passed: bool
    detail: str


@dataclass
class Anomaly:
    name: str
    month: int
    detail: str
    severity: str  # "info" | "warning"


@dataclass
class ValidationResult:
    invariants: list[Check]
    anomalies: list[Anomaly]
    passed: bool


def validate(raw: pd.DataFrame, metrics: pd.DataFrame) -> ValidationResult:
    """Run hard invariant checks and soft anomaly detection."""
    invariants: list[Check] = []
    anomalies: list[Anomaly] = []

    expected_cols = [
        "user_id",
        "month",
        "plan",
        "monthly_price",
        "payment_status",
        "amount_paid",
        "is_active",
    ]
    invariants.append(_check_schema(raw, expected_cols))
    invariants.append(_check_no_nulls(raw, expected_cols))
    invariants.append(_check_row_count(raw))
    invariants.append(_check_monthly_price_positive(raw))
    invariants.append(_check_amount_paid_consistency(raw))
    invariants.append(_check_payment_status_values(raw))
    invariants.append(_check_revenue_reconciliation(raw, metrics))
    invariants.append(_check_paid_le_active(metrics))
    invariants.append(_check_churn_rate_bounds(metrics))
    invariants.append(_check_active_monotonic(metrics))
    invariants.append(_check_churn_closure(metrics))
    invariants.append(_check_churned_consistency(metrics))

    anomalies.extend(_detect_revenue_drop(metrics))
    anomalies.extend(_detect_churn_spike(metrics))
    anomalies.extend(_detect_failed_spike(raw))

    passed = all(c.passed for c in invariants)
    return ValidationResult(invariants=invariants, anomalies=anomalies, passed=passed)


def _check_schema(raw: pd.DataFrame, expected: list[str]) -> Check:
    missing = [c for c in expected if c not in raw.columns]
    passed = len(missing) == 0
    return Check(
        name="schema_complete",
        passed=passed,
        detail=f"Missing columns: {missing}" if not passed else "All expected columns present",
    )


def _check_no_nulls(raw: pd.DataFrame, cols: list[str]) -> Check:
    nulls = {c: int(raw[c].isna().sum()) for c in cols if raw[c].isna().any()}
    passed = len(nulls) == 0
    return Check(
        name="no_nulls",
        passed=passed,
        detail=f"Nulls found: {nulls}" if not passed else "No nulls in required columns",
    )


def _check_row_count(raw: pd.DataFrame) -> Check:
    n_users = raw["user_id"].nunique()
    n_months = raw["month"].nunique()
    expected = n_users * n_months
    actual = len(raw)
    passed = actual == expected
    return Check(
        name="row_count",
        passed=passed,
        detail=f"Expected {expected}, got {actual}" if not passed else f"Row count OK ({actual})",
    )


def _check_monthly_price_positive(raw: pd.DataFrame) -> Check:
    bad = (raw["monthly_price"] <= 0).sum()
    passed = bad == 0
    return Check(
        name="monthly_price_positive",
        passed=passed,
        detail=f"{bad} rows with non-positive price" if not passed else "All prices positive",
    )


def _check_amount_paid_consistency(raw: pd.DataFrame) -> Check:
    paid_ok = (
        (raw["payment_status"] == "paid") & (raw["amount_paid"] == raw["monthly_price"])
    ).sum()
    nonpaid_ok = ((raw["payment_status"] != "paid") & (raw["amount_paid"] == 0)).sum()
    total = len(raw)
    passed = (paid_ok + nonpaid_ok) == total
    return Check(
        name="amount_paid_consistency",
        passed=passed,
        detail=f"Inconsistent amount_paid in {total - paid_ok - nonpaid_ok} rows"
        if not passed
        else "amount_paid consistent",
    )


def _check_payment_status_values(raw: pd.DataFrame) -> Check:
    valid = {"paid", "failed", "churned"}
    bad = raw[~raw["payment_status"].isin(valid)]
    passed = len(bad) == 0
    return Check(
        name="payment_status_values",
        passed=passed,
        detail=f"Invalid statuses: {bad['payment_status'].unique().tolist()}"
        if not passed
        else "All statuses valid",
    )


def _check_revenue_reconciliation(raw: pd.DataFrame, metrics: pd.DataFrame) -> Check:
    computed = (
        raw[raw["payment_status"] == "paid"].groupby("month")["amount_paid"].sum().reset_index()
    )
    merged = computed.merge(metrics[["month", "monthly_revenue"]], on="month")
    ok = (merged["amount_paid"] - merged["monthly_revenue"]).abs() == 0
    passed = ok.all()
    return Check(
        name="revenue_reconciliation",
        passed=passed,
        detail="Revenue mismatch detected" if not passed else "Revenue reconciles with raw data",
    )


def _check_paid_le_active(metrics: pd.DataFrame) -> Check:
    ok = (metrics["paid_users"] <= metrics["active_users"]).all()
    return Check(
        name="paid_le_active",
        passed=bool(ok),
        detail="paid_users exceeds active_users in some month"
        if not ok
        else "paid_users <= active_users OK",
    )


def _check_churn_rate_bounds(metrics: pd.DataFrame) -> Check:
    ok = ((metrics["churn_rate"] >= 0) & (metrics["churn_rate"] <= 1)).all()
    return Check(
        name="churn_rate_bounds",
        passed=bool(ok),
        detail="churn_rate outside [0, 1]" if not ok else "churn_rate within bounds",
    )


def _check_active_monotonic(metrics: pd.DataFrame) -> Check:
    diffs = metrics["active_users"].diff().dropna()
    ok = (diffs <= 0).all()
    return Check(
        name="active_monotonic",
        passed=bool(ok),
        detail="active_users increased month-over-month"
        if not ok
        else "active_users monotonically non-increasing",
    )


def _check_churn_closure(metrics: pd.DataFrame) -> Check:
    total_churned = metrics[metrics["month"] > 1]["churned_users"].sum()
    closure = metrics["active_users"].iloc[0] - metrics["active_users"].iloc[-1]
    passed = total_churned == closure
    return Check(
        name="churn_closure",
        passed=passed,
        detail=f"Total churned {total_churned} != closure {closure}"
        if not passed
        else "Churn closure OK",
    )


def _check_churned_consistency(metrics: pd.DataFrame) -> Check:
    ok = True
    detail = "churned_users consistent with active delta"
    for idx, row in metrics.iterrows():
        m = int(row["month"])
        if m == 1:
            if row["churned_users"] != 0:
                ok = False
                detail = f"Month 1 churned_users should be 0, got {row['churned_users']}"
                break
        else:
            expected = metrics["active_users"].iloc[idx - 1] - row["active_users"]
            if row["churned_users"] != expected:
                ok = False
                detail = f"Month {m}: churned_users {row['churned_users']} != expected {expected}"
                break
    return Check(name="churned_consistency", passed=ok, detail=detail)


def _detect_revenue_drop(metrics: pd.DataFrame) -> list[Anomaly]:
    anomalies = []
    for idx in range(1, len(metrics)):
        prev = metrics["monthly_revenue"].iloc[idx - 1]
        curr = metrics["monthly_revenue"].iloc[idx]
        if prev > 0:
            drop = (prev - curr) / prev
            if drop > 0.15:
                anomalies.append(
                    Anomaly(
                        name="revenue_drop",
                        month=int(metrics["month"].iloc[idx]),
                        detail=f"Revenue dropped {drop:.1%} MoM",
                        severity="warning",
                    )
                )
    return anomalies


def _detect_churn_spike(metrics: pd.DataFrame) -> list[Anomaly]:
    churn_slice = metrics[metrics["month"] > 1]["churn_rate"]
    if churn_slice.empty:
        return []
    median_churn = churn_slice.median()
    anomalies = []
    for _, row in metrics.iterrows():
        m = int(row["month"])
        if m == 1:
            continue
        if row["churn_rate"] > 2 * median_churn:
            anomalies.append(
                Anomaly(
                    name="churn_spike",
                    month=m,
                    detail=f"churn_rate {row['churn_rate']:.4f} > 2x median {median_churn:.4f}",
                    severity="warning",
                )
            )
    return anomalies


def _detect_failed_spike(raw: pd.DataFrame) -> list[Anomaly]:
    anomalies = []
    active = raw[raw["is_active"]]
    monthly = (
        active.groupby("month")
        .agg(
            total=("payment_status", "size"),
            failed=("payment_status", lambda x: (x == "failed").sum()),
        )
        .reset_index()
    )
    monthly["failed_share"] = monthly["failed"] / monthly["total"]
    for _, row in monthly.iterrows():
        m = int(row["month"])
        if row["failed_share"] > 0.15:
            anomalies.append(
                Anomaly(
                    name="failed_spike",
                    month=m,
                    detail=f"Failed payment share {row['failed_share']:.1%} in month {m}",
                    severity="warning",
                )
            )
    return anomalies
