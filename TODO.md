# TODO List

## High Priority

### Zarr Backend Fallback

Currently, when `xr.open_dataset(..., engine="ome-zarr")` is called on a regular (non-OME-NGFF) zarr file, it will raise an error. We should detect this case and automatically fall back to xarray's native zarr backend.

**Implementation notes:**

- The backend's `open_dataset()` and `open_datatree()` already check `_detect_store_type()`
- They try to fall back when `store_type == "unknown"`
- However, the fallback currently calls `open_ome_dataset()` which also checks and raises ValueError
- Need to either:
  1. Catch ValueError in backend and retry with zarr engine
  2. Pass a flag to `open_ome_dataset()` to skip the check
  3. Restructure so backend does fallback before calling `open_ome_dataset()`

**Related code:**

- `xarray_ome/backend.py`: Backend entry point with fallback logic
- `xarray_ome/reader.py`: `open_ome_dataset()` and `open_ome_datatree()` with detection
- `xarray_ome/_store_utils.py`: `_detect_store_type()` function

## Medium Priority

### Add working code example at docs homepage start

The docs homepage should have a concrete working example right at the start that users can copy-paste and run immediately.

### HCS Plate Structure Support

Add support for High Content Screening (HCS) plate/well structures from OME-NGFF.

**References:**

- <https://ngff.openmicroscopy.org/latest/#hcs-layout>

### Performance Optimizations

- Benchmark and optimize coordinate transformation
- Consider caching metadata parsing
- Profile large file opening

### Integration with Visualization Tools

- Examples with matplotlib/napari
- Helper functions for common viz patterns

## Low Priority

### Additional Metadata Validation Options

- More granular validation controls
- Custom validation rules
- Better error messages for invalid metadata

### Time Label Support

Infrastructure is ready in `transforms_to_coords()` with `time_labels` parameter, but OME-NGFF spec doesn't currently define standard time labels location (unlike channel labels in `omero.channels[].label`).

Wait for spec extension before implementing.
