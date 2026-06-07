"""Metric computation from raw user data."""

import pandas as pd


def compute_monthly_metrics(df: pd.DataFrame) -> pd.DataFrame:
    """Compute monthly aggregated metrics from the user-level panel.

    Revenue and collected amounts are in whole cents (int).
    MRR is contract value of active subscriptions (sum of monthly_price for is_active=True).
    This makes MRR independent of temporary payment failures.
    """
    months = sorted(df["month"].unique())

    active_users = []
    paid_users = []
    monthly_revenue = []  # collected revenue (paid only)
    mrr = []  # contract MRR (all active, regardless of payment status)
    churned_users = []

    for m in months:
        month_df = df[df["month"] == m]
        active = int(month_df["is_active"].sum())
        paid = int((month_df["payment_status"] == "paid").sum())
        revenue = int(month_df.loc[month_df["payment_status"] == "paid", "amount_paid"].sum())
        contract = int(month_df.loc[month_df["is_active"], "monthly_price"].sum())

        active_users.append(active)
        paid_users.append(paid)
        monthly_revenue.append(revenue)
        mrr.append(contract)
        churned_users.append(0)

    for idx, _m in enumerate(months):
        if _m == 1:
            churned_users[idx] = 0
        else:
            churned_users[idx] = active_users[idx - 1] - active_users[idx]

    churn_rates = []
    for idx, _m in enumerate(months):
        if _m == 1:
            churn_rates.append(0.0)
        else:
            prev_active = active_users[idx - 1]
            churn_rates.append(churned_users[idx] / prev_active if prev_active > 0 else 0.0)

    arpus = []
    for idx, _m in enumerate(months):
        active = active_users[idx]
        arpus.append(monthly_revenue[idx] / active if active > 0 else 0.0)

    # Fintech metrics
    cohort_retention = [active_users[idx] / active_users[0] for idx in range(len(months))]
    logo_churn_rate = churn_rates
    revenue_churn = []
    for idx, _m in enumerate(months):
        if _m == 1:
            revenue_churn.append(0.0)
        else:
            prev_mrr = mrr[idx - 1]
            revenue_churn.append((prev_mrr - mrr[idx]) / prev_mrr if prev_mrr > 0 else 0.0)
    nrr = [mrr[idx] / mrr[0] for idx in range(len(months))]

    metrics = pd.DataFrame(
        {
            "month": months,
            "active_users": active_users,
            "paid_users": paid_users,
            "churned_users": churned_users,
            "monthly_revenue": monthly_revenue,
            "churn_rate": churn_rates,
            "arpu": arpus,
            "mrr": mrr,
            "cohort_retention": cohort_retention,
            "logo_churn_rate": logo_churn_rate,
            "revenue_churn": revenue_churn,
            "nrr": nrr,
        }
    )

    return metrics


def metrics_to_dollars(df: pd.DataFrame) -> pd.DataFrame:
    """Return a copy with monetary cent columns converted to dollars for display."""
    out = df.copy()
    for col in ["monthly_revenue", "arpu", "mrr"]:
        if col in out.columns:
            out[col] = (out[col] / 100.0).round(2)
    for col in ["churn_rate", "cohort_retention", "logo_churn_rate", "revenue_churn", "nrr"]:
        if col in out.columns:
            out[col] = out[col].round(4)
    return out
