# Omero

The `omero` field carries **display metadata** for the channel axis: per-channel labels, colors, and contrast-limit windows. It describes how to render the data, not the data itself. It is the only NGFF 0.5 field with officially *transitional* status, and the only one where the spec itself warns the metadata model may change. Any mapping must preserve it faithfully without pretending it is stable.

## Status: transitional

The spec labels this section **"omero" metadata (transitional)** ({ref}`omero-metadata` in the spec). Two practical consequences:

1. **Fields may be added or renamed in a future NGFF version.** The mapping cannot hard-code an exhaustive list of keys and drop anything else — unknown keys must round-trip.
2. **Not every OME-Zarr in the wild carries omero.** It is optional. Readers must handle its absence gracefully and produce sensible defaults.

## The JSON structure

From the spec:

```json
{
  "id": 1,
  "name": "example.tif",
  "channels": [
    {
      "active": true,
      "coefficient": 1,
      "color": "0000FF",
      "family": "linear",
      "inverted": false,
      "label": "LaminB1",
      "window": {
        "end": 1500,
        "max": 65535,
        "min": 0,
        "start": 0
      }
    }
  ],
  "rdefs": {
    "defaultT": 0,
    "defaultZ": 118,
    "model": "color"
  }
}
```

## Required fields

If `omero` is present, the spec requires:

| field | requirement |
|---|---|
| `channels` | MUST be present; array of channel dicts. |
| `channels[].color` | MUST be a 6-hex-digit RGB string (e.g. `"00FF00"`). |
| `channels[].window` | MUST be an object with `min`, `max`, `start`, `end`. |

`label`, `active`, `coefficient`, `family`, `inverted`, top-level `id`, `name`, and `rdefs` are not formally required in 0.5, but producers typically emit them and readers should preserve them.

### The `window` object

Four floats with a specific semantics:

- `min`, `max`: the data range (roughly: the dtype min/max, or the observed value range).
- `start`, `end`: the display range (the values that map to black and white in the rendered image).

`start/end` is normally within `[min, max]` but is not formally constrained. These are float-valued even for integer image data.

## Relationship to the channel axis

`omero.channels` is a parallel list to the channel axis: `channels[i]` describes index `i` along the axis whose NGFF `type` is `"channel"`. The length of `channels` MUST match the length of that axis. Nothing else in NGFF connects a channel *index* to a channel *identity* — `omero.label` is the only source of truth.

This has two consequences for the mapping:

1. **Channel labels are a string coordinate** on the channel dim. This is the consensus across the ecosystem (see [](../prior-art.md)). It enables `da.sel(c="LaminB1")`, which is the natural xarray idiom.
2. **The rest of the channel metadata has no natural xarray home.** `color` and `window` are per-channel floats/strings that do not influence `.sel` or math — they are display hints.

## Where the fields end up in xarray

Preview of the mapping (full detail in [](../mapping/omero-to-coords.md)):

| NGFF field | xarray location |
|---|---|
| `omero.channels[i].label` | string coord on the channel dim, value at index `i` |
| `omero.channels[i].color` | per-channel attr — candidate locations: coord attr on `c`, or a parallel coord |
| `omero.channels[i].window` | per-channel attr — same question |
| `omero.channels[i]` other fields (`active`, `coefficient`, `family`, `inverted`) | preserve in attrs; not semantically interpreted |
| `omero.id`, `omero.name`, `omero.rdefs` | dataset-level attrs; passthrough |

The open design question is how to store per-channel non-label metadata. There is no clean idiomatic answer in xarray — see the open questions below.

## Edge cases worth naming

- **Length mismatch between `omero.channels` and the channel axis.** Spec-illegal but has been observed in the wild. Reader policy: warn and truncate/pad? Fail?
- **Missing `label`.** Channels without labels cannot be `.sel`-ed by name. Fall back to index-based labels (`"ch0"`, `"ch1"`, …)?
- **Duplicate labels.** Breaks `.sel`. Preserve them in attrs but produce a distinct indexed coord (`label:0`, `label:1`, …) if we detect duplicates? Or refuse to construct a string coord at all?
- **Non-hex `color`.** Spec MUST, but malformed strings exist. Round-trip as-is without validation?
- **Unknown keys at any level.** `omero.channels[].custom_field = "..."` — guaranteed by "transitional" status. Must pass through untouched.
- **No channel axis but omero present.** Nonsensical but possible — behaviour unclear.

## Questions this raised (resolved in the mapping)

1. **Where do `color` and `window` live?**
   - (a) As nested coord attrs on the channel coord (`ds.c.attrs["colors"] = [...]`). Robust to slicing if we store them as arrays aligned with `c`.
   - (b) As parallel coords on the channel dim (`ds = ds.assign_coords(color=("c", [...]))`). More discoverable; selects follow the channel automatically.
   - (c) As a scalar dataset attr (`ds.attrs["omero"]["channels"] = [...]`). Simple, but decoheres on slicing — selecting one channel keeps the whole list.

   Option (b) is the most xarray-native but adds user-visible coords that most workflows do not need. Option (a) plus a full `omero` passthrough in attrs may be the pragmatic middle.

2. **What survives `.isel(c=[0, 2])`?** If `color`/`window` are aligned with `c`, slicing selects them correctly. If they are in a monolithic `attrs["omero"]["channels"]` list, the attr goes stale immediately. This argues for (a) or (b).

3. **Writing back.** When we regenerate `omero` on write, do we rebuild from the structured coords, or trust the stashed passthrough dict? If the user edited `ds.c` labels but not the underlying dict, we need the structured view to win.

These are resolved in [](../mapping/omero-to-coords.md).

:::{seealso}
- [](axes.ipynb) — the channel axis omero decorates
- [](../mapping/omero-to-coords.md) — mapping decisions for channel display metadata
- [](../prior-art.md) § bioio — how other tools treat channel labels
:::
