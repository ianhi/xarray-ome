"""The ``.ngff`` accessor: the package's discoverable front door.

Registers a ``.ngff`` accessor on both :class:`xarray.Dataset` and
:class:`xarray.DataTree`, exposing the NGFF metadata carrier as typed reads,
resolving coordinate names by role (world / pixel), and offering small builder
methods to add or fix a coordinate transform *after the fact*.

Design contract
---------------
* **Reads never mutate.** ``version``, ``axes``, ``units``, ``calibrated``,
  ``channels`` and friends only read; they return plain typed values.
* **Builders return NEW objects.** ``set_scale`` / ``set_translation`` /
  ``set_units`` / ``crop`` never modify ``self._obj`` in place -- they build and
  return a fresh :class:`~xarray.Dataset` (or a ``.sel``-derived object).
* **Defensive against a partial carrier.** A missing ``multiscales`` / ``omero``
  / ``axes`` key yields ``None`` / ``[]`` / ``{}`` -- never a ``KeyError``.

The verbatim NGFF metadata carrier lives at ``ds.attrs["ome"]`` (Dataset) and on
the DataTree root node (``dt["/"].dataset.attrs["ome"]`` / ``dt.attrs["ome"]``).
"""

from __future__ import annotations

import copy
from dataclasses import dataclass
from functools import cached_property
from typing import TYPE_CHECKING, Any, cast

import xarray as xr

from .indexes import transform_coords

if TYPE_CHECKING:
    from collections.abc import Hashable

# Axes that carry an affine physical coordinate (mirrors reader._PHYSICAL_AXES).
_PHYSICAL_AXES = ("t", "z", "y", "x")


@dataclass(frozen=True)
class AxisInfo:
    """A single NGFF axis, as declared in ``multiscales[0].axes``.

    Parameters
    ----------
    name : str
        Axis name (also the dimension name, e.g. ``"x"``).
    type : str or None
        NGFF axis type (``"space"``, ``"time"``, ``"channel"``, ...) or ``None``
        when the store does not declare one.
    unit : str or None
        Declared physical unit (e.g. ``"micrometer"``), or ``None`` when the axis
        is uncalibrated.
    """

    name: str
    type: str | None
    unit: str | None


@dataclass(frozen=True)
class ChannelInfo:
    """A single omero channel.

    Parameters
    ----------
    label : str
        Channel label.
    color : str or None
        Hex color string, or ``None`` if absent.
    window : dict or None
        Display window mapping (``min``/``max``/``start``/``end``), or ``None``.
    """

    label: str
    color: str | None
    window: dict[str, Any] | None


def _carrier_from(obj: xr.Dataset | xr.DataTree) -> dict[str, Any]:
    """Return the verbatim ``ome`` carrier dict, or ``{}`` if absent.

    For a :class:`~xarray.DataTree` the carrier lives on the root node's attrs;
    for a :class:`~xarray.Dataset` it lives on ``ds.attrs``.
    """
    if isinstance(obj, xr.DataTree):
        ome = obj.attrs.get("ome")
    else:
        ome = obj.attrs.get("ome")
    return ome if isinstance(ome, dict) else {}


def _multiscale(ome: dict[str, Any]) -> dict[str, Any]:
    """First multiscales entry, or ``{}`` if absent/empty (never raises)."""
    ms = ome.get("multiscales")
    if not ms:
        return {}
    first = ms[0]
    return first if isinstance(first, dict) else {}


