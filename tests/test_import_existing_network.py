import geopandas as gpd
from shapely.geometry import LineString, Point

from epanet_tools.io.vector import read_existing_network
from epanet_tools.workflows.import_existing_network import _map_fields


def test_read_existing_network_reads_explicit_node_and_pipe_layers(tmp_path) -> None:
    path = tmp_path / "network.gpkg"
    nodes = gpd.GeoDataFrame(
        {"ID": ["N1", "N2"], "Z": [10.0, 11.0], "DEMANDA": [0.0, 1.5]},
        geometry=[Point(0, 0), Point(10, 0)],
        crs="EPSG:32721",
    )
    pipes = gpd.GeoDataFrame(
        {
            "ID": ["P1"],
            "NODE_INI": ["N1"],
            "NODE_FIN": ["N2"],
            "LONGITUD": [10.0],
            "DIAMETRO": [75.0],
            "C_HW": [140.0],
            "MATERIAL": ["PVC"],
        },
        geometry=[LineString([(0, 0), (10, 0)])],
        crs="EPSG:32721",
    )
    nodes.to_file(path, layer="nodos", driver="GPKG")
    pipes.to_file(path, layer="tramos", driver="GPKG")

    read_nodes, read_pipes = read_existing_network(
        path,
        node_layer="nodos",
        pipe_layer="tramos",
        working_crs="EPSG:32721",
    )

    assert len(read_nodes) == 2
    assert len(read_pipes) == 1
    assert read_nodes.crs == "EPSG:32721"
    assert read_pipes.crs == "EPSG:32721"
    assert read_nodes["_source_layer"].iloc[0] == "nodos"
    assert read_pipes["_source_layer"].iloc[0] == "tramos"


def test_map_fields_creates_canonical_fields_and_defaults() -> None:
    data = gpd.GeoDataFrame(
        {"ID": ["N1"], "Z": [10.0]},
        geometry=[Point(0, 0)],
        crs="EPSG:32721",
    )

    mapped = _map_fields(
        data,
        {"node_id": "ID", "elevation_m": "Z"},
        defaults={"demand": 0.0},
    )

    assert mapped["node_id"].tolist() == ["N1"]
    assert mapped["elevation_m"].tolist() == [10.0]
    assert mapped["demand"].tolist() == [0.0]
