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
import html
import math
from dataclasses import dataclass
from functools import cached_property
from typing import TYPE_CHECKING, Any, cast

import xarray as xr

from .indexes import transform_coords

if TYPE_CHECKING:
    from collections.abc import Hashable

# Axes that carry an affine physical coordinate (mirrors reader._PHYSICAL_AXES).
_PHYSICAL_AXES = ("t", "z", "y", "x")

# Fallback axis-type inference from a dimension name, used only when neither the
# carrier nor the coordinate's ``axis_type`` attr declares a type.
_AXIS_TYPE_BY_NAME = {
    "x": "space",
    "y": "space",
    "z": "space",
    "t": "time",
    "c": "channel",
}


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


def _carrier_from(obj: xr.Dataset | xr.DataTree | xr.DataArray) -> dict[str, Any]:
    """Return the verbatim ``ome`` carrier dict, or ``{}`` if absent.

    For a :class:`~xarray.DataTree` the carrier lives on the root node's attrs;
    for a :class:`~xarray.Dataset` it lives on ``ds.attrs``; for a
    :class:`~xarray.DataArray` it lives on the *variable's* attrs (usually absent,
    since extracting a variable drops the parent Dataset's ``attrs``).
    """
    ome = obj.attrs.get("ome")
    return ome if isinstance(ome, dict) else {}


def _multiscale(ome: dict[str, Any]) -> dict[str, Any]:
    """First multiscales entry, or ``{}`` if absent/empty (never raises)."""
    ms = ome.get("multiscales")
    if not ms:
        return {}
    first = ms[0]
    return first if isinstance(first, dict) else {}


_HEX_DIGITS = frozenset("0123456789abcdefABCDEF")


def _normalize_hex(color: str | None) -> str | None:
    """Return a bare 3/6-digit hex string (no ``#``) if valid, else ``None``.

    Accepts values with or without a leading ``#``; anything that is not a
    well-formed 3- or 6-digit hex triple is rejected so a malformed carrier
    value can never inject markup or a broken swatch.
    """
    if not isinstance(color, str):
        return None
    c = color.lstrip("#")
    if len(c) in (3, 6) and all(ch in _HEX_DIGITS for ch in c):
        return c
    return None


def _window_range(window: dict[str, Any] | None) -> str:
    """Compact ``lo–hi`` string for an omero display window, or ``""``.

    Prefers the display ``start``/``end`` pair (the visible range); falls back to
    the data ``min``/``max`` bounds. Returns ``""`` when neither pair is present.
    """
    if not isinstance(window, dict):
        return ""
    for lo_key, hi_key in (("start", "end"), ("min", "max")):
        lo, hi = window.get(lo_key), window.get(hi_key)
        if isinstance(lo, (int, float)) and isinstance(hi, (int, float)):
            return f"{lo:g}–{hi:g}"
    return ""


# --- HTML repr styling ---------------------------------------------------
# Theme-awareness strategy: never hardcode a foreground/background color. All
# ink is ``currentColor`` (the viewer's text color, so it reads on light AND
# dark). Soft lines/fills use ``color-mix(... currentColor N%, transparent)``
# with a plain ``currentColor`` first declaration as a graceful fallback for
# engines without ``color-mix``. Secondary text is dimmed with ``opacity``.
_SOFT_BORDER = "border:1px solid currentColor;border-color:color-mix(in srgb,currentColor 25%,transparent)"
_CARD_STYLE = (
    "font-family:var(--jp-content-font-family,ui-sans-serif,system-ui,sans-serif);"
    "font-size:0.82em;line-height:1.45;display:inline-block;max-width:100%;"
    "padding:0.55em 0.7em;border-radius:7px;color:inherit;" + _SOFT_BORDER
)
_TITLE_STYLE = "font-weight:600;font-size:1.05em"
_MUTED_STYLE = "opacity:0.6"
_PILL_STYLE = (
    "font-size:0.85em;padding:0.05em 0.45em;border-radius:999px;margin-left:0.4em;"
    "border:1px solid currentColor;"
    "border-color:color-mix(in srgb,currentColor 30%,transparent)"
)
_GROUP_STYLE = f"{_MUTED_STYLE};font-weight:600;margin:0.35em 0 0.1em"
_TH_STYLE = (
    "text-align:left;padding:0.1em 0.9em 0.1em 0;"
    f"font-weight:600;{_MUTED_STYLE};border-bottom:1px solid currentColor;"
    "border-bottom-color:color-mix(in srgb,currentColor 20%,transparent)"
)
_TD_STYLE = "text-align:left;padding:0.1em 0.9em 0.1em 0;vertical-align:top"
_CODE = 'style="background:none"'
_DASH = f'<span style="{_MUTED_STYLE}">—</span>'


