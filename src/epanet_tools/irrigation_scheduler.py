"""Generate EPANET binary demand patterns for irrigation sectors.

The generated patterns control nodal demands only. They do not physically open
or close pipes, valves, pumps, or solenoid valves. To represent real valves,
model EPANET links such as valves or controlled pipes. This approach is useful
for hydraulic planning of sectorized irrigation networks.
"""

from __future__ import annotations

import math
import re
import warnings
from collections.abc import Mapping, Sequence
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import pandas as pd


def generate_irrigation_patterns(
    sectors: Sequence[Mapping[str, Any]],
    start_time: str = "06:00",
    pattern_step_minutes: int = 5,
    cycle_duration_hours: int | float = 24,
    tank_usable_volume_m3: float = 4.24,
    refill_flow_m3h: float = 3.6,
    min_tank_volume_m3: float = 1.0,
    safety_factor: float = 1.0,
    round_up: bool = True,
) -> dict[str, Any]:
    """Generate EPANET demand patterns for one irrigation cycle.

    Parameters
    ----------
    sectors:
        Sequence of dictionaries with ``sector_id``, ``nodes``,
        ``required_volume_m3`` and ``nominal_flow_m3h``.
    start_time:
        Start clock time in ``HH:MM`` format.
    pattern_step_minutes:
        Pattern time step. For 24 h and 5 min this gives 288 multipliers.
    cycle_duration_hours:
        Total cycle duration.
    tank_usable_volume_m3:
        Initial usable tank volume.
    refill_flow_m3h:
        Continuous refill flow into the tanks.
    min_tank_volume_m3:
        Minimum allowed tank volume.
    safety_factor:
        Multiplier applied to the required volume before calculating duration.
    round_up:
        If true, round irrigation durations up to full pattern steps.

    Returns
    -------
    dict
        ``patterns``, ``schedule``, ``tank_balance`` and ``node_to_pattern``.

    Notes
    -----
    Patterns are binary demand multipliers: ``1`` means sector demand is active
    and ``0`` means it is off. They do not open or close pipes physically.
    """
    normalized = _normalize_sectors(sectors)
    _validate_common_inputs(
        pattern_step_minutes,
        cycle_duration_hours,
        tank_usable_volume_m3,
        refill_flow_m3h,
        min_tank_volume_m3,
        safety_factor,
    )
    _parse_start_time(start_time)

    total_steps = _total_steps(cycle_duration_hours, pattern_step_minutes)
    dt_h = pattern_step_minutes / 60.0
    tank_volume = float(tank_usable_volume_m3)
    current_step = 0

    patterns = {sector["pattern_id"]: [0] * total_steps for sector in normalized}
    node_to_pattern = {
        node: sector["pattern_id"] for sector in normalized for node in sector["nodes"]
    }
    schedule_rows: list[dict[str, Any]] = []
    balance_rows: list[dict[str, Any]] = []

    for sector in normalized:
        adjusted_volume = sector["required_volume_m3"] * safety_factor
        irrigation_time_h = adjusted_volume / sector["nominal_flow_m3h"]
        irrigation_steps = _duration_to_steps(
            irrigation_time_h,
            pattern_step_minutes=pattern_step_minutes,
            round_up=round_up,
        )

        if irrigation_steps == 0:
            schedule_rows.append(
                _schedule_row(
                    sector,
                    start_time,
                    current_step,
                    current_step,
                    pattern_step_minutes,
                    0.0,
                    tank_volume,
                    tank_volume,
                    recovery_before_min=0,
                )
            )
            continue

        _warn_if_sector_exceeds_single_drawdown(
            sector,
            irrigation_steps,
            dt_h,
            refill_flow_m3h,
            tank_usable_volume_m3,
            min_tank_volume_m3,
        )

        recovery_before_steps = 0
        while _full_run_drops_below_minimum(
            tank_volume,
            sector["nominal_flow_m3h"],
            refill_flow_m3h,
            dt_h,
            irrigation_steps,
            min_tank_volume_m3,
        ):
            if current_step >= total_steps:
                break
            balance_rows.append(
                _balance_row(
                    start_time,
                    current_step,
                    pattern_step_minutes,
                    None,
                    refill_flow_m3h,
                    0.0,
                    tank_volume,
                )
            )
            tank_volume = min(tank_usable_volume_m3, tank_volume + refill_flow_m3h * dt_h)
            current_step += 1
            recovery_before_steps += 1
            if math.isclose(tank_volume, tank_usable_volume_m3, abs_tol=1e-9):
                break

        start_step = current_step
        tank_volume_start = tank_volume
        active_steps_done = 0

        while active_steps_done < irrigation_steps:
            if current_step >= total_steps:
                warnings.warn(
                    f"Sector {sector['sector_id']} does not fit in the "
                    f"configured {cycle_duration_hours:g} h cycle.",
                    RuntimeWarning,
                    stacklevel=2,
                )
                break

            projected = tank_volume + (
                refill_flow_m3h - sector["nominal_flow_m3h"]
            ) * dt_h
            if projected < min_tank_volume_m3 - 1e-9:
                balance_rows.append(
                    _balance_row(
                        start_time,
                        current_step,
                        pattern_step_minutes,
                        None,
                        refill_flow_m3h,
                        0.0,
                        tank_volume,
                    )
                )
                tank_volume = min(tank_usable_volume_m3, tank_volume + refill_flow_m3h * dt_h)
                current_step += 1
                continue

            patterns[sector["pattern_id"]][current_step] = 1
            balance_rows.append(
                _balance_row(
                    start_time,
                    current_step,
                    pattern_step_minutes,
                    sector["sector_id"],
                    refill_flow_m3h,
                    sector["nominal_flow_m3h"],
                    tank_volume,
                )
            )
            tank_volume = projected
            current_step += 1
            active_steps_done += 1

        delivered_volume = sector["nominal_flow_m3h"] * active_steps_done * dt_h
        schedule_rows.append(
            _schedule_row(
                sector,
                start_time,
                start_step,
                current_step,
                pattern_step_minutes,
                delivered_volume,
                tank_volume_start,
                tank_volume,
                recovery_before_min=recovery_before_steps * pattern_step_minutes,
            )
        )

    while current_step < total_steps:
        balance_rows.append(
            _balance_row(
                start_time,
                current_step,
                pattern_step_minutes,
                None,
                refill_flow_m3h,
                0.0,
                tank_volume,
            )
        )
        tank_volume = min(tank_usable_volume_m3, tank_volume + refill_flow_m3h * dt_h)
        current_step += 1

    return {
        "patterns": patterns,
        "schedule": pd.DataFrame(schedule_rows),
        "tank_balance": pd.DataFrame(balance_rows),
        "node_to_pattern": node_to_pattern,
    }


