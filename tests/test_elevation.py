import numpy as np
import geopandas as gpd
import rasterio
from rasterio.transform import from_origin
from shapely.geometry import Point

from epanet_tools.terrain.elevation import sample_junction_elevations


def test_sample_junction_elevations_from_dem(tmp_path) -> None:
    dem_path = tmp_path / "dem.tif"
    data = np.array([[10.0, 11.0], [20.0, 21.0]], dtype="float32")
    transform = from_origin(0.0, 2.0, 1.0, 1.0)
    with rasterio.open(
        dem_path,
        "w",
        driver="GTiff",
        height=2,
        width=2,
        count=1,
        dtype="float32",
        crs="EPSG:32719",
        transform=transform,
    ) as dataset:
        dataset.write(data, 1)

    junctions = gpd.GeoDataFrame(
        {"node_id": ["J000001", "J000002"], "geometry": [Point(0.5, 1.5), Point(1.5, 0.5)]},
        crs="EPSG:32719",
    )

    sampled, report = sample_junction_elevations(junctions, dem_path)

    assert sampled["elevation_m"].tolist() == [10.0, 21.0]
    assert report.node_count == 2
    assert report.sampled_count == 2
    assert report.missing_count == 0
    assert report.dem_crs == "EPSG:32719"
