"""LLM agent orchestration via OpenAI with structured outputs."""

import json
import re

import pandas as pd
from openai import OpenAI

from churn_agent.config import OPENAI_API_KEY, OPENAI_MODEL
from churn_agent.prompts import (
    REPORT_JSON_SCHEMA,
    STRUCTURED_OUTPUT_SYSTEM,
    format_task_prompt,
)
from churn_agent.tools import lookup_metric

MAX_ITERATIONS = 8


def _build_tools() -> list[dict]:
    return [
        {
            "type": "function",
            "function": {
                "name": "lookup_metric",
                "description": "Get an exact metric value for a specific month.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "month": {
                            "type": "integer",
                            "description": "Month number (1-12)",
                        },
                        "name": {
                            "type": "string",
                            "description": "Metric column name, e.g. monthly_revenue, churn_rate, arpu",
                        },
                    },
                    "required": ["month", "name"],
                },
            },
        }
    ]


def _run_tool_loop(
    client: OpenAI,
    model_name: str,
    messages: list[dict],
) -> list[dict]:
    """Optional tool-gathering phase. Returns updated messages."""
    for _ in range(MAX_ITERATIONS):
        response = client.chat.completions.create(
            model=model_name,
            messages=messages,
            tools=_build_tools(),
            tool_choice="auto",
            temperature=0,
        )
        message = response.choices[0].message
        if not message.tool_calls:
            messages.append({"role": "assistant", "content": message.content or ""})
            return messages

        messages.append(
            {
                "role": "assistant",
                "content": message.content or "",
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": tc.type,
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    }
                    for tc in message.tool_calls
                ],
            }
        )

        for tc in message.tool_calls:
            name = tc.function.name
            args = json.loads(tc.function.arguments)
            try:
                if name == "lookup_metric":
                    result = lookup_metric(args["month"], args["name"])
                else:
                    result = "Unknown tool"
            except Exception as exc:
                result = f"Error: {exc}"

            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": json.dumps({"value": result}),
                }
            )
    return messages


def run_agent(
    metrics_table: str,
    invariants: list,
    anomalies: list,
    api_key: str | None = None,
    model: str | None = None,
) -> tuple[dict, str | None]:
    """Run the LLM agent and return parsed JSON report + system_fingerprint."""
    client = OpenAI(api_key=api_key or OPENAI_API_KEY)
    model_name = model or OPENAI_MODEL

    task_prompt = format_task_prompt(metrics_table, invariants, anomalies)

    messages = [
        {"role": "system", "content": STRUCTURED_OUTPUT_SYSTEM},
        {"role": "user", "content": task_prompt},
    ]

    # Phase 1: optional fact gathering via tools
    messages = _run_tool_loop(client, model_name, messages)

    # Phase 2: structured JSON output
    messages.append(
        {
            "role": "user",
            "content": (
                "Now generate the final structured report in JSON using the exact schema provided. "
                "List every numeric value you used in the cited_numbers array."
            ),
        }
    )

    response = client.chat.completions.create(
        model=model_name,
        messages=messages,
        response_format={"type": "json_schema", "json_schema": REPORT_JSON_SCHEMA},
        temperature=0,
    )

    content = response.choices[0].message.content or "{}"
    data = json.loads(content)
    fingerprint = getattr(response, "system_fingerprint", None)
    return data, fingerprint


def extract_numbers(text: str) -> list[tuple[int | None, float]]:
    """Extract numeric values from report text for guardrail checking."""
    numbers = []
    lines = text.splitlines()
    current_month: int | None = None

    for line in lines:
        month_match = re.search(r"\bmonth\s+(\d{1,2})\b|\bm(\d{1,2})\b", line, re.IGNORECASE)
        if month_match:
            current_month = int(month_match.group(1) or month_match.group(2))

        for match in re.finditer(r"\$?([0-9,]+(?:\.[0-9]+)?)", line):
            num_str = match.group(1).replace(",", "")
            if not num_str:
                continue
            num = float(num_str)
            numbers.append((current_month, num))

    return numbers


def verify_cited_numbers(
    cited_numbers: list[float],
    metrics_path: str = "reports/metrics.csv",
    raw_path: str = "data/users.csv",
) -> list[str]:
    """Verify every cited number exists in metrics or raw data."""
    metrics = pd.read_csv(metrics_path)
    raw = pd.read_csv(raw_path)
    issues = []

    metric_values: set[float] = set()
    for _, row in metrics.iterrows():
        metric_values.add(round(float(row["monthly_revenue"]), 2))
        metric_values.add(round(float(row["churn_rate"]), 4))
        metric_values.add(round(float(row["arpu"]), 2))
        metric_values.add(round(float(row.get("mrr", row["monthly_revenue"])), 2))
        metric_values.add(round(float(row.get("cohort_retention", 0)), 4))
        metric_values.add(round(float(row.get("revenue_churn", 0)), 4))
        metric_values.add(round(float(row.get("nrr", 0)), 4))
        metric_values.add(float(row["active_users"]))
        metric_values.add(float(row["paid_users"]))
        metric_values.add(float(row["churned_users"]))

    for idx in range(1, len(metrics)):
        prev_rev = metrics["monthly_revenue"].iloc[idx - 1]
        curr_rev = metrics["monthly_revenue"].iloc[idx]
        if prev_rev > 0:
            drop_pct = round((prev_rev - curr_rev) / prev_rev * 100, 1)
            metric_values.add(drop_pct)
            metric_values.add(round(drop_pct, 2))

    active = raw[raw["is_active"]]
    monthly_failed = (
        active.groupby("month")
        .agg(
            total=("payment_status", "size"),
            failed=("payment_status", lambda x: (x == "failed").sum()),
        )
        .reset_index()
    )
    monthly_failed["failed_share"] = monthly_failed["failed"] / monthly_failed["total"] * 100
    for _, row in monthly_failed.iterrows():
        metric_values.add(round(float(row["failed_share"]), 1))
        metric_values.add(round(float(row["failed_share"]), 2))

    def is_close(val: float, target: float, tol: float = 0.05) -> bool:
        return abs(val - target) <= tol

    for num in cited_numbers:
        candidates = [num, num / 100, num * 100]
        found = any(is_close(c, mv) for c in candidates for mv in metric_values)
        if not found:
            issues.append(f"Cited number {num} not found in metrics or raw data")

    return issues
