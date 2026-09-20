import geopandas as gpd
import pandas as pd
from shapely.geometry import LineString, Point

from epanet_tools.workflows.align_vertical_sectors import align_vertical_sectors


def test_align_vertical_sectors_moves_confirmed_sector_as_rigid_block(tmp_path) -> None:
    source = tmp_path / "network.gpkg"
    nodes = gpd.GeoDataFrame(
        {
            "ID": ["FIXED", "M1", "M2", "OTHER"],
            "SECTOR": [5.0, 15.0, 15.0, 6.0],
            "X": [100.0, 10.0, 12.0, 200.0],
            "Y": [50.0, 5.0, 7.0, 200.0],
        },
        geometry=[Point(100, 50), Point(10, 5), Point(12, 7), Point(200, 200)],
        crs="EPSG:32721",
    )
    pipes = gpd.GeoDataFrame(
        {
            "ID": ["P15", "P6"],
            "SECTOR": [15.0, 6.0],
            "NODE_INI": ["M1", "OTHER"],
            "NODE_FIN": ["M2", "OTHER"],
        },
        geometry=[
            LineString([(10, 5), (12, 7)]),
            LineString([(200, 200), (201, 200)]),
        ],
        crs="EPSG:32721",
    )
    nodes.to_file(source, layer="nodos", driver="GPKG")
    pipes.to_file(source, layer="tramos", driver="GPKG")

    table = tmp_path / "align.csv"
    pd.DataFrame(
        [
            {
                "sector": 15,
                "moving_reference_node": "M1",
                "fixed_reference_node": "FIXED",
                "enabled": True,
                "source_node": "G",
                "target_node": "M1",
                "target_z": -0.15,
                "vertical_length_m": 4.45,
                "direction": "DOWN",
            },
            {
                "sector": 9,
                "moving_reference_node": "X",
                "fixed_reference_node": "",
                "enabled": False,
                "source_node": "G2",
                "target_node": "X",
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
  table_path: {table.as_posix()}
  output_path: {output.as_posix()}
  report_path: {report.as_posix()}
""",
        encoding="utf-8",
    )

    result = align_vertical_sectors(config)

    moved_nodes = gpd.read_file(output, layer="nodos")
    moved_pipes = gpd.read_file(output, layer="tramos")
    m1 = moved_nodes.loc[moved_nodes["ID"] == "M1"].iloc[0]
    m2 = moved_nodes.loc[moved_nodes["ID"] == "M2"].iloc[0]
    other = moved_nodes.loc[moved_nodes["ID"] == "OTHER"].iloc[0]
    p15 = moved_pipes.loc[moved_pipes["ID"] == "P15"].iloc[0]

    assert (m1.geometry.x, m1.geometry.y) == (100.0, 50.0)
    assert (m2.geometry.x, m2.geometry.y) == (102.0, 52.0)
    assert (m2["X"], m2["Y"]) == (102.0, 52.0)
    assert (other.geometry.x, other.geometry.y) == (200.0, 200.0)
    assert list(p15.geometry.coords) == [(100.0, 50.0), (102.0, 52.0)]
    assert result.aligned_sectors == 1
    assert result.skipped_sectors == 1

    report_df = pd.read_csv(report)
    assert report_df.loc[report_df["sector"] == 15, "status"].iloc[0] == "aligned"
    assert report_df.loc[report_df["sector"] == 9, "status"].iloc[0] == "skipped"
