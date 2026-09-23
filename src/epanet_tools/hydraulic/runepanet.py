"""Small wrapper around the EPANET 2.2 runepanet.exe command-line solver."""
from __future__ import annotations

import re
import subprocess
from pathlib import Path


def run_epanet(executable: str | Path, inp: str | Path, rpt: str | Path, out: str | Path) -> None:
    cmd = [str(executable), str(inp), str(rpt), str(out)]
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise RuntimeError(
            f"EPANET failed with exit code {result.returncode}: "
            f"{result.stdout}\n{result.stderr}"
        )
    report = Path(rpt).read_text(encoding="utf-8", errors="replace")
    fatal = ["Error 110:", "cannot solve network hydraulic equations"]
    if any(token.lower() in report.lower() for token in fatal):
        raise RuntimeError("EPANET hydraulic solution failed; inspect " + str(rpt))


def parse_node_pressures(rpt: str | Path, node_ids: list[str]) -> dict[str, float]:
    """Parse requested node pressures from a steady-state EPANET report.

    The report must contain the standard node results table. The final numeric
    column is Pressure for hydraulic reports using the normal EPANET layout.
    """
    wanted = set(node_ids)
    found: dict[str, float] = {}
    text = Path(rpt).read_text(encoding="utf-8", errors="replace")
    for line in text.splitlines():
        cols = line.split()
        if not cols or cols[0] not in wanted or len(cols) < 4:
            continue
        try:
            found[cols[0]] = float(cols[-1])
        except ValueError:
            continue
    missing = wanted - set(found)
    if missing:
        raise ValueError(
            "Node pressure results missing from report for: " + ", ".join(sorted(missing))
        )
    return found


def report_has_hydraulic_warnings(rpt: str | Path) -> bool:
    text = Path(rpt).read_text(encoding="utf-8", errors="replace").lower()
    tokens = (
        "system unbalanced",
        "negative pressures",
        "system disconnected",
        "ill-conditioned",
        "cannot solve network hydraulic equations",
    )
    return any(token in text for token in tokens)
