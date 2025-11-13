# Xarray-OME

This package provides an Xarray Backend (<https://docs.xarray.dev/en/stable/internals/how-to-add-new-backend.html>) that allows one line opening of an
OME-Zarr file (<https://ngff.openmicroscopy.org/0.5/index.html>) with `xr.open_ome("path/to/a/ome.zarr")` which will result in opening an xr.DataTree of the whole file. With lazy loading of the data.

- We will also support opening a single scale level in an ome-zarr group as an xr.Dataset
- Initially we will provide different explicit functions for this (e.g. open as dataset, open as datatree)
- After the initial implementation we will consider the option to have a function that magically "does the right thing" regarding what object it returns.

## Architecture

This library uses **ngff-zarr** (<https://ngff-zarr.readthedocs.io/>) as the foundation for OME-Zarr I/O operations. The ngff-zarr library handles:

- Reading and parsing OME-NGFF metadata (v0.1-v0.5)
- Zarr store interactions
- Metadata validation
- Multi-backend support (zarr-python, tensorstore)

**xarray-ome focuses on the integration layer**, providing:

- Conversion between OME-NGFF coordinate transformations and xarray coordinates
- DataTree/Dataset construction from OME-Zarr structures
- Round-trip preservation of OME metadata through xarray attrs
- Xarray backend implementation

```text
User Code
    ↓
xarray-ome API (open_ome_datatree, open_ome_dataset)
    ↓
Coordinate Translation Layer (our core logic)
    ↓
ngff-zarr (handles OME-Zarr spec, zarr I/O, metadata)
    ↓
zarr-python / tensorstore
    ↓
Storage (local, S3, etc.)
```

## Roundtripping

We will support roundtripping an ome-zarr through xarray. This will require storing the ome-metadata in the xarray attrs and using it our custom write function

## Metadata Handling

For inspiration on handling ome-metadata we will look at this repo: <https://github.com/JaneliaSciComp/xarray-ome-ngff>

From the author of that library ([@d-v-b](https://github.com/d-v-b))
> in particular, these two functions are important:
> <https://github.com/JaneliaSciComp/xarray-ome-ngff/blob/19bc86e7a38e00e7419c5e5b14fea289aee63ebd/src/xarray_ome_ngff/v04/multiscale.py#L118-L123>
> <https://github.com/JaneliaSciComp/xarray-ome-ngff/blob/19bc86e7a38e00e7419c5e5b14fea289aee63ebd/src/xarray_ome_ngff/v04/multiscale.py#L219-L224>
> that's the core logic for going between xarray coordinates and ome-zarr 0.4 transforms

## Implementation Staging

1. ✅ Support OME-NGFF v0.1-v0.5 (via ngff-zarr)
2. ✅ Reading a whole store as a datatree (using ngff-zarr for I/O)
3. ✅ Reading a group or array as a dataset
4. ✅ Support writing back to disk (using ngff-zarr for I/O - v0.4-v0.5)
5. ✅ Integrate as an Xarray backend
6. ✅ Support for older OME spec versions (automatically via ngff-zarr)

**Status**: All planned features implemented!

**Note**: We support all OME-NGFF versions (v0.1-v0.5) for reading through ngff-zarr.
Writing is supported for v0.4 and v0.5 (the current standard versions).

## Recent Enhancements

Beyond the original plan, the following enhancements have been added:

- **Channel label support**: Automatically extracts channel names from OME metadata (`omero.channels[].label`) and uses them as xarray coordinate values
- **String dtype coordinates**: Channel coordinates use string dtype (instead of object) for better type safety
- **Executable documentation**: MyST-NB integration allows documentation examples to execute during build
- **Read the Docs**: Configured with uv for dependency management
- **Comprehensive metadata handling**: All relevant OME-NGFF metadata is preserved in xarray attrs for round-tripping
