"""Writing xarray DataTree and Dataset objects to OME-Zarr format."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ngff_zarr import to_multiscales, to_ngff_image, to_ngff_zarr  # type: ignore[import-untyped]

from .transforms import coords_to_transforms

if TYPE_CHECKING:
    from pathlib import Path

    import xarray as xr


def write_ome_dataset(
    dataset: xr.Dataset,
    path: str | Path,
    *,
    scale_factors: list[int] | None = None,
    chunks: int | tuple[int, ...] | None = None,
) -> None:
    """
    Write an xarray Dataset to OME-Zarr format.

    Parameters
    ----------
    dataset : xr.Dataset
        Dataset to write
    path : str or Path
        Output path for the OME-Zarr store
    scale_factors : list of int, optional
        Scale factors for multiscale pyramid generation.
        If None, writes only the provided resolution level.
        Example: [2, 4] creates two additional downsampled levels.
    chunks : int or tuple of int, optional
        Chunk sizes for the zarr array. If None, uses ngff-zarr defaults.

    Notes
    -----
    Converts xarray coordinates to OME-NGFF coordinate transformations.
    Extracts OME-NGFF metadata from dataset attrs if present.
    Uses ngff-zarr for the actual writing.

    Examples
    --------
    >>> ds = open_ome_dataset("input.ome.zarr")
    >>> write_ome_dataset(ds, "output.ome.zarr")

    >>> # With multiscale pyramid
    >>> write_ome_dataset(ds, "output.ome.zarr", scale_factors=[2, 4])
    """
    # Get the first data variable (assumes single image array)
    data_var_name = next(iter(dataset.data_vars))
    data_array = dataset[data_var_name]

    # Extract data and dimensions
    data = data_array.values
    dims = list(data_array.dims)

    # Convert coordinates back to OME-NGFF transformations
    scale, translation = coords_to_transforms(dataset)

    # Convert to string keys for ngff-zarr
    scale_dict = {str(k): float(v) for k, v in scale.items()}
    translation_dict = {str(k): float(v) for k, v in translation.items()}

    # Extract axes units and orientations if present
    axes_units = None
    if "ome_axes_units" in dataset.attrs:
        axes_units = dataset.attrs["ome_axes_units"]

    # Create NgffImage
    ngff_image = to_ngff_image(
        data,
        dims=dims,
        scale=scale_dict,
        translation=translation_dict,
        name=data_var_name,
        axes_units=axes_units,
    )

    # Create multiscales
    kwargs = {}
    if chunks is not None:
        kwargs["chunks"] = chunks

    if scale_factors is not None:
        multiscales = to_multiscales(ngff_image, scale_factors=scale_factors, **kwargs)
    else:
        # Single resolution - still need to wrap in Multiscales
        multiscales = to_multiscales(ngff_image, scale_factors=[], **kwargs)

    # Write to disk
    to_ngff_zarr(str(path), multiscales)


def write_ome_datatree(
    datatree: xr.DataTree,
    path: str | Path,
    *,
    chunks: int | tuple[int, ...] | None = None,
) -> None:
    """
    Write an xarray DataTree to OME-Zarr format.

    Parameters
    ----------
    datatree : xr.DataTree
        DataTree with multiscale pyramid structure to write.
        Child nodes should be named "scale0", "scale1", etc.
    path : str or Path
        Output path for the OME-Zarr store
    chunks : int or tuple of int, optional
        Chunk sizes for the zarr arrays. If None, uses ngff-zarr defaults.

    Notes
    -----
    Extracts OME-NGFF metadata from datatree attrs and converts xarray
    coordinates back to OME-NGFF coordinate transformations. Uses ngff-zarr
    for the actual writing.

    The DataTree is expected to have a structure like:
    - root (with ome_ngff_metadata in attrs)
      - scale0 (highest resolution)
      - scale1
      - scale2
      - ...

    Examples
    --------
    >>> dt = open_ome_datatree("input.ome.zarr")
    >>> write_ome_datatree(dt, "output.ome.zarr")
    """
    # Get scale levels in order
    scale_nodes = sorted(
        [(int(name.replace("scale", "")), child) for name, child in datatree.children.items()],
        key=lambda x: x[0],
    )

    if not scale_nodes:
        msg = "DataTree has no scale children to write"
        raise ValueError(msg)

    # Convert each scale level to NgffImage
    ngff_images = []
    for _, scale_node in scale_nodes:
        dataset = scale_node.ds
        if dataset is None:
            continue

        # Get the first data variable
        data_var_name = next(iter(dataset.data_vars))
        data_array = dataset[data_var_name]

        # Extract data and dimensions
        data = data_array.values
        dims = list(data_array.dims)

        # Convert coordinates to transforms
        scale, translation = coords_to_transforms(dataset)
        scale_dict = {str(k): float(v) for k, v in scale.items()}
        translation_dict = {str(k): float(v) for k, v in translation.items()}

        # Extract axes units if present
        axes_units = None
        if "ome_axes_units" in dataset.attrs:
            axes_units = dataset.attrs["ome_axes_units"]

        # Create NgffImage
        ngff_image = to_ngff_image(
            data,
            dims=dims,
            scale=scale_dict,
            translation=translation_dict,
            name=data_var_name,
            axes_units=axes_units,
        )
        ngff_images.append(ngff_image)

    # For a DataTree with pre-computed resolution levels, we need to write each
    # image separately to ensure proper metadata. We'll use to_multiscales with
    # the original (scale0) image, but specify that the pyramid already exists
    # by setting scale_factors to match the number of existing scales.

    # Calculate scale factors from the existing images
    # If we have 3 images, we might have scale factors like [2, 4]
    # For now, let to_ngff_zarr handle writing multiple images by using the
    # first approach with a simple call

    # Actually, the simplest approach is to just write all NgffImages at once
    # by creating the multiscales structure that to_ngff_zarr expects
    from ngff_zarr import to_multiscales  # type: ignore[import-untyped]

    # We create a multiscales from the first image with no downsampling,
    # then we'll overwrite with all our images. But we need to manually update
    # the metadata datasets list to match.
    base_multiscales = to_multiscales(ngff_images[0], scale_factors=[])

    # Update the images list
    base_multiscales.images = ngff_images

    # Update the metadata to include dataset entries for each resolution level
    # The metadata should have a datasets list with one entry per resolution
    for i in range(1, len(ngff_images)):
        # Copy the first dataset entry and update the path
        from copy import deepcopy

        new_dataset = deepcopy(base_multiscales.metadata.datasets[0])
        new_dataset.path = str(i)
        base_multiscales.metadata.datasets.append(new_dataset)

    # Write to disk
    to_ngff_zarr(str(path), base_multiscales)
