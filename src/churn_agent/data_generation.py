"""Synthetic data generation for churn & revenue analysis."""

import numpy as np
import pandas as pd

from churn_agent.config import (
    ANOMALY_FAIL_RATE,
    BASE_FAIL_RATE,
    DEFAULT_ANOMALY_MONTH,
    DEFAULT_N_MONTHS,
    DEFAULT_N_USERS,
    DEFAULT_SEED,
    FAIL_TO_CHURN_RATE,
    MONTHLY_HAZARD,
    PLANS,
)


def generate_users(
    n_users: int = DEFAULT_N_USERS,
    n_months: int = DEFAULT_N_MONTHS,
    seed: int = DEFAULT_SEED,
    inject_anomaly: bool = True,
    anomaly_month: int = DEFAULT_ANOMALY_MONTH,
) -> pd.DataFrame:
    """Generate a synthetic user cohort with monthly payment and churn data.

    Returns a long-panel DataFrame with one row per (user, month).
    Monetary columns (monthly_price, amount_paid) are in whole cents.
    """
    rng = np.random.default_rng(seed)

    plan_names = list(PLANS.keys())
    plan_weights = [PLANS[p]["share"] for p in plan_names]
    user_plans = rng.choice(plan_names, size=n_users, p=plan_weights)
    user_prices = np.array([PLANS[p]["price_cents"] for p in user_plans])

    churn_months = _assign_churn_months(n_users, n_months, rng, inject_anomaly, anomaly_month)

    rows = []
    for user in range(n_users):
        price = int(user_prices[user])
        churn = churn_months[user]
        for month in range(1, n_months + 1):
            if churn is not None and month >= churn:
                is_active = False
                payment_status = "churned"
                amount_paid = 0
            else:
                is_active = True
                p_fail = (
                    ANOMALY_FAIL_RATE
                    if (inject_anomaly and month == anomaly_month)
                    else BASE_FAIL_RATE
                )
                payment_status = "failed" if rng.random() < p_fail else "paid"
                amount_paid = price if payment_status == "paid" else 0

            rows.append(
                {
                    "user_id": user,
                    "month": month,
                    "plan": user_plans[user],
                    "monthly_price": price,
                    "payment_status": payment_status,
                    "amount_paid": amount_paid,
                    "is_active": is_active,
                }
            )

    df = pd.DataFrame(rows)
    df = df[
        [
            "user_id",
            "month",
            "plan",
            "monthly_price",
            "payment_status",
            "amount_paid",
            "is_active",
        ]
    ]
    return df


def _assign_churn_months(
    n_users: int,
    n_months: int,
    rng: np.random.Generator,
    inject_anomaly: bool,
    anomaly_month: int,
) -> list[int | None]:
    """Determine the first churn month for each user (None if survives all months)."""
    fail_matrix = np.zeros((n_users, n_months + 1), dtype=bool)
    for month in range(1, n_months + 1):
        p_fail = (
            ANOMALY_FAIL_RATE if (inject_anomaly and month == anomaly_month) else BASE_FAIL_RATE
        )
        fail_matrix[:, month] = rng.random(n_users) < p_fail

    churn_months: list[int | None] = [None] * n_users
    active = np.ones(n_users, dtype=bool)

    for month in range(1, n_months):
        if not active.any():
            break

        hazard = MONTHLY_HAZARD.get(month + 1, 0.0)
        base_churn = active & (rng.random(n_users) < hazard)

        candidates = active & (~base_churn) & fail_matrix[:, month]
        involuntary_churn = candidates & (rng.random(n_users) < FAIL_TO_CHURN_RATE)

        total_churn = base_churn | involuntary_churn
        churn_months = [
            (month + 1 if total_churn[u] and churn_months[u] is None else churn_months[u])
            for u in range(n_users)
        ]
        active &= ~total_churn

    return churn_months
