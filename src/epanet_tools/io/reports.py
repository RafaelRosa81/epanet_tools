"""Report exporters for validation workflows."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

import pandas as pd

from epanet_tools.hydraulic.validation import BasicModelValidationReport
from epanet_tools.topology.validation import PipeValidationReport, issues_to_records


def write_validation_report(
    report: PipeValidationReport,
    outdir: str | Path,
    name: str,
) -> dict[str, Path]:
    """Write validation report artifacts as JSON and CSV."""
    report_dir = Path(outdir) / "report"
    report_dir.mkdir(parents=True, exist_ok=True)

    records = issues_to_records(report.issues)
    summary: dict[str, Any] = {
        "feature_count": report.feature_count,
        "has_errors": report.has_errors,
        "issue_counts": report.count_by_severity(),
        "issues": records,
    }

    json_path = report_dir / f"{name}_validation.json"
    csv_path = report_dir / f"{name}_validation.csv"

    json_text = json.dumps(summary, indent=2, ensure_ascii=False)
    json_path.write_text(json_text, encoding="utf-8")
    pd.DataFrame.from_records(records).to_csv(csv_path, index=False)

    return {"json": json_path, "csv": csv_path}


def write_basic_model_validation_report(
    report: BasicModelValidationReport,
    outdir: str | Path,
    name: str,
) -> Path:
    """Write the basic EPANET model validation summary as a one-row CSV."""
    report_dir = Path(outdir) / "report"
    report_dir.mkdir(parents=True, exist_ok=True)
    csv_path = report_dir / f"{name}_basic_model_validation.csv"
    pd.DataFrame([asdict(report)]).to_csv(csv_path, index=False)
    return csv_path
