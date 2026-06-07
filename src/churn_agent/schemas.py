"""Pydantic schemas for data validation."""

from typing import Literal

from pydantic import BaseModel, Field, field_validator


class UserRow(BaseModel):
    """Schema for a single user-month row."""

    user_id: int = Field(..., ge=0)
    month: int = Field(..., ge=1, le=12)
    plan: Literal["Basic", "Pro", "Premium"]
    monthly_price: int = Field(..., gt=0)
    payment_status: Literal["paid", "failed", "churned"]
    amount_paid: int = Field(..., ge=0)
    is_active: bool

    @field_validator("amount_paid")
    @classmethod
    def check_amount_paid(cls, v: int, info) -> int:
        values = info.data
        if values.get("payment_status") == "paid" and v != values.get("monthly_price"):
            raise ValueError("amount_paid must equal monthly_price when paid")
        if values.get("payment_status") != "paid" and v != 0:
            raise ValueError("amount_paid must be 0 when not paid")
        return v


class MetricRow(BaseModel):
    """Schema for a single month of aggregated metrics."""

    month: int = Field(..., ge=1, le=12)
    active_users: int = Field(..., ge=0)
    paid_users: int = Field(..., ge=0)
    churned_users: int = Field(..., ge=0)
    monthly_revenue: int = Field(..., ge=0)
    churn_rate: float = Field(..., ge=0, le=1)
    arpu: float = Field(..., ge=0)
    mrr: int = Field(..., ge=0)
    cohort_retention: float = Field(..., ge=0, le=1)
    logo_churn_rate: float = Field(..., ge=0, le=1)
    revenue_churn: float = Field(..., ge=0, le=1)
    nrr: float = Field(..., ge=0)

    @field_validator("paid_users")
    @classmethod
    def check_paid_users(cls, v: int, info) -> int:
        values = info.data
        if v > values.get("active_users", 0):
            raise ValueError("paid_users cannot exceed active_users")
        return v
