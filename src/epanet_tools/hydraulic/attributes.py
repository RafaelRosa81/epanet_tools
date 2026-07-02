"""Hydraulic attribute assignment for cleaned pipe layers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import geopandas as gpd
import pandas as pd


HYDRAULIC_PIPE_FIELDS = (
    "diameter_mm",
    "roughness",
    "minor_loss",
    "status",
    "material",
)
_VALID_STATUSES = {"OPEN", "CLOSED", "CV"}


@dataclass(frozen=True)
class HydraulicAttributeReport:
    """Summary of hydraulic attribute assignment."""

    pipe_count: int
    existing_value_count: int
    category_value_count: int
    default_value_count: int
    missing_required_count: int
    invalid_value_count: int
    undefined_category_count: int


def apply_hydraulic_attributes(
    pipes: gpd.GeoDataFrame,
    hydraulics_config: dict[str, Any] | None,
) -> tuple[gpd.GeoDataFrame, HydraulicAttributeReport]:
    """Apply hydraulic attributes using existing values, categories and defaults.

    Priority per field is:

    1. valid existing value in ``pipes``;
    2. category rule selected by ``hydraulics.category_field``;
    3. ``hydraulics.pipe_defaults``;
    4. leave missing and report.
    """
    config = hydraulics_config if isinstance(hydraulics_config, dict) else {}
    defaults = _mapping(config.get("pipe_defaults"))
    categories = _mapping(config.get("categories"))
    category_field = config.get("category_field")

    result = pipes.copy()
    for field in HYDRAULIC_PIPE_FIELDS:
        if field not in result.columns:
            result[field] = pd.NA

    existing_value_count = 0
    category_value_count = 0
    default_value_count = 0
    missing_required_count = 0
    invalid_value_count = 0
    undefined_category_count = 0

    for index, row in result.iterrows():
        category_values: dict[str, Any] = {}
        category_defined = False
        if category_field is not None and str(category_field) in result.columns:
            raw_category = row.get(str(category_field))
            if _has_value(raw_category):
                category_key = str(raw_category)
                category_values = _mapping(categories.get(category_key))
                if category_values:
                    category_defined = True
                else:
                    undefined_category_count += 1

        for field in HYDRAULIC_PIPE_FIELDS:
            current_value = row.get(field)
            if _is_valid_field_value(field, current_value):
                existing_value_count += 1
                continue

            new_value_source = None
            if category_defined and field in category_values:
                candidate = category_values[field]
                if _is_valid_field_value(field, candidate):
                    result.at[index, field] = _normalize_field_value(field, candidate)
                    new_value_source = "category"
                    category_value_count += 1
                else:
                    invalid_value_count += 1

            if new_value_source is None and field in defaults:
                candidate = defaults[field]
                if _is_valid_field_value(field, candidate):
                    result.at[index, field] = _normalize_field_value(field, candidate)
                    new_value_source = "default"
                    default_value_count += 1
                else:
                    invalid_value_count += 1

            if new_value_source is None:
                value_after = result.at[index, field]
                if not _is_valid_field_value(field, value_after):
                    missing_required_count += 1

    report = HydraulicAttributeReport(
        pipe_count=len(result),
        existing_value_count=existing_value_count,
        category_value_count=category_value_count,
        default_value_count=default_value_count,
        missing_required_count=missing_required_count,
        invalid_value_count=invalid_value_count,
        undefined_category_count=undefined_category_count,
    )
    return result, report


def _mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _has_value(value: Any) -> bool:
    if value is None or value is pd.NA:
        return False
    try:
        if pd.isna(value):
            return False
    except TypeError:
        pass
    return str(value) != ""


def _is_valid_field_value(field: str, value: Any) -> bool:
    if not _has_value(value):
        return False
    if field in {"diameter_mm", "roughness"}:
        return _positive_float(value)
    if field == "minor_loss":
        return _non_negative_float(value)
    if field == "status":
        return str(value).upper() in _VALID_STATUSES
    if field == "material":
        return str(value).strip() != ""
    return True


def _normalize_field_value(field: str, value: Any) -> Any:
    if field in {"diameter_mm", "roughness", "minor_loss"}:
        return float(value)
    if field == "status":
        return str(value).upper()
    if field == "material":
        return str(value)
    return value


def _positive_float(value: Any) -> bool:
    try:
        return float(value) > 0
    except (TypeError, ValueError):
        return False


def _non_negative_float(value: Any) -> bool:
    try:
        return float(value) >= 0
    except (TypeError, ValueError):
        return False
