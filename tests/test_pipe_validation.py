import geopandas as gpd
from shapely.geometry import LineString, MultiLineString, Point

from epanet_tools.topology.validation import PipeValidationOptions, validate_pipe_layer


def test_valid_projected_linestring_layer_has_no_issues() -> None:
    pipes = gpd.GeoDataFrame(
        {"id": [1], "geometry": [LineString([(0, 0), (10, 0)])]},
        crs="EPSG:32721",
    )

    report = validate_pipe_layer(pipes)

    assert report.feature_count == 1
    assert report.has_errors is False
    assert report.count_by_severity() == {"info": 0, "warning": 0, "error": 0}


def test_missing_crs_is_error() -> None:
    pipes = gpd.GeoDataFrame({"geometry": [LineString([(0, 0), (10, 0)])]})

    report = validate_pipe_layer(pipes)

    assert report.has_errors is True
    assert report.issues[0].code == "MISSING_CRS"


def test_geographic_crs_is_error_when_projected_required() -> None:
    pipes = gpd.GeoDataFrame(
        {"geometry": [LineString([(-56.0, -34.0), (-56.0, -34.1)])]},
        crs="EPSG:4326",
    )

    report = validate_pipe_layer(pipes)

    assert report.has_errors is True
    assert report.issues[0].code == "NON_PROJECTED_CRS"


def test_point_geometry_is_unsupported_for_pipes() -> None:
    pipes = gpd.GeoDataFrame({"geometry": [Point(0, 0)]}, crs="EPSG:32721")

    report = validate_pipe_layer(pipes)

    assert report.has_errors is True
    assert report.issues[0].code == "UNSUPPORTED_GEOMETRY_TYPE"


def test_multiline_can_be_warning_when_allowed() -> None:
    pipes = gpd.GeoDataFrame(
        {"geometry": [MultiLineString([[(0, 0), (1, 0)], [(1, 0), (2, 0)]])]},
        crs="EPSG:32721",
    )

    report = validate_pipe_layer(pipes, PipeValidationOptions(allow_multilines=True))

    assert report.has_errors is False
    assert report.issues[0].severity == "warning"
    assert report.issues[0].code == "UNSUPPORTED_GEOMETRY_TYPE"


def test_zero_length_linestring_is_error() -> None:
    pipes = gpd.GeoDataFrame(
        {"geometry": [LineString([(0, 0), (0, 0)])]},
        crs="EPSG:32721",
    )

    report = validate_pipe_layer(pipes)

    assert report.has_errors is True
    assert any(issue.code == "NON_POSITIVE_LENGTH" for issue in report.issues)
