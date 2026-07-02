import geopandas as gpd
import pytest
from shapely.geometry import LineString

from epanet_tools.exceptions import ConfigurationError
from epanet_tools.io.vector import read_pipe_layers


def _write_pipe_layer(path, layer, crs="EPSG:32721") -> None:
    pipes = gpd.GeoDataFrame(
        {"id": [1], "geometry": [LineString([(0, 0), (10, 0)])]},
        crs=crs,
    )
    pipes.to_file(path, layer=layer, driver="GPKG")


def test_read_pipe_layers_combines_sources_and_preserves_traceability(tmp_path) -> None:
    path_1 = tmp_path / "pipes_1.gpkg"
    path_2 = tmp_path / "pipes_2.gpkg"
    _write_pipe_layer(path_1, "pipes")
    _write_pipe_layer(path_2, "pipes")

    combined = read_pipe_layers(
        [
            {"path": str(path_1), "layer": "pipes"},
            {"path": str(path_2), "layer": "pipes"},
        ]
    )

    assert len(combined) == 2
    assert combined.crs == "EPSG:32721"
    assert combined["_source_order"].tolist() == [1, 2]
    assert combined["_source_layer"].tolist() == ["pipes", "pipes"]
    assert combined["_source_path"].str.endswith(".gpkg").all()
    assert combined["_source_crs"].tolist() == ["EPSG:32721", "EPSG:32721"]


def test_read_pipe_layers_rejects_mixed_crs_without_working_crs(tmp_path) -> None:
    path_1 = tmp_path / "pipes_1.gpkg"
    path_2 = tmp_path / "pipes_2.gpkg"
    _write_pipe_layer(path_1, "pipes", crs="EPSG:32721")
    _write_pipe_layer(path_2, "pipes", crs="EPSG:4326")

    with pytest.raises(ConfigurationError, match="working_crs"):
        read_pipe_layers(
            [
                {"path": str(path_1), "layer": "pipes"},
                {"path": str(path_2), "layer": "pipes"},
            ]
        )


def test_read_pipe_layers_reprojects_to_working_crs(tmp_path) -> None:
    path_1 = tmp_path / "pipes_1.gpkg"
    path_2 = tmp_path / "pipes_2.gpkg"
    _write_pipe_layer(path_1, "pipes", crs="EPSG:32721")
    _write_pipe_layer(path_2, "pipes", crs="EPSG:4326")

    combined = read_pipe_layers(
        [
            {"path": str(path_1), "layer": "pipes"},
            {"path": str(path_2), "layer": "pipes"},
        ],
        working_crs="EPSG:32721",
    )

    assert len(combined) == 2
    assert combined.crs == "EPSG:32721"
    assert combined["_source_crs"].tolist() == ["EPSG:32721", "EPSG:4326"]


def test_read_pipe_layers_rejects_non_projected_working_crs(tmp_path) -> None:
    path_1 = tmp_path / "pipes_1.gpkg"
    _write_pipe_layer(path_1, "pipes", crs="EPSG:32721")

    with pytest.raises(ConfigurationError, match="projected"):
        read_pipe_layers(
            [{"path": str(path_1), "layer": "pipes"}],
            working_crs="EPSG:4326",
        )
