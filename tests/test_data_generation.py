"""Tests for synthetic data generation."""

import pandas as pd

from churn_agent.config import (
    DEFAULT_ANOMALY_MONTH,
    DEFAULT_N_MONTHS,
    DEFAULT_N_USERS,
    DEFAULT_SEED,
)
from churn_agent.data_generation import generate_users


def test_row_count():
    df = generate_users()
    assert len(df) == DEFAULT_N_USERS * DEFAULT_N_MONTHS


def test_amount_paid_consistency():
    df = generate_users()
    paid_mask = df["payment_status"] == "paid"
    assert (df.loc[paid_mask, "amount_paid"] == df.loc[paid_mask, "monthly_price"]).all()
    nonpaid_mask = df["payment_status"] != "paid"
    assert (df.loc[nonpaid_mask, "amount_paid"] == 0).all()


def test_active_users_monotonically_non_increasing():
    df = generate_users()
    active_counts = df.groupby("month")["is_active"].sum().tolist()
    for i in range(1, len(active_counts)):
        assert active_counts[i] <= active_counts[i - 1]


def test_determinism():
    df1 = generate_users(seed=DEFAULT_SEED)
    df2 = generate_users(seed=DEFAULT_SEED)
    pd.testing.assert_frame_equal(df1, df2)


def test_anomaly_increases_failures():
    df_base = generate_users(seed=DEFAULT_SEED, inject_anomaly=False)
    df_anom = generate_users(seed=DEFAULT_SEED, inject_anomaly=True)

    base_fails = df_base[
        (df_base["month"] == DEFAULT_ANOMALY_MONTH) & (df_base["payment_status"] == "failed")
    ].shape[0]
    anom_fails = df_anom[
        (df_anom["month"] == DEFAULT_ANOMALY_MONTH) & (df_anom["payment_status"] == "failed")
    ].shape[0]

    assert anom_fails > base_fails * 3


def test_churned_rows_are_inactive():
    df = generate_users()
    churned = df[df["payment_status"] == "churned"]
    assert (~churned["is_active"]).all()
    assert (churned["amount_paid"] == 0).all()
