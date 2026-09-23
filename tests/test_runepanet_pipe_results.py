from pathlib import Path

from epanet_tools.hydraulic.runepanet import parse_inp_pipes, pipe_hydraulic_results


def test_pipe_hydraulic_results_computes_velocity(tmp_path: Path) -> None:
    inp = tmp_path / "m.inp"
    inp.write_text(
        "[PIPES]\n"
        ";ID Node1 Node2 Length Diameter Roughness MinorLoss Status\n"
        "P1 J1 J2 10 100 120 0 OPEN\n\n"
        "[OPTIONS]\nUNITS LPM\n",
        encoding="utf-8",
    )
    rpt = tmp_path / "m.rpt"
    rpt.write_text(
        "Link Results:\n"
        "Link Flow Velocity Headloss\n"
        "P1 471.2389 1.00 0.1\n",
        encoding="utf-8",
    )
    pipes = parse_inp_pipes(inp)
    assert pipes["P1"]["diameter_mm"] == 100.0
    rows = pipe_hydraulic_results(inp, rpt)
    assert len(rows) == 1
    assert rows[0]["pipe_id"] == "P1"
    assert abs(rows[0]["velocity_m_s"] - 1.0) < 1e-5
