# Churn & Revenue Agent

Deterministic CLI agent that generates synthetic subscription data, computes churn and revenue metrics, validates data quality, and produces a business narrative report. The core pipeline runs without an API key; LLM mode adds a polished narrative but does not change the numbers.

## Why this design

- **Numbers come from code, not LLM.** All calculations — cohort simulation, revenue aggregation, validation — run in deterministic Python with fixed seeds. The LLM only reads metrics and writes prose.
- **Money is tracked in cents.** `monthly_price`, `amount_paid`, and `monthly_revenue` are stored and summed as integers (cents). Dollar formatting happens only at the output boundary. This eliminates float drift and makes revenue reconciliation exact.
- **Fail-closed on bad data.** If hard validation invariants fail, the pipeline exits with a non-zero code and emits a warning report, not a normal narrative. In fintech, a report on broken data is worse than no report.
- **Reproducible by seed.** The same seed produces identical `users.csv` and `metrics.csv` every time. The `--no-llm` mode guarantees this even without an API key.

## Assumptions

- **Closed cohort.** 1000 users join in month 1. No new acquisitions in months 2-12.
- **No reactivation.** Users who churn never return. This makes `active_users` monotonically non-increasing.
- **Full grid.** Every user has a row for every month (12 000 rows total). After churn, `payment_status` is `"churned"` and `amount_paid` is 0.
- **Active vs paid are distinct.** A user with a failed payment is still active (grace period) but does not generate revenue. `paid_users` is a subset of `active_users`.
- **Failed payments and churn are separate events.** Base churn follows a monthly hazard curve. On top of that, 40% of users with a failed payment in month m churn in month m+1 (involuntary churn).
- **ARPU on active base.** `ARPU = monthly_revenue / active_users`, including grace-period users. This reflects real pressure during payment outages.
- **Monetary fields in cents.** `monthly_price`, `amount_paid`, and `monthly_revenue` are integers representing whole cents. Dollars appear only in CSV display and reports.
- **Report language.** English by default.
- **Artifacts.** `data/users.csv` and `reports/*` are generated artifacts. They are committed for visibility, but the code guarantees identical regeneration from the same seed.

## Installation

Requires Python 3.11+ and `uv`.

```bash
uv sync --extra dev
```

Or use Make:

```bash
make install
```

## Running

With LLM narrative (requires `OPENAI_API_KEY`):

```bash
make report
# or explicitly
uv run python -m churn_agent run
```

Without LLM — deterministic template mode, no key needed:

```bash
uv run python -m churn_agent run --no-llm
```

Generate data only:

```bash
uv run python -m churn_agent generate
```

Run the full pipeline with custom parameters:

```bash
uv run python -m churn_agent run --seed 123 --n-users 500 --months 6 --no-anomaly --no-llm
```

## Reproducibility

The generator uses `numpy.random.default_rng(seed)`. The same seed produces bit-identical `users.csv` and `metrics.csv`. Default seed is 42. The `--seed` flag controls this explicitly.

LLM output is best-effort reproducible (`temperature=0`, `seed` passed to OpenAI), but OpenAI does not guarantee bitwise identical text. Hard reproducibility is provided by the deterministic core and `--no-llm` mode.

## Environment

Copy `.env.example` to `.env` and fill in your key:

```bash
OPENAI_API_KEY=sk-proj-...
OPENAI_MODEL=gpt-4o-mini
```

## Project structure

```
churn-revenue-agent/
├── README.md
├── AGENTIC_APPROACH.md
├── pyproject.toml
├── uv.lock
├── Makefile
├── .env.example
├── .gitignore
├── src/
│   └── churn_agent/
│       ├── __init__.py
│       ├── __main__.py
│       ├── config.py
│       ├── schemas.py
│       ├── data_generation.py
│       ├── metrics.py
│       ├── validation.py
│       ├── tools.py
│       ├── prompts.py
│       ├── agent.py
│       ├── report.py
│       └── cli.py
├── tests/
│   ├── test_data_generation.py
│   ├── test_metrics.py
│   └── test_validation.py
├── data/
│   └── users.csv
└── reports/
    ├── metrics.csv
    ├── report.md
    └── run_manifest.json
```

## Tests

```bash
make test
```

All tests run without an API key.

## Lint

```bash
make lint
```

## Architecture

See [AGENTIC_APPROACH.md](AGENTIC_APPROACH.md) for a detailed explanation of the agentic workflow, tools, prompts, guardrails, and the rationale behind the design.

## Security and PII hygiene

- Secrets are read only from environment variables. They never appear in code or logs.
- `.env` is in `.gitignore`; only `.env.example` is committed.
- The LLM receives only the aggregated metrics table, not row-level user data. On real data, always aggregate or anonymize before sending to any external API.
- `user_id` is a synthetic integer surrogate with no link to real PII.
