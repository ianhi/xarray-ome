# xarray-ome

Read and write OME-Zarr files with xarray.

This package provides a simple interface for working with OME-Zarr (OME-NGFF) files in xarray, with support for:

- Lazy loading of multiscale image pyramids
- Physical coordinates from OME-NGFF transformations
- Remote data access (HTTP, S3)
- Round-trip preservation of metadata

Built on [ngff-zarr](https://ngff-zarr.readthedocs.io/) for robust OME-NGFF support.

## Installation

### From PyPI (when released)

```bash
pip install xarray-ome
```

### Local development install

```bash
git clone https://github.com/your-org/xarray-ome.git
cd xarray-ome
uv sync
```

This will install the package in editable mode with all development dependencies.

## Quick Start

```python
from xarray_ome import open_ome_datatree, open_ome_dataset

# Open entire multiscale pyramid as DataTree
dt = open_ome_datatree("path/to/data.ome.zarr")

# Open single resolution level as Dataset
ds = open_ome_dataset("path/to/data.ome.zarr", resolution=0)

# Works with remote URLs - try with real sample data!
url = "https://uk1s3.embassy.ebi.ac.uk/idr/zarr/v0.4/idr0062A/6001240.zarr"
ds = open_ome_dataset(url)
print(ds)  # No download required!
```

### Try it now

You can immediately try xarray-ome with publicly available OME-NGFF sample data from the Image Data Resource (IDR):

```python
from xarray_ome import open_ome_dataset

# Load remote sample data (4D: 2 channels × 236 z-slices × 275 y × 271 x)
url = "https://uk1s3.embassy.ebi.ac.uk/idr/zarr/v0.4/idr0062A/6001240.zarr"
ds = open_ome_dataset(url)

# Process a subset - only downloads what you need!
result = ds["image"].sel(c=0).isel(z=0).compute()
```

More sample datasets: [OME-NGFF Samples](https://idr.github.io/ome-ngff-samples/)

## Documentation

Full documentation is available at [link-when-hosted].

### Building documentation locally

```bash
# Install documentation dependencies
uv sync --group docs

# Build HTML documentation
uv run sphinx-build docs docs/_build/html

# View the built docs
open docs/_build/html/index.html
```

### Live documentation editing

For development, use sphinx-autobuild to automatically rebuild docs on changes:

```bash
# Install documentation dependencies (includes sphinx-autobuild)
uv sync --group docs

# Start autobuild server
uv run sphinx-autobuild docs docs/_build/html

# Open browser to http://127.0.0.1:8000
# Docs will auto-reload when you save changes
```

The autobuild server watches for changes to documentation files and automatically rebuilds and refreshes your browser.

## Development

### Setup

```bash
# Clone the repository
git clone https://github.com/your-org/xarray-ome.git
cd xarray-ome

# Install with development dependencies
uv sync --group dev

# Install pre-commit hooks
uv run pre-commit install
```

### Running tests

```bash
# Run all tests (fast + slow integration tests)
uv run pytest

# Run only fast tests (skip network-dependent integration tests)
uv run pytest -m "not slow"

# Run only integration tests with real IDR data
uv run pytest -m slow
```

### Type checking

```bash
uv run mypy xarray_ome
```

### Code formatting

```bash
uv run ruff check --fix
```

## License

[License info]

## Contributing

See [CONTRIBUTING.md](docs/contributing.md) for development guidelines.
