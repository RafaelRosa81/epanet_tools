"""Initial CLI placeholder for GIS network validation.

The real implementation will read GIS layers, validate topology and export QA
reports. For now, this module defines the public entrypoint and keeps the
workflow importable while the architecture is being built.
"""

from __future__ import annotations

import argparse
from pathlib import Path


def validate_network(config_path: str | Path) -> dict[str, str]:
    """Validate a pipe network from a configuration file.

    Parameters
    ----------
    config_path:
        Path to a YAML workflow configuration.

    Returns
    -------
    dict[str, str]
        Minimal status payload. This will later become a typed workflow result.
    """
    path = Path(config_path)
    if not path.exists():
        msg = f"Configuration file not found: {path}"
        raise FileNotFoundError(msg)
    return {"status": "not_implemented", "config": str(path)}


def main() -> None:
    """Command-line entrypoint for network validation."""
    parser = argparse.ArgumentParser(description="Validate a GIS pipe network for EPANET export.")
    parser.add_argument("--config", required=True, help="Path to the workflow YAML configuration.")
    args = parser.parse_args()
    result = validate_network(args.config)
    print(result)


if __name__ == "__main__":
    main()
