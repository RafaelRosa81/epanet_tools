"""Time-series plots for normalized EPANET results."""

from math import ceil
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


def _select_elements(
    df: pd.DataFrame,
    id_column: str,
    elements: Sequence[str] | None,
) -> pd.DataFrame:
    data = df.copy()
    if elements is None:
        return data

    requested = list(elements)
    data = data[data[id_column].isin(requested)]
    missing = sorted(set(requested).difference(data[id_column].unique()))
    if missing:
        raise KeyError(f"Selected values not found: {', '.join(missing)}")
    return data


def _prepare_plot_data(
    df: pd.DataFrame,
    id_column: str,
    variable: str,
    elements: Sequence[str] | None,
) -> tuple[pd.DataFrame, str]:
    if variable not in df.columns:
        raise ValueError(f"Result table does not contain '{variable}'.")

    data = _select_elements(df, id_column, elements)
    if data.empty:
        raise ValueError("There are no data to plot.")

    data = data.sort_values([id_column, "time"])
    data["_plot_time"], x_label = _simulation_time_axis(data["time"])
    return data, x_label


def _save_figure(fig, output: str | Path | None) -> None:
    if output is None:
        return
    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=150, bbox_inches="tight")


def _plot_timeseries(
    df: pd.DataFrame,
    id_column: str,
    variable: str,
    elements: Sequence[str] | None,
    output: str | Path | None,
    title: str,
    show_legend: bool = True,
):
    data, x_label = _prepare_plot_data(df, id_column, variable, elements)

    fig, ax = plt.subplots(figsize=(12, 5))
    for element_id, group in data.groupby(id_column, sort=True):
        group = group.sort_values("_plot_time")
        ax.plot(group["_plot_time"], group[variable], label=str(element_id), linewidth=1.8)

    ax.set_title(title)
    ax.set_xlabel(x_label)
    ax.set_ylabel(variable.replace("_", " ").title())
    ax.set_xlim(data["_plot_time"].min(), data["_plot_time"].max())
    ax.grid(True, alpha=0.35)

    if show_legend:
        n_series = data[id_column].nunique()
        if n_series > 10:
            ax.legend(title=id_column, loc="center left", bbox_to_anchor=(1.01, 0.5))
        else:
            ax.legend(title=id_column, loc="best")

    fig.tight_layout()
    _save_figure(fig, output)
    return fig, ax


def _plot_timeseries_grid(
    df: pd.DataFrame,
    id_column: str,
    variable: str,
    elements: Sequence[str] | None,
    output: str | Path | None,
    title: str,
    ncols: int = 3,
):
    data, x_label = _prepare_plot_data(df, id_column, variable, elements)
    element_ids = list(data[id_column].drop_duplicates())
    nrows = ceil(len(element_ids) / ncols)

    fig, axes = plt.subplots(
        nrows=nrows,
        ncols=ncols,
        figsize=(5 * ncols, 2.4 * nrows),
        sharex=True,
        sharey=True,
    )
    axes_list = list(pd.Series(axes.ravel() if hasattr(axes, "ravel") else [axes]))

    for ax, element_id in zip(axes_list, element_ids, strict=False):
        group = data[data[id_column] == element_id].sort_values("_plot_time")
        ax.plot(group["_plot_time"], group[variable], linewidth=1.8)
        ax.set_title(str(element_id), fontsize=10)
        ax.grid(True, alpha=0.35)
        ax.axhline(0, linewidth=0.8, alpha=0.5)

    for ax in axes_list[len(element_ids) :]:
        ax.set_visible(False)

    fig.suptitle(title)
    fig.supxlabel(x_label)
    fig.supylabel(variable.replace("_", " ").title())
    fig.tight_layout()
    _save_figure(fig, output)
    return fig, axes


def plot_multiple_links(results: dict, variable="flow", links=None, output=None, show_legend=True):
    """Plot a reported variable for selected links in one shared axis."""
    return _plot_timeseries(
        results["links"],
        "link_id",
        variable,
        links,
        output,
        f"EPANET link {variable}",
        show_legend=show_legend,
    )


def plot_multiple_nodes(results: dict, variable="pressure", nodes=None, output=None, show_legend=True):
    """Plot a reported variable for selected nodes in one shared axis."""
    return _plot_timeseries(
        results["nodes"],
        "node_id",
        variable,
        nodes,
        output,
        f"EPANET node {variable}",
        show_legend=show_legend,
    )


def plot_multiple_links_grid(results: dict, variable="flow", links=None, output=None, ncols=3):
    """Plot selected links as small multiples, one subplot per link."""
    return _plot_timeseries_grid(
        results["links"], "link_id", variable, links, output, f"EPANET link {variable}", ncols=ncols
    )


def plot_multiple_nodes_grid(results: dict, variable="pressure", nodes=None, output=None, ncols=3):
    """Plot selected nodes as small multiples, one subplot per node."""
    return _plot_timeseries_grid(
        results["nodes"], "node_id", variable, nodes, output, f"EPANET node {variable}", ncols=ncols
    )


def plot_link_flows(results: dict, links=None, output=None, show_legend=True):
    """Plot flow time series for selected links in one shared axis."""
    return plot_multiple_links(results, "flow", links, output, show_legend=show_legend)


def plot_link_flows_grid(results: dict, links=None, output=None, ncols=3):
    """Plot flow time series for selected links as small multiples."""
    return plot_multiple_links_grid(results, "flow", links, output, ncols=ncols)


def plot_link_velocities(results: dict, links=None, output=None, show_legend=True):
    """Plot velocity time series for selected links."""
    return plot_multiple_links(results, "velocity", links, output, show_legend=show_legend)


def plot_node_pressures(results: dict, nodes=None, output=None, show_legend=True):
    """Plot pressure time series for selected nodes."""
    return plot_multiple_nodes(results, "pressure", nodes, output, show_legend=show_legend)


def plot_node_pressures_grid(results: dict, nodes=None, output=None, ncols=3):
    """Plot pressure time series for selected nodes as small multiples."""
    return plot_multiple_nodes_grid(results, "pressure", nodes, output, ncols=ncols)


def plot_node_demands(results: dict, nodes=None, output=None, show_legend=True):
    """Plot demand time series for selected nodes."""
    return plot_multiple_nodes(results, "demand", nodes, output, show_legend=show_legend)
