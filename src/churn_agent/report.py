"""Deterministic report generation and markdown rendering."""

import pandas as pd

from churn_agent.validation import ValidationResult


def render_report_md(report_json: dict, metrics_table: str) -> str:
    """Render a structured JSON report into markdown."""
    lines = []
    lines.append("# Churn & Revenue Report")
    lines.append("")

    if report_json.get("data_quality_warning"):
        lines.append(
            "**Warning: Data quality checks failed. Metrics below may not be trustworthy.**"
        )
        lines.append("")

    sections = [
        ("executive_summary", "Executive summary"),
        ("monthly_revenue_trend", "Monthly revenue trend"),
        ("churn_trend", "Churn trend"),
        ("arpu_trend", "ARPU trend"),
        ("data_quality_checks", "Data quality checks"),
        ("business_interpretation", "Business interpretation"),
    ]

    for key, title in sections:
        text = report_json.get(key, "")
        if text:
            lines.append(f"## {title}")
            lines.append(text)
            lines.append("")

    # Inject metrics table into Monthly revenue trend if present
    if "monthly_revenue_trend" in report_json:
        md = "\n".join(lines)
        if "| month |" not in md:
            # Insert table after the Monthly revenue trend section
            for i, line in enumerate(lines):
                if line == "## Monthly revenue trend":
                    # Find the next blank line after the section text
                    j = i + 1
                    while j < len(lines) and lines[j].strip() != "":
                        j += 1
                    lines.insert(j + 1, metrics_table)
                    lines.insert(j + 2, "")
                    break

    return "\n".join(lines)


