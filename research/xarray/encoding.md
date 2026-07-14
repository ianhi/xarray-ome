# Encoding

xarray's `encoding` dict lives on each Variable and carries *storage mechanics* — the parameters that control how the array is written to and read from disk. It is the one xarray surface that is genuinely unsafe for domain metadata, and saying exactly why pins down a recurring temptation in the mapping.

## What `encoding` is for

On read, the backend populates `encoding` with the layout it found; on write, it consumes `encoding` to decide how to serialise. For the Zarr backend the recognised keys are codec/layout only: `chunks`, `shards`, `compressors`, `filters`, `serializer`, `dtype`, `fill_value`. xarray's CF layer *also* routes some keys here: time `units`+`calendar`, `scale_factor`/`add_offset`, and `_FillValue` are moved from `attrs` into `encoding` on read.

## Why it is wrong for NGFF metadata

Three properties disqualify it:

1. **Unknown keys are silently deleted on write.** The Zarr backend whitelists; anything outside the recognised set is dropped with no error. Axis `type`, `unit`, or a transform stashed in `encoding` would simply vanish on the next write — the worst possible failure for a "never lose data" library.
2. **It is invisible.** `encoding` does not appear in the repr and is not part of the data model users inspect, so metadata there is undiscoverable (failing requirement #2).
3. **It is not propagated through computation.** Operations do not carry `encoding` forward the way they carry `attrs`.

This is precisely what Experiment 4 in [](../spec/axes-experiments.ipynb) demonstrated empirically. Domain metadata therefore lives in coordinate `attrs` and the round-trip carrier ([](../mapping/axes-to-dims.md), [](../mapping/round-trip.md)); `encoding` is left to do its real job — chunking and compression.

## The one legitimate overlap

`encoding` *is* the right place for the storage parameters NGFF also cares about — chunk and shard shapes, compressors — because those are exactly what it was designed for. The backend reads NGFF/Zarr chunking into `encoding` and writes it back from there; that is mechanics, not domain metadata, and is not in tension with anything above.

:::{seealso}
- [](../spec/axes-experiments.ipynb) — Experiment 4: encoding tested for axis metadata and rejected
- [](data-model.md) — `attrs` durability vs. `encoding` fragility
- [](../mapping/round-trip.md) — the carrier that holds what `encoding` cannot
:::
