.PHONY: install run report test lint

install:
	uv sync --extra dev

run:
	uv run python -m churn_agent run

report:
	uv run python -m churn_agent run --no-llm

test:
	uv run pytest tests/ -v

lint:
	uv run ruff check src tests
	uv run ruff format --check src tests
