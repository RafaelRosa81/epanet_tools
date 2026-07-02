import geopandas as gpd
from shapely.geometry import LineString

from epanet_tools.topology.connectivity import build_junctions_and_connectivity


def test_build_junctions_and_connectivity_assigns_nodes_and_lengths() -> None:
    pipes = gpd.GeoDataFrame(
        {
            "name": ["p1", "p2"],
            "geometry": [
                LineString([(0.0, 0.0), (10.0, 0.0)]),
                LineString([(10.0, 0.0), (10.0, 5.0)]),
            ],
        },
        crs="EPSG:32719",
    )

    connected, junctions, report = build_junctions_and_connectivity(pipes)

    assert len(connected) == 2
    assert len(junctions) == 3
    assert report.pipe_count == 2
    assert report.junction_count == 3
    assert report.skipped_geometry_count == 0

    assert connected["pipe_id"].tolist() == ["P000001", "P000002"]
    assert connected["from_node"].tolist() == ["J000001", "J000002"]
    assert connected["to_node"].tolist() == ["J000002", "J000003"]
    assert connected["length_m"].tolist() == [10.0, 5.0]
    assert junctions["node_id"].tolist() == ["J000001", "J000002", "J000003"]
