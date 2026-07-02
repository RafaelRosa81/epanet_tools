"""Demand assignment utilities for master nodes."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import geopandas as gpd
import pandas as pd


@dataclass(frozen=True)
class DemandAssignmentReport:
    """Summary of demand assignment to nodes."""

    node_count: int
    existing_demand_count: int
    default_demand_count: int
    rule_demand_count: int
    missing_demand_count: int


def apply_node_demands(
    nodes: gpd.GeoDataFrame,
    demands_config: dict[str, Any] | None,
) -> tuple[gpd.GeoDataFrame, DemandAssignmentReport]:
    """Apply base demands and patterns to nodes from configuration."""
    config = demands_config if isinstance(demands_config, dict) else {}
    result = nodes.copy()
    if "base_demand" not in result.columns:
        result["base_demand"] = pd.NA
    if "demand_pattern" not in result.columns:
        result["demand_pattern"] = ""

    existing_count = int(result["base_demand"].map(_valid_demand).sum())
    default_count = 0
    rule_count = 0

    default = config.get("default")
    if isinstance(default, dict):
        missing = ~result["base_demand"].map(_valid_demand)
        if "base_demand" in default:
            result.loc[missing, "base_demand"] = default["base_demand"]
            default_count = int(missing.sum())
        if "pattern" in default:
            pattern_missing = result["demand_pattern"].isna() | (result["demand_pattern"].astype(str) == "")
            result.loc[pattern_missing, "demand_pattern"] = default["pattern"]

    rules = config.get("rules")
    if isinstance(rules, list):
        for rule in rules:
            if not isinstance(rule, dict):
                continue
            match = rule.get("match")
            values = rule.get("values")
            if not isinstance(match, dict) or not isinstance(values, dict):
                continue
            mask = _match_mask(result, match)
            if "base_demand" in values:
                result.loc[mask, "base_demand"] = values["base_demand"]
                rule_count += int(mask.sum())
            if "pattern" in values:
                result.loc[mask, "demand_pattern"] = values["pattern"]

    missing_count = int((~result["base_demand"].map(_valid_demand)).sum())
    report = DemandAssignmentReport(
        node_count=len(result),
        existing_demand_count=existing_count,
        default_demand_count=default_count,
        rule_demand_count=rule_count,
        missing_demand_count=missing_count,
    )
    return result, report


def _match_mask(nodes: gpd.GeoDataFrame, match: dict[str, Any]) -> pd.Series:
    mask = pd.Series(True, index=nodes.index)
    for field, expected in match.items():
        if field not in nodes.columns:
            mask &= False
        else:
            mask &= nodes[field].astype(str) == str(expected)
    return mask


def _valid_demand(value: Any) -> bool:
    try:
        return float(value) >= 0
    except (TypeError, ValueError):
        return False
