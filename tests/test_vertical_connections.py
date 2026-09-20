import geopandas as gpd
from shapely.geometry import LineString, Point

from epanet_tools.hydraulic.validation import validate_basic_epanet_model
from epanet_tools.hydraulic.vertical_connections import add_vertical_connections


def test_add_vertical_connections_connects_sector_with_explicit_hydraulic_lengths(tmp_path) -> None:
    nodes = gpd.GeoDataFrame(
        {
            "node_id": ["G", "ANCHOR", "TARGET", "OTHER"],
            "elevation_m": [4.3, 4.3, 3.33333, 3.33333],
            "demand": [0.0, 0.0, 0.0, 0.0],
            "ID": ["G", "ANCHOR", "TARGET", "OTHER"],
            "SECTOR": [None, 5.0, 15.0, 15.0],
            "X": [0.0, 0.3, 100.0, 102.0],
            "Y": [0.0, 0.0, 100.0, 100.0],
            "Z": [4.3, 4.3, 3.33333, 3.33333],
        },
        geometry=[Point(0, 0), Point(0.3, 0), Point(100, 100), Point(102, 100)],
        crs="EPSG:32721",
    )
    pipes = gpd.GeoDataFrame(
        {
            "pipe_id": ["P15"],
            "from_node": ["TARGET"],
            "to_node": ["OTHER"],
            "length_m": [2.0],
            "diameter_mm": [63.0],
            "roughness": [120.0],
            "minor_loss": [0.0],
            "status": ["OPEN"],
            "ID": ["P15"],
            "SECTOR": [15.0],
        },
        geometry=[LineString([(100, 100), (102, 100)])],
        crs="EPSG:32721",
    )
    table = tmp_path / "vertical.csv"
    table.write_text(
        "sector,source_node,anchor_node,target_node,target_z,vertical_length_m,direction\n"
        "15,G,ANCHOR,TARGET,-0.15,4.45,DOWN\n",
        encoding="utf-8",
    )

    out_nodes, out_pipes, report = add_vertical_connections(
        nodes,
        pipes,
        {
            "table_path": str(table),
            "diameter_mm": 63.0,
            "roughness": 120.0,
            "display_offset_x": -0.75,
        },
    )

    assert len(out_nodes) == 5
    assert len(out_pipes) == 3
    assert set(out_pipes["pipe_id"]) == {"P15", "15_V001", "15_E001"}
    assert out_nodes.loc[out_nodes["node_id"] == "15_R001", "elevation_m"].iloc[0] == -0.15
    assert set(out_nodes.loc[out_nodes["SECTOR"] == 15.0, "elevation_m"]) == {-0.15}
    assert out_pipes.loc[out_pipes["pipe_id"] == "15_V001", "length_m"].iloc[0] == 4.45
    assert abs(out_pipes.loc[out_pipes["pipe_id"] == "15_E001", "length_m"].iloc[0] - 0.3) < 1e-9
    assert report.loc[0, "riser_node"] == "15_R001"

    validation = validate_basic_epanet_model(out_nodes, out_pipes)
    assert validation.disconnected_components == 1
    assert validation.invalid_node_references == 0
    assert validation.isolated_junctions == 0
