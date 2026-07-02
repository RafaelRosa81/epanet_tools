# Development guide

## Environment

```bash
conda env create -f environment.yml
conda activate epanet_tools
pip install -e .
```

## Checks

Run tests:

```bash
pytest
```

Run linting and formatting:

```bash
ruff check .
ruff format .
```

Run type checks:

```bash
mypy src
```

## Development principles

- Prefer small, tested functions over large scripts.
- Keep GIS I/O, topology logic and EPANET serialization separated.
- Never silently overwrite source GIS files.
- Every automatic correction must be configurable and reportable.
- Use deterministic IDs whenever possible.
- Keep test datasets synthetic, small and safe to version.

## Suggested implementation order

1. Configuration loader.
2. Vector pipe reader.
3. CRS and geometry validation.
4. Validation report model and exporters.
5. Endpoint extraction and intersection detection.
6. Synthetic test datasets.
7. Topology correction and graph construction.
8. DEM sampling.
9. Minimal INP writer.