def _html_swatch(hexc: str | None) -> str:
    """A small color-swatch ``<span>`` for a normalized hex, or ``""`` if none."""
    if hexc is None:
        return ""
    return (
        '<span style="display:inline-block;width:0.75em;height:0.75em;'
        "border-radius:2px;vertical-align:middle;margin-right:0.3em;"
        f"background:#{hexc};border:1px solid currentColor;"
        'border-color:color-mix(in srgb,currentColor 40%,transparent)"></span>'
    )


def _html_table(header: list[str], rows: list[list[str]]) -> str:
    """Assemble a styled ``<table>`` from a header + pre-rendered HTML cells."""
    head = "<tr>" + "".join(f"<th style=\"{_TH_STYLE}\">{h}</th>" for h in header) + "</tr>"
    body = "".join(
        "<tr>" + "".join(f'<td style="{_TD_STYLE}">{c}</td>' for c in r) + "</tr>"
        for r in rows
    )
    return (
        '<table style="border-collapse:collapse;margin:0.1em 0 0.35em">' + head + body + "</table>"
    )


class _NgffCommon:
    """Shared read logic for the Dataset and DataTree accessors.

    Subclasses set ``self._obj`` and (for coordinate reads) ``self._dataset`` --
    the Dataset whose coords carry per-axis units / calibration signal.
    """

    _obj: xr.Dataset | xr.DataTree | xr.DataArray
    # The object whose ``.coords`` / ``.sizes`` carry the per-axis physical
    # signal. A Dataset for the Dataset/DataTree accessors; the DataArray itself
    # for the DataArray accessor (a DataArray also has ``.coords``/``.sizes``).
    _dataset: xr.Dataset | xr.DataArray

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
    @cached_property
    def axes(self) -> list[AxisInfo]:
        """Axes as :class:`AxisInfo`.

        Carrier-first: when ``multiscales[0].axes`` declares axes they are
        authoritative (they fix axis order and type). When the carrier declares
        no axes -- e.g. a variable extracted from a Dataset (``ds["image"]``), a
        level pulled from a DataTree with no attrs, or a bare DataArray -- the
        axes are *reconstructed* from the object's dimensions/coordinates via
        :meth:`_axes_from_coords`, which survive extraction. Returns ``[]`` only
        when there is neither a carrier axis list nor any dimension.
        """
        declared = self._ms.get("axes") or []
        if not declared:
            return self._axes_from_coords()
        return [
            AxisInfo(
                name=cast("str", a.get("name")),
                type=a.get("type"),
                unit=a.get("unit"),
            )
            for a in declared
            if isinstance(a, dict)
        ]

    def _axes_from_coords(self) -> list[AxisInfo]:
        """Reconstruct axes from the object's dims/coords (carrier-free fallback).

        One :class:`AxisInfo` per dimension, in dimension order. ``unit`` comes
        from the coordinate's CF ``units`` attr; ``type`` from the coordinate's
        ``axis_type`` attr, else inferred from the axis name (``x``/``y``/``z`` ->
        ``"space"``, ``t`` -> ``"time"``, ``c`` -> ``"channel"``), else ``None``.
        Both attrs are written by the reader and round-trip on the coordinate, so
        they persist where the fragile Dataset-level ``attrs["ome"]`` does not.
        """
        coords = self._dataset.coords
        axes: list[AxisInfo] = []
        for dim in self._dataset.sizes:
            name = str(dim)
            unit: str | None = None
            axis_type: str | None = None
            coord = coords.get(dim)
            if coord is not None:
                unit = coord.attrs.get("units")
                axis_type = coord.attrs.get("axis_type")
            if axis_type is None:
                axis_type = _AXIS_TYPE_BY_NAME.get(name)
            axes.append(AxisInfo(name=name, type=axis_type, unit=unit))
        return axes

    @cached_property
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

    @cached_property
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

    # ---- coordinate transforms (scale / translation) --------------------
    @cached_property
    def _transforms(self) -> dict[str, tuple[float, float]]:
        """Axis name -> ``(scale, translation)``, reconstructed from coords.

        Preferred source is the coordinate's affine index
        (:class:`~xarray_ngff.indexes.TransformIndex`), whose wrapped
        ``AffineCoordinateTransform`` carries the exact ``scale`` / ``translation``
        without touching any data. When the coord is a plain dense numeric array
        (no affine index) the affine is derived from just the first two samples
        (``scale = c[1]-c[0]``, ``translation = c[0]``) -- read lazily, never
        materializing the whole coordinate. Only axes that actually have a
        coordinate are included; non-numeric coords (e.g. categorical ``c``
        labels) and size-<2 coords are skipped.
        """
        out: dict[str, tuple[float, float]] = {}
        coords = self._dataset.coords
        xindexes = self._dataset.xindexes
        for axis in self.axes:
            name = axis.name
            # Membership test, NOT ``coords.get``: a dimension without a real
            # coordinate (e.g. a categorical-less ``c``) yields a *virtual* default
            # integer index from ``.get``/``[]``, which must not masquerade as a
            # declared transform.
            if name not in coords:
                continue
            coord = coords[name]
            # Exact path: pull straight off the affine index's transform.
            transform = getattr(xindexes.get(name), "transform", None)
            scale = getattr(transform, "scale", None)
            translation = getattr(transform, "translation", None)
            if scale is not None and translation is not None:
                out[name] = (float(scale), float(translation))
                continue
            # Dense fallback: derive from the first two values only.
            if coord.dtype.kind not in "iuf" or coord.size < 2:
                continue
            head = coord[:2].values
            derived_scale, derived_trans = float(head[1] - head[0]), float(head[0])
            # Defensive (mirrors transforms.coords_to_transforms): never surface a
            # non-finite affine from a degenerate coord.
            if not (math.isfinite(derived_scale) and math.isfinite(derived_trans)):
                continue
            out[name] = (derived_scale, derived_trans)
        return out

    @property
    def scale(self) -> dict[str, float]:
        """Axis name -> per-axis affine ``scale``, reconstructed from coords."""
        return {name: s for name, (s, _t) in self._transforms.items()}

    @property
    def translation(self) -> dict[str, float]:
        """Axis name -> per-axis affine ``translation``, reconstructed from coords."""
        return {name: t for name, (_s, t) in self._transforms.items()}

    # ---- channels --------------------------------------------------------
    @cached_property
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

    # ---- repr ------------------------------------------------------------
    # Overridable hooks let the DataTree accessor add rows without
    # re-implementing the whole repr.
    _shape_label = "shape"

    def _extra_rows(self) -> list[tuple[str, str]]:
        """Extra ``(label, value)`` rows for both reprs. Overridden by subclasses."""
        return []

    def _meta_rows(self) -> list[tuple[str, str]]:
        """Trailing ``(label, value)`` rows shared by both reprs.

        Single source of truth for which trailing rows exist and in what order
        (data vars, shape, then any subclass extras), so the text and HTML reprs
        can never drift.
        """
        rows: list[tuple[str, str]] = []
        data = self._data_str()
        if data:
            rows.append(("data", data))
        shape = self._shape_str()
        if shape:
            rows.append((self._shape_label, shape))
        rows.extend(self._extra_rows())
        return rows

    def _shape_str(self) -> str:
        """Compact ``dim=size`` shape of the carrier Dataset (``""`` if none)."""
        sizes = self._dataset.sizes
        if not sizes:
            return ""
        return " ".join(f"{dim}={size}" for dim, size in sizes.items())

    def _cal_text(self, axis_name: str) -> str:
        """Human string for an axis's unit/calibration state (text repr)."""
        unit = self.units.get(axis_name)
        if self.calibrated.get(axis_name):
            return unit or "(calibrated)"
        return f"{unit} (uncalibrated)" if unit else "(uncalibrated, pixel/index)"

    def _transform_text(self, axis_name: str) -> str:
        """Compact ``scale S, +T`` string for an axis, or ``""`` if no transform."""
        st = self._transforms.get(axis_name)
        if st is None:
            return ""
        scale, translation = st
        return f"scale {scale:g}, {translation:+g}"

    @cached_property
    def _extent(self) -> dict[str, tuple[float, float]]:
        """Axis name -> ``(first, last)`` world value, derived from the affine.

        Computed purely from ``(scale, translation)`` and the axis size -- no
        coordinate data is materialized. ``first`` is the world value at pixel 0
        (the translation) and ``last`` at pixel ``size-1``.
        """
        sizes = self._dataset.sizes
        out: dict[str, tuple[float, float]] = {}
        for name, (scale, translation) in self._transforms.items():
            size = int(sizes.get(name, 0))
            if size <= 0:
                continue
            out[name] = (translation, scale * (size - 1) + translation)
        return out

    def _extent_text(self, axis_name: str) -> str:
        """Compact ``lo … hi`` world-extent string for an axis, or ``""``."""
        ext = self._extent.get(axis_name)
        if ext is None:
            return ""
        first, last = ext
        return f"{first:g} … {last:g}"

    def _data_str(self) -> str:
        """Compact ``name: dtype`` summary of the data variable(s) (``""`` if none)."""
        obj = self._obj
        if isinstance(obj, xr.DataArray):
            name = str(obj.name) if obj.name is not None else "<unnamed>"
            return f"{name}: {obj.dtype}"
        return ", ".join(f"{name}: {var.dtype}" for name, var in self._dataset.data_vars.items())

    def _channel_axis_name(self) -> str | None:
        """Name of the axis the omero channels belong to, or ``None``.

        Prefers an axis explicitly typed ``"channel"``, then falls back to the
        conventional ``"c"`` axis. Returns ``None`` when there are no channels or
        no plausible channel axis, so callers can degrade to a standalone list.
        """
        if not self.channels:
            return None
        for a in self.axes:
            if a.type == "channel":
                return a.name
        for a in self.axes:
            if a.name == "c":
                return a.name
        return None

    @staticmethod
    def _channel_detail(ch: ChannelInfo) -> tuple[str | None, str]:
        """``(normalized hex or None, window-range str)`` for a channel.

        Shared by the text and HTML reprs so both derive colour and window
        identically. A missing / malformed colour yields ``None`` and a missing
        window yields ``""`` -- neither ever raises, so a partial channel (label
        only) renders cleanly.
        """
        return _normalize_hex(ch.color), _window_range(ch.window)

    def _channel_label_text(self, ch: ChannelInfo) -> str:
        """``label (#color, lo–hi)`` string for a channel (text repr).

        Degrades gracefully: drops the colour and/or window fragment when absent,
        falling back to just the bare label.
        """
        hexc, win = self._channel_detail(ch)
        bits: list[str] = []
        if hexc is not None:
            bits.append(f"#{hexc}")
        if win:
            bits.append(win)
        return f"{ch.label} ({', '.join(bits)})" if bits else ch.label

    def _axes_by_type(self) -> list[tuple[str, list[AxisInfo]]]:
        """Group axes by their ``type``, in first-appearance order.

        Each group is ``(type_label, axes)``; axes with no declared type fall
        under ``"other"``. Drives the one-table-per-type repr layout.
        """
        groups: dict[str, list[AxisInfo]] = {}
        order: list[str] = []
        for a in self.axes:
            key = a.type or "other"
            if key not in groups:
                groups[key] = []
                order.append(key)
            groups[key].append(a)
        return [(k, groups[k]) for k in order]

    def _axes_table_html(self, group: list[AxisInfo]) -> str:
        """HTML table for a non-channel axis group (axis / unit / transform / extent)."""
        esc = html.escape
        units, calibrated = self.units, self.calibrated
        rows: list[list[str]] = []
        for a in group:
            unit = units.get(a.name)
            if calibrated.get(a.name):
                unit_cell = f'<span title="calibrated (world)">{esc(unit or "—")}</span>'
            else:
                label = esc(unit) if unit else "pixel/index"
                unit_cell = f'<span style="{_MUTED_STYLE}" title="uncalibrated">{label} ·</span>'
            tf = self._transform_text(a.name)
            tf_cell = (
                f'<code {_CODE} title="world = scale * pixel + translation">{esc(tf)}</code>'
                if tf
                else _DASH
            )
            ext = self._extent_text(a.name)
            ext_cell = f"<code {_CODE}>{esc(ext)}</code>" if ext else _DASH
            rows.append([f"<code {_CODE}>{esc(a.name)}</code>", unit_cell, tf_cell, ext_cell])
        return _html_table(["axis", "unit", "transform", "extent (world)"], rows)

    def _channels_table_html(self) -> str:
        """HTML table listing the omero channels (channel / color / window)."""
        esc = html.escape
        rows: list[list[str]] = []
        for ch in self.channels or []:
            hexc, win = self._channel_detail(ch)
            if hexc is not None:
                color_cell = f"{_html_swatch(hexc)}<code {_CODE}>#{esc(hexc)}</code>"
            else:
                color_cell = _DASH
            win_cell = f"<code {_CODE}>{esc(win)}</code>" if win else _DASH
            rows.append([esc(ch.label), color_cell, win_cell])
        return _html_table(["channel", "color", "window"], rows)

    def __repr__(self) -> str:
        kind = type(self._obj).__name__
        axes = self.axes
        channels = self.channels
        if not self.raw and not axes:
            return f"<{kind}.ngff: no OME-NGFF metadata>"

        header = f"{kind}.ngff"
        version = self.version
        if version:
            header += f"  v{version}"
        name = self.name
        if name:
            header += f'  "{name}"'
        lines = [header]

        # One block per axis type; the channel axis nests its omero channels.
        chan_axis = self._channel_axis_name()
        for type_label, group in self._axes_by_type():
            lines.append(f"  {type_label}:")
            name_w = max(len(a.name) for a in group)
            plain = [a for a in group if a.name != chan_axis]
            cal_w = max((len(self._cal_text(a.name)) for a in plain), default=0)
            tf_w = max((len(self._transform_text(a.name)) for a in plain), default=0)
            for a in group:
                if channels is not None and a.name == chan_axis:
                    labels = ", ".join(self._channel_label_text(c) for c in channels)
                    lines.append(f"    {a.name:<{name_w}}  ({len(channels)}) {labels}")
                    continue
                row = f"    {a.name:<{name_w}}  {self._cal_text(a.name):<{cal_w}}"
                transform = self._transform_text(a.name)
                if tf_w:
                    row += f"  {transform:<{tf_w}}"
                extent = self._extent_text(a.name)
                if extent:
                    row += f"  [{extent}]"
                lines.append(row.rstrip())

        # Channels with no identifiable channel axis fall back to a flat list.
        if channels is not None and chan_axis is None:
            labels = ", ".join(self._channel_label_text(c) for c in channels)
            lines.append(f"  channels ({len(channels)}):  {labels}")

        for label, value in self._meta_rows():
            lines.append(f"  {label}:  {value}")

        return "\n".join(lines)

    def _repr_html_(self) -> str:
        esc = html.escape
        kind = type(self._obj).__name__
        axes = self.axes
        channels = self.channels

        if not self.raw and not axes:
            return (
                f'<div style="{_CARD_STYLE}">'
                f'<span style="{_TITLE_STYLE}">{kind}.ngff</span>'
                f'<span style="{_MUTED_STYLE};margin-left:0.5em">'
                "no OME-NGFF metadata</span></div>"
            )

        parts: list[str] = [f'<div style="{_CARD_STYLE}">']

        # Title line: kind.ngff + version pill + name.
        title = [f'<span style="{_TITLE_STYLE}">{kind}.ngff</span>']
        version = self.version
        if version:
            title.append(f'<span style="{_PILL_STYLE}">v{esc(str(version))}</span>')
        name = self.name
        if name:
            title.append(
                f'<span style="margin-left:0.5em;{_MUTED_STYLE}">{esc(str(name))}</span>'
            )
        parts.append(f'<div style="margin-bottom:0.35em">{"".join(title)}</div>')

        # One table per axis type; the channel axis renders as a channel table.
        chan_axis = self._channel_axis_name()
        for type_label, group in self._axes_by_type():
            if channels is not None and any(a.name == chan_axis for a in group):
                parts.append(
                    f'<div style="{_GROUP_STYLE}">{esc(type_label)} '
                    f'<span style="font-weight:400">({esc(str(chan_axis))})</span></div>'
                )
                parts.append(self._channels_table_html())
            else:
                parts.append(f'<div style="{_GROUP_STYLE}">{esc(type_label)}</div>')
                parts.append(self._axes_table_html(group))

        # Channels with no identifiable channel axis fall back to their own table.
        if channels is not None and chan_axis is None:
            parts.append(f'<div style="{_GROUP_STYLE}">channels ({len(channels)})</div>')
            parts.append(self._channels_table_html())

        # Trailing meta rows (data vars + shape + subclass extras), shared with
        # the text repr via ``_meta_rows``.
        for label, value in self._meta_rows():
            parts.append(
                f'<div style="margin:0.1em 0"><span style="{_MUTED_STYLE}">'
                f"{esc(label)}:</span> "
                f'<code style="background:none;font-size:0.95em">{esc(value)}</code></div>'
            )

        parts.append("</div>")
        return "".join(parts)


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


