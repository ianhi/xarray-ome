# Xarray-OME

This package provides an Xarray Backend (<https://docs.xarray.dev/en/stable/internals/how-to-add-new-backend.html>) that allows one line opening of an
OME-Zarr file (<https://ngff.openmicroscopy.org/0.5/index.html>) with `xr.open_ome("path/to/a/ome.zarr")` which will result in opening an xr.DataTree of the whole file. With lazy loading of the data.

- We will also support opening a single scale level in an ome-zarr group as an xr.Dataset
- Initially we will provide different explicit functions for this (e.g. open as dataset, open as datatree)
- After the initial implementation we will consider the option to have a function that magically "does the right thing" regarding what object it returns.

## Roundtripping

We will support roundtripping an ome-zarr through xarray. This will require storing the ome-metadata in the xarray attrs and using it our custom write function

## Metadata Handling

For inspiration on handling ome-metadata we will look at this repo: <https://github.com/JaneliaSciComp/xarray-ome-ngff>

From the author of that library ([@d-v=b](https://github.com/d-v-b))
> in particular, these two functions are important:
> <https://github.com/JaneliaSciComp/xarray-ome-ngff/blob/19bc86e7a38e00e7419c5e5b14fea289aee63ebd/src/xarray_ome_ngff/v04/multiscale.py#L118-L123>
> <https://github.com/JaneliaSciComp/xarray-ome-ngff/blob/19bc86e7a38e00e7419c5e5b14fea289aee63ebd/src/xarray_ome_ngff/v04/multiscale.py#L219-L224>
> that's the core logic for going between xarray coordinates and ome-zarr 0.4 transforms

## implementation staging

1. At first only support ome v0.5
2. Reading a whole store as a datatree
3. Reading a group or array as a dataset
4. Support writing back to disk
5. Support for older version of ome spec
