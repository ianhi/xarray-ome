"""Writing xarray DataTree and Dataset objects to OME-Zarr format."""

from __future__ import annotations

import json
from copy import deepcopy
from typing import TYPE_CHECKING, Any, cast

from ngff_zarr import to_multiscales, to_ngff_image, to_ngff_zarr  # type: ignore[import-untyped]

from .transforms import coords_to_transforms

if TYPE_CHECKING:
    from collections.abc import Hashable, Mapping, Sequence
    from pathlib import Path

    import xarray as xr


def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Recursively merge ``override`` into ``base``, returning a new dict.

    Dicts are merged key-wise; for any key present in both, if BOTH values are
    dicts they merge recursively, otherwise the ``override`` value wins. Keys
    present only in ``base`` are kept. Neither input is mutated.
    """
    merged: dict[str, Any] = dict(base)
    for key, over_val in override.items():
        base_val = merged.get(key)
        if isinstance(base_val, dict) and isinstance(over_val, dict):
            merged[key] = deep_merge(base_val, over_val)
        else:
            merged[key] = over_val
    return merged


def _merge_carrier_into_store(path: str | Path, carrier: dict[str, Any] | None) -> None:
    """Deep-merge a preserved ``ome`` carrier into the just-written store.

    ngff-zarr regenerates a correct *managed* ``multiscales`` block (axes,
    datasets/scale/translation, version) but drops every other carrier field.
    We deep-merge the verbatim carrier read from the source object with the
    freshly written ``ome`` such that the written managed fields (``multiscales``)
    WIN (so ``set_scale``/``set_units`` edits are honored), while EVERY other
    carrier key is preserved unchanged -- not just ``omero``, but any unknown or
    future top-level field the writer does not model (forward-compat, lossless).

    In zarr v3 / NGFF 0.5 the group metadata lives at ``<store>/zarr.json`` with
    the block under ``attributes.ome``. If there is no carrier (a freshly built,
    never-opened object) there is nothing to preserve and this is a no-op.
    """
    if not carrier:
        return

    from pathlib import Path as _Path

    zarr_json = _Path(str(path)) / "zarr.json"
    if not zarr_json.exists():
        # Unexpected layout (e.g. a non-v3 store); nothing safe to merge.
        return

    with zarr_json.open("r", encoding="utf-8") as fh:
        group_meta = json.load(fh)

    attributes = group_meta.setdefault("attributes", {})
    written_ome = attributes.get("ome", {})
    if not isinstance(written_ome, dict):
        written_ome = {}

    # deep_merge(carrier, written_ome): the written managed fields (multiscales)
    # override the carrier, while carrier-only keys (omero, extensions, unknown
    # top-level fields) persist.
    attributes["ome"] = deep_merge(carrier, written_ome)

    with zarr_json.open("w", encoding="utf-8") as fh:
        json.dump(group_meta, fh)


def _axes_units_from_coords(dataset: xr.Dataset, dims: Sequence[Hashable]) -> dict[str, str] | None:
    """Collect CF ``units`` coord attrs into the ``axes_units`` mapping ngff-zarr expects.

    The validated reader stores per-axis physical units as the CF ``units``
    attribute on each coordinate (e.g. ``ds["x"].attrs["units"]``), not in a
    dataset-level ``ome_axes_units`` attr. Returns ``None`` if no axis carries a
    unit so ngff-zarr applies its own defaults.
    """
    units: dict[str, str] = {}
    for dim in dims:
        if dim in dataset.coords:
            unit = dataset.coords[dim].attrs.get("units")
            if unit is not None:
                units[str(dim)] = unit
    return units or None


def _dataset_to_ngff_image(dataset: xr.Dataset) -> Any:
    """Convert a Dataset into an ngff-zarr ``NgffImage``.

    Selects the first data variable (single-image assumption), derives dims and
    the per-axis scale/translation via :func:`coords_to_transforms`, collects the
    CF ``units`` coord attrs, and builds the ``NgffImage`` ngff-zarr expects.
    """
    # Get the first data variable (assumes single image array)
    data_var_name = next(iter(dataset.data_vars))
    data_array = dataset[data_var_name]

    # Extract data and dimensions
    data = data_array.values
    dims = [str(d) for d in data_array.dims]

    # Convert coordinates back to OME-NGFF transformations
    scale, translation = coords_to_transforms(dataset)
    scale_dict: dict[Hashable, float] = {str(k): float(v) for k, v in scale.items()}
    translation_dict: dict[Hashable, float] = {str(k): float(v) for k, v in translation.items()}

    # Extract axes units from CF `units` coord attrs (validated-design layout).
    axes_units = _axes_units_from_coords(dataset, dims)

    # Create NgffImage. dims/axes_units carry NGFF axis letters and unit strings;
    # cast to the precise Literal-based types ngff-zarr declares.
    return to_ngff_image(
        data,
        dims=cast("Sequence[Any]", dims),
        scale=scale_dict,
        translation=translation_dict,
        name=str(data_var_name),
        axes_units=cast("Mapping[str, Any]", axes_units),
    )


def write_ngff_dataset(
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
    >>> ds = open_ngff_dataset("input.ome.zarr")
    >>> write_ngff_dataset(ds, "output.ome.zarr")

    >>> # With multiscale pyramid
    >>> write_ngff_dataset(ds, "output.ome.zarr", scale_factors=[2, 4])
    """
    ngff_image = _dataset_to_ngff_image(dataset)

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

    # Re-emit the verbatim carrier (omero + unknown fields) that ngff-zarr drops.
    carrier = dataset.attrs.get("ome")
    _merge_carrier_into_store(path, carrier if isinstance(carrier, dict) else None)


