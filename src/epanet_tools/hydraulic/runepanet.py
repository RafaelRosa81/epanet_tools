"""Small wrapper around the EPANET 2.2 runepanet.exe command-line solver."""
from __future__ import annotations

import math
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
        raise ValueError("Node pressure results missing from report for: " + ", ".join(sorted(missing)))
    return found


def parse_inp_pipes(inp: str | Path) -> dict[str, dict[str, object]]:
    """Read pipe endpoints and diameters from the INP [PIPES] section."""
    pipes: dict[str, dict[str, object]] = {}
    in_pipes = False
    for line in Path(inp).read_text(encoding="utf-8-sig", errors="replace").splitlines():
        stripped = line.strip()
        if stripped.upper() == "[PIPES]":
            in_pipes = True
            continue
        if in_pipes and stripped.startswith("["):
            break
        if not in_pipes or not stripped or stripped.startswith(";"):
            continue
        cols = line.split(";", 1)[0].split()
        if len(cols) < 6:
            continue
        try:
            diameter_mm = float(cols[4])
        except ValueError:
            continue
        pipes[cols[0]] = {"from_node": cols[1], "to_node": cols[2], "diameter_mm": diameter_mm}
    return pipes


def parse_link_flows(rpt: str | Path, link_ids: list[str]) -> dict[str, float]:
    """Parse Flow from the standard EPANET link-results table (model units: L/min here)."""
    wanted = set(link_ids)
    found: dict[str, float] = {}
    text = Path(rpt).read_text(encoding="utf-8", errors="replace")
    for line in text.splitlines():
        cols = line.split()
        if not cols or cols[0] not in wanted or len(cols) < 4:
            continue
        try:
            # Standard link table: Link, Flow, Velocity, Headloss, ...
            found[cols[0]] = float(cols[1])
        except ValueError:
            continue
    return found


def pipe_hydraulic_results(inp: str | Path, rpt: str | Path, *, min_abs_flow_l_min: float = 0.01) -> list[dict[str, object]]:
    """Return active-pipe flow and velocity results for an LPM/mm EPANET model."""
    pipes = parse_inp_pipes(inp)
    flows = parse_link_flows(rpt, list(pipes))
    rows: list[dict[str, object]] = []
    for pipe_id, meta in pipes.items():
        if pipe_id not in flows:
            continue
        flow_l_min = float(flows[pipe_id])
        if abs(flow_l_min) < min_abs_flow_l_min:
            continue
        diameter_mm = float(meta["diameter_mm"])
        q_m3_s = abs(flow_l_min) / 60000.0
        area_m2 = math.pi * (diameter_mm / 1000.0) ** 2 / 4.0
        velocity_m_s = q_m3_s / area_m2 if area_m2 > 0 else float("nan")
        rows.append({
            "pipe_id": pipe_id,
            "from_node": meta["from_node"],
            "to_node": meta["to_node"],
            "diameter_mm": diameter_mm,
            "flow_l_min": flow_l_min,
            "abs_flow_l_min": abs(flow_l_min),
            "velocity_m_s": velocity_m_s,
        })
    return rows


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
