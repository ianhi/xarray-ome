
# Xarray-OME

This package provides an Xarray Backend (https://docs.xarray.dev/en/stable/internals/how-to-add-new-backend.html) that allows one line opening of an 
OME-Zarr file (https://ngff.openmicroscopy.org/0.5/index.html) with `xr.open_ome("path/to/a/ome.zarr")` which will result in opening an xr.DataTree of the whole file. With lazy loading of the data.

- We will also support opening a single scale level in an ome-zarr group as an xr.Dataset
- Initially we will provide different explicit functions for this (e.g. open as dataset, open as datatree)
- After the initial implementation we will consider the option to have a function that magically "does the right thing" regarding what object it returns.


