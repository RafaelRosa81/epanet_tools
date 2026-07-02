"""Master node layer utilities for EPANET model building."""

from __future__ import annotations

from typing import Any

import geopandas as gpd
import pandas as pd


NODE_TYPE_JUNCTION = "JUNCTION"
NODE_TYPE_RESERVOIR = "RESERVOIR"
NODE_TYPE_TANK = "TANK"
SUPPORTED_NODE_TYPES = {NODE_TYPE_JUNCTION, NODE_TYPE_RESERVOIR, NODE_TYPE_TANK}


def build_nodes_from_junctions(
    junctions: gpd.GeoDataFrame,
    node_config: dict[str, Any] | None = None,
) -> gpd.GeoDataFrame:
    """Build a master nodes layer from generated junctions.

    The returned layer keeps junction-compatible fields and adds EPANET-oriented
    fields that allow later classification as JUNCTION, RESERVOIR or TANK.
    """
    config = node_config if isinstance(node_config, dict) else {}
    nodes = junctions.copy()

    if "node_id" not in nodes.columns:
        msg = "junctions must contain node_id before building nodes."
        raise ValueError(msg)

    _ensure_column(nodes, "node_type", NODE_TYPE_JUNCTION)
    _ensure_column(nodes, "base_demand", 0.0)
    _ensure_column(nodes, "demand_pattern", "")
    _ensure_column(nodes, "head", pd.NA)
    _ensure_column(nodes, "init_level", pd.NA)
    _ensure_column(nodes, "min_level", pd.NA)
    _ensure_column(nodes, "max_level", pd.NA)
    _ensure_column(nodes, "tank_diameter", pd.NA)
    _ensure_column(nodes, "source", "generated")
    _ensure_column(nodes, "remarks", "")

    nodes = _apply_node_defaults(nodes, config.get("defaults"))
    nodes = _apply_node_rules(nodes, config.get("rules"))
    nodes["node_type"] = nodes["node_type"].map(_normalize_node_type)
    return nodes


def junctions_from_nodes(nodes: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Return EPANET junction rows derived from the master nodes layer."""
    if "node_type" not in nodes.columns:
        return nodes.copy()
    return nodes.loc[nodes["node_type"].map(_normalize_node_type) == NODE_TYPE_JUNCTION].copy()


def reservoirs_from_nodes(nodes: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Return EPANET reservoir rows derived from the master nodes layer."""
    return nodes.loc[nodes["node_type"].map(_normalize_node_type) == NODE_TYPE_RESERVOIR].copy()


def tanks_from_nodes(nodes: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Return EPANET tank rows derived from the master nodes layer."""
    return nodes.loc[nodes["node_type"].map(_normalize_node_type) == NODE_TYPE_TANK].copy()


def _ensure_column(nodes: gpd.GeoDataFrame, column: str, default: Any) -> None:
    if column not in nodes.columns:
        nodes[column] = default


def _apply_node_defaults(nodes: gpd.GeoDataFrame, defaults: Any) -> gpd.GeoDataFrame:
    if not isinstance(defaults, dict):
        return nodes
    for field, value in defaults.items():
        if field not in nodes.columns:
            nodes[field] = pd.NA
        missing = nodes[field].isna() | (nodes[field].astype(str) == "")
        nodes.loc[missing, field] = value
    return nodes


def _apply_node_rules(nodes: gpd.GeoDataFrame, rules: Any) -> gpd.GeoDataFrame:
    if not isinstance(rules, list):
        return nodes
    for rule in rules:
        if not isinstance(rule, dict):
            continue
        match = rule.get("match")
        values = rule.get("values")
        if not isinstance(match, dict) or not isinstance(values, dict):
            continue
        mask = pd.Series(True, index=nodes.index)
        for field, expected in match.items():
            if field not in nodes.columns:
                mask &= False
            else:
                mask &= nodes[field].astype(str) == str(expected)
        for field, value in values.items():
            if field not in nodes.columns:
                nodes[field] = pd.NA
            nodes.loc[mask, field] = value
    return nodes


def _normalize_node_type(value: Any) -> str:
    node_type = str(value).strip().upper()
    return node_type if node_type in SUPPORTED_NODE_TYPES else NODE_TYPE_JUNCTION
