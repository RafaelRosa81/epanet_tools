# GIS data contract

This document defines the expected input data for the first `epanet_tools` workflows.

## Pipe layers

Pipe layers may be provided as Shapefile, GeoPackage or GeoJSON. A project may define one or several pipe layers. Multiple pipe layers are read and combined into one internal network layer before validation and later topology construction.

Required properties:

- Geometry type: `LineString`. `MultiLineString` is currently reported and will later be normalized through explicit explode rules.
- CRS: all pipe layers must have a defined CRS.
- Working CRS: if `spatial.working_crs` is defined in the YAML configuration, every pipe layer is reprojected in memory to that CRS before combining layers.
- CRS compatibility without working CRS: if `spatial.working_crs` is not defined, all pipe layers must already use the same CRS.
- Projected CRS: the working CRS must be projected. Length, snapping and tolerance calculations must not be performed in a geographic CRS.
- Length: calculated from geometry in the working CRS, not trusted blindly from an attribute field.

The source layers are never overwritten. When layers are combined, each feature keeps traceability fields:

| Field | Meaning |
|---|---|
| `_source_order` | order of the input layer in the YAML config |
| `_source_path` | source file path |
| `_source_layer` | source layer name, when applicable |
| `_source_index` | original feature index before combining layers |
| `_source_crs` | original CRS before optional in-memory reprojection |

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