def build_no_llm_report(metrics_table: str, result: ValidationResult) -> dict:
    """Build a structured JSON report deterministically (no LLM)."""
    metrics = pd.read_csv("reports/metrics.csv")
    # Read back as cents for exact computation
    for col in ["monthly_revenue", "arpu", "mrr"]:
        if col in metrics.columns:
            metrics[col] = (metrics[col] * 100).round().astype(int)

    total_revenue = int(metrics["monthly_revenue"].sum())
    start_revenue = int(metrics["monthly_revenue"].iloc[0])
    end_revenue = int(metrics["monthly_revenue"].iloc[-1])

    revenue_diffs = metrics["monthly_revenue"].diff()
    sharpest_drop_idx = revenue_diffs.idxmin()
    sharpest_drop_month = int(metrics.loc[sharpest_drop_idx, "month"])
    sharpest_drop_revenue = int(metrics.loc[sharpest_drop_idx, "monthly_revenue"])
    sharpest_drop_amount = int(-revenue_diffs.min())

    max_churn_idx = metrics["churn_rate"].idxmax()
    max_churn_month = int(metrics.loc[max_churn_idx, "month"])
    max_churn_rate = float(metrics.loc[max_churn_idx, "churn_rate"])

    min_churn_idx = metrics[metrics["month"] > 1]["churn_rate"].idxmin()
    min_churn_month = int(metrics.loc[min_churn_idx, "month"])
    min_churn_rate = float(metrics.loc[min_churn_idx, "churn_rate"])

    start_arpu = int(metrics["arpu"].iloc[0])
    min_arpu_idx = metrics["arpu"].idxmin()
    min_arpu_month = int(metrics.loc[min_arpu_idx, "month"])
    min_arpu = int(metrics.loc[min_arpu_idx, "arpu"])

    month_7_revenue = int(metrics.loc[metrics["month"] == 7, "monthly_revenue"].iloc[0])
    month_8_revenue = int(metrics.loc[metrics["month"] == 8, "monthly_revenue"].iloc[0])
    month_9_churned = int(metrics.loc[metrics["month"] == 9, "churned_users"].iloc[0])
    month_8_churned = int(metrics.loc[metrics["month"] == 8, "churned_users"].iloc[0])
    mrr_month_1 = int(metrics.loc[metrics["month"] == 1, "mrr"].iloc[0])
    mrr_month_8 = int(metrics.loc[metrics["month"] == 8, "mrr"].iloc[0])
    nrr_month_12 = float(metrics.loc[metrics["month"] == 12, "nrr"].iloc[0])
    retention_month_12 = float(metrics.loc[metrics["month"] == 12, "cohort_retention"].iloc[0])

    def fmt_dollars(cents: int) -> str:
        return f"${cents / 100:.2f}"

    report = {
        "data_quality_warning": not result.passed,
        "executive_summary": (
            f"The cohort of 1000 users generated {fmt_dollars(total_revenue)} in total revenue over 12 months. "
            f"Revenue declined from {fmt_dollars(start_revenue)} in month 1 to {fmt_dollars(end_revenue)} in month 12. "
            f"The sharpest revenue drop occurred in month {sharpest_drop_month} ({fmt_dollars(sharpest_drop_revenue)}), "
            f"driven by a payment failure anomaly that spilled into elevated churn in month {max_churn_month}. "
            f"Early churn (months 2-3) consumed the largest share of the cohort. "
            f"Cohort retention at month 12 is {retention_month_12:.4f} and NRR is {nrr_month_12:.4f}."
        ),
        "monthly_revenue_trend": (
            f"Revenue started at {fmt_dollars(start_revenue)} in month 1 and trended downward as the cohort shrank. "
            f"The sharpest single-month drop was from month {sharpest_drop_month - 1} to month {sharpest_drop_month}, "
            f"losing {fmt_dollars(sharpest_drop_amount)}. After the anomaly, revenue partially recovered but never returned to pre-anomaly levels."
        ),
        "churn_trend": (
            f"Month 1 churn rate is N/A because there is no preceding month. "
            f"The highest churn rate was in month {max_churn_month} ({max_churn_rate:.4f}), "
            f"while the lowest rate after month 1 was in month {min_churn_month} ({min_churn_rate:.4f}). "
            f"Months 2 and 3 show elevated rates consistent with an onboarding cliff."
        ),
        "arpu_trend": (
            f"ARPU began at {fmt_dollars(start_arpu)} and dipped to {fmt_dollars(min_arpu)} in month {min_arpu_month}, "
            f"the same month as the payment failure spike. "
            f"ARPU is calculated on the full active base, including grace-period users, "
            f"so a surge in failed payments directly depresses the metric even when the active count is stable."
        ),
        "data_quality_checks": (
            "Hard invariants checked:\n"
            + "\n".join(
                f"- {'PASS' if c.passed else 'FAIL'}: {c.name} — {c.detail}"
                for c in result.invariants
            )
            + "\n\n"
            + (
                "Soft anomalies detected:\n"
                + "\n".join(
                    f"- {a.severity.upper()}: {a.name} (month {a.month}) — {a.detail}"
                    for a in result.anomalies
                )
                if result.anomalies
                else "No soft anomalies detected."
            )
        ),
        "business_interpretation": (
            f"Revenue declined steadily because the closed cohort shrinks each month through churn. "
            f"The payment anomaly in month 8 cost approximately {fmt_dollars(month_7_revenue - month_8_revenue)} in immediate MRR "
            f"and triggered {month_9_churned} churned users in month 9 versus {month_8_churned} in month 8. "
            f"This confirms that failed payments are not just a revenue timing issue—they directly accelerate attrition.\n\n"
            f"Key takeaways:\n"
            f"1. Early churn (months 2-3) removes a large fraction of the cohort. Target onboarding improvements in the first 60 days. "
            f"Month 2 churn alone was {metrics.loc[metrics['month'] == 2, 'churn_rate'].iloc[0]:.4f}, "
            f"month 3 was {metrics.loc[metrics['month'] == 3, 'churn_rate'].iloc[0]:.4f}.\n"
            f"2. The month 8 payment failure spike cost {fmt_dollars(month_7_revenue - month_8_revenue)} in MRR and pushed {month_9_churned} users into churn in month 9. "
            f"Implement retry and dunning flows to catch failed payments before they convert to involuntary churn.\n"
            f"3. ARPU compression in month {min_arpu_month} shows that failed payments hurt the metric even when user counts look stable. "
            f"Monitor failed-payment share as a leading indicator of both revenue and churn risk.\n"
            f"4. Logo churn and revenue churn coincide in this model because the hazard rate does not depend on plan. "
            f"On real data, if expensive plans churn faster, revenue churn would exceed logo churn—worth segmenting by plan."
        ),
        "cited_numbers": [
            total_revenue / 100,
            start_revenue / 100,
            end_revenue / 100,
            sharpest_drop_month,
            sharpest_drop_revenue / 100,
            sharpest_drop_amount / 100,
            max_churn_month,
            max_churn_rate,
            min_churn_month,
            min_churn_rate,
            start_arpu / 100,
            min_arpu / 100,
            min_arpu_month,
            month_7_revenue / 100,
            month_8_revenue / 100,
            month_9_churned,
            month_8_churned,
            mrr_month_1 / 100,
            mrr_month_8 / 100,
            nrr_month_12,
            retention_month_12,
        ],
    }

    return report
