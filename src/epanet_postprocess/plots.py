"""Time-series plots for normalized EPANET results."""

from pathlib import Path
from typing import Sequence

import matplotlib.pyplot as plt
import pandas as pd


def _simulation_time_axis(series: pd.Series) -> tuple[pd.Series, str]:
    """Return x-axis values and label for a simulation time column.

    EPANET reports are parsed as pandas Timedelta values. Matplotlib can plot
    timedeltas directly, but it displays them as internal nanosecond values.
    For hydraulic reports it is clearer to show elapsed simulation time in
    hours.
    """
    if pd.api.types.is_timedelta64_dtype(series):
        return series.dt.total_seconds() / 3600.0, "Simulation time [h]"

    converted = pd.to_timedelta(series, errors="coerce")
    if converted.notna().all():
        return converted.dt.total_seconds() / 3600.0, "Simulation time [h]"

    return series, "Simulation time"


def _plot_timeseries(
    df: pd.DataFrame,
    id_column: str,
    variable: str,
    elements: Sequence[str] | None,
    output: str | Path | None,
    title: str,
):
    if variable not in df.columns:
        raise ValueError(f"Result table does not contain '{variable}'.")

    data = df.copy()
    if elements is not None:
        requested = list(elements)
        data = data[data[id_column].isin(requested)]
        missing = sorted(set(requested).difference(data[id_column].unique()))
        if missing:
            raise KeyError(f"Selected values not found: {', '.join(missing)}")
    if data.empty:
        raise ValueError("There are no data to plot.")

    data = data.sort_values([id_column, "time"])
    data["_plot_time"], x_label = _simulation_time_axis(data["time"])

    fig, ax = plt.subplots(figsize=(12, 5))
    for element_id, group in data.groupby(id_column, sort=True):
        group = group.sort_values("_plot_time")
        ax.plot(group["_plot_time"], group[variable], label=str(element_id))

    ax.set_title(title)
    ax.set_xlabel(x_label)
    ax.set_ylabel(variable.replace("_", " ").title())
    ax.set_xlim(data["_plot_time"].min(), data["_plot_time"].max())
    ax.grid(True, alpha=0.35)
    ax.legend(title=id_column, loc="best")
    fig.tight_layout()

    if output is not None:
        output_path = Path(output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(output_path, dpi=150, bbox_inches="tight")
    return fig, ax


def plot_multiple_links(results: dict, variable="flow", links=None, output=None):
    """Plot a reported variable for selected links."""
    return _plot_timeseries(
        results["links"], "link_id", variable, links, output, f"EPANET link {variable}"
    )


def plot_multiple_nodes(results: dict, variable="pressure", nodes=None, output=None):
    """Plot a reported variable for selected nodes."""
    return _plot_timeseries(
        results["nodes"], "node_id", variable, nodes, output, f"EPANET node {variable}"
    )


def plot_link_flows(results: dict, links=None, output=None):
    """Plot flow time series for selected links."""
    return plot_multiple_links(results, "flow", links, output)


def plot_link_velocities(results: dict, links=None, output=None):
    """Plot velocity time series for selected links."""
    return plot_multiple_links(results, "velocity", links, output)


def plot_node_pressures(results: dict, nodes=None, output=None):
    """Plot pressure time series for selected nodes."""
    return plot_multiple_nodes(results, "pressure", nodes, output)


def plot_node_demands(results: dict, nodes=None, output=None):
    """Plot demand time series for selected nodes."""
    return plot_multiple_nodes(results, "demand", nodes, output)
