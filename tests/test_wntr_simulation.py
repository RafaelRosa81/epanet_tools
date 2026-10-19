"""Tests for the optional WNTR simulation adapter."""
import pytest

from epanet_postprocess.simulation import run_inp


def test_missing_inp_raises(tmp_path):
    pytest.importorskip("wntr")
    with pytest.raises(FileNotFoundError):
        run_inp(tmp_path / "missing.inp")


def test_simulation_contract(tmp_path):
    pytest.importorskip("wntr")
    inp = tmp_path / "simple.inp"
    inp.write_text(
        "[TITLE]\nSimple\n"
        "[JUNCTIONS]\n J1 0 1\n"
        "[RESERVOIRS]\n R1 50\n"
        "[PIPES]\n P1 R1 J1 100 100 100 0 Open\n"
        "[OPTIONS]\n UNITS LPS\n HEADLOSS H-W\n"
        "[TIMES]\n DURATION 01:00\n HYDRAULIC TIMESTEP 01:00\n"
        " REPORT TIMESTEP 01:00\n"
        "[END]\n",
        encoding="utf-8",
    )
    result = run_inp(inp)
    assert set(result) == {"nodes", "links", "metadata"}
    assert {"pressure_m", "demand_lps", "hour"}.issubset(result["nodes"].columns)
    assert {"flow_lps", "velocity_m_s", "element_type"}.issubset(result["links"].columns)
    assert result["metadata"]["rounded"] is False
    assert not result["nodes"].empty
