import geopandas as gpd
from shapely.geometry import LineString

from epanet_tools.topology.cleaning import snap_pipe_endpoints


def test_snap_pipe_endpoints_moves_near_endpoints_to_common_point() -> None:
    pipes = gpd.GeoDataFrame(
        {
            "id": [1, 2],
            "geometry": [
                LineString([(0.0, 0.0), (10.0, 0.0)]),
                LineString([(10.1, 0.0), (20.0, 0.0)]),
            ],
        },
        crs="EPSG:32719",
    )

    cleaned, report = snap_pipe_endpoints(pipes, tolerance_m=0.2)

    first_end = list(cleaned.geometry.iloc[0].coords)[-1]
    second_start = list(cleaned.geometry.iloc[1].coords)[0]

    assert first_end == second_start
    assert first_end == (10.05, 0.0)
    assert report.snapped_endpoint_count == 2
    assert report.snap_group_count == 1


def test_snap_pipe_endpoints_does_not_move_endpoints_outside_tolerance() -> None:
    pipes = gpd.GeoDataFrame(
        {
            "id": [1, 2],
            "geometry": [
                LineString([(0.0, 0.0), (10.0, 0.0)]),
                LineString([(11.0, 0.0), (20.0, 0.0)]),
            ],
        },
        crs="EPSG:32719",
    )

    cleaned, report = snap_pipe_endpoints(pipes, tolerance_m=0.2)

    assert cleaned.geometry.equals(pipes.geometry)
    assert report.snapped_endpoint_count == 0
    assert report.snap_group_count == 0
