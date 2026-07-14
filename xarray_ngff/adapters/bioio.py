"""Adapter: a :class:`bioio.BioImage` -> the xarray-ngff representation.

``bioio`` fetches the bytes but flattens every format to a fixed ``TCZYX`` shape,
inventing size-1 axes and dropping the OME-Zarr scale/units/omero metadata a store
declares. This adapter re-imposes that metadata.

For an **OME-Zarr source** (tier 1, implemented here) bioio preserves the pristine
group metadata on the xarray object::

    img.xarray_dask_data.attrs["unprocessed"].attributes["ome"]

That ``ome`` dict is exactly what our reader consumes. So the highest-fidelity
adapter does *not* try to un-mangle bioio's ``TCZYX`` DataArray -- it recovers the
verbatim ``ome`` block, pairs it with bioio's (already fetched, still lazy) dask
array, and rebuilds our representation by reusing the tested reader machinery
(:func:`~xarray_ngff.reader._build_level_dataset` and friends). Scale/translation
come from the ``ome`` block, never re-derived from bioio's coordinate values.

Non-OME-Zarr sources (CZI/ND2/LIF/...) carry no ``ome`` block; synthesizing our
layer from bioio's flattened surface (tier 2) is not yet implemented.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

import xarray as xr
from ngff_zarr import to_ngff_image  # type: ignore[import-untyped]

from ..reader import (
    _axis_types_from_ome,
    _build_level_dataset,
    _channel_labels_from_ome,
)

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence


def _recover_ome_block(img: Any) -> tuple[Any, dict[str, Any]]:
    """Recover the (DataArray, verbatim ``ome`` dict) pair from a bioio object.

    Accepts either a :class:`bioio.BioImage` (uses its ``xarray_dask_data``) or the
    ``xarray_dask_data`` DataArray directly. Raises with an actionable message when
    the object is not an OME-Zarr-backed bioio image (tier 2 territory).
    """
    xd = getattr(img, "xarray_dask_data", img)

    unprocessed = getattr(xd, "attrs", {}).get("unprocessed")
    # bioio stows the raw group metadata as a zarr ``GroupMetadata`` whose
    # ``.attributes`` dict holds the ``ome`` block. Be tolerant of a plain dict too.
    attributes = getattr(unprocessed, "attributes", None)
    if attributes is None and isinstance(unprocessed, dict):
        attributes = unprocessed.get("attributes", unprocessed)

    ome = attributes.get("ome") if isinstance(attributes, dict) else None
    if not isinstance(ome, dict) or "multiscales" not in ome:
        msg = (
            "from_bioio (tier 1) needs an OME-Zarr-backed bioio image: the raw "
            "`ome` block was not found at `xarray_dask_data.attrs['unprocessed']`. "
            "This is likely a non-OME-Zarr source (CZI/ND2/LIF/...), which tier 2 "
            "would handle by synthesizing metadata from bioio's flattened surface "
            "-- not yet implemented."
        )
        raise NotImplementedError(msg)

    return xd, ome


def _compose_transforms(
    transform_lists: list[list[dict[str, Any]]], axis_names: list[str]
) -> tuple[dict[str, float], dict[str, float]]:
    """Compose an ordered chain of NGFF ``scale``/``translation`` transforms.

    NGFF applies a dataset's own ``coordinateTransformations`` first, then the
    multiscale-level ones. Each subsequent scale multiplies and each translation
    adds, following ``coord = s * i + t``: for a later scale ``s2`` and translation
    ``t2`` applied after ``(s1, t1)`` the result is ``s2*s1*i + (s2*t1 + t2)``.
    Missing transforms fall back to identity (scale 1.0, translation 0.0).
    """
    scale = {a: 1.0 for a in axis_names}
    translation = {a: 0.0 for a in axis_names}
    for transforms in transform_lists:
        for ct in transforms:
            ttype = ct.get("type")
            if ttype == "scale":
                for a, v in zip(axis_names, ct.get("scale", [])):
                    scale[a] *= float(v)
                    translation[a] *= float(v)
            elif ttype == "translation":
                for a, v in zip(axis_names, ct.get("translation", [])):
                    translation[a] += float(v)
    return scale, translation


def _extract_level_data(xd: Any, real_dims: list[str]) -> Any:
    """Reshape bioio's ``TCZYX`` DataArray down to the store's real axes.

    bioio invents size-1 axes not present in the store. Because ``real_dims`` comes
    from the ``ome`` block we know exactly which axes are genuine: any bioio dim
    whose (lowercased) name is not among them is an invented singleton -- select
    index 0 and drop it. A *genuinely* size-1 real axis stays, because it is in
    ``real_dims``. Returns the underlying (lazy) dask/numpy array in ``real_dims``
    order.
    """
    present = {str(d).lower(): d for d in xd.dims}

    missing = [d for d in real_dims if d.lower() not in present]
    if missing:
        msg = (
            f"bioio does not expose axes {missing} from the store's `ome` block; it "
            "only models T/C/Z/Y/X. from_bioio cannot rebuild non-standard axis "
            f"names (store axes: {real_dims})."
        )
        raise NotImplementedError(msg)

    real_lower = {d.lower() for d in real_dims}
    drop: dict[Any, int] = {}
    for lower, dim in present.items():
        if lower in real_lower:
            continue
        # Guard: an axis bioio kept at size > 1 but the store does not declare would
        # silently lose data if we indexed it away. For a valid OME-Zarr these are
        # always invented singletons.
        if xd.sizes[dim] != 1:
            msg = (
                f"bioio dim {dim!r} has size {xd.sizes[dim]} but is not one of the "
                f"store's declared axes {real_dims}; refusing to drop it (would lose "
                "data)."
            )
            raise ValueError(msg)
        drop[dim] = 0

    da = xd.isel(drop) if drop else xd
    da = da.rename({present[d.lower()]: d for d in real_dims})
    da = da.transpose(*real_dims)
    return da.data


def _n_levels(ome: dict[str, Any]) -> int:
    """Number of resolution levels the ``ome`` block declares."""
    return len(ome["multiscales"][0].get("datasets", []))


def _select_level(img: Any, xd: Any, resolution: int) -> Any:
    """Return bioio's DataArray for ``resolution``, reusing its fetched bytes.

    A :class:`bioio.BioImage` switches level in place via ``set_resolution_level``;
    a bare DataArray only exposes the level it was extracted at (level 0 only).
    """
    if hasattr(img, "set_resolution_level"):
        img.set_resolution_level(resolution)
        return img.xarray_dask_data
    if resolution != 0:
        msg = (
            "A bare DataArray only exposes its current resolution level; pass a "
            f"bioio.BioImage to rebuild level {resolution}."
        )
        raise ValueError(msg)
    return xd


def _build_level(xd: Any, ome: dict[str, Any], resolution: int) -> xr.Dataset:
    """Build one level's Dataset (no ``ome`` carrier attached) from bioio's data.

    Reuses the reader machinery so the result is identical to a reader node:
    scale/translation are composed from the ``ome`` block (dataset-level then
    multiscale-level), bioio's ``TCZYX`` array is reshaped to the real axes, and
    :func:`~xarray_ngff.reader._build_level_dataset` adds the lazy coords, CF attrs,
    and channel labels.
    """
    multiscale = ome["multiscales"][0]
    axes = multiscale.get("axes", [])
    real_dims = [a["name"] for a in axes]
    axes_units = {a["name"]: a["unit"] for a in axes if a.get("unit")}
    name = multiscale.get("name") or "image"

    # Scale/translation come from the `ome` block, never bioio's coord values:
    # the dataset's own transforms first, then any multiscale-level ones.
    scale, translation = _compose_transforms(
        [
            multiscale["datasets"][resolution].get("coordinateTransformations", []),
            multiscale.get("coordinateTransformations", []),
        ],
        real_dims,
    )

    data = _extract_level_data(xd, real_dims)

    # dims/scale/translation/axes_units carry NGFF axis letters and unit strings;
    # cast to the precise Literal-based types ngff-zarr declares (mirrors the writer).
    image = to_ngff_image(
        data,
        dims=cast("Sequence[Any]", real_dims),
        scale=cast("Mapping[Any, float]", scale),
        translation=cast("Mapping[Any, float]", translation),
        name=name,
        axes_units=cast("Mapping[str, Any]", axes_units) or None,
    )

    return _build_level_dataset(
        image,
        _channel_labels_from_ome(ome),
        _axis_types_from_ome(ome),
    )


def from_bioio(img: Any, resolution: int = 0) -> xr.Dataset:
    """Rebuild the xarray-ngff representation from a bioio OME-Zarr image.

    Parameters
    ----------
    img : bioio.BioImage or xarray.DataArray
        A :class:`bioio.BioImage` (an OME-Zarr source) or its
        ``xarray_dask_data``. The object must carry the raw ``ome`` block at
        ``xarray_dask_data.attrs['unprocessed']`` (tier 1).
    resolution : int, default 0
        Which resolution level to rebuild (0 = finest). For a ``BioImage`` the
        requested level is fetched via ``set_resolution_level``; when a bare
        DataArray is passed only its current level is available.

    Returns
    -------
    xarray.Dataset
        A single-level Dataset built exactly like the reader's output: real axis
        dims, lazy transform-backed physical coordinates with CF ``units`` /
        ``axis_type`` attrs, omero channel labels on ``c`` when present, and the
        verbatim ``ome`` carrier on ``attrs["ome"]``. Equal to
        ``open_ngff_dataset(store, resolution)`` for an OME-Zarr source.

    Raises
    ------
    NotImplementedError
        If the object carries no ``ome`` block (a non-OME-Zarr source -- tier 2),
        or declares axis names bioio cannot model.
    ValueError
        If ``resolution`` is out of range.
    """
    xd, ome = _recover_ome_block(img)

    if resolution >= _n_levels(ome):
        msg = f"Resolution level {resolution} not found. Available levels: 0-{_n_levels(ome) - 1}"
        raise ValueError(msg)

    xd = _select_level(img, xd, resolution)
    ds = _build_level(xd, ome, resolution)
    ds.attrs["ome"] = ome
    return ds


def from_bioio_datatree(img: Any) -> xr.DataTree:
    """Rebuild every resolution level of a bioio OME-Zarr image as a DataTree.

    Mirrors :func:`xarray_ngff.open_ngff_datatree`: one child node per resolution
    level named ``"0"``, ``"1"``, ... each carrying lazy physical coordinates, with
    the verbatim ``ome`` carrier on the root node's ``attrs["ome"]``.

    Parameters
    ----------
    img : bioio.BioImage or xarray.DataArray
        A :class:`bioio.BioImage` (recommended -- exposes every level via
        ``set_resolution_level``) or its ``xarray_dask_data`` (a bare DataArray
        yields a single-level tree, since it only carries level 0's pixels).

    Returns
    -------
    xarray.DataTree
        Equal to ``open_ngff_datatree(store)`` for an OME-Zarr source read through
        a ``BioImage``.

    Raises
    ------
    NotImplementedError
        If the object carries no ``ome`` block (a non-OME-Zarr source -- tier 2),
        or declares axis names bioio cannot model.
    """
    xd, ome = _recover_ome_block(img)

    # A bare DataArray only holds level 0; a BioImage can page through every level.
    n_levels = 1 if not hasattr(img, "set_resolution_level") else _n_levels(ome)

    nodes: dict[str, xr.Dataset] = {}
    for level in range(n_levels):
        level_xd = _select_level(img, xd, level)
        nodes[f"/{level}"] = _build_level(level_xd, ome, level)

    # Carrier on the root only (matches the reader), so nothing the parser dropped
    # is lost on round-trip.
    nodes["/"] = xr.Dataset(attrs={"ome": ome})
    return xr.DataTree.from_dict(nodes)