class _NgffCommon:
    """Shared read logic for the Dataset and DataTree accessors.

    Subclasses set ``self._obj`` and (for coordinate reads) ``self._dataset`` --
    the Dataset whose coords carry per-axis units / calibration signal.
    """

    _obj: xr.Dataset | xr.DataTree
    _dataset: xr.Dataset

    # ---- carrier ---------------------------------------------------------
    @cached_property
    def raw(self) -> dict[str, Any]:
        """The verbatim NGFF metadata carrier dict (``{}`` if absent).

        Cached: the accessor instance is itself cached on the xarray object, and
        builders (``set_scale`` / ``set_units`` / ...) return NEW objects with a
        fresh accessor, so this never goes stale relative to the receiver.
        """
        return _carrier_from(self._obj)

    @cached_property
    def _ms(self) -> dict[str, Any]:
        """First ``multiscales`` entry of the (cached) carrier, or ``{}``."""
        return _multiscale(self.raw)

    # ---- scalar reads ----------------------------------------------------
    @property
    def version(self) -> str | None:
        """NGFF version string.

        NGFF 0.5 carries ``version`` at the top of the ``ome`` block; older
        layouts put it on ``multiscales[0]``. Prefer the top-level value and
        fall back to the multiscale entry.
        """
        return self.raw.get("version") or self._ms.get("version")

    @property
    def name(self) -> str | None:
        """Multiscale name from ``multiscales[0].name`` (else top-level), or ``None``."""
        return self._ms.get("name") or self.raw.get("name")

    # ---- axes ------------------------------------------------------------
    @property
    def axes(self) -> list[AxisInfo]:
        """Declared axes as :class:`AxisInfo` (``[]`` if none declared)."""
        axes = self._ms.get("axes") or []
        return [
            AxisInfo(
                name=cast("str", a.get("name")),
                type=a.get("type"),
                unit=a.get("unit"),
            )
            for a in axes
            if isinstance(a, dict)
        ]

    @property
    def units(self) -> dict[str, str | None]:
        """Axis name -> unit, read from coord attrs, falling back to the carrier.

        The coordinate ``units`` attr is the source of truth (it round-trips
        through the writer); the carrier's declared ``unit`` is a fallback for
        axes that have no coordinate (e.g. ``c``).
        """
        out: dict[str, str | None] = {}
        for axis in self.axes:
            unit: str | None = None
            coord = self._dataset.coords.get(axis.name)
            if coord is not None:
                unit = coord.attrs.get("units")
            if unit is None:
                unit = axis.unit
            out[axis.name] = unit
        return out

    @property
    def calibrated(self) -> dict[str, bool]:
        """Axis name -> whether the coord carries a real physical ``units`` attr.

        This is the honest pixel-vs-world signal: ``True`` only when the
        coordinate for that axis has a ``units`` attribute (a declared physical
        unit). Axes with no coord, or coords under the identity/pixel fallback,
        are ``False``.
        """
        out: dict[str, bool] = {}
        for axis in self.axes:
            coord = self._dataset.coords.get(axis.name)
            out[axis.name] = bool(coord is not None and coord.attrs.get("units") is not None)
        return out

    # ---- channels --------------------------------------------------------
    @property
    def channels(self) -> list[ChannelInfo] | None:
        """omero channels as :class:`ChannelInfo`, or ``None`` if no omero block."""
        omero = self.raw.get("omero")
        if not isinstance(omero, dict):
            return None
        channels = omero.get("channels")
        if not channels:
            return None
        return [
            ChannelInfo(
                label=ch.get("label", str(i)),
                color=ch.get("color"),
                window=ch.get("window"),
            )
            for i, ch in enumerate(channels)
            if isinstance(ch, dict)
        ]

    # ---- coord role lookup (PROVISIONAL) ---------------------------------
    def coord_name(self, axis: str, kind: str = "world") -> Hashable | None:
        """Resolve the coordinate name for an axis *role*.

        PROVISIONAL. The reader's separable output uses ``coord name == axis
        name`` for world coordinates, so this is a thin, cf-xarray-style lookup.

        Parameters
        ----------
        axis : str
            Axis (dimension) name, e.g. ``"x"``.
        kind : {"world", "pixel"}, default "world"
            Which role to resolve. ``"world"`` returns the axis-named coord if
            present, otherwise a ``world_{axis}`` coord if that (warped)
            convention appears. ``"pixel"`` returns a ``pixel_{axis}`` coord if
            present, else ``None``.

        Returns
        -------
        hashable or None
            The resolved coordinate name, or ``None`` if unresolved.
        """
        coords = self._dataset.coords
        if kind == "world":
            if axis in coords:
                return axis
            warped = f"world_{axis}"
            if warped in coords:
                return warped
            return None
        if kind == "pixel":
            pixel = f"pixel_{axis}"
            return pixel if pixel in coords else None
        raise ValueError(f"kind must be 'world' or 'pixel'; got {kind!r}")

    def world_coord(self, axis: str) -> xr.DataArray | None:
        """The resolved world coordinate for ``axis`` (PROVISIONAL), or ``None``."""
        name = self.coord_name(axis, kind="world")
        return None if name is None else self._dataset.coords[name]

    def pixel_coord(self, axis: str) -> xr.DataArray | None:
        """The resolved pixel coordinate for ``axis`` (PROVISIONAL), or ``None``."""
        name = self.coord_name(axis, kind="pixel")
        return None if name is None else self._dataset.coords[name]

    # ---- builders (return NEW objects; never mutate) ---------------------
    def crop(self, **axis_range: tuple[float, float]) -> Any:
        """Return a world-bbox sub-selection (``.sel`` with label slices).

        Convenience for a world-space bounding-box crop. Works for both diagonal
        (exact) and warped (covering bbox) transforms because selection goes
        through :class:`~xarray_ngff.indexes.TransformIndex`. Works on both a
        :class:`~xarray.Dataset` and a :class:`~xarray.DataTree` -- it only uses
        ``self._obj.sel``.

        Parameters
        ----------
        **axis_range : tuple of (float, float)
            ``axis=(lo, hi)`` world-unit intervals, e.g. ``crop(x=(0.0, 5.0))``.

        Returns
        -------
        xarray.Dataset or xarray.DataTree
            The sub-extent (a view/copy from ``.sel``; the receiver is unchanged).
        """
        selectors = {axis: slice(lo, hi) for axis, (lo, hi) in axis_range.items()}
        return self._obj.sel(**selectors)


