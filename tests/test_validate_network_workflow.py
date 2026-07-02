import json

import geopandas as gpd
import yaml
from shapely.geometry import LineString

from epanet_tools.workflows.validate_network import validate_network


def test_validate_network_workflow_reads_vector_layer_and_writes_reports(tmp_path) -> None:
    vector_path = tmp_path / "pipes.gpkg"
    outdir = tmp_path / "outputs"
    config_path = tmp_path / "config.yml"

    pipes = gpd.GeoDataFrame(
        {"id": [1], "geometry": [LineString([(0, 0), (10, 0)])]},
        crs="EPSG:32721",
    )
    pipes.to_file(vector_path, layer="pipes", driver="GPKG")

    config = {
        "pipeline": "validate_network",
        "name": "demo",
        "outdir": str(outdir),
        "inputs": {"pipes": [{"path": str(vector_path), "layer": "pipes"}]},
        "topology": {"explode_multilines": True},
    }
    config_path.write_text(yaml.safe_dump(config), encoding="utf-8")

    result = validate_network(config_path)

    assert result.status == "ok"
    assert result.feature_count == 1
    assert result.has_errors is False
    assert result.report_paths["json"].exists()
    assert result.report_paths["csv"].exists()

    payload = json.loads(result.report_paths["json"].read_text(encoding="utf-8"))
    assert payload["feature_count"] == 1
    assert payload["has_errors"] is False
