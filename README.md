# epanet_tools

Python toolkit for building, editing, validating and analysing EPANET models from GIS data.

The project starts from geospatial inputs such as pipe layers, DEM/DTM rasters and optional demand, sector or asset layers, and aims to generate reproducible EPANET `.inp` models together with QA reports and GIS outputs for QGIS/QEPANET workflows.

## Main goals

- Read pipes from Shapefile, GeoPackage or GeoJSON layers.
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

## First planned workflow

```bash
python -m epanet_tools.workflows.validate_network --config config/validate_network_example.yml
```

The initial workflow will read a pipe layer, validate CRS/geometries/endpoints/intersections and export a QA report without modifying source data.

## Documentation

- [`docs/architecture.md`](docs/architecture.md)
- [`docs/roadmap.md`](docs/roadmap.md)
- [`docs/data_contract.md`](docs/data_contract.md)
- [`docs/development.md`](docs/development.md)
