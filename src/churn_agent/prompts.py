"""Prompts for the LLM agent."""

SYSTEM_PROMPT = """You are a senior subscription and fintech analyst writing a monthly churn and revenue report.

Hard rules:
- Use ONLY numbers available via the provided metrics table and the lookup_metric tool. Never invent, estimate, average, or extrapolate any figure. If something is not derivable from the data, state that the data does not support it.
- Reference specific months and exact values. Connect churn to revenue causally only where the data supports it.
- Output exactly six markdown sections in order, with the headers provided below.
- No filler, no hedging boilerplate, no emojis. Tight prose.
- If validation reports any hard-invariant failure, open with a data-quality warning and explicitly state the metrics are not trustworthy.

Output structure (exact headers):
1. Executive summary
2. Monthly revenue trend
3. Churn trend
4. ARPU trend
5. Data quality checks
6. Business interpretation
"""

TASK_PROMPT_TEMPLATE = """Generate the churn and revenue report based on the following data.

Context: 1000 users, 12-month closed cohort, subscription fintech product.

Metrics table:
{metrics_table}

Validation invariants:
{invariants}

Detected anomalies:
{anomalies}

Instructions:
- Write exactly six sections with the headers specified in your system prompt.
- Use the lookup_metric tool if you need exact values for specific months.
- In section 3 (Churn trend), note that month 1 churn rate is N/A because there is no previous month.
- In section 6 (Business interpretation), cover: revenue changes, high/low churn months, causal link between month 8 and month 9 (payment failure spike -> churn spike), anomalies, and 2-3 concrete actionable business takeaways with exact numbers.
- Keep each section concise and specific. Avoid generic advice.
"""

STRUCTURED_OUTPUT_SYSTEM = """You are a senior subscription and fintech analyst. Generate the final structured churn and revenue report in JSON.

Hard rules:
- Use ONLY numbers from the data provided. Never invent or estimate.
- Every number cited in the text must also appear in the cited_numbers array.
- Sections must be concise, specific, and free of filler or emojis.
"""


def format_task_prompt(
    metrics_table: str,
    invariants: list,
    anomalies: list,
) -> str:
    """Build the task prompt from structured inputs."""
    inv_lines = "\n".join(
        f"- {'PASS' if c.passed else 'FAIL'}: {c.name} — {c.detail}" for c in invariants
    )
    if anomalies:
        anom_lines = "\n".join(
            f"- {a.severity.upper()}: {a.name} (month {a.month}) — {a.detail}" for a in anomalies
        )
    else:
        anom_lines = "None detected."

    return TASK_PROMPT_TEMPLATE.format(
        metrics_table=metrics_table,
        invariants=inv_lines,
        anomalies=anom_lines,
    )


REPORT_JSON_SCHEMA = {
    "name": "churn_report",
    "strict": True,
    "schema": {
        "type": "object",
        "properties": {
            "executive_summary": {
                "type": "string",
                "description": "3-5 sentences: revenue trend, churn trend, main finding.",
            },
            "monthly_revenue_trend": {
                "type": "string",
                "description": "Revenue month-by-month with exact values and the drop point.",
            },
            "churn_trend": {
                "type": "string",
                "description": "Churn by month with exact values. Note month 1 is N/A.",
            },
            "arpu_trend": {
                "type": "string",
                "description": "ARPU dynamics and explanation of the anomaly-month dip.",
            },
            "data_quality_checks": {
                "type": "string",
                "description": "What hard invariants were checked, results, and anomalies found.",
            },
            "business_interpretation": {
                "type": "string",
                "description": "Revenue changes, churn months, causal link m8->m9, anomalies, 2-3 actionable takeaways with exact numbers.",
            },
            "cited_numbers": {
                "type": "array",
                "items": {"type": "number"},
                "description": "Every numeric value used in the report text. Include dollars, percentages, and counts.",
            },
        },
        "required": [
            "executive_summary",
            "monthly_revenue_trend",
            "churn_trend",
            "arpu_trend",
            "data_quality_checks",
            "business_interpretation",
            "cited_numbers",
        ],
        "additionalProperties": False,
    },
}