def write_ngff_datatree(
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
    >>> dt = open_ngff_datatree("input.ome.zarr")
    >>> write_ngff_datatree(dt, "output.ome.zarr")
    """

    # Get scale levels in order. The validated reader names level nodes by their
    # integer level index ("0", "1", ...). Older/strawman trees used "scaleN" or
    # "scaleN_image"; keep tolerating those so a hand-built tree still writes.
    def extract_scale_number(name: str) -> int:
        if name.startswith("scale"):
            after_scale = name[5:]
            num_str = after_scale.split("_")[0]
            return int(num_str)
        try:
            return int(name)
        except ValueError:
            return 0

    scale_nodes = sorted(
        [
            (extract_scale_number(name), child)
            for name, child in datatree.children.items()
            if child.ds is not None and len(child.ds.data_vars) > 0
        ],
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

        ngff_images.append(_dataset_to_ngff_image(dataset))

    # The DataTree already carries pre-computed resolution levels, so we do not
    # re-downsample. Build the multiscales from level 0, then attach every level's image and
    # rebuild the per-level dataset metadata. Each level's coordinate
    # transformations must be derived from THAT level's own image -- deriving
    # them by copying level 0 (as this once did) silently reverts every coarser
    # level's scale/translation to the finest level's.
    base_multiscales = to_multiscales(ngff_images[0], scale_factors=[])

    # Update the images list
    base_multiscales.images = ngff_images

    # Rebuild the datasets list so each level carries its own scale/translation.
    # to_multiscales(img, scale_factors=[]) computes correct single-level dataset
    # metadata from that image; we take its lone dataset and set the level path.
    datasets = []
    for i, image in enumerate(ngff_images):
        level_dataset = deepcopy(to_multiscales(image, scale_factors=[]).metadata.datasets[0])
        level_dataset.path = str(i)
        datasets.append(level_dataset)
    base_multiscales.metadata.datasets = datasets

    # Write to disk
    to_ngff_zarr(str(path), base_multiscales)

    # Re-emit the verbatim carrier from the DataTree ROOT's attrs (omero +
    # unknown fields) that ngff-zarr drops.
    carrier = datatree.attrs.get("ome")
    _merge_carrier_into_store(path, carrier if isinstance(carrier, dict) else None)
