"""Export normalized EPANET results and derived tables."""

from pathlib import Path
from typing import Mapping

import pandas as pd


def export_results_to_csv(results: dict, folder: str | Path) -> dict[str, Path]:
    """Export node and link time series to a folder of CSV files."""
    target = Path(folder)
    target.mkdir(parents=True, exist_ok=True)
    files = {"nodes": target / "nodes_results.csv", "links": target / "links_results.csv"}
    results["nodes"].to_csv(files["nodes"], index=False)
    results["links"].to_csv(files["links"], index=False)
    return files


def export_results_to_excel(
    results: dict,
    path: str | Path,
    diagnostics: Mapping[str, pd.DataFrame] | None = None,
) -> Path:
    """Export raw result tables, metadata and optional diagnostics to Excel."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(target, engine="openpyxl") as writer:
        results["nodes"].to_excel(writer, sheet_name="nodes", index=False)
        results["links"].to_excel(writer, sheet_name="links", index=False)
        pd.DataFrame([results.get("metadata", {})]).to_excel(writer, sheet_name="metadata", index=False)
        for name, table in (diagnostics or {}).items():
            table.to_excel(writer, sheet_name=name[:31], index=False)
    return target


def export_summary_to_excel(
    link_summary: pd.DataFrame,
    node_summary: pd.DataFrame,
    path: str | Path,
) -> Path:
    """Export link and node summary statistics to Excel."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(target, engine="openpyxl") as writer:
        link_summary.to_excel(writer, sheet_name="link_summary", index=False)
        node_summary.to_excel(writer, sheet_name="node_summary", index=False)
    return target
