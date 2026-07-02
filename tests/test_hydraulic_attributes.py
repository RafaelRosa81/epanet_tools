import geopandas as gpd
import pandas as pd
from shapely.geometry import LineString

from epanet_tools.hydraulic.attributes import apply_hydraulic_attributes


def test_apply_hydraulic_attributes_uses_existing_category_then_defaults() -> None:
    pipes = gpd.GeoDataFrame(
        {
            "clase": ["PRIMARIA", "SECUNDARIA", "NO_DEFINIDA"],
            "diameter_mm": [160, pd.NA, pd.NA],
            "geometry": [
                LineString([(0, 0), (1, 0)]),
                LineString([(1, 0), (2, 0)]),
                LineString([(2, 0), (3, 0)]),
            ],
        },
        crs="EPSG:32719",
    )
    config = {
        "pipe_defaults": {
            "diameter_mm": 63,
            "roughness": 140,
            "minor_loss": 0,
            "status": "OPEN",
            "material": "PEAD",
        },
        "category_field": "clase",
        "categories": {
            "PRIMARIA": {
                "diameter_mm": 110,
                "roughness": 140,
                "minor_loss": 0,
                "status": "OPEN",
                "material": "PEAD",
            },
            "SECUNDARIA": {
                "diameter_mm": 75,
                "roughness": 140,
                "minor_loss": 0,
                "status": "OPEN",
                "material": "PVC",
            },
        },
    }

    assigned, report = apply_hydraulic_attributes(pipes, config)

    assert assigned["diameter_mm"].tolist() == [160, 75.0, 63.0]
    assert assigned["material"].tolist() == ["PEAD", "PVC", "PEAD"]
    assert assigned["status"].tolist() == ["OPEN", "OPEN", "OPEN"]
    assert report.pipe_count == 3
    assert report.undefined_category_count == 1
    assert report.missing_required_count == 0
    assert report.invalid_value_count == 0
