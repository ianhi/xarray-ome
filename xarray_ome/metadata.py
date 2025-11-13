"""Bidirectional conversion between OME-NGFF metadata and xarray structures.

This module handles the conversion of OME-NGFF metadata to xarray coordinates
and attributes, and the reverse conversion for writing.

Design Principle:
-----------------
Metadata that can be properly represented in xarray's data model should be
stored there (e.g., coordinates, dimension names), not duplicated in attrs.
Attrs should only contain metadata that has no native xarray representation.

OME-NGFF Metadata Mapping:
--------------------------
1. **Stored as xarray coordinates**:
   - Axis scales/translations -> coordinate arrays (via transforms_to_coords)
   - Channel labels (omero.channels[].label) -> channel coordinate values
   - Time labels (if present) -> time coordinate values

2. **Stored as xarray dimension names**:
   - Axis names (axes[].name) -> Dataset.dims

3. **Stored in attrs** (no native xarray representation):
   - Axis types (axes[].type)
   - Axis units (axes[].unit) - stored for reference, also derivable from coords
   - Axis orientations (axes[].orientation)
   - Image name
   - OME-NGFF version
   - Multiscale paths/resolutions
   - Channel colors (omero.channels[].color)
   - Channel window settings (omero.channels[].window)
   - Full metadata dict (for complete round-tripping)

Round-Tripping:
---------------
The full OME-NGFF metadata dict is always preserved in attrs to ensure perfect
round-tripping, even if we don't fully understand all metadata fields.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import xarray as xr


def metadata_to_xarray_attrs(metadata_dict: dict[str, Any]) -> dict[str, Any]:
    """Convert OME-NGFF metadata to xarray attrs (non-coordinate metadata only).

    This extracts metadata that cannot be represented as xarray coordinates
    or dimension names. Coordinate-based metadata (scales, translations,
    channel labels) should be handled separately via transforms_to_coords().

    Parameters
    ----------
    metadata_dict : dict
        Full OME-NGFF metadata dictionary

    Returns
    -------
    dict
        Dictionary of attributes to add to Dataset/DataTree attrs
        Does NOT include coordinate-based information

    Examples
    --------
    >>> metadata = {
    ...     'name': 'image',
    ...     'version': '0.4',
    ...     'axes': [
    ...         {'name': 'c', 'type': 'channel'},
    ...         {'name': 'z', 'type': 'space', 'unit': 'micrometer'},
    ...     ],
    ...     'omero': {
    ...         'channels': [
    ...             {'label': 'DAPI', 'color': '0000FF'},
    ...         ],
    ...     },
    ... }
    >>> attrs = metadata_to_xarray_attrs(metadata)
    >>> attrs['ome_name']
    'image'
    >>> attrs['ome_axes_types']
    ['channel', 'space']
    """
    attrs = {}

    # Basic metadata
    if "name" in metadata_dict:
        attrs["ome_name"] = metadata_dict["name"]
    if "version" in metadata_dict:
        attrs["ome_version"] = metadata_dict["version"]

    # Axes information (types, units, orientations - not names, those are dims)
    if "axes" in metadata_dict:
        axes = metadata_dict["axes"]

        # Axis types (e.g., 'channel', 'space', 'time')
        attrs["ome_axes_types"] = [ax.get("type") for ax in axes]

        # Units (if present) - maps axis name to unit
        units = {ax["name"]: ax.get("unit") for ax in axes if ax.get("unit")}
        if units:
            attrs["ome_axes_units"] = units

        # Orientations (if present) - maps axis name to orientation
        orientations = {ax["name"]: ax.get("orientation") for ax in axes if ax.get("orientation")}
        if orientations:
            attrs["ome_axes_orientations"] = orientations

    # Multiscale dataset information
    if "datasets" in metadata_dict:
        datasets = metadata_dict["datasets"]
        attrs["ome_multiscale_paths"] = [ds["path"] for ds in datasets]
        attrs["ome_num_resolutions"] = len(datasets)

    # OMERO metadata (channel colors, rendering settings)
    # Note: channel labels are NOT stored here - they go in coordinates
    if "omero" in metadata_dict and metadata_dict["omero"]:
        omero = metadata_dict["omero"]

        # Channel information (colors and rendering only)
        if "channels" in omero:
            channels = omero["channels"]

            # Channel colors (hex RGB)
            colors = [ch.get("color") for ch in channels]
            if any(c is not None for c in colors):
                attrs["ome_channel_colors"] = colors

            # Window settings (rendering)
            windows = [ch.get("window") for ch in channels if "window" in ch]
            if windows:
                attrs["ome_channel_windows"] = windows

    # Always keep full metadata for complete round-tripping
    attrs["ome_ngff_metadata"] = metadata_dict

    return attrs


def xarray_to_metadata(
    dataset: xr.Dataset,
    *,
    preserve_original: bool = True,
) -> dict[str, Any]:
    """Convert xarray Dataset back to OME-NGFF metadata dictionary.

    Reconstructs OME-NGFF metadata from xarray coordinates, dimensions,
    and attributes. Ensures round-trip fidelity.

    Parameters
    ----------
    dataset : xr.Dataset
        Dataset to extract metadata from
    preserve_original : bool, default True
        If True and 'ome_ngff_metadata' is in attrs, use that as the base
        and only update fields that might have changed (for perfect round-trip).
        If False, reconstruct metadata entirely from xarray structure.

    Returns
    -------
    dict
        OME-NGFF metadata dictionary ready for writing

    Notes
    -----
    When preserve_original=True (default), this ensures perfect round-tripping
    by preserving all metadata fields we don't actively use, even if we don't
    understand them.

    Examples
    --------
    >>> import xarray as xr
    >>> import numpy as np
    >>> ds = xr.Dataset({
    ...     'image': xr.DataArray(
    ...         np.zeros((2, 10, 10)),
    ...         dims=['c', 'y', 'x'],
    ...         coords={'c': ['DAPI', 'GFP']},
    ...     ),
    ... })
    >>> ds.attrs['ome_name'] = 'test'
    >>> ds.attrs['ome_version'] = '0.4'
    >>> metadata = xarray_to_metadata(ds, preserve_original=False)
    >>> metadata['name']
    'test'
    """
    # Start with original metadata if available and requested
    if preserve_original and "ome_ngff_metadata" in dataset.attrs:
        metadata = dict(dataset.attrs["ome_ngff_metadata"])
    else:
        metadata = {}

    # Update basic metadata from attrs
    if "ome_name" in dataset.attrs:
        metadata["name"] = dataset.attrs["ome_name"]
    if "ome_version" in dataset.attrs:
        metadata["version"] = dataset.attrs["ome_version"]

    # Reconstruct axes from dimensions and attrs
    # Get the first data variable to access dimensions
    first_var = next(iter(dataset.data_vars))
    data_array = dataset[first_var]

    axes = []
    for i, dim in enumerate(data_array.dims):
        axis = {"name": str(dim)}

        # Add type if available
        if "ome_axes_types" in dataset.attrs:
            axis_type = dataset.attrs["ome_axes_types"][i]
            if axis_type is not None:
                axis["type"] = axis_type

        # Add unit if available
        if "ome_axes_units" in dataset.attrs:
            units_dict = dataset.attrs["ome_axes_units"]
            if dim in units_dict:
                axis["unit"] = units_dict[dim]

        # Add orientation if available
        if "ome_axes_orientations" in dataset.attrs:
            orient_dict = dataset.attrs["ome_axes_orientations"]
            if dim in orient_dict:
                axis["orientation"] = orient_dict[dim]

        axes.append(axis)

    metadata["axes"] = axes

    # Reconstruct OMERO metadata if channel info present
    if "ome_channel_colors" in dataset.attrs or "ome_channel_windows" in dataset.attrs:
        omero = metadata.get("omero", {})
        channels = omero.get("channels", [])

        # Ensure we have enough channel entries
        if "c" in dataset.coords:
            n_channels = len(dataset.coords["c"])
            while len(channels) < n_channels:
                channels.append({})

            # Add channel labels from coordinates
            channel_coords = dataset.coords["c"].values
            if channel_coords.dtype.kind in ("U", "S", "O"):  # String types
                for i, label in enumerate(channel_coords):
                    channels[i]["label"] = str(label)

            # Add colors if present
            if "ome_channel_colors" in dataset.attrs:
                colors = dataset.attrs["ome_channel_colors"]
                for i, color in enumerate(colors):
                    if color is not None and i < len(channels):
                        channels[i]["color"] = color

            # Add windows if present
            if "ome_channel_windows" in dataset.attrs:
                windows = dataset.attrs["ome_channel_windows"]
                for i, window in enumerate(windows):
                    if window is not None and i < len(channels):
                        channels[i]["window"] = window

        omero["channels"] = channels
        metadata["omero"] = omero

    return metadata
