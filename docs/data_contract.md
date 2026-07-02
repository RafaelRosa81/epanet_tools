# GIS data contract

This document defines the expected input data for the first `epanet_tools` workflows.

## Pipe layers

Pipe layers may be provided as Shapefile, GeoPackage or GeoJSON. A project may define one or several pipe layers. Multiple pipe layers are read and combined into one internal network layer before validation and later topology construction.

Required properties:

- Geometry type: `LineString`. `MultiLineString` is currently reported and will later be normalized through explicit explode rules.
- CRS: all pipe layers must have a defined CRS.
- CRS compatibility: all pipe layers in the same validation workflow must currently use the same CRS. The software must not silently mix coordinate systems.
- Projected CRS: metric projected CRS is required for length, snapping and tolerance calculations.
- Length: calculated from geometry in the layer CRS, not trusted blindly from an attribute field.

The source layers are never overwritten. When layers are combined, each feature keeps traceability fields:

| Field | Meaning |
|---|---|
| `_source_order` | order of the input layer in the YAML config |
| `_source_path` | source file path |
| `_source_layer` | source layer name, when applicable |
| `_source_index` | original feature index before combining layers |

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
