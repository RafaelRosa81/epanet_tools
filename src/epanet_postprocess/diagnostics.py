"""Hydraulic and sector-operation diagnostics for EPANET results."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

import pandas as pd


def _table(results: dict, name: str) -> pd.DataFrame:
    if name not in results:
        raise KeyError(f"Results do not contain '{name}'.")
    return results[name]


def check_negative_pressures(results: dict, threshold: float = 0.0) -> pd.DataFrame:
    """Return node records with pressure below ``threshold``."""
    nodes = _table(results, "nodes")
    return nodes.loc[nodes["pressure"] < threshold].copy()


def check_extreme_negative_pressures(results: dict, threshold: float = -10.0) -> pd.DataFrame:
    """Return potentially non-physical, strongly negative pressure records."""
    return check_negative_pressures(results, threshold=threshold)


def check_negative_flows(results: dict, threshold: float = 0.0) -> pd.DataFrame:
    """Return links whose signed flow is below ``threshold``.

    Negative flow normally indicates direction opposite to the link orientation;
    it is reported for review and is not labelled as a hydraulic error.
    """
    links = _table(results, "links")
    return links.loc[links["flow"] < threshold].copy()


def check_high_velocities(results: dict, max_velocity: float = 2.0) -> pd.DataFrame:
    """Return links exceeding the design velocity limit."""
    links = _table(results, "links")
    return links.loc[links["velocity"].abs() > max_velocity].copy()


def check_low_pressures(results: dict, min_pressure: float = 10.0) -> pd.DataFrame:
    """Return node records below the required service pressure."""
    nodes = _table(results, "nodes")
    return nodes.loc[nodes["pressure"] < min_pressure].copy()


def check_closed_links(results: dict, flow_tolerance: float = 1e-9) -> pd.DataFrame:
    """Return closed links and flag any non-negligible reported flow."""
    links = _table(results, "links")
    if "status" not in links.columns:
        return pd.DataFrame(columns=list(links.columns) + ["has_flow_while_closed"])

    closed = links[links["status"].astype("string").str.upper().str.contains("CLOSED", na=False)].copy()
    closed["has_flow_while_closed"] = closed["flow"].abs() > flow_tolerance
    return closed


def identify_active_sectors(
    results: dict,
    sector_map: Mapping[str, Sequence[str]],
    flow_threshold: float = 1e-6,
) -> pd.DataFrame:
    """Identify active sectors from selected representative link flows.

    Each sector should map to one or more *representative* links, normally the
    sector inlet or meter link. Mapping every internal pipe would sum the same
    sector flow repeatedly and should be avoided.
    """
    links = _table(results, "links")
    rows: list[dict] = []
    for time, step in links.groupby("time", sort=True):
        for sector, link_ids in sector_map.items():
            selected = step[step["link_id"].isin(link_ids)]
            simulated_flow = selected["flow"].abs().sum()
            rows.append(
                {
                    "time": time,
                    "sector": sector,
                    "reported_links": len(selected),
                    "simulated_flow": simulated_flow,
                    "is_active": simulated_flow > flow_threshold,
                }
            )
    return pd.DataFrame(rows)


def check_single_active_sector(active_sectors: pd.DataFrame) -> pd.DataFrame:
    """Return time steps where the number of active sectors is not exactly one."""
    if active_sectors.empty:
        return pd.DataFrame(columns=["time", "active_sector_count", "status"])

    count = (
        active_sectors.groupby("time")["is_active"].sum().rename("active_sector_count").reset_index()
    )
    result = count.loc[count["active_sector_count"] != 1].copy()
    result["status"] = result["active_sector_count"].map(
        lambda value: "no_active_sector" if value == 0 else "multiple_active_sectors"
    )
    return result


def check_sector_flow_balance(
    results: dict,
    sector_expected_flows: Mapping[str, float],
    sector_map: Mapping[str, Sequence[str]],
    flow_threshold: float = 1e-6,
) -> pd.DataFrame:
    """Compare expected sector flows against reported representative-link flow."""
    balance = identify_active_sectors(results, sector_map, flow_threshold=flow_threshold)
    balance["expected_flow"] = balance["sector"].map(sector_expected_flows)
    balance["flow_difference"] = balance["simulated_flow"] - balance["expected_flow"]
    balance["relative_difference"] = balance["flow_difference"] / balance["expected_flow"]
    return balance
