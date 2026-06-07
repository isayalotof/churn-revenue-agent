"""CLI entry point with typer."""

import json
import logging
import sys
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from churn_agent.config import (
    DEFAULT_ANOMALY_MONTH,
    DEFAULT_N_MONTHS,
    DEFAULT_N_USERS,
    DEFAULT_SEED,
    GEN_META_JSON,
    METRICS_CSV,
    OPENAI_API_KEY,
    OPENAI_MODEL,
    REPORT_MD,
    USERS_CSV,
)
from churn_agent.report import build_no_llm_report, render_report_md
from churn_agent.tools import (
    compute_metrics,
    generate_data,
    run_validation,
    write_manifest,
)
from churn_agent.validation import ValidationResult

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger(__name__)

app = typer.Typer(help="Churn & Revenue Reporting Agent")
console = Console()


def _print_validation(result: ValidationResult) -> None:
    table = Table(title="Validation Results")
    table.add_column("Check", style="cyan")
    table.add_column("Status", style="green")
    table.add_column("Detail", style="white")
    for check in result.invariants:
        status = "[green]PASS[/green]" if check.passed else "[red]FAIL[/red]"
        table.add_row(check.name, status, check.detail)
    console.print(table)
    if result.anomalies:
        console.print("[yellow]Anomalies detected:[/yellow]")
        for a in result.anomalies:
            console.print(f"  {a.severity.upper()}: {a.name} (month {a.month}) — {a.detail}")


def _read_gen_meta() -> dict:
    if Path(GEN_META_JSON).exists():
        with open(GEN_META_JSON, encoding="utf-8") as f:
            return json.load(f)
    return {
        "seed": DEFAULT_SEED,
        "n_users": DEFAULT_N_USERS,
        "n_months": DEFAULT_N_MONTHS,
        "inject_anomaly": True,
        "anomaly_month": DEFAULT_ANOMALY_MONTH,
    }


@app.command()
def generate(
    n_users: int = typer.Option(DEFAULT_N_USERS, help="Number of users"),
    n_months: int = typer.Option(DEFAULT_N_MONTHS, help="Number of months"),
    seed: int = typer.Option(DEFAULT_SEED, help="Random seed"),
    anomaly: bool = typer.Option(True, "--anomaly/--no-anomaly", help="Inject payment anomaly"),
    anomaly_month: int = typer.Option(DEFAULT_ANOMALY_MONTH, help="Anomaly month"),
    output: str = typer.Option(USERS_CSV, help="Output CSV path"),
) -> None:
    """Generate synthetic user data."""
    df = generate_data(
        n_users=n_users,
        n_months=n_months,
        seed=seed,
        inject_anomaly=anomaly,
        anomaly_month=anomaly_month,
        output_path=output,
    )
    console.print(
        f"[green]Generated {len(df)} rows ({n_users} users x {n_months} months) "
        f"with seed={seed}, anomaly={anomaly}.[/green]"
    )


@app.command()
def report(
    input_path: str = typer.Option(USERS_CSV, help="Input users CSV"),
    metrics_path: str = typer.Option(METRICS_CSV, help="Output metrics CSV"),
    report_path: str = typer.Option(REPORT_MD, help="Output report path"),
    no_llm: bool = typer.Option(False, "--no-llm", help="Skip LLM, use deterministic template"),
    model: str | None = typer.Option(OPENAI_MODEL, help="OpenAI model"),
) -> None:
    """Compute metrics, validate, and generate report."""
    import pandas as pd

    if not Path(input_path).exists():
        console.print(f"[red]Input file not found: {input_path}. Run 'generate' first.[/red]")
        raise typer.Exit(code=1)

    raw_df = pd.read_csv(input_path)
    raw_df["monthly_price"] = (raw_df["monthly_price"] * 100).round().astype(int)
    raw_df["amount_paid"] = (raw_df["amount_paid"] * 100).round().astype(int)

    metrics_df, metrics_table = compute_metrics(df=raw_df, output_path=metrics_path)
    console.print(f"[green]Metrics written to {metrics_path}[/green]")

    val_result = run_validation(raw_df=raw_df, metrics_df=metrics_df)
    _print_validation(val_result)

    if not val_result.passed:
        warning_report = {
            "data_quality_warning": True,
            "executive_summary": "Data quality checks failed. Metrics are not trustworthy.",
            "monthly_revenue_trend": "N/A — data failed validation.",
            "churn_trend": "N/A — data failed validation.",
            "arpu_trend": "N/A — data failed validation.",
            "data_quality_checks": "\n".join(
                f"{'PASS' if c.passed else 'FAIL'}: {c.name} — {c.detail}"
                for c in val_result.invariants
            ),
            "business_interpretation": "Do not use this report for business decisions.",
            "cited_numbers": [],
        }
        md = render_report_md(warning_report, metrics_table)
        Path(report_path).parent.mkdir(parents=True, exist_ok=True)
        Path(report_path).write_text(md, encoding="utf-8")
        console.print(f"[yellow]Warning report written to {report_path}[/yellow]")
        raise typer.Exit(code=2)

    system_fingerprint = None
    if no_llm:
        report_json = build_no_llm_report(metrics_df, val_result)
        console.print("[blue]Report generated in deterministic mode (--no-llm)[/blue]")
    else:
        if not OPENAI_API_KEY:
            console.print("[red]OPENAI_API_KEY not set. Use --no-llm or set the key.[/red]")
            raise typer.Exit(code=1)

        from churn_agent.agent import run_agent, verify_report_numbers

        report_json, system_fingerprint = run_agent(
            metrics_table=metrics_table,
            invariants=val_result.invariants,
            anomalies=val_result.anomalies,
            model=model,
        )
        issues = verify_report_numbers(report_json, metrics_path, input_path)
        if issues:
            console.print("[red]Guardrail: number mismatches found:[/red]")
            for issue in issues:
                console.print(f"  - {issue}")
            raise typer.Exit(code=3)
        console.print("[green]Guardrail: all numbers in report match metrics[/green]")

    md = render_report_md(report_json, metrics_table)
    Path(report_path).parent.mkdir(parents=True, exist_ok=True)
    Path(report_path).write_text(md, encoding="utf-8")
    console.print(f"[green]Report written to {report_path}[/green]")

    meta = _read_gen_meta()
    write_manifest(
        seed=meta["seed"],
        n_users=meta["n_users"],
        n_months=meta["n_months"],
        inject_anomaly=meta["inject_anomaly"],
        anomaly_month=meta["anomaly_month"],
        model=model,
        system_fingerprint=system_fingerprint,
        passed=val_result.passed,
    )