def _rebuild_axis_coords(
    ds: xr.Dataset,
    *,
    scale_overrides: dict[str, float] | None = None,
    translate_overrides: dict[str, float] | None = None,
) -> xr.Dataset:
    """Rebuild affine coords for the physical axes present, applying overrides.

    Reads the current per-axis scale/translation off the existing coordinates
    (``coord[1]-coord[0]`` and ``coord[0]``), applies any overrides, and rebuilds
    every present physical-axis coordinate in one :func:`transform_coords` call.
    ``units`` / ``axis_type`` coord attrs are preserved. Returns a NEW Dataset.
    """
    scale_overrides = scale_overrides or {}
    translate_overrides = translate_overrides or {}

    physical = [a for a in _PHYSICAL_AXES if a in ds.dims]
    if not physical:
        raise ValueError("no physical (t/z/y/x) axes present to rebuild")

    sizes: dict[str, int] = {}
    scale: dict[str, float] = {}
    translate: dict[str, float] = {}
    saved_attrs: dict[str, dict[str, Any]] = {}
    for axis in physical:
        sizes[axis] = int(ds.sizes[axis])
        # Derive current scale/translation from the existing coordinate.
        cur_scale, cur_trans = 1.0, 0.0
        if axis in ds.coords:
            vals = ds.coords[axis].values
            if vals.size > 1:
                cur_scale = float(vals[1] - vals[0])
            if vals.size > 0:
                cur_trans = float(vals[0])
            saved_attrs[axis] = dict(ds.coords[axis].attrs)
        scale[axis] = float(scale_overrides.get(axis, cur_scale))
        translate[axis] = float(translate_overrides.get(axis, cur_trans))

    new_coords = transform_coords(sizes, scale, translate)
    out = ds.assign_coords(new_coords)
    for axis, attrs in saved_attrs.items():
        out[axis].attrs.update(attrs)
    return out


def _update_carrier_transforms(
    ome: dict[str, Any],
    *,
    scale_overrides: dict[str, float] | None = None,
    translate_overrides: dict[str, float] | None = None,
) -> dict[str, Any]:
    """Best-effort update of the carrier's ``coordinateTransformations``.

    Mutates a *deep copy* of ``ome`` (never the original) so the returned dict
    reflects the new scale/translation on every dataset entry, matching the
    coord-driven change. The coordinate itself remains the source of truth for
    write-back; this keeps ``.ngff.raw`` internally consistent.
    """
    scale_overrides = scale_overrides or {}
    translate_overrides = translate_overrides or {}
    if not ome:
        return {}
    ome = copy.deepcopy(ome)
    ms = _multiscale(ome)
    axes = ms.get("axes") or []
    axis_order = [a.get("name") for a in axes if isinstance(a, dict)]
    for dataset in ms.get("datasets") or []:
        if not isinstance(dataset, dict):
            continue
        for ct in dataset.get("coordinateTransformations") or []:
            if not isinstance(ct, dict):
                continue
            if ct.get("type") == "scale" and isinstance(ct.get("scale"), list):
                for i, ax in enumerate(axis_order):
                    if ax in scale_overrides and i < len(ct["scale"]):
                        ct["scale"][i] = float(scale_overrides[ax])
            if ct.get("type") == "translation" and isinstance(ct.get("translation"), list):
                for i, ax in enumerate(axis_order):
                    if ax in translate_overrides and i < len(ct["translation"]):
                        ct["translation"][i] = float(translate_overrides[ax])
    return ome


