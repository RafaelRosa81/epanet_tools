# epanet_tools

Python toolkit for building, editing, validating and analysing EPANET models from GIS data.

The project starts from geospatial inputs such as pipe layers, DEM/DTM rasters and optional demand, sector or asset layers, and aims to generate reproducible EPANET `.inp` models together with QA reports and GIS outputs for QGIS/QEPANET workflows.

## Main goals

- Read pipes from Shapefile, GeoPackage or GeoJSON layers.
- Combine several pipe layers into one internal network while preserving source traceability.
- Reproject source layers in memory to an explicit projected working CRS.
- Validate and optionally correct network topology.
- Detect pipe endpoints, intersections and hydraulic junctions.
- Assign deterministic IDs to nodes and links.
- Sample node elevations from a DEM/DTM.
- Compute pipe lengths from projected geometries.
- Attach hydraulic attributes such as diameter, roughness, material, status and demand.
- Export EPANET-compatible `.inp` files.
- Support bulk editing, thematic maps, result import and future QGIS integration.

## Repository status

The current implementation validates GIS pipe inputs, writes a combined network layer and generates a first `pipes_clean` layer by snapping near pipe endpoints. It also includes an initial `epanet_postprocess` package for reading standard EPANET 2.x `.rpt` time-series reports, graphing results, generating summaries, exporting tables and running hydraulic diagnostics.

## Package layout

```text
src/
├── epanet_tools/
│   ├── io/
│   ├── topology/
│   ├── terrain/
│   ├── hydraulic/
│   ├── editing/
│   ├── analysis/
│   ├── visualization/
│   └── workflows/
└── epanet_postprocess/
    ├── reader.py
    ├── plots.py
    ├── summary.py
    ├── diagnostics.py
    └── export.py
```

## Installation

```bash
conda env create -f environment.yml
conda activate epanet_tools
pip install -e .
```

For Excel exports:

```bash
pip install -e ".[excel]"
```

## EPANET result postprocessing

`epanet_postprocess.read_rpt()` recognizes the standard EPANET 2.x blocks named `Node Results at <time> Hrs:` and `Link Results at <time> Hrs:`, including page continuations. It returns normalized `pandas` tables:

```python
from epanet_postprocess.reader import read_rpt
from epanet_postprocess.plots import plot_link_flows
from epanet_postprocess.diagnostics import check_low_pressures

results = read_rpt("palo_alto_secundarias.rpt")

plot_link_flows(
    results,
    links=["P000008", "P000009", "P000016"],
    output="outputs/flows_selected_links.png",
)

print(check_low_pressures(results, min_pressure=10.0))
```

The returned structure is:

```python
{
    "nodes": nodes_dataframe,
    "links": links_dataframe,
    "metadata": metadata_dictionary,
}
```

The reader preserves the units reported by EPANET. Confirm the unit system from the source report before setting hydraulic thresholds. Negative flow records are retained because they usually describe flow direction relative to the link orientation, rather than an error.

See `examples/example_postprocess.py` for the complete workflow, including charts, diagnostic tables and Excel export.

## Development checks

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

The workflow reads one or several pipe layers, reprojects them in memory to `spatial.working_crs` when provided, validates CRS/geometries and exports QA outputs without modifying source data.

Generated outputs:

```text
outputs/<run_name>/report/<run_name>_validation.json
outputs/<run_name>/report/<run_name>_validation.csv
outputs/<run_name>/gis/<run_name>_network.gpkg
outputs/<run_name>/gis/<run_name>_working.gpkg
```

Open `<run_name>_network.gpkg` in QGIS and load `pipes_combined` to inspect the network interpreted by the software.

Open `<run_name>_working.gpkg` to inspect:

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

`pipes_raw` is the combined source network. `pipes_clean` is generated from it by snapping pipe endpoints within `snap_tolerance_m`. The remaining layers are placeholders for later processing steps.

## Documentation

- [`docs/architecture.md`](docs/architecture.md)
- [`docs/roadmap.md`](docs/roadmap.md)
- [`docs/data_contract.md`](docs/data_contract.md)
- [`docs/development.md`](docs/development.md)
