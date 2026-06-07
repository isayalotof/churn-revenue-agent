"""Tests for metric computation."""

import pytest

from churn_agent.config import DEFAULT_N_MONTHS, DEFAULT_SEED
from churn_agent.data_generation import generate_users
from churn_agent.metrics import compute_monthly_metrics


@pytest.fixture
def sample_data():
    return generate_users(seed=DEFAULT_SEED)


@pytest.fixture
def sample_metrics(sample_data):
    return compute_monthly_metrics(sample_data)


def test_churned_users_equals_active_delta(sample_metrics):
    for idx, row in sample_metrics.iterrows():
        m = int(row["month"])
        if m == 1:
            assert row["churned_users"] == 0
        else:
            prev_active = sample_metrics["active_users"].iloc[idx - 1]
            assert row["churned_users"] == prev_active - row["active_users"]


def test_churn_rate_bounds(sample_metrics):
    assert (sample_metrics["churn_rate"] >= 0).all()
    assert (sample_metrics["churn_rate"] <= 1).all()
    assert sample_metrics.loc[sample_metrics["month"] == 1, "churn_rate"].iloc[0] == 0.0


def test_churn_closure(sample_metrics):
    total_churned = sample_metrics[sample_metrics["month"] > 1]["churned_users"].sum()
    closure = sample_metrics["active_users"].iloc[0] - sample_metrics["active_users"].iloc[-1]
    assert total_churned == closure


def test_revenue_reconciliation(sample_data, sample_metrics):
    for m in range(1, DEFAULT_N_MONTHS + 1):
        month_df = sample_data[
            (sample_data["month"] == m) & (sample_data["payment_status"] == "paid")
        ]
        expected = month_df["amount_paid"].sum()
        actual = sample_metrics.loc[sample_metrics["month"] == m, "monthly_revenue"].iloc[0]
        assert expected == actual


def test_arpu_formula(sample_metrics):
    for _, row in sample_metrics.iterrows():
        expected = row["monthly_revenue"] / row["active_users"] if row["active_users"] > 0 else 0.0
        assert abs(row["arpu"] - expected) < 1e-6


def test_monetary_columns_are_int(sample_data, sample_metrics):
    assert sample_data["monthly_price"].dtype in ("int64", "int32")
    assert sample_data["amount_paid"].dtype in ("int64", "int32")
    assert sample_metrics["monthly_revenue"].dtype in ("int64", "int32")
    assert sample_metrics["mrr"].dtype in ("int64", "int32")


def test_fintech_metrics_present(sample_metrics):
    for col in ["mrr", "cohort_retention", "logo_churn_rate", "revenue_churn", "nrr"]:
        assert col in sample_metrics.columns


def test_mrr_is_contract_value_of_active_users(sample_data, sample_metrics):
    for m in range(1, DEFAULT_N_MONTHS + 1):
        month_df = sample_data[(sample_data["month"] == m) & (sample_data["is_active"])]
        expected = month_df["monthly_price"].sum()
        actual = sample_metrics.loc[sample_metrics["month"] == m, "mrr"].iloc[0]
        assert expected == actual


def test_cohort_retention_bounds(sample_metrics):
    assert (sample_metrics["cohort_retention"] >= 0).all()
    assert (sample_metrics["cohort_retention"] <= 1).all()
    assert sample_metrics.loc[sample_metrics["month"] == 1, "cohort_retention"].iloc[0] == 1.0


def test_nrr_bounds(sample_metrics):
    assert (sample_metrics["nrr"] >= 0).all()
    assert sample_metrics.loc[sample_metrics["month"] == 1, "nrr"].iloc[0] == 1.0


def test_revenue_churn_matches_logo_churn_within_sampling_error(sample_metrics):
    # MRR is contract value of active base; churn hazard is uniform across plans,
    # so revenue_churn and logo_churn_rate coincide in expectation.
    # With 1000 users, sampling error is ~O(1/sqrt(n)) ≈ 0.003.
    for _, row in sample_metrics.iterrows():
        if row["month"] == 1:
            assert row["revenue_churn"] == 0.0
        else:
            assert abs(row["revenue_churn"] - row["logo_churn_rate"]) < 0.01
