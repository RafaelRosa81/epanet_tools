# GIS data contract

This document defines the expected input data for the first `epanet_tools` workflows.

## Pipe layers

Pipe layers may be provided as Shapefile, GeoPackage or GeoJSON.

Required properties:

- Geometry type: `LineString`. `MultiLineString` support will be implemented through explicit explode/normalization.
- CRS: projected CRS with metric units. Geographic CRS in degrees must fail validation unless a safe reprojection target is supplied.
- Length: calculated from geometry in the working CRS, not trusted blindly from an attribute field.

Optional pipe attributes:

| Internal field | Typical GIS field | Required for final INP |
|---|---|---|
| `source_id` | `id`, `fid`, `codigo` | no |
| `diameter_mm` | `diametro`, `dn`, `diameter` | yes |
| `roughness` | `rugosidad`, `roughness`, `c` | yes |
| `material` | `material` | no |
| `status` | `estado`, `status` | yes, with default |
| `minor_loss` | `minor_loss`, `km` | yes, with default |

Missing hydraulic fields are allowed during topology validation but must be reported before `.inp` export.

## DEM/DTM

The DEM/DTM must:

- be georeferenced;
- cover all generated hydraulic nodes;
- have documented vertical units;
- expose `nodata` consistently.

The first elevation sampling method will be `nearest`; other methods may be added later.

## Auxiliary layers

Future workflows may accept:

- sector polygons;
- parcels;
- demand points;
- valves;
- tanks;
- reservoirs;
- pumps.

These should be introduced through explicit adapters and field mappings, not as untyped generic attributes.

## Topology rules

Important assumptions must always be explicit in configuration:

- snapping tolerance in metres;
- whether intersections represent hydraulic connections;
- whether zero-length geometries are dropped or only reported;
- whether duplicate pipes are removed, merged or only reported.
