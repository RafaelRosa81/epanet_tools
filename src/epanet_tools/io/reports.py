"""Report exporters for validation workflows."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from epanet_tools.topology.validation import PipeValidationReport, issues_to_records


def write_validation_report(
    report: PipeValidationReport,
    outdir: str | Path,
    name: str,
) -> dict[str, Path]:
    """Write validation report artifacts as JSON and CSV.

    Parameters
    ----------
    report:
        Validation report to serialize.
    outdir:
        Output directory root.
    name:
        Run/model name used as filename prefix.
    """
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
