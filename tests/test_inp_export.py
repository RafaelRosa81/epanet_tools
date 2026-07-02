import geopandas as gpd
from shapely.geometry import LineString, Point

from epanet_tools.io.inp import build_basic_inp_text


def test_build_basic_inp_text_contains_minimum_sections() -> None:
    junctions = gpd.GeoDataFrame(
        {
            "node_id": ["J000001", "J000002"],
            "elevation_m": [10.0, 12.0],
            "geometry": [Point(0.0, 0.0), Point(10.0, 0.0)],
        },
        crs="EPSG:32719",
    )
    pipes = gpd.GeoDataFrame(
        {
            "pipe_id": ["P000001"],
            "from_node": ["J000001"],
            "to_node": ["J000002"],
            "length_m": [10.0],
            "diameter_mm": [75.0],
            "roughness": [140.0],
            "minor_loss": [0.0],
            "status": ["OPEN"],
            "geometry": [LineString([(0.0, 0.0), (5.0, 1.0), (10.0, 0.0)])],
        },
        crs="EPSG:32719",
    )

    text = build_basic_inp_text(junctions, pipes)

    assert "[JUNCTIONS]" in text
    assert "[PIPES]" in text
    assert "[COORDINATES]" in text
    assert "[VERTICES]" in text
    assert "[OPTIONS]" in text
    assert "[END]" in text
    assert "J000001" in text
    assert "P000001" in text
    assert "75" in text
    assert "5" in text
