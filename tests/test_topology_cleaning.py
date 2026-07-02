import geopandas as gpd
from shapely.geometry import LineString, Point

from epanet_tools.topology.cleaning import normalize_pipe_topology, snap_pipe_endpoints
from epanet_tools.topology.connectivity import build_junctions_and_connectivity


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


def test_snap_pipe_endpoints_preserves_z_coordinates() -> None:
    pipes = gpd.GeoDataFrame(
        {
            "id": [1, 2],
            "geometry": [
                LineString([(0.0, 0.0, 1.0), (10.0, 0.0, 2.0)]),
                LineString([(10.1, 0.0, 3.0), (20.0, 0.0, 4.0)]),
            ],
        },
        crs="EPSG:32719",
    )

    cleaned, report = snap_pipe_endpoints(pipes, tolerance_m=0.2)

    first_end = list(cleaned.geometry.iloc[0].coords)[-1]
    second_start = list(cleaned.geometry.iloc[1].coords)[0]

    assert first_end == (10.05, 0.0, 2.0)
    assert second_start == (10.05, 0.0, 3.0)
    assert report.snapped_endpoint_count == 2
    assert report.snap_group_count == 1


def test_normalize_pipe_topology_snaps_endpoint_to_segment_and_splits_target() -> None:
    pipes = gpd.GeoDataFrame(
        {
            "id": ["main", "lateral"],
            "geometry": [
                LineString([(0.0, 0.0), (10.0, 0.0)]),
                LineString([(5.0, 0.15), (5.0, 3.0)]),
            ],
        },
        crs="EPSG:32719",
    )

    cleaned, report = normalize_pipe_topology(pipes, tolerance_m=0.2)

    assert len(cleaned) == 3
    assert report.endpoint_to_segment_snap_count == 1
    assert report.split_pipe_count == 1
    assert report.output_feature_count == 3

    lateral = cleaned.loc[cleaned["id"] == "lateral"].geometry.iloc[0]
    assert Point(list(lateral.coords)[0]).equals_exact(Point(5.0, 0.0), tolerance=1e-9)

    main_parts = cleaned.loc[cleaned["id"] == "main"].geometry.tolist()
    assert len(main_parts) == 2
    assert sorted(round(part.length, 6) for part in main_parts) == [5.0, 5.0]


def test_normalize_pipe_topology_splits_existing_tee_before_connectivity() -> None:
    pipes = gpd.GeoDataFrame(
        {
            "id": ["main", "lateral"],
            "geometry": [
                LineString([(0.0, 0.0), (10.0, 0.0)]),
                LineString([(5.0, 0.0), (5.0, 3.0)]),
            ],
        },
        crs="EPSG:32719",
    )

    cleaned, report = normalize_pipe_topology(pipes, tolerance_m=0.2)
    connected, junctions, _ = build_junctions_and_connectivity(cleaned)

    assert len(cleaned) == 3
    assert report.endpoint_to_segment_snap_count == 0
    assert report.connection_split_point_count >= 1
    assert report.split_pipe_count == 1

    main_parts = connected.loc[connected["id"] == "main"]
    lateral = connected.loc[connected["id"] == "lateral"].iloc[0]
    tee_node = lateral["from_node"]

    assert len(main_parts) == 2
    assert tee_node in set(junctions["node_id"])
    assert sum(tee_node in {row.from_node, row.to_node} for row in main_parts.itertuples()) == 2


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
