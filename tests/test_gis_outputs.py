import geopandas as gpd
from shapely.geometry import LineString

from epanet_tools.io.gis_outputs import write_combined_pipe_layer, write_working_geopackage


def test_geopackage_export_renames_reserved_geom_attribute(tmp_path) -> None:
    pipes = gpd.GeoDataFrame(
        {
            "geom": ["source geometry text"],
            "fid": ["source fid"],
            "geometry": [LineString([(0, 0), (1, 0)])],
        },
        geometry="geometry",
        crs="EPSG:32719",
    )

    network_path = write_combined_pipe_layer(pipes, tmp_path, "demo")
    working_path = write_working_geopackage(pipes, tmp_path, "demo")

    exported_network = gpd.read_file(network_path, layer="pipes_combined")
    exported_working = gpd.read_file(working_path, layer="pipes_raw")

    assert "source_geom" in exported_network.columns
    assert "source_fid" in exported_network.columns
    assert "geom" not in exported_network.columns
    assert "source_geom" in exported_working.columns
    assert "source_fid" in exported_working.columns