def write_patterns_section(patterns: Mapping[str, Sequence[int]], output_path: str | Path) -> None:
    """Write an EPANET ``[PATTERNS]`` section to a text file."""
    Path(output_path).write_text(_patterns_section_text(patterns), encoding="utf-8")


def insert_patterns_into_inp(
    inp_path: str | Path,
    patterns: Mapping[str, Sequence[int]],
    node_to_pattern: Mapping[str, str],
    output_path: str | Path,
) -> None:
    """Insert patterns and assign them to nodes in an EPANET ``.inp`` file.

    The function replaces the ``[PATTERNS]`` section if present, or inserts it
    before ``[END]``. Pattern assignment is attempted first in ``[DEMANDS]``.
    Nodes without explicit demand rows are assigned in ``[JUNCTIONS]`` when the
    row has a base-demand column.
    """
    text = Path(inp_path).read_text(encoding="utf-8")
    text = _replace_or_insert_section(text, "PATTERNS", _patterns_section_text(patterns))
    text = _assign_patterns_to_demands_or_junctions(text, node_to_pattern)
    Path(output_path).write_text(text, encoding="utf-8")


def plot_schedule(schedule: pd.DataFrame):
    """Plot a horizontal schedule chart and return the matplotlib axes."""
    _fig, ax = plt.subplots()
    if schedule.empty:
        ax.set_title("Irrigation schedule")
        return ax
    starts = pd.to_datetime(schedule["start_time"])
    ends = pd.to_datetime(schedule["end_time"])
    start_h = starts.dt.hour + starts.dt.minute / 60.0
    duration_h = (ends - starts).dt.total_seconds() / 3600.0
    y = range(len(schedule))
    ax.barh(list(y), duration_h, left=start_h)
    ax.set_yticks(list(y), schedule["sector_id"].astype(str).tolist())
    ax.set_xlabel("Hour of day")
    ax.set_ylabel("Sector")
    ax.set_title("Irrigation schedule")
    return ax


