"""Readers that normalize EPANET report and tabular result files.

The RPT reader supports the standard EPANET 2.x ``Node Results at ... Hrs``
and ``Link Results at ... Hrs`` blocks, including page continuations.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pandas as pd

_RESULT_HEADER = re.compile(
    r"^\s*(Node|Link) Results at\s+(.+?)\s+Hrs:\s*(?:\(continued\))?\s*$",
    flags=re.IGNORECASE,
)
_NUMBER = re.compile(r"^[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[Ee][-+]?\d+)?$")

NODE_COLUMNS = ["time", "node_id", "demand", "head", "pressure", "quality"]
LINK_COLUMNS = ["time", "link_id", "flow", "velocity", "headloss", "status"]


def _parse_report_time(value: str) -> pd.Timedelta | str:
    """Return a Timedelta when an EPANET report time can be interpreted."""
    value = value.strip()
    try:
        return pd.to_timedelta(value)
    except ValueError:
        try:
            return pd.to_timedelta(pd.to_datetime(value).strftime("%H:%M:%S"))
        except (TypeError, ValueError):
            return value


def _is_number(value: str) -> bool:
    return bool(_NUMBER.fullmatch(value))


def _normalize_time_column(df: pd.DataFrame) -> pd.DataFrame:
    """Convert a time column to timedeltas where all values are parseable."""
    if "time" not in df.columns or df.empty:
        return df

    converted = pd.to_timedelta(df["time"], errors="coerce")
    if converted.notna().all():
        df = df.copy()
        df["time"] = converted
    return df


def _validate_columns(df: pd.DataFrame, required: set[str], label: str) -> pd.DataFrame:
    missing = required.difference(df.columns)
    if missing:
        missing_text = ", ".join(sorted(missing))
        raise ValueError(f"{label} file is missing required columns: {missing_text}.")
    return _normalize_time_column(df)


def read_node_results_csv(path: str | Path, **kwargs: Any) -> pd.DataFrame:
    """Read normalized node results from CSV.

    Required columns are ``time`` and ``node_id``. Other expected columns are
    ``demand``, ``head``, ``pressure`` and ``quality``.
    """
    return _validate_columns(
        pd.read_csv(path, **kwargs), {"time", "node_id"}, "Node results CSV"
    )


def read_link_results_csv(path: str | Path, **kwargs: Any) -> pd.DataFrame:
    """Read normalized link results from CSV.

    Required columns are ``time`` and ``link_id``. Other expected columns are
    ``flow``, ``velocity``, ``headloss`` and ``status``.
    """
    return _validate_columns(
        pd.read_csv(path, **kwargs), {"time", "link_id"}, "Link results CSV"
    )


def read_rpt(path: str | Path, encoding: str = "utf-8") -> dict[str, Any]:
    """Read a standard EPANET 2.x ``.rpt`` file into normalized DataFrames.

    The parser recognizes the normal report blocks headed by ``Node Results at
    <time> Hrs:`` and ``Link Results at <time> Hrs:``, including blocks marked
    ``(continued)`` on later pages. It ignores static input tables and other
    report sections. Values in the returned tables preserve the units reported
    by EPANET; inspect ``results['metadata']['units']`` before interpreting
    magnitudes.

    Parameters
    ----------
    path:
        EPANET report file.
    encoding:
        Preferred text encoding. Invalid bytes are replaced so reports written
        by older installations remain readable.
    """
    report_path = Path(path)
    if not report_path.is_file():
        raise FileNotFoundError(f"EPANET report not found: {report_path}")

    text = report_path.read_text(encoding=encoding, errors="replace")
    node_rows: list[dict[str, Any]] = []
    link_rows: list[dict[str, Any]] = []
    current_kind: str | None = None
    current_time: pd.Timedelta | str | None = None

    for raw_line in text.splitlines():
        header = _RESULT_HEADER.match(raw_line)
        if header:
            current_kind = header.group(1).lower()
            current_time = _parse_report_time(header.group(2))
            continue

        if current_kind is None:
            continue

        stripped = raw_line.strip()
        if not stripped or stripped.startswith(("Page ", "---", "Node ", "Link ", "ID ")):
            continue

        values = stripped.split()
        if current_kind == "node":
            if len(values) < 4 or not all(_is_number(value) for value in values[1:4]):
                continue
            quality = float(values[4]) if len(values) > 4 and _is_number(values[4]) else float("nan")
            node_rows.append(
                {
                    "time": current_time,
                    "node_id": values[0],
                    "demand": float(values[1]),
                    "head": float(values[2]),
                    "pressure": float(values[3]),
                    "quality": quality,
                }
            )
        else:
            if len(values) < 4 or not all(_is_number(value) for value in values[1:4]):
                continue
            link_rows.append(
                {
                    "time": current_time,
                    "link_id": values[0],
                    "flow": float(values[1]),
                    "velocity": float(values[2]),
                    "headloss": float(values[3]),
                    "status": " ".join(values[4:]) if len(values) > 4 else pd.NA,
                }
            )

    nodes = pd.DataFrame(node_rows, columns=NODE_COLUMNS)
    links = pd.DataFrame(link_rows, columns=LINK_COLUMNS)
    nodes = _normalize_time_column(nodes)
    links = _normalize_time_column(links)

    if nodes.empty and links.empty:
        raise ValueError(
            "No EPANET node or link result blocks were found. Ensure the report "
            "contains time-series Node Results and/or Link Results tables."
        )

    units = {
        "demand": "as reported by EPANET",
        "head": "as reported by EPANET",
        "pressure": "as reported by EPANET",
        "flow": "as reported by EPANET",
        "velocity": "as reported by EPANET",
        "headloss": "as reported by EPANET",
    }

    return {
        "nodes": nodes,
        "links": links,
        "metadata": {
            "source_file": str(report_path),
            "format": "EPANET RPT",
            "parser": "epanet_postprocess.read_rpt",
            "node_records": len(nodes),
            "link_records": len(links),
            "node_time_steps": int(nodes["time"].nunique()) if not nodes.empty else 0,
            "link_time_steps": int(links["time"].nunique()) if not links.empty else 0,
            "units": units,
        },
    }
