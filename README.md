# epanet_tools

Python toolkit for building, editing, validating and analysing EPANET models from GIS data.

The project starts from geospatial inputs such as pipe layers, DEM/DTM rasters and optional demand, sector or asset layers, and aims to generate reproducible EPANET `.inp` models together with QA reports and GIS outputs for QGIS/QEPANET workflows.

## Main goals

- Read pipes from Shapefile, GeoPackage or GeoJSON layers.
- Combine several pipe layers into one internal network while preserving source traceability.
- Validate and optionally correct network topology.
- Detect pipe endpoints, intersections and hydraulic junctions.
- Assign deterministic IDs to nodes and links.
- Sample node elevations from a DEM/DTM.
- Compute pipe lengths from projected geometries.
- Attach hydraulic attributes such as diameter, roughness, material, status and demand.
- Export EPANET-compatible `.inp` files.
- Support bulk editing, thematic maps, result import and future QGIS integration.

## Repository status

This repository is in the architecture and bootstrap stage. The first implementation milestone is intentionally limited to GIS network validation before automatic correction or `.inp` export.

## Package layout

```text
src/epanet_tools/
├── io/              # GIS, raster and EPANET input/output
├── topology/        # topology validation, snapping, intersections and graph tools
├── terrain/         # DEM/DTM elevation sampling
├── hydraulic/       # hydraulic model schema and EPANET model building
├── editing/         # bulk and spatial editing rules
├── analysis/        # network and hydraulic analysis utilities
├── visualization/   # GIS outputs and QGIS styles
└── workflows/       # end-to-end reproducible workflows
```

## Installation

### Conda environment

```bash
conda env create -f environment.yml
conda activate epanet_tools
pip install -e .
```

### Development checks

```bash
pytest
ruff check .
ruff format .
mypy src
```

## First validation workflow

```bash
python -m epanet_tools.workflows.validate_network --config config/validate_network_example.yml
```

The initial workflow reads one or several pipe layers, validates CRS/geometries and exports QA outputs without modifying source data.

Generated outputs:

```text
outputs/<run_name>/report/<run_name>_validation.json
outputs/<run_name>/report/<run_name>_validation.csv
outputs/<run_name>/gis/<run_name>_network.gpkg
outputs/<run_name>/gis/<run_name>_working.gpkg
```

Open `<run_name>_network.gpkg` in QGIS and load `pipes_combined` to inspect the network interpreted by the software.

Open `<run_name>_working.gpkg` to inspect the standard working structure for the EPANET workflow:

```text
pipes_raw
pipes_clean
junctions
reservoirs
tanks
pumps
valves
demands
sectors
topology_errors
topology_report
```

At this stage `pipes_raw` is populated from the combined source layers; the other layers are empty placeholders for later processing steps.

## Documentation

- [`docs/architecture.md`](docs/architecture.md)
- [`docs/roadmap.md`](docs/roadmap.md)
- [`docs/data_contract.md`](docs/data_contract.md)
- [`docs/development.md`](docs/development.md)
