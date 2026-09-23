"""Utilities for minimum required-head experiments with EPANET."""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Callable


@dataclass(frozen=True)
class HeadTrial:
    iteration: int
    trial_head_m: float
    min_pressure_bar: float
    critical_node: str
    margin_bar: float
    passes: bool


def _sections(text: str) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    current = ""
    for line in text.splitlines():
        m = re.match(r"^\s*\[([^]]+)\]\s*$", line)
        if m:
            current = m.group(1).upper()
            out.setdefault(current, [])
        elif current:
            out[current].append(line)
    return out


def _replace_section(text: str, name: str, lines: list[str]) -> str:
    pat = re.compile(rf"(?ms)^\s*\[{re.escape(name)}\]\s*$.*?(?=^\s*\[[^]]+\]\s*$|\Z)")
    block = f"[{name}]\n" + "\n".join(lines).rstrip() + "\n\n"
    if not pat.search(text):
        raise ValueError(f"INP section [{name}] not found")
    return pat.sub(block, text, count=1)


def prepare_constant_head_scenario(
    master_inp: str | Path,
    output_inp: str | Path,
    *,
    active_demands_l_min: dict[str, float],
    trial_head_m: float,
    reservoir_id: str = "Tanque_1",
    pump_id: str = "B_Impulsion",
    bypass_length_m: float = 0.01,
    bypass_diameter_mm: float = 1000.0,
    bypass_roughness: float = 150.0,
) -> Path:
    """Create a steady-state demand scenario.

    The physical pump is replaced by a negligible-loss pipe and the reservoir
    head is set to ``trial_head_m``. Thus trial head represents the head that
    the pump would have to add to a zero-head source (apart from the explicitly
    retained suction-pipe losses).
    """
    master_inp = Path(master_inp)
    text = master_inp.read_text(encoding="utf-8-sig", errors="replace")
    sec = _sections(text)

    # Zero all junction base demands, then assign the selected sprinklers.
    junctions: list[str] = []
    found = set()
    for line in sec.get("JUNCTIONS", []):
        raw, *comment = line.split(";", 1)
        cols = raw.split()
        if len(cols) >= 3 and not raw.lstrip().startswith(";"):
            node = cols[0]
            cols[2] = str(float(active_demands_l_min.get(node, 0.0)))
            if node in active_demands_l_min:
                found.add(node)
            raw = "\t".join(cols)
        junctions.append(raw + ((" ;" + comment[0]) if comment else ""))
    missing = set(active_demands_l_min) - found
    if missing:
        raise ValueError(f"Active nodes not found in [JUNCTIONS]: {sorted(missing)}")
    text = _replace_section(text, "JUNCTIONS", junctions)

    # Remove category demands so only the explicit base demands above remain.
    if "DEMANDS" in sec:
        text = _replace_section(text, "DEMANDS", ["; demand categories disabled for required-head experiment"])

    reservoirs: list[str] = []
    reservoir_found = False
    for line in sec.get("RESERVOIRS", []):
        raw, *comment = line.split(";", 1)
        cols = raw.split()
        if cols and cols[0] == reservoir_id:
            if len(cols) < 2:
                raise ValueError(f"Malformed reservoir row for {reservoir_id}")
            cols[1] = str(float(trial_head_m))
            if len(cols) > 2:
                cols = cols[:2]  # remove any head pattern
            raw = "\t".join(cols)
            reservoir_found = True
        reservoirs.append(raw + ((" ;" + comment[0]) if comment else ""))
    if not reservoir_found:
        raise ValueError(f"Reservoir {reservoir_id!r} not found")
    text = _replace_section(text, "RESERVOIRS", reservoirs)

    pumps: list[str] = []
    endpoints = None
    for line in sec.get("PUMPS", []):
        cols = line.split(";", 1)[0].split()
        if cols and cols[0] == pump_id:
            if len(cols) < 3:
                raise ValueError(f"Malformed pump row for {pump_id}")
            endpoints = (cols[1], cols[2])
        else:
            pumps.append(line)
    if endpoints is None:
        raise ValueError(f"Pump {pump_id!r} not found")
    text = _replace_section(text, "PUMPS", pumps or ["; physical pump replaced by trial-head bypass"])

    pipes = list(sec.get("PIPES", []))
    pipes.append(
        f"{pump_id}\t{endpoints[0]}\t{endpoints[1]}\t{bypass_length_m}\t"
        f"{bypass_diameter_mm}\t{bypass_roughness}\t0\tOPEN ; trial-head bypass"
    )
    text = _replace_section(text, "PIPES", pipes)

    # Disable time controls/rules and force a single steady hydraulic state.
    if "CONTROLS" in sec:
        text = _replace_section(text, "CONTROLS", ["; disabled for required-head experiment"])
    if "RULES" in sec:
        text = _replace_section(text, "RULES", ["; disabled for required-head experiment"])
    times = [
        "DURATION\t0:00",
        "HYDRAULIC TIMESTEP\t0:05",
        "QUALITY TIMESTEP\t0:05",
        "PATTERN TIMESTEP\t0:30",
        "PATTERN START\t0:00",
        "REPORT TIMESTEP\t0:05",
        "REPORT START\t0:00",
        "START CLOCKTIME\t12:00 AM",
        "STATISTIC\tNONE",
    ]
    text = _replace_section(text, "TIMES", times)

    output_inp = Path(output_inp)
    output_inp.parent.mkdir(parents=True, exist_ok=True)
    output_inp.write_text(text, encoding="utf-8")
    return output_inp


def binary_search_required_head(
    evaluate: Callable[[float], tuple[float, str]],
    *,
    target_pressure_bar: float,
    low_head_m: float = 0.0,
    high_head_m: float = 80.0,
    pressure_tolerance_bar: float = 0.01,
    head_tolerance_m: float = 0.02,
    max_iterations: int = 20,
) -> tuple[float, list[HeadTrial]]:
    """Find the lowest trial head that satisfies the target pressure."""
    trials: list[HeadTrial] = []
    lo, hi = float(low_head_m), float(high_head_m)
    for iteration in range(1, max_iterations + 1):
        h = (lo + hi) / 2.0
        pmin, critical = evaluate(h)
        margin = pmin - target_pressure_bar
        passes = margin >= 0.0
        trials.append(HeadTrial(iteration, h, pmin, critical, margin, passes))
        if passes:
            hi = h
        else:
            lo = h
        if (hi - lo) <= head_tolerance_m or abs(margin) <= pressure_tolerance_bar:
            break
    return hi, trials
