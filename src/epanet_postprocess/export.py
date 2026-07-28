"""Export normalized EPANET results and derived tables."""

from pathlib import Path
from typing import Mapping

import pandas as pd
from openpyxl import Workbook


def export_results_to_csv(results: dict, folder: str | Path) -> dict[str, Path]:
    """Export node and link time series to a folder of CSV files."""
    target = Path(folder)
    target.mkdir(parents=True, exist_ok=True)
    files = {"nodes": target / "nodes_results.csv", "links": target / "links_results.csv"}
    results["nodes"].to_csv(files["nodes"], index=False)
    results["links"].to_csv(files["links"], index=False)
    return files


def _excel_value(value):
    """Convert pandas and nested Python values to Excel-compatible scalars."""
    if pd.isna(value) if not isinstance(value, (dict, list, tuple, set)) else False:
        return None
    if isinstance(value, pd.Timedelta):
        return str(value)
    if isinstance(value, pd.Timestamp):
        return value.to_pydatetime()
    if isinstance(value, (dict, list, tuple, set)):
        return str(value)
    if hasattr(value, "item"):
        try:
            return value.item()
        except (ValueError, TypeError):
            pass
    return value


def _append_dataframe_streaming(workbook: Workbook, name: str, table: pd.DataFrame) -> None:
    """Append a DataFrame to a write-only worksheet without retaining cells in RAM."""
    worksheet = workbook.create_sheet(title=name[:31])
    worksheet.append([str(column) for column in table.columns])
    for row in table.itertuples(index=False, name=None):
        worksheet.append([_excel_value(value) for value in row])


def _write_tables_streaming(path: Path, tables: Mapping[str, pd.DataFrame]) -> Path:
    """Write multiple DataFrames to an XLSX workbook using openpyxl streaming mode."""
    path.parent.mkdir(parents=True, exist_ok=True)
    workbook = Workbook(write_only=True)
    try:
        for name, table in tables.items():
            _append_dataframe_streaming(workbook, name, table)
        workbook.save(path)
    except Exception:
        if path.exists():
            path.unlink()
        raise
    return path


def export_results_to_excel(
    results: dict,
    path: str | Path,
    diagnostics: Mapping[str, pd.DataFrame] | None = None,
) -> Path:
    """Export raw results, metadata and diagnostics using memory-efficient streaming."""
    tables: dict[str, pd.DataFrame] = {
        "nodes": results["nodes"],
        "links": results["links"],
        "metadata": pd.DataFrame([results.get("metadata", {})]),
    }
    tables.update(diagnostics or {})
    return _write_tables_streaming(Path(path), tables)


def export_summary_to_excel(
    link_summary: pd.DataFrame,
    node_summary: pd.DataFrame,
    path: str | Path,
) -> Path:
    """Export link and node summary statistics using memory-efficient streaming."""
    return _write_tables_streaming(
        Path(path),
        {
            "link_summary": link_summary,
            "node_summary": node_summary,
        },
    )
