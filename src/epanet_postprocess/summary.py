"""Summary statistics for EPANET result tables."""

import pandas as pd


def summarize_variable(df: pd.DataFrame, id_col: str, variable: str) -> pd.DataFrame:
    """Calculate time-series statistics for one variable by element."""
    if variable not in df.columns:
        return pd.DataFrame(columns=[id_col, "variable", "minimum", "maximum", "mean", "std", "first", "last"])

    ordered = df.sort_values([id_col, "time"])
    summary = (
        ordered.groupby(id_col, dropna=False)[variable]
        .agg(minimum="min", maximum="max", mean="mean", std="std", first="first", last="last")
        .reset_index()
    )
    summary.insert(1, "variable", variable)
    return summary


def _summarize(results: dict, table: str, id_col: str, variables: list[str]) -> pd.DataFrame:
    frames = [summarize_variable(results[table], id_col, variable) for variable in variables]
    frames = [frame for frame in frames if not frame.empty]
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def summarize_links(results: dict) -> pd.DataFrame:
    """Summarize flow, velocity and headloss by link."""
    return _summarize(results, "links", "link_id", ["flow", "velocity", "headloss"])


def summarize_nodes(results: dict) -> pd.DataFrame:
    """Summarize demand, head and pressure by node."""
    return _summarize(results, "nodes", "node_id", ["demand", "head", "pressure"])