@xr.register_dataarray_accessor("ngff")
class NgffDataArrayAccessor(_NgffCommon):
    """The ``.ngff`` accessor on a :class:`~xarray.DataArray` -- a *read* view.

    A DataArray's ``attrs`` are the variable's own attrs, so the ``ome`` carrier
    is usually absent (extracting a variable from a Dataset, or a coord-inherited
    DataTree level, drops the parent's ``attrs["ome"]``). Consequently
    ``version`` / ``name`` / ``channels`` honestly return ``None`` -- but
    ``axes`` / ``units`` / ``calibrated`` reconstruct from the DataArray's
    coordinates, which *do* survive extraction (each physical coord keeps its
    ``units`` / ``axis_type`` attrs and its :class:`~xarray_ngff.indexes.TransformIndex`).

    Read-only by construction: the mutating builders (``set_scale`` /
    ``set_translation`` / ``set_units``) live only on the Dataset accessor and
    are intentionally not exposed here. Access via ``da.ngff``.
    """

    def __init__(self, obj: xr.DataArray) -> None:
        self._obj = obj
        # A DataArray has ``.coords`` / ``.sizes``, which is all the coord-derived
        # reads (units / calibrated / _axes_from_coords / role lookup) need.
        self._dataset = obj


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

    # ---- repr ------------------------------------------------------------
    _shape_label = "finest shape"

    def _extra_rows(self) -> list[tuple[str, str]]:
        """Add a resolution-levels row to the shared repr."""
        levels = self.levels
        if not levels:
            return []
        return [("levels", f"{len(levels)} ({', '.join(levels)})")]

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
    "NgffDataArrayAccessor",
    "NgffDatasetAccessor",
    "NgffDataTreeAccessor",
]
