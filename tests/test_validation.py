"""Tests for validation logic."""

import pytest

from churn_agent.config import DEFAULT_SEED
from churn_agent.data_generation import generate_users
from churn_agent.metrics import compute_monthly_metrics
from churn_agent.validation import validate


@pytest.fixture
def valid_data():
    raw = generate_users(seed=DEFAULT_SEED)
    metrics = compute_monthly_metrics(raw)
    return raw, metrics


def test_all_invariants_pass_on_valid_data(valid_data):
    raw, metrics = valid_data
    result = validate(raw, metrics)
    assert result.passed
    for check in result.invariants:
        assert check.passed, f"Invariant failed: {check.name} — {check.detail}"


def test_broken_amount_paid_fails():
    raw = generate_users(seed=DEFAULT_SEED)
    metrics = compute_monthly_metrics(raw)
    raw.loc[0, "amount_paid"] = raw.loc[0, "amount_paid"] + 1.0
    result = validate(raw, metrics)
    assert not result.passed
    assert any(c.name == "amount_paid_consistency" and not c.passed for c in result.invariants)


def test_anomaly_detected():
    raw = generate_users(seed=DEFAULT_SEED, inject_anomaly=True)
    metrics = compute_monthly_metrics(raw)
    result = validate(raw, metrics)
    assert any(a.name == "failed_spike" and a.month == 8 for a in result.anomalies)
