from pathlib import Path

from epanet_postprocess.reader import read_rpt


REPORT = """
Node Results at 0:00 Hrs:
----------------------------------------------------------------------
Node                Demand      Head  Pressure   Quality
ID                     CMH         m         m
----------------------------------------------------------------------
J000001               0.00    100.00     10.00      0.00
Node Results at 0:00 Hrs: (continued)
----------------------------------------------------------------------
J000002               1.50     99.00      8.50      0.00
Link Results at 0:00 Hrs:
----------------------------------------------------------------------
Link                  Flow  VelocityUnit Headloss    Status
ID                     CMH       m/s      m/km
----------------------------------------------------------------------
P000001               1.50      0.20      1.00      Open
Link Results at 0:00 Hrs: (continued)
----------------------------------------------------------------------
123                  -1.50      0.20      1.00      Closed
Node Results at 1:00 Hrs:
----------------------------------------------------------------------
J000001               0.00    100.00     11.00      0.00
Link Results at 1:00 Hrs:
----------------------------------------------------------------------
P000001               0.00      0.00      0.00      Closed
"""


def test_read_rpt_parses_time_blocks_and_continuations(tmp_path: Path) -> None:
    report_path = tmp_path / "example.rpt"
    report_path.write_text(REPORT)

    results = read_rpt(report_path)

    assert len(results["nodes"]) == 3
    assert len(results["links"]) == 3
    assert results["metadata"]["node_time_steps"] == 2
    assert results["metadata"]["link_time_steps"] == 2
    assert results["metadata"]["link_count"] == 2
    assert results["links"].loc[1, "link_id"] == "123"
    assert results["links"].loc[1, "flow"] == -1.5
    assert results["links"].loc[1, "status"] == "Closed"
