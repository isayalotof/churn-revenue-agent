"""Metric computation from raw user data."""

import pandas as pd


def compute_monthly_metrics(df: pd.DataFrame) -> pd.DataFrame:
    """Compute monthly aggregated metrics from the user-level panel.

    Revenue and MRR are computed in whole cents (int) to avoid float drift.
    ARPU is in cents (float) and rounded only on output.
    """
    months = sorted(df["month"].unique())

    active_users = []
    paid_users = []
    monthly_revenue = []
    churned_users = []

    for m in months:
        month_df = df[df["month"] == m]
        active = int(month_df["is_active"].sum())
        paid = int((month_df["payment_status"] == "paid").sum())
        revenue = int(month_df.loc[month_df["payment_status"] == "paid", "amount_paid"].sum())

        active_users.append(active)
        paid_users.append(paid)
        monthly_revenue.append(revenue)

    for idx, _m in enumerate(months):
        if _m == 1:
            churned_users.append(0)
        else:
            churned_users.append(active_users[idx - 1] - active_users[idx])

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
    mrr = monthly_revenue  # For monthly subscription, MRR = monthly revenue
    cohort_retention = [active_users[idx] / active_users[0] for idx in range(len(months))]
    logo_churn_rate = churn_rates
    revenue_churn = []
    for idx, _m in enumerate(months):
        if _m == 1:
            revenue_churn.append(0.0)
        else:
            prev_rev = monthly_revenue[idx - 1]
            revenue_churn.append(
                (prev_rev - monthly_revenue[idx]) / prev_rev if prev_rev > 0 else 0.0
            )
    nrr = [monthly_revenue[idx] / monthly_revenue[0] for idx in range(len(months))]

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