def plot_tank_balance(tank_balance: pd.DataFrame):
    """Plot tank volume through time and return the matplotlib axes."""
    _fig, ax = plt.subplots()
    if not tank_balance.empty:
        ax.plot(pd.to_datetime(tank_balance["time"]), tank_balance["tank_volume_m3"])
    ax.set_xlabel("Time")
    ax.set_ylabel("Tank volume (m3)")
    ax.set_title("Tank balance")
    return ax


def plot_patterns(patterns: Mapping[str, Sequence[int]]):
    """Plot binary pattern values by sector and return the matplotlib axes."""
    _fig, ax = plt.subplots()
    for idx, (pattern_id, values) in enumerate(patterns.items()):
        ax.step(range(len(values)), [idx + int(v) * 0.8 for v in values], where="post")
    ax.set_yticks(range(len(patterns)), list(patterns))
    ax.set_xlabel("Pattern step")
    ax.set_ylabel("Pattern")
    ax.set_title("EPANET demand patterns")
    return ax


def _normalize_sectors(sectors: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    if not sectors:
        raise ValueError("sectors cannot be empty.")
    normalized = []
    for raw in sectors:
        sector_id = str(raw["sector_id"])
        nodes = [str(node) for node in raw.get("nodes", [])]
        required_volume_m3 = float(raw["required_volume_m3"])
        nominal_flow_m3h = float(raw["nominal_flow_m3h"])
        if required_volume_m3 < 0:
            raise ValueError(f"Sector {sector_id}: required_volume_m3 must be >= 0.")
        if nominal_flow_m3h <= 0:
            raise ValueError(f"Sector {sector_id}: nominal_flow_m3h must be > 0.")
        if not nodes:
            warnings.warn(
                f"Sector {sector_id} has no nodes; its pattern will not be assigned.",
                RuntimeWarning,
                stacklevel=2,
            )
        normalized.append(
            {
                "sector_id": sector_id,
                "pattern_id": _pattern_id(sector_id),
                "nodes": nodes,
                "required_volume_m3": required_volume_m3,
                "nominal_flow_m3h": nominal_flow_m3h,
            }
        )
    return normalized


def _validate_common_inputs(
    pattern_step_minutes: int,
    cycle_duration_hours: int | float,
    tank_usable_volume_m3: float,
    refill_flow_m3h: float,
    min_tank_volume_m3: float,
    safety_factor: float,
) -> None:
    if pattern_step_minutes <= 0:
        raise ValueError("pattern_step_minutes must be greater than zero.")
    if cycle_duration_hours <= 0:
        raise ValueError("cycle_duration_hours must be greater than zero.")
    if tank_usable_volume_m3 <= min_tank_volume_m3:
        raise ValueError("tank_usable_volume_m3 must be greater than min_tank_volume_m3.")
    if refill_flow_m3h < 0:
        raise ValueError("refill_flow_m3h must be greater than or equal to zero.")
    if min_tank_volume_m3 < 0:
        raise ValueError("min_tank_volume_m3 must be greater than or equal to zero.")
    if safety_factor <= 0:
        raise ValueError("safety_factor must be greater than zero.")


def _duration_to_steps(irrigation_time_h: float, pattern_step_minutes: int, round_up: bool) -> int:
    if irrigation_time_h <= 0:
        return 0
    raw_steps = irrigation_time_h * 60.0 / pattern_step_minutes
    steps = math.ceil(raw_steps) if round_up else round(raw_steps)
    return max(1, int(steps))


def _total_steps(cycle_duration_hours: int | float, pattern_step_minutes: int) -> int:
    raw_steps = cycle_duration_hours * 60.0 / pattern_step_minutes
    if not math.isclose(raw_steps, round(raw_steps), abs_tol=1e-9):
        raise ValueError("cycle_duration_hours must be exactly divisible by pattern_step_minutes.")
    return int(round(raw_steps))


def _warn_if_sector_exceeds_single_drawdown(
    sector: Mapping[str, Any],
    irrigation_steps: int,
    dt_h: float,
    refill_flow_m3h: float,
    tank_usable_volume_m3: float,
    min_tank_volume_m3: float,
) -> None:
    drawdown_available = tank_usable_volume_m3 - min_tank_volume_m3
    net_from_tank = max(0.0, (sector["nominal_flow_m3h"] - refill_flow_m3h) * irrigation_steps * dt_h)
    if net_from_tank > drawdown_available + 1e-9:
        warnings.warn(
            f"Sector {sector['sector_id']} requires {net_from_tank:.2f} m3 net from "
            f"tanks, above the allowed drawdown of {drawdown_available:.2f} m3. "
            "The generated pattern may include recovery pauses inside the sector.",
            RuntimeWarning,
            stacklevel=2,
        )


def _full_run_drops_below_minimum(
    tank_volume: float,
    sector_flow_m3h: float,
    refill_flow_m3h: float,
    dt_h: float,
    irrigation_steps: int,
    min_tank_volume_m3: float,
) -> bool:
    projected = tank_volume + (refill_flow_m3h - sector_flow_m3h) * irrigation_steps * dt_h
    return projected < min_tank_volume_m3 - 1e-9


def _schedule_row(
    sector: Mapping[str, Any],
    start_time: str,
    start_step: int,
    end_step: int,
    pattern_step_minutes: int,
    delivered_volume_m3: float,
    tank_volume_start_m3: float,
    tank_volume_end_m3: float,
    recovery_before_min: int,
) -> dict[str, Any]:
    elapsed_duration_min = (end_step - start_step) * pattern_step_minutes
    if delivered_volume_m3:
        duration_min = round(delivered_volume_m3 / sector["nominal_flow_m3h"] * 60)
    else:
        duration_min = 0
    return {
        "sector_id": sector["sector_id"],
        "start_time": _time_at_step(start_time, start_step, pattern_step_minutes),
        "end_time": _time_at_step(start_time, end_step, pattern_step_minutes),
        "duration_min": duration_min,
        "elapsed_duration_min": elapsed_duration_min,
        "required_volume_m3": sector["required_volume_m3"],
        "nominal_flow_m3h": sector["nominal_flow_m3h"],
        "delivered_volume_m3": delivered_volume_m3,
        "tank_volume_start_m3": tank_volume_start_m3,
        "tank_volume_end_m3": tank_volume_end_m3,
        "recovery_before_min": recovery_before_min,
        "recovery_internal_min": max(0, elapsed_duration_min - duration_min),
    }


def _balance_row(
    start_time: str,
    step: int,
    pattern_step_minutes: int,
    active_sector: str | None,
    inflow_m3h: float,
    outflow_m3h: float,
    tank_volume_m3: float,
) -> dict[str, Any]:
    return {
        "time": _time_at_step(start_time, step, pattern_step_minutes),
        "active_sector": active_sector,
        "inflow_m3h": inflow_m3h,
        "outflow_m3h": outflow_m3h,
        "tank_volume_m3": tank_volume_m3,
    }


def _time_at_step(start_time: str, step: int, pattern_step_minutes: int) -> str:
    return (_parse_start_time(start_time) + timedelta(minutes=step * pattern_step_minutes)).strftime(
        "%H:%M"
    )


def _parse_start_time(start_time: str) -> datetime:
    return datetime.strptime(start_time, "%H:%M")


def _pattern_id(sector_id: str) -> str:
    safe_id = re.sub(r"[^A-Za-z0-9_]+", "_", str(sector_id)).strip("_")
    return f"sector_{safe_id}"


def _patterns_section_text(patterns: Mapping[str, Sequence[int]]) -> str:
    lines = ["[PATTERNS]"]
    for pattern_id, values in patterns.items():
        clean_values = [int(v) for v in values]
        if any(value not in (0, 1) for value in clean_values):
            raise ValueError(f"Pattern {pattern_id} contains values other than 0 or 1.")
        lines.append(f"{pattern_id}  " + " ".join(str(value) for value in clean_values))
    return "\n".join(lines) + "\n"


def _replace_or_insert_section(text: str, section_name: str, replacement: str) -> str:
    pattern = re.compile(
        rf"(?ims)^\s*\[{re.escape(section_name)}\]\s*$.*?(?=^\s*\[[^\]]+\]\s*$|\Z)"
    )
    if pattern.search(text):
        return pattern.sub(replacement.rstrip() + "\n\n", text, count=1)
    end_match = re.search(r"(?im)^\s*\[END\]\s*$", text)
    if end_match:
        return text[: end_match.start()] + replacement + "\n" + text[end_match.start() :]
    return text.rstrip() + "\n\n" + replacement


def _assign_patterns_to_demands_or_junctions(
    text: str, node_to_pattern: Mapping[str, str]
) -> str:
    text, assigned = _assign_in_section(text, "DEMANDS", node_to_pattern, pattern_column=2)
    remaining = {node: pat for node, pat in node_to_pattern.items() if node not in assigned}
    if remaining:
        text, assigned_junctions = _assign_in_section(text, "JUNCTIONS", remaining, pattern_column=3)
        still_remaining = set(remaining) - assigned_junctions
        if still_remaining:
            warnings.warn(
                "No [DEMANDS] or editable [JUNCTIONS] row found for nodes: "
                + ", ".join(sorted(still_remaining)),
                RuntimeWarning,
                stacklevel=2,
            )
    return text


def _assign_in_section(
    text: str,
    section_name: str,
    node_to_pattern: Mapping[str, str],
    pattern_column: int,
) -> tuple[str, set[str]]:
    lines = text.splitlines()
    output: list[str] = []
    assigned: set[str] = set()
    in_section = False
    for line in lines:
        stripped = line.strip()
        if stripped.upper() == f"[{section_name}]":
            in_section = True
            output.append(line)
            continue
        if stripped.startswith("[") and stripped.endswith("]"):
            in_section = False
            output.append(line)
            continue
        if not in_section or not stripped or stripped.startswith(";"):
            output.append(line)
            continue

        content, comment = _split_comment(line)
        parts = content.split()
        node = parts[0] if parts else ""
        if node in node_to_pattern and len(parts) >= pattern_column:
            while len(parts) <= pattern_column:
                parts.append("")
            parts[pattern_column] = node_to_pattern[node]
            line = "  ".join(parts).rstrip() + comment
            assigned.add(node)
        output.append(line)
    return "\n".join(output) + ("\n" if text.endswith("\n") else ""), assigned


def _split_comment(line: str) -> tuple[str, str]:
    if ";" not in line:
        return line, ""
    content, comment = line.split(";", 1)
    return content.rstrip(), "  ;" + comment


EXAMPLE_SECTORS = [
    {
        "sector_id": "1",
        "nodes": ["J000024", "J000023"],
        "required_volume_m3": 4.00,
        "nominal_flow_m3h": 14.20,
    },
    {
        "sector_id": "2",
        "nodes": ["J000021"],
        "required_volume_m3": 4.75,
        "nominal_flow_m3h": 16.88,
    },
    {
        "sector_id": "3",
        "nodes": ["J000026", "J000027"],
        "required_volume_m3": 1.85,
        "nominal_flow_m3h": 16.20,
    },
    {
        "sector_id": "41",
        "nodes": ["J000017", "J000042", "J000016"],
        "required_volume_m3": 5.64,
        "nominal_flow_m3h": 20.03,
    },
    {
        "sector_id": "42",
        "nodes": ["J000020", "J000041"],
        "required_volume_m3": 1.77,
        "nominal_flow_m3h": 15.53,
    },
    {
        "sector_id": "5",
        "nodes": ["J000031", "J000032", "J000039"],
        "required_volume_m3": 6.60,
        "nominal_flow_m3h": 23.44,
    },
    {
        "sector_id": "6",
        "nodes": ["J000037"],
        "required_volume_m3": 1.33,
        "nominal_flow_m3h": 4.71,
    },
    {
        "sector_id": "7",
        "nodes": ["J000035", "J000033"],
        "required_volume_m3": 2.24,
        "nominal_flow_m3h": 19.63,
    },
    {
        "sector_id": "8",
        "nodes": ["J000048", "J000047", "J000044", "J000045"],
        "required_volume_m3": 0.32,
        "nominal_flow_m3h": 0.63,
    },
]


__all__ = [
    "EXAMPLE_SECTORS",
    "generate_irrigation_patterns",
    "insert_patterns_into_inp",
    "plot_patterns",
    "plot_schedule",
    "plot_tank_balance",
    "write_patterns_section",
]
