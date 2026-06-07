# Churn & Revenue Report

## Executive summary
The cohort of 1000 users generated $120473.96 in total revenue over 12 months. Revenue declined from $15470.27 in month 1 to $6865.72 in month 12. The sharpest revenue drop occurred in month 8 ($7085.48), driven by a payment failure anomaly that spilled into elevated churn in month 9. Early churn (months 2-3) consumed the largest share of the cohort. Cohort retention at month 12 is 0.4410 and NRR is 0.4438.

## Monthly revenue trend
Revenue started at $15470.27 in month 1 and trended downward as the cohort shrank. The sharpest single-month drop was from month 7 to month 8, losing $2338.49. After the anomaly, revenue partially recovered but never returned to pre-anomaly levels.

| month | active_users | paid_users | churned_users | monthly_revenue | churn_rate | arpu |
|-------|-------------|------------|---------------|-----------------|------------|------|
| 1 | 1000 | 973 | 0 | 15470.27 | 0.0000 | 15.47 |
| 2 | 910 | 877 | 90 | 13991.23 | 0.0900 | 15.37 |
| 3 | 820 | 801 | 90 | 12541.99 | 0.0989 | 15.30 |
| 4 | 756 | 729 | 64 | 11462.71 | 0.0780 | 15.16 |
| 5 | 703 | 693 | 53 | 10953.07 | 0.0701 | 15.58 |
| 6 | 665 | 645 | 38 | 10253.55 | 0.0541 | 15.42 |
| 7 | 619 | 603 | 46 | 9423.97 | 0.0692 | 15.22 |
| 8 | 582 | 452 | 37 | 7085.48 | 0.0598 | 12.17 |
| 9 | 510 | 496 | 72 | 7855.04 | 0.1237 | 15.40 |
| 10 | 477 | 471 | 33 | 7525.29 | 0.0647 | 15.78 |
| 11 | 455 | 436 | 22 | 7045.64 | 0.0461 | 15.48 |
| 12 | 441 | 428 | 14 | 6865.72 | 0.0308 | 15.57 |

## Churn trend
Month 1 churn rate is N/A because there is no preceding month. The highest churn rate was in month 9 (0.1237), while the lowest rate after month 1 was in month 12 (0.0308). Months 2 and 3 show elevated rates consistent with an onboarding cliff.

## ARPU trend
ARPU began at $15.47 and dipped to $12.17 in month 8, the same month as the payment failure spike. ARPU is calculated on the full active base, including grace-period users, so a surge in failed payments directly depresses the metric even when the active count is stable.

## Data quality checks
Hard invariants checked:
- PASS: schema_complete — All expected columns present
- PASS: no_nulls — No nulls in required columns
- PASS: row_count — Row count OK (12000)
- PASS: monthly_price_positive — All prices positive
- PASS: amount_paid_consistency — amount_paid consistent
- PASS: payment_status_values — All statuses valid
- PASS: revenue_reconciliation — Revenue reconciles with raw data
- PASS: paid_le_active — paid_users <= active_users OK
- PASS: churn_rate_bounds — churn_rate within bounds
- PASS: active_monotonic — active_users monotonically non-increasing
- PASS: churn_closure — Churn closure OK
- PASS: churned_consistency — churned_users consistent with active delta

Soft anomalies detected:
- WARNING: revenue_drop (month 8) — Revenue dropped 24.8% MoM
- WARNING: failed_spike (month 8) — Failed payment share 22.3% in month 8

## Business interpretation
Revenue declined steadily because the closed cohort shrinks each month through churn. The payment anomaly in month 8 cost approximately $2338.49 in immediate MRR and triggered 72 churned users in month 9 versus 37 in month 8. This confirms that failed payments are not just a revenue timing issue—they directly accelerate attrition.

Key takeaways:
1. Early churn (months 2-3) removes a large fraction of the cohort. Target onboarding improvements in the first 60 days. Month 2 churn alone was 0.0900, month 3 was 0.0989.
2. The month 8 payment failure spike cost $2338.49 in MRR and pushed 72 users into churn in month 9. Implement retry and dunning flows to catch failed payments before they convert to involuntary churn.
3. ARPU compression in month 8 shows that failed payments hurt the metric even when user counts look stable. Monitor failed-payment share as a leading indicator of both revenue and churn risk.
4. Logo churn and revenue churn coincide in this model because the hazard rate does not depend on plan. On real data, if expensive plans churn faster, revenue churn would exceed logo churn—worth segmenting by plan.
