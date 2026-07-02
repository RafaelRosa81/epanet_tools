import geopandas as gpd
from shapely.geometry import LineString, Point

from epanet_tools.hydraulic.validation import validate_basic_epanet_model


def test_validate_basic_epanet_model_reports_export_ready() -> None:
    junctions = gpd.GeoDataFrame(
        {
            "node_id": ["J000001", "J000002"],
            "elevation_m": [10.0, 11.0],
            "geometry": [Point(0, 0), Point(1, 0)],
        },
        crs="EPSG:32719",
    )
    pipes = gpd.GeoDataFrame(
        {
            "pipe_id": ["P000001"],
            "from_node": ["J000001"],
            "to_node": ["J000002"],
            "diameter_mm": [75.0],
            "roughness": [140.0],
            "minor_loss": [0.0],
            "status": ["OPEN"],
            "geometry": [LineString([(0, 0), (1, 0)])],
        },
        crs="EPSG:32719",
    )

    report = validate_basic_epanet_model(junctions, pipes)

    assert report.export_ready is True
    assert report.missing_elevations == 0
    assert report.invalid_node_references == 0
    assert report.disconnected_components == 1


def test_validate_basic_epanet_model_reports_blocking_issues() -> None:
    junctions = gpd.GeoDataFrame(
        {
            "node_id": ["J000001", "J000002"],
            "elevation_m": [None, 11.0],
            "geometry": [Point(0, 0), Point(1, 0)],
        },
        crs="EPSG:32719",
    )
    pipes = gpd.GeoDataFrame(
        {
            "pipe_id": ["P000001"],
            "from_node": ["J000001"],
            "to_node": ["J999999"],
            "diameter_mm": [0.0],
            "roughness": [140.0],
            "minor_loss": [0.0],
            "status": ["BAD"],
            "geometry": [LineString([(0, 0), (1, 0)])],
        },
        crs="EPSG:32719",
    )

    report = validate_basic_epanet_model(junctions, pipes)

    assert report.export_ready is False
    assert report.missing_elevations == 1
    assert report.missing_diameters == 1
    assert report.invalid_pipe_status == 1
    assert report.invalid_node_references == 1
