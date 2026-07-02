# Roadmap

## Milestone 0 — Bootstrap and architecture

Status: started.

Deliverables:

- package skeleton;
- reproducible Conda environment;
- quality tooling configuration;
- architecture documentation;
- data contract;
- first unit tests.

Acceptance criterion: repository can be installed in editable mode and tests can be executed.

## Milestone 1 — GIS network validation

Scope:

- read pipe layers with GeoPandas;
- validate CRS, geometry type, empty geometries and length;
- detect line endpoints;
- detect basic intersections;
- produce validation issues as JSON/CSV and optional GIS layers.

Acceptance criterion: a pipe layer produces a reproducible QA report without modifying source data.

## Milestone 2 — Topology construction

Scope:

- optional snapping;
- optional splitting at hydraulic intersections;
- deterministic junction and pipe IDs;
- from/to node assignment;
- NetworkX graph construction;
- disconnected component detection.

Acceptance criterion: a clean GIS network becomes a coherent node/link topology.

## Milestone 3 — Terrain and minimal INP export

Scope:

- sample node elevations from DEM/DTM;
- assign pipe lengths and hydraulic defaults;
- export minimal EPANET sections: `[JUNCTIONS]`, `[PIPES]`, `[COORDINATES]`, `[VERTICES]`, `[OPTIONS]`.

Acceptance criterion: a simple model opens in EPANET/QEPANET and preserves GIS geometry.

## Milestone 4 — Bulk hydraulic editing

Scope:

- update diameter, roughness, material, status and demand by rules;
- filter by attributes;
- select by sector/polygon;
- audit every change.

Acceptance criterion: a YAML rule updates only selected elements and produces a change log.

## Milestone 5 — Extended EPANET elements and simulation

Scope:

- reservoirs, tanks, pumps, valves, patterns and demand allocation;
- evaluate integration with an EPANET Python engine or toolkit;
- import simulation results.

Acceptance criterion: workflows support complete executable models, not only pipes and junctions.

## Milestone 6 — Analysis, maps and QGIS integration

Scope:

- thematic maps of pressure, flow, velocity and headloss;
- critical element identification;
- sectorization utilities;
- QGIS styles and future plugin layer.

Acceptance criterion: results are directly useful in QGIS/QEPANET workflows.