@app.command()
def run(
    n_users: int = typer.Option(DEFAULT_N_USERS, help="Number of users"),
    n_months: int = typer.Option(DEFAULT_N_MONTHS, help="Number of months"),
    seed: int = typer.Option(DEFAULT_SEED, help="Random seed"),
    no_llm: bool = typer.Option(False, "--no-llm", help="Skip LLM"),
    anomaly: bool = typer.Option(True, "--anomaly/--no-anomaly", help="Inject payment anomaly"),
    anomaly_month: int = typer.Option(DEFAULT_ANOMALY_MONTH, help="Anomaly month"),
    model: str | None = typer.Option(OPENAI_MODEL, help="OpenAI model"),
    output: str = typer.Option(REPORT_MD, help="Output report path"),
) -> None:
    """Full end-to-end pipeline: generate, compute, validate, report."""

    raw_df = generate_data(
        n_users=n_users,
        n_months=n_months,
        seed=seed,
        inject_anomaly=anomaly,
        anomaly_month=anomaly_month,
        output_path=USERS_CSV,
    )
    console.print(
        f"[green]Generated {len(raw_df)} rows ({n_users} users x {n_months} months) "
        f"with seed={seed}, anomaly={anomaly}.[/green]"
    )

    metrics_df, metrics_table = compute_metrics(df=raw_df, output_path=METRICS_CSV)
    console.print(f"[green]Metrics written to {METRICS_CSV}[/green]")

    val_result = run_validation(raw_df=raw_df, metrics_df=metrics_df)
    _print_validation(val_result)

    if not val_result.passed:
        warning_report = {
            "data_quality_warning": True,
            "executive_summary": "Data quality checks failed. Metrics are not trustworthy.",
            "monthly_revenue_trend": "N/A — data failed validation.",
            "churn_trend": "N/A — data failed validation.",
            "arpu_trend": "N/A — data failed validation.",
            "data_quality_checks": "\n".join(
                f"{'PASS' if c.passed else 'FAIL'}: {c.name} — {c.detail}"
                for c in val_result.invariants
            ),
            "business_interpretation": "Do not use this report for business decisions.",
            "cited_numbers": [],
        }
        md = render_report_md(warning_report, metrics_table)
        Path(output).parent.mkdir(parents=True, exist_ok=True)
        Path(output).write_text(md, encoding="utf-8")
        console.print(f"[yellow]Warning report written to {output}[/yellow]")
        raise typer.Exit(code=2)

    system_fingerprint = None
    if no_llm:
        report_json = build_no_llm_report(metrics_df, val_result)
        console.print("[blue]Report generated in deterministic mode (--no-llm)[/blue]")
    else:
        if not OPENAI_API_KEY:
            console.print("[red]OPENAI_API_KEY not set. Use --no-llm or set the key.[/red]")
            raise typer.Exit(code=1)

        from churn_agent.agent import run_agent, verify_report_numbers

        report_json, system_fingerprint = run_agent(
            metrics_table=metrics_table,
            invariants=val_result.invariants,
            anomalies=val_result.anomalies,
            model=model,
        )
        issues = verify_report_numbers(report_json, METRICS_CSV, USERS_CSV)
        if issues:
            console.print("[red]Guardrail: number mismatches found:[/red]")
            for issue in issues:
                console.print(f"  - {issue}")
            raise typer.Exit(code=3)
        console.print("[green]Guardrail: all numbers in report match metrics[/green]")

    md = render_report_md(report_json, metrics_table)
    Path(output).parent.mkdir(parents=True, exist_ok=True)
    Path(output).write_text(md, encoding="utf-8")
    console.print(f"[green]Report written to {output}[/green]")

    write_manifest(
        seed=seed,
        n_users=n_users,
        n_months=n_months,
        inject_anomaly=anomaly,
        anomaly_month=anomaly_month,
        model=model,
        system_fingerprint=system_fingerprint,
        passed=val_result.passed,
    )


def main() -> None:
    app()


if __name__ == "__main__":
    main()
