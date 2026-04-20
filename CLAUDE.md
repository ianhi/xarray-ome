# Project Rules

Also read `AGENTS.md` for code style guidelines and development workflow.

## Project Overview

xarray-ome provides an xarray backend for reading and writing OME-Zarr (OME-NGFF) files. Uses **ngff-zarr** as the foundation for OME-Zarr I/O.

## Active Work: Research Book

We're building a jupyter-book under `research/` that documents the NGFF 0.5 to xarray mapping, leading to an RFC.

### Research Book Infrastructure

- **Jupyter Book v2** — uses `myst.yml`, NOT `_config.yml`/`_toc.yml`
- Config: `research/myst.yml`
- Dependencies: `research/pyproject.toml` (uv project, not installable)
- Execute notebooks: `cd research && uv run jupyter execute <path> --inplace`
- Dev server: `cd research && uvx jupyter-book start` (serves at `http://localhost:3000`)
- Build: `cd research && uvx jupyter-book build`

### Collaborative Workflow

**The workflow is collaborative: gather research, present findings, discuss, then write together.**

- Do NOT write a full notebook page without checking in first
- Present research findings and proposed structure before writing
- Discuss design decisions interactively
- Build pages incrementally with user feedback

### Terminology

- Use **"NGFF"** for the format/specification
- Use **"OME-Zarr"** for concrete `.ome.zarr` stores on disk

### Design Requirements for NGFF-to-xarray Mapping

1. **Robust to user mistakes** — no raw dicts; the API should make wrong things hard
2. **Usable for developers** — typed, structured, discoverable
3. **Never loses data** — full round-trip fidelity, including unknown fields (forward compat)

### Key Design Decisions

- Axis names map to dims (unambiguous)
- Custom backend is the recommended write path (not constrained to `to_zarr()`)
- Accessor provides typed API; backend handles serialization
- Coordinate attrs (CF-style) are a good fit for type/unit on coordinates

## Environment

- Use `uv run` for all Python commands (main project and research/)
- The research/ directory has its own venv and pyproject.toml
- pydantic-ome-ngff is incompatible (requires zarr v2, we need v3)

## Git

- Never use `git add -A` or `git add .` — always add specific files
- Only commit when explicitly asked
