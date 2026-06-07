# Agentic Approach

## 1. Role of the agent

The agent is a reporting orchestrator, not a calculation engine. Its job is to:

1. Run a deterministic data-to-metrics pipeline.
2. Gate the output through hard validation invariants.
3. If data passes, call an LLM to turn the metric table into a tight business narrative.
4. If data fails, issue a data-quality warning and refuse to present the metrics as trustworthy.

All numbers — synthetic data, aggregated metrics, validation checks — come from deterministic Python code. The LLM only reads numbers and writes prose.

## 2. Agent structure

The agent has four tools defined in `tools.py`:

- `generate_data(...)` — creates the synthetic panel and writes `data/users.csv`.
- `compute_metrics(...)` — reads the panel, writes `reports/metrics.csv`, and returns a markdown table.
- `run_validation(...)` — returns hard invariant results and soft anomalies.
- `lookup_metric(month, name)` — returns a single scalar from `reports/metrics.csv`.

The flow in `agent.py` / `cli.py` is:

1. CLI calls `generate_data`, `compute_metrics`, and `run_validation` in sequence. This is pure code, reproducible, and requires no API key.
2. If `validation.passed == False`, the report opens with a data-quality warning. CLI exits with code 2.
3. If `validation.passed == True` and `--no-llm` is off, the OpenAI model receives the metrics table, invariant list, and anomaly list. It may call `lookup_metric` up to 8 times (tool loop limit) to pull exact values for specific months.
4. After the tool loop, a final structured-output call returns a JSON object with six text sections and a `cited_numbers` array. This JSON is rendered to markdown by `report.py`.
5. A guardrail verifies every number in `cited_numbers` against `reports/metrics.csv` and raw data. Mismatches block the report (exit code 3).
6. If `--no-llm` is on, `report.py` builds the same JSON structure deterministically, then renders it to markdown.
7. On every run, `run_manifest.json` records seed, model, hashes, and `system_fingerprint`.

## 3. Where ordinary calculations live (and why)

- **Data generation (`data_generation.py`)** — Cohort simulation with hazard rates, payment failures, and anomaly injection. Code is the only way to guarantee a fixed seed produces identical output.
- **Metrics (`metrics.py`)** — Group-by aggregations on the panel. Computing churn rate, ARPU, MRR, cohort retention, NRR, and revenue churn from the raw table keeps the metrics independent of the generation model. This makes the tests meaningful: they check that metrics match the data, not that the data matches an internal state.
- **Validation (`validation.py`)** — Hard invariants (schema, row count, revenue reconciliation, monotonicity, churn closure) and soft anomaly detection (MoM revenue drops, churn spikes, failed-payment spikes). These are pure logic; an LLM would be slower, more expensive, and prone to missing edge cases.

Pydantic schemas in `schemas.py` add type safety at the row level, but the bulk validation is plain pandas for speed on 12 000 rows.

## 4. Prompts

### System prompt

```
You are a senior subscription and fintech analyst writing a monthly churn and revenue report.

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
```

### Task prompt template

```
Generate the churn and revenue report based on the following data.

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
```

### Structured output prompt

After the tool loop, the agent sends a final user message:

```
Now generate the final structured report in JSON using the exact schema provided. List every numeric value you used in the cited_numbers array.
```

The JSON schema enforces six string fields and a `cited_numbers` array of numbers. `strict: true` prevents the model from adding extra fields.

## 5. Guardrails

1. **LLM does not produce numbers freely.** All figures come from tools or pre-computed metrics. Structured output enforces a `cited_numbers` field that is programmatically verified.
2. **Validation gate.** Hard invariant failures block the normal narrative. The report is prefixed with a data-quality warning and CLI exits non-zero.
3. **Deterministic core.** Fixed seed, identical artifacts on every run. Covered by `test_determinism`.
4. **Temperature = 0.** Stabilizes reasoning and reduces hallucination variance.
5. **Pydantic row schemas.** Type-safe boundaries between generation, metrics, and validation.
6. **Post-check of cited numbers.** Every value in `cited_numbers` is compared against `metrics.csv` and raw data. Mismatches block the report.
7. **Tool-loop limit.** Max 8 iterations prevents runaway tool calling.
8. **No external network calls except OpenAI API.** No data leaves the local environment.
9. **Fallback `--no-llm`.** Full pipeline works and is testable without any API key.

## 6. Why this approach

The task explicitly asks for simplicity as a signal of maturity. A single agent with four tools is enough because the problem is well-defined: data -> metrics -> validation -> narrative. Splitting this into multiple agents adds coordination overhead without value.

LLMs excel at language and interpretation, not at precise arithmetic on structured tables. By locking all calculations into tested Python functions, we get:

- Reproducibility (same seed, same CSV).
- Verifiability (pytest covers metrics and validation).
- Cost control (no LLM tokens spent on math; single main call per report).
- Auditability (every number traces back to a pandas groupby).

The LLM adds value only where it is genuinely better: turning a table into a coherent business story with causal framing, provided the guardrails keep it honest.

## Hard invariants vs soft anomalies

**Hard invariants** are mathematical truths that must hold for the data to be internally consistent. If `active_users` increases month-over-month, or `amount_paid` differs from `monthly_price` for a paid row, the dataset is broken. These are not statistical quirks; they are logic errors. The pipeline treats them as blockers.

**Soft anomalies** are statistically unusual but valid patterns. A 25% MoM revenue drop, a churn rate double the median, or a failed-payment share of 22% are all real events that can happen in production. They flag opportunities for investigation, not bugs in the data. The report uses them as narrative anchors — the month 8 payment spike and the month 9 churn rebound — but they never prevent the pipeline from completing.

Keeping the two levels separate shows that the system understands the difference between "the data is wrong" and "the data is telling us something important."

## Money in cents

All monetary values inside the pipeline are integers representing whole cents. `Basic = 999`, `Pro = 1999`, `Premium = 3999`. `amount_paid` is either the plan price in cents or `0`. Revenue is summed as `int` and reconciled with exact equality — no epsilon tolerance.

Dollar formatting happens only at the CSV and report boundaries (`/ 100.0` with 2 decimal places). This eliminates the classic fintech bug where `0.1 + 0.2 != 0.3` breaks a reconciliation check.

## Trade-offs and scope boundaries

**What was deliberately not built:**

- **Multi-agent system.** The task asks for one agent, not a swarm. Adding planner, executor, and critic agents would be over-engineering for a 12 000-row dataset.
- **Database or queue.** pandas in memory is sufficient. PostgreSQL or Redis would add operational complexity with no benefit at this scale.
- **Docker as mandatory.** A `Dockerfile` is nice for portability, but `uv` + `pyproject.toml` already guarantees reproducible dependencies. Docker is noted as optional.
- **CI pipeline.** Not required for a CLI tool that is run on demand.
- **Frontend or dashboard.** Out of scope. Output is CSV and markdown.

**What would come next at scale:**

- Batch reporting: loop over multiple cohorts, reuse the same deterministic core.
- Prompt caching: the system prompt and schema are static; OpenAI prompt caching reduces cost.
- Plan-segmented hazard: in real data, churn hazard varies by plan. This would split `logo_churn_rate` and `revenue_churn` visibly.
