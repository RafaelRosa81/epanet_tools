"""Workflow configuration loading utilities."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from epanet_tools.exceptions import ConfigurationError


def load_yaml_config(path: str | Path) -> dict[str, Any]:
    """Load a YAML configuration file as a dictionary."""
    config_path = Path(path)
    if not config_path.exists():
        msg = f"Configuration file not found: {config_path}"
        raise FileNotFoundError(msg)

    with config_path.open("r", encoding="utf-8") as file:
        data = yaml.safe_load(file)

    if not isinstance(data, dict):
        msg = f"Configuration file must contain a YAML mapping: {config_path}"
        raise ConfigurationError(msg)
    return data


def require_mapping(data: dict[str, Any], key: str) -> dict[str, Any]:
    """Return a required nested mapping from a configuration dictionary."""
    value = data.get(key)
    if not isinstance(value, dict):
        msg = f"Missing or invalid mapping in configuration: {key}"
        raise ConfigurationError(msg)
    return value
