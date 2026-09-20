import geopandas as gpd
from shapely.geometry import LineString, Point

from epanet_tools.io.vector import read_existing_network
from epanet_tools.workflows.import_existing_network import (
    _apply_node_attributes_csv,
    _apply_pipe_attributes_csv,
    _filter_network,
    _map_fields,
)


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


def test_filter_network_excludes_sectors_and_preserves_endpoints() -> None:
    nodes = gpd.GeoDataFrame(
        {
            "node_id": ["N1", "N2", "N3", "N4"],
            "SECTOR": [1.0, 1.0, 8.0, 8.0],
        },
        geometry=[Point(0, 0), Point(1, 0), Point(2, 0), Point(3, 0)],
        crs="EPSG:32721",
    )
    pipes = gpd.GeoDataFrame(
        {
            "pipe_id": ["P1", "P2", "P3"],
            "from_node": ["N1", "N3", "N2"],
            "to_node": ["N2", "N4", "N3"],
            "SECTOR": [1.0, 8.0, 1.0],
        },
        geometry=[
            LineString([(0, 0), (1, 0)]),
            LineString([(2, 0), (3, 0)]),
            LineString([(1, 0), (2, 0)]),
        ],
        crs="EPSG:32721",
    )

    filtered_nodes, filtered_pipes = _filter_network(
        nodes, pipes, {"exclude_sectors": [8]}
    )

    assert filtered_nodes["node_id"].tolist() == ["N1", "N2"]
    assert filtered_pipes["pipe_id"].tolist() == ["P1"]


def test_apply_node_attributes_csv_overrides_all_retained_elevations(tmp_path) -> None:
    nodes = gpd.GeoDataFrame(
        {"node_id": ["N1", "N2", "N3"], "elevation_m": [None, None, None]},
        geometry=[Point(0, 0), Point(1, 0), Point(2, 0)],
        crs="EPSG:32721",
    )
    csv_path = tmp_path / "node_z.csv"
    csv_path.write_text("ID,Z\nN1,10.1\nN2,11.2\nN3,12.3\n", encoding="utf-8")

    enriched = _apply_node_attributes_csv(
        nodes,
        {
            "path": str(csv_path),
            "key": "ID",
            "node_key": "node_id",
            "fields": {"elevation_m": "Z"},
        },
    )

    assert enriched["elevation_m"].tolist() == [10.1, 11.2, 12.3]


def test_apply_pipe_attributes_csv_overrides_retained_hydraulics(tmp_path) -> None:
    pipes = gpd.GeoDataFrame(
        {
            "pipe_id": ["P1", "P2"],
            "diameter_mm": [None, None],
            "roughness": [None, None],
        },
        geometry=[
            LineString([(0, 0), (1, 0)]),
            LineString([(1, 0), (2, 0)]),
        ],
        crs="EPSG:32721",
    )
    csv_path = tmp_path / "pipe_hydraulics.csv"
    csv_path.write_text(
        "ID,DIAMETRO,C_HW\nP1,63,120\nP2,75,130\n",
        encoding="utf-8",
    )

    enriched = _apply_pipe_attributes_csv(
        pipes,
        {
            "path": str(csv_path),
            "key": "ID",
            "pipe_key": "pipe_id",
            "fields": {"diameter_mm": "DIAMETRO", "roughness": "C_HW"},
        },
    )

    assert enriched["diameter_mm"].tolist() == [63, 75]
    assert enriched["roughness"].tolist() == [120, 130]