@xr.register_dataset_accessor("ngff")
class NgffDatasetAccessor(_NgffCommon):
    """The ``.ngff`` accessor on a :class:`~xarray.Dataset`.

    Typed reads over the NGFF carrier plus builder methods that return NEW
    Datasets. Access via ``ds.ngff``.
    """

    def __init__(self, obj: xr.Dataset) -> None:
        self._obj = obj
        self._dataset = obj

    # ---- builders (return NEW objects; never mutate) ---------------------
    def set_scale(self, **axis_scale: float) -> xr.Dataset:
        """Return a new Dataset with the given axes' scale replaced.

        Rebuilds the affected axis coordinates via :func:`transform_coords`,
        preserving the other axes and the ``units`` / ``axis_type`` coord attrs.
        Also best-effort-updates the carrier's matching scale transforms so
        ``.ngff.raw`` stays consistent. The coordinate is the source of truth for
        write-back.

        Parameters
        ----------
        **axis_scale : float
            ``axis=scale`` overrides, e.g. ``set_scale(x=6.0, y=6.0)``.

        Returns
        -------
        xarray.Dataset
            A new Dataset (the receiver is unchanged).
        """
        out = _rebuild_axis_coords(self._obj, scale_overrides=axis_scale)
        if "ome" in out.attrs:
            out.attrs["ome"] = _update_carrier_transforms(
                out.attrs["ome"], scale_overrides=axis_scale
            )
        return out

    def set_translation(self, **axis_translation: float) -> xr.Dataset:
        """Return a new Dataset with the given axes' translation replaced.

        Parameters
        ----------
        **axis_translation : float
            ``axis=translation`` overrides, e.g. ``set_translation(x=10.0)``.

        Returns
        -------
        xarray.Dataset
            A new Dataset (the receiver is unchanged).
        """
        out = _rebuild_axis_coords(self._obj, translate_overrides=axis_translation)
        if "ome" in out.attrs:
            out.attrs["ome"] = _update_carrier_transforms(
                out.attrs["ome"], translate_overrides=axis_translation
            )
        return out

    def set_units(self, **axis_unit: str) -> xr.Dataset:
        """Return a new Dataset with the given axes' ``units`` coord attr set.

        Sets the CF ``units`` attribute on each named axis coordinate (this is
        what the writer round-trips) and best-effort-updates the carrier axes'
        ``unit`` field.

        Parameters
        ----------
        **axis_unit : str
            ``axis=unit`` mappings, e.g. ``set_units(x="micrometer")``.

        Returns
        -------
        xarray.Dataset
            A new Dataset (the receiver is unchanged).
        """
        out = self._obj.copy()
        for axis, unit in axis_unit.items():
            if axis not in out.coords:
                raise ValueError(f"axis {axis!r} has no coordinate to attach units to")
            # copy() shares attrs dicts; replace to avoid mutating the original.
            out[axis].attrs = {**out[axis].attrs, "units": unit}
        if "ome" in out.attrs:
            ome = copy.deepcopy(out.attrs["ome"])
            for a in _multiscale(ome).get("axes") or []:
                if isinstance(a, dict) and a.get("name") in axis_unit:
                    a["unit"] = axis_unit[a["name"]]
            out.attrs["ome"] = ome
        return out


