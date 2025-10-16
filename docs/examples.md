# Examples

This section provides executable examples demonstrating various features of xarray-ome. All examples use real OME-NGFF sample data from the [Image Data Resource (IDR)](https://idr.openmicroscopy.org/).

```{note}
These examples are executed automatically during documentation builds, ensuring they always work with the latest version of xarray-ome.
```

## Featured Sample Dataset

All examples use this publicly accessible dataset:

- **URL**: `https://uk1s3.embassy.ebi.ac.uk/idr/zarr/v0.4/idr0062A/6001240.zarr`
- **Source**: [idr0062A - Drug treatment study](https://idr.openmicroscopy.org/webclient/?show=screen-1951)
- **Dimensions**: 4D (2 channels × 236 z-slices × 275 y × 271 x)
- **Channels**: LaminB1, Dapi
- **Resolution levels**: 3 (multiscale pyramid)
- **OME-NGFF version**: 0.4

## Example Notebooks

::::{grid} 2

:::{grid-item-card} Basic Usage
:link: examples/basic_usage
:link-type: doc

Learn the fundamentals of opening and working with OME-Zarr files.

- Opening as Dataset and DataTree
- Exploring coordinates and metadata
- Lazy loading with Dask
- Selecting subsets
:::

:::{grid-item-card} Channel Labels
:link: examples/channel_labels
:link-type: doc

Work with channel labels from OME metadata.

- Accessing channel names
- Selecting by channel label
- Physical coordinates and units
- Metadata inspection
:::

::::

## Running Examples Locally

All examples can be run from the command line or in a Jupyter notebook:

### As Python Scripts

The examples are also available as standalone Python scripts in the `examples/` directory:

```bash
# Using uv (recommended)
uv run python examples/idr_channel_labels.py

# Or with standard Python
python examples/idr_channel_labels.py
```

### In Jupyter

Convert any example to a Jupyter notebook:

```bash
# Install jupytext if needed
uv add --dev jupytext

# Convert MyST markdown to notebook
jupytext --to ipynb docs/examples/basic_usage.md

# Open in Jupyter
jupyter notebook basic_usage.ipynb
```

## Additional Resources

- Browse more sample datasets: [OME-NGFF Samples](https://idr.github.io/ome-ngff-samples/)
- Complete API reference: [API Documentation](api.md)
- Usage guide: [Usage Guide](usage.md)

```{toctree}
:maxdepth: 1
:hidden:

examples/basic_usage
examples/channel_labels
```
