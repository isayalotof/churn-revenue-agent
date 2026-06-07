# Churn & Revenue Report

## Executive summary
The revenue trend shows a decline from month 1 to month 8, followed by a slight recovery in month 9. Churn rates have fluctuated, with a notable spike in month 9. The main finding indicates a correlation between the failed payment spike in month 8 and the increased churn in month 9.

## Monthly revenue trend
Monthly revenue values are as follows: Month 1: 15470.27, Month 2: 13991.23, Month 3: 12541.99, Month 4: 11462.71, Month 5: 10953.07, Month 6: 10253.55, Month 7: 9423.97, Month 8: 7085.48 (drop point), Month 9: 7855.04, Month 10: 7525.29, Month 11: 7045.64, Month 12: 6865.72.


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
Churn rates by month are as follows: Month 1: N/A, Month 2: 0.0900, Month 3: 0.0989, Month 4: 0.0780, Month 5: 0.0701, Month 6: 0.0541, Month 7: 0.0692, Month 8: 0.0598, Month 9: 0.1237, Month 10: 0.0647, Month 11: 0.0461, Month 12: 0.0308.

## ARPU trend
ARPU values show a slight decline over the months, with a notable dip in month 8 to 12.17, likely due to the drop in paid users. The ARPU recovered slightly in month 9 to 15.40.

## Data quality checks
All validation invariants passed: schema_complete, no_nulls, row_count, monthly_price_positive, amount_paid_consistency, payment_status_values, revenue_reconciliation, paid_le_active, churn_rate_bounds, active_monotonic, churn_closure, churned_consistency.

## Business interpretation
Revenue decreased significantly in month 8, with a drop of 24.8%. The churn rate peaked in month 9 at 0.1237, likely due to the failed payment spike of 22.3% in month 8. Actionable takeaways include investigating the revenue drop in month 8, addressing the high failed payment rate, and focusing on retention strategies in month 9.
