import geopandas as gpd
import pandas as pd
from shapely.geometry import LineString, Point

from epanet_tools.workflows.align_vertical_sectors import align_vertical_sectors


def test_align_vertical_sectors_moves_all_configured_sectors_with_same_vector(tmp_path) -> None:
    source = tmp_path / "network.gpkg"
    nodes = gpd.GeoDataFrame(
        {
            "ID": ["FIXED", "REF15", "N15", "N9", "OTHER"],
            "SECTOR": [5.0, 15.0, 15.0, 9.0, 6.0],
            "X": [100.0, 10.0, 12.0, 20.0, 200.0],
            "Y": [50.0, 5.0, 7.0, 15.0, 200.0],
        },
        geometry=[
            Point(100, 50),
            Point(10, 5),
            Point(12, 7),
            Point(20, 15),
            Point(200, 200),
        ],
        crs="EPSG:32721",
    )
    pipes = gpd.GeoDataFrame(
        {
            "ID": ["P15", "P9", "P6"],
            "SECTOR": [15.0, 9.0, 6.0],
            "NODE_INI": ["REF15", "N9", "OTHER"],
            "NODE_FIN": ["N15", "N9", "OTHER"],
        },
        geometry=[
            LineString([(10, 5), (12, 7)]),
            LineString([(20, 15), (21, 15)]),
            LineString([(200, 200), (201, 200)]),
        ],
        crs="EPSG:32721",
    )
    nodes.to_file(source, layer="nodos", driver="GPKG")
    pipes.to_file(source, layer="tramos", driver="GPKG")

    table = tmp_path / "connections.csv"
    pd.DataFrame(
        [
            {
                "sector": 15,
                "source_node": "G1",
                "target_node": "REF15",
                "target_z": -0.15,
                "vertical_length_m": 4.45,
                "direction": "DOWN",
            },
            {
                "sector": 9,
                "source_node": "G1",
                "target_node": "N9",
                "target_z": 8.67,
                "vertical_length_m": 4.45,
                "direction": "UP",
            },
        ]
    ).to_csv(table, index=False)

    output = tmp_path / "connected.gpkg"
    report = tmp_path / "report.csv"
    config = tmp_path / "config.yml"
    config.write_text(
        f"""inputs:
  existing_network:
    path: {source.as_posix()}
    node_layer: nodos
    pipe_layer: tramos
vertical_sector_alignment:
  moving_reference_node: REF15
  fixed_reference_node: FIXED
  sectors: [9, 15]
  table_path: {table.as_posix()}
  output_path: {output.as_posix()}
  report_path: {report.as_posix()}
""",
        encoding="utf-8",
    )

    result = align_vertical_sectors(config)

    moved_nodes = gpd.read_file(output, layer="nodos")
    moved_pipes = gpd.read_file(output, layer="tramos")
    ref15 = moved_nodes.loc[moved_nodes["ID"] == "REF15"].iloc[0]
    n15 = moved_nodes.loc[moved_nodes["ID"] == "N15"].iloc[0]
    n9 = moved_nodes.loc[moved_nodes["ID"] == "N9"].iloc[0]
    other = moved_nodes.loc[moved_nodes["ID"] == "OTHER"].iloc[0]
    p15 = moved_pipes.loc[moved_pipes["ID"] == "P15"].iloc[0]
    p9 = moved_pipes.loc[moved_pipes["ID"] == "P9"].iloc[0]

    # REF15 -> FIXED defines dx=90, dy=45 for both sectors 15 and 9.
    assert (ref15.geometry.x, ref15.geometry.y) == (100.0, 50.0)
    assert (n15.geometry.x, n15.geometry.y) == (102.0, 52.0)
    assert (n9.geometry.x, n9.geometry.y) == (110.0, 60.0)
    assert (n9["X"], n9["Y"]) == (110.0, 60.0)
    assert (other.geometry.x, other.geometry.y) == (200.0, 200.0)
    assert list(p15.geometry.coords) == [(100.0, 50.0), (102.0, 52.0)]
    assert list(p9.geometry.coords) == [(110.0, 60.0), (111.0, 60.0)]
    assert result.aligned_sectors == 2
    assert result.dx_m == 90.0
    assert result.dy_m == 45.0

    report_df = pd.read_csv(report)
    assert set(report_df["sector"]) == {9, 15}
    assert set(report_df["status"]) == {"aligned"}
    assert set(report_df["dx_m"]) == {90.0}
    assert set(report_df["dy_m"]) == {45.0}
