"""Example: generate EPANET demand patterns for irrigation sectors.

Usage
-----
python examples/example_irrigation_scheduler.py
"""

from __future__ import annotations

from pathlib import Path

from epanet_tools.irrigation_scheduler import (
    EXAMPLE_SECTORS,
    generate_irrigation_patterns,
    plot_patterns,
    plot_schedule,
    plot_tank_balance,
    write_patterns_section,
)


def main() -> None:
    output_folder = Path("outputs/irrigation_scheduler")
    output_folder.mkdir(parents=True, exist_ok=True)

    result = generate_irrigation_patterns(
        EXAMPLE_SECTORS,
        start_time="06:00",
        pattern_step_minutes=5,
        cycle_duration_hours=24,
        tank_usable_volume_m3=4.24,
        refill_flow_m3h=3.6,
        min_tank_volume_m3=1.0,
    )

    patterns = result["patterns"]
    schedule = result["schedule"]
    tank_balance = result["tank_balance"]

    print(schedule)
    schedule.to_csv(output_folder / "irrigation_schedule.csv", index=False)
    tank_balance.to_csv(output_folder / "tank_balance.csv", index=False)
    write_patterns_section(patterns, output_folder / "patterns_section.inp")

    ax = plot_schedule(schedule)
    ax.figure.savefig(output_folder / "schedule.png", dpi=150, bbox_inches="tight")

    ax = plot_tank_balance(tank_balance)
    ax.figure.savefig(output_folder / "tank_balance.png", dpi=150, bbox_inches="tight")

    ax = plot_patterns(patterns)
    ax.figure.savefig(output_folder / "patterns.png", dpi=150, bbox_inches="tight")


if __name__ == "__main__":
    main()
