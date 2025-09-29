# Examples

This directory contains example scripts for testing xarray-ome functionality.

## Sample Data

Test with OME-NGFF sample files from: <https://idr.github.io/ome-ngff-samples/>

## Example Scripts

- `basic_reading.py` - Basic example of reading OME-Zarr files
- `inspect_structure.py` - Inspect the structure of OME-Zarr files

## Running Examples

```bash
# Run with uv
uv run python examples/basic_reading.py

# Or activate the environment
uv sync
source .venv/bin/activate
python examples/basic_reading.py
```
