from __future__ import annotations

from pathlib import Path

import pytest

from epanet_tools.irrigation_scheduler import (
    EXAMPLE_SECTORS,
    generate_irrigation_patterns,
    insert_patterns_into_inp,
    write_patterns_section,
)


def test_generate_irrigation_patterns_returns_expected_tables() -> None:
    result = generate_irrigation_patterns(EXAMPLE_SECTORS)

    assert set(result) == {"patterns", "schedule", "tank_balance", "node_to_pattern"}
    assert len(result["patterns"]) == len(EXAMPLE_SECTORS)
    assert all(len(values) == 288 for values in result["patterns"].values())
    assert len(result["schedule"]) == len(EXAMPLE_SECTORS)
    assert len(result["tank_balance"]) == 288
    assert result["tank_balance"]["tank_volume_m3"].min() >= 1.0
    assert result["node_to_pattern"]["J000024"] == "sector_1"


def test_pattern_steps_deliver_at_least_required_volume_when_rounded_up() -> None:
    result = generate_irrigation_patterns(EXAMPLE_SECTORS, round_up=True)
    schedule = result["schedule"]

    assert (schedule["delivered_volume_m3"] >= schedule["required_volume_m3"]).all()


def test_write_patterns_section(tmp_path: Path) -> None:
    output_path = tmp_path / "patterns.inp"

    write_patterns_section({"sector_1": [0, 1, 1, 0], "sector_2": [0, 0, 1, 1]}, output_path)

    text = output_path.read_text(encoding="utf-8")
    assert text.startswith("[PATTERNS]")
    assert "sector_1  0 1 1 0" in text
    assert "sector_2  0 0 1 1" in text


def test_insert_patterns_into_inp_updates_patterns_and_demands(tmp_path: Path) -> None:
    inp_path = tmp_path / "input.inp"
    output_path = tmp_path / "output.inp"
    inp_path.write_text(
        """[TITLE]
Example

[JUNCTIONS]
;ID Elevation Demand Pattern
J1 10 0.5
J2 11 0.4

[DEMANDS]
;Junction Demand Pattern
J1 0.5 old_pattern

[PATTERNS]
old_pattern 1 1 1

[END]
""",
        encoding="utf-8",
    )

    insert_patterns_into_inp(
        inp_path,
        {"sector_1": [0, 1, 0], "sector_2": [1, 0, 1]},
        {"J1": "sector_1", "J2": "sector_2"},
        output_path,
    )

    text = output_path.read_text(encoding="utf-8")
    assert "old_pattern 1 1 1" not in text
    assert "sector_1  0 1 0" in text
    assert "sector_2  1 0 1" in text
    assert "J1  0.5  sector_1" in text
    assert "J2  11  0.4  sector_2" in text


def test_invalid_sector_flow_raises() -> None:
    with pytest.raises(ValueError, match="nominal_flow_m3h"):
        generate_irrigation_patterns(
            [
                {
                    "sector_id": "bad",
                    "nodes": ["J1"],
                    "required_volume_m3": 1.0,
                    "nominal_flow_m3h": 0.0,
                }
            ]
        )