@xr.register_datatree_accessor("ngff")
class NgffDataTreeAccessor(_NgffCommon):
    """The ``.ngff`` accessor on a :class:`~xarray.DataTree`.

    Reads the NGFF carrier from the ROOT node and adds resolution-level
    navigation. Coordinate reads (``units`` / ``calibrated`` / role lookup) use
    the finest resolution level. Access via ``dt.ngff``.
    """

    def __init__(self, obj: xr.DataTree) -> None:
        self._obj = obj
        # Coordinate-derived reads use the finest level's Dataset.
        levels = self._level_names(obj)
        self._dataset = obj[levels[0]].to_dataset() if levels else xr.Dataset()

    # ---- level discovery -------------------------------------------------
    @staticmethod
    def _level_names(obj: xr.DataTree) -> list[str]:
        """Child node names that hold data variables, ordered by level index."""

        def key(name: str) -> tuple[int, str]:
            try:
                return (int(name), "")
            except ValueError:
                return (1 << 30, name)

        names = [
            name
            for name, child in obj.children.items()
            if child.dataset is not None and len(child.dataset.data_vars) > 0
        ]
        return sorted(names, key=key)

    @cached_property
    def levels(self) -> list[str]:
        """Resolution-level child node names, finest first.

        Cached: the tree structure is fixed for a given object (DataTree builders
        raise rather than mutate), and the accessor is cached on the object.
        """
        return self._level_names(self._obj)

    @property
    def n_levels(self) -> int:
        """Number of resolution levels."""
        return len(self.levels)

    def level(self, i: int) -> xr.DataTree:
        """The resolution-level node at index ``i`` (0 = finest)."""
        return self._obj[self.levels[i]]

    @property
    def finest(self) -> xr.DataTree:
        """The highest-resolution level node."""
        return self.level(0)

    @property
    def coarsest(self) -> xr.DataTree:
        """The lowest-resolution level node."""
        return self.level(self.n_levels - 1)

    def coarsest_at_least(self, size: int, dim: str = "x") -> xr.DataTree:
        """The coarsest level whose ``dim`` size is at least ``size``.

        Falls back to the finest level if no level is large enough. This is an
        accessor *method* (not an index) because it selects across whole
        resolution levels, which an index cannot do.

        Parameters
        ----------
        size : int
            Minimum required size along ``dim``.
        dim : str, default "x"
            Dimension to measure.

        Returns
        -------
        xarray.DataTree
            The chosen level node.
        """
        # levels are finest -> coarsest; walk from coarsest back toward finest.
        chosen: xr.DataTree | None = None
        for name in self.levels:  # finest -> coarsest
            node = self._obj[name]
            ds = node.dataset
            if ds is not None and dim in ds.sizes and ds.sizes[dim] >= size:
                chosen = node  # keep the coarsest one that still qualifies
        return chosen if chosen is not None else self.finest

    # ---- builders --------------------------------------------------------
    def set_scale(self, **axis_scale: float) -> xr.DataTree:
        """Not supported on a DataTree -- scale differs per resolution level.

        Raises
        ------
        NotImplementedError
            Always. Rebuild per level via ``dt[level].to_dataset().ngff.set_scale``
            instead, since each pyramid level has its own scale.
        """
        raise NotImplementedError(
            "set_scale is Dataset-scoped: each pyramid level has a distinct scale. "
            "Apply it per level, e.g. dt['0'].to_dataset().ngff.set_scale(...)."
        )

    def set_units(self, **axis_unit: str) -> xr.DataTree:
        """Not supported on a DataTree; apply per level instead.

        Raises
        ------
        NotImplementedError
            Always. Apply per level via
            ``dt[level].to_dataset().ngff.set_units(...)``.
        """
        raise NotImplementedError(
            "set_units is Dataset-scoped. Apply it per level, e.g. "
            "dt['0'].to_dataset().ngff.set_units(...)."
        )

    def set_translation(self, **axis_translation: float) -> xr.DataTree:
        """Not supported on a DataTree; apply per level instead.

        Raises
        ------
        NotImplementedError
            Always.
        """
        raise NotImplementedError(
            "set_translation is Dataset-scoped. Apply it per level, e.g. "
            "dt['0'].to_dataset().ngff.set_translation(...)."
        )


__all__ = [
    "AxisInfo",
    "ChannelInfo",
    "NgffDatasetAccessor",
    "NgffDataTreeAccessor",
]
