"""Utilities for detecting and working with OME-Zarr stores."""

from __future__ import annotations

from typing import Any


def read_ome_block(path: str) -> dict[str, Any] | None:
    """Read the raw ``ome`` metadata block from a store's root group attrs.

    In NGFF 0.5 (zarr v3) the OME-NGFF metadata is nested under the ``ome`` key;
    in 0.4 (zarr v2) it lives at the top level of the group attributes. Returns
    the relevant dict, or ``None`` if the store can't be opened.
    """
    try:
        import zarr

        group = zarr.open_group(path, mode="r")
        attrs: dict[str, Any] = dict(group.attrs)
    except Exception:
        return None

    # NGFF 0.5 nests everything under "ome"; 0.4 keeps it top-level.
    ome = attrs.get("ome")
    if isinstance(ome, dict):
        return ome
    return attrs


def detect_store_type(path: str) -> str:
    """
    Detect the type of OME-Zarr store by inspecting metadata.

    Parameters
    ----------
    path : str
        Path or URL to the OME-Zarr store

    Returns
    -------
    str
        Store type: 'image', 'hcs', or 'unknown'

    Notes
    -----
    Classifies by *presence* of well-known keys in the ``ome`` block rather than
    by relying on ``ngff_zarr.validate`` raising. This is robust for both zarr v3
    / NGFF 0.5 (attrs nested under ``ome``) and zarr v2 / NGFF 0.4 (top-level).

    - ``plate`` or ``well`` -> ``"hcs"``
    - ``multiscales`` -> ``"image"``
    - otherwise -> ``"unknown"``
    """
    ome = read_ome_block(path)
    if not isinstance(ome, dict):
        return "unknown"

    # HCS structures take precedence: a plate/well node is never a plain image.
    if "plate" in ome or "well" in ome:
        return "hcs"
    if "multiscales" in ome:
        return "image"
    return "unknown"


# Backwards-compatible aliases for internal callers that imported the
# underscore-prefixed names before these helpers were made public.
_read_ome_block = read_ome_block
_detect_store_type = detect_store_type
