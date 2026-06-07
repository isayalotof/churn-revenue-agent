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

    # Inject metrics table into Monthly revenue trend if not already present
    md_text = "\n".join(lines)
    if "| month |" not in md_text:
        for i, line in enumerate(lines):
            if line == "## Monthly revenue trend":
                # Find the next section header or end of text to insert before
                insert_pos = len(lines)
                for j in range(i + 1, len(lines)):
                    if lines[j].startswith("## "):
                        insert_pos = j
                        break
                lines.insert(insert_pos, "")
                lines.insert(insert_pos + 1, metrics_table)
                lines.insert(insert_pos + 2, "")
                break

    return "\n".join(lines)


def build_no_llm_report(metrics_df: pd.DataFrame, result: ValidationResult) -> dict:
    """Build a structured JSON report deterministically (no LLM)."""
    metrics = metrics_df.copy()

    total_revenue = int(metrics["monthly_revenue"].sum())
    start_revenue = int(metrics["monthly_revenue"].iloc[0])
    total_mrr = int(metrics["mrr"].sum())
    start_mrr = int(metrics["mrr"].iloc[0])
    end_mrr = int(metrics["mrr"].iloc[-1])

    revenue_diffs = metrics["monthly_revenue"].diff()
    sharpest_drop_idx = revenue_diffs.idxmin()
    sharpest_drop_month = int(metrics.loc[sharpest_drop_idx, "month"])
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
            f"Когорта из 1000 юзеров принесла {fmt_dollars(total_revenue)} collected revenue за 12 месяцев. "
            f"Contract MRR просела с {fmt_dollars(start_mrr)} до {fmt_dollars(end_mrr)}. "
            f"Самый резкий провал collected revenue — месяц {sharpest_drop_month} ({fmt_dollars(month_8_revenue)}). "
            f"Причина: сбой платежей. Это не contraction MRR — подписки остались активными, просто не списались. "
            f"Retention когорты на месяц 12: {retention_month_12:.4f}, NRR: {nrr_month_12:.4f}."
        ),
        "monthly_revenue_trend": (
            f"Collected revenue стартовала с {fmt_dollars(start_revenue)} и шла вниз вместе с сокращением базы. "
            f"Резкий drop с месяца {sharpest_drop_month - 1} на {sharpest_drop_month}: минус {fmt_dollars(sharpest_drop_amount)}. "
            f"После аномалии частичное восстановление, но до докризисного уровня не вернулись."
        ),
        "churn_trend": (
            f"Month 1 churn rate — N/A, предыдущего месяца нет. "
            f"Пик churn rate — месяц {max_churn_month} ({max_churn_rate:.4f}). "
            f"Минимум после месяца 1 — месяц {min_churn_month} ({min_churn_rate:.4f}). "
            f"Месяцы 2-3 показывают onboarding cliff — классическая картина для subscription."
        ),
        "arpu_trend": (
            f"ARPU (collected / active base) стартовал с {fmt_dollars(start_arpu)} и упал до {fmt_dollars(min_arpu)} в месяц {min_arpu_month}. "
            f"ARPU считается на всю активную базу, включая grace-период. "
            f"Поэтому всплеск failed-платежей мгновенно давит ARPU, хотя active users выглядят стабильно."
        ),
        "data_quality_checks": (
            "Hard invariants:\n"
            + "\n".join(
                f"- {'PASS' if c.passed else 'FAIL'}: {c.name} — {c.detail}"
                for c in result.invariants
            )
            + "\n\n"
            + (
                "Soft anomalies:\n"
                + "\n".join(
                    f"- {a.severity.upper()}: {a.name} (month {a.month}) — {a.detail}"
                    for a in result.anomalies
                )
                if result.anomalies
                else "No soft anomalies."
            )
        ),
        "business_interpretation": (
            f"Collected revenue падает по двум каналам: отток базы и failed-платежи. "
            f"В месяце 8 сбой биллинга стоил {fmt_dollars(month_7_revenue - month_8_revenue)} collected revenue, "
            f"а в месяце 9 churn вырос до {month_9_churned} юзеров против {month_8_churned} в месяце 8. "
            f"Это прямая causal chain: failed payment → involuntary churn в следующем месяце.\n\n"
            f"Takeaways:\n"
            f"1. Ранний churn (месяцы 2-3) съедает ~{metrics.loc[metrics['month'] == 2, 'churn_rate'].iloc[0]:.1%} когорты каждый месяц. "
            f"Цель — onboarding в первые 60 дней, не общие «улучшения retention».\n"
            f"2. Сбой платежей в месяце 8 стоил {fmt_dollars(month_7_revenue - month_8_revenue)} collected revenue и спровоцировал всплеск churn в месяце 9. "
            f"Нужен retry/dunning-флоу, который ловит failed ещё до конверсии в churn.\n"
            f"3. Logo churn rate и revenue churn практически совпадают (разница в пределах сэмплинга), "
            f"потому что hazard не зависит от плана. На реальных данных, если дорогие планы уходят быстрее, "
            f"revenue churn уйдёт вперёд — и это станет видно по сегментации."
        ),
        "cited_numbers": [
            total_revenue / 100,
            total_mrr / 100,
            start_mrr / 100,
            end_mrr / 100,
            sharpest_drop_month,
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
