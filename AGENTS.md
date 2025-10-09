# Agent Instructions for xarray-ome

## Project Context

**ALWAYS read `plan.md` first** to understand the project's goals, architecture decisions, and implementation approach before making any code changes.

xarray-ome provides an xarray backend for reading and writing OME-Zarr (OME-NGFF) files. We use **ngff-zarr** as the foundation for OME-Zarr I/O operations, and focus on the xarray integration layer.

## Architecture

```text
User Code → xarray-ome API → Coordinate Translation → ngff-zarr → zarr → Storage
```

- **ngff-zarr**: Handles OME-Zarr spec parsing, zarr I/O, metadata validation
- **xarray-ome**: Converts OME-NGFF transforms ↔ xarray coordinates, builds DataTree/Dataset structures

## Module Structure

- `reader.py`: `open_ome_datatree()`, `open_ome_dataset()` - read OME-Zarr into xarray
- `writer.py`: `write_ome_datatree()`, `write_ome_dataset()` - write xarray to OME-Zarr
- `transforms.py`: Coordinate transformation logic (OME-NGFF ↔ xarray)

## Current Status

Branch: `implement-ngff-zarr-integration`

**Completed:**

- OME-NGFF v0.1-v0.5 support (read all, write v0.4-v0.5 via ngff-zarr)
- Core reading functionality (open_ome_dataset, open_ome_datatree)
- Coordinate transformation logic (transforms_to_coords, coords_to_transforms)
- Writing functionality (write_ome_dataset, write_ome_datatree)
- Comprehensive test suite (42 tests: reading, writing, transforms, backend, integration)
- Xarray backend integration (engine="ome-zarr")
- Complete Sphinx documentation with MyST Markdown
- Integration tests with real IDR sample data

**Future Enhancements:**

- HCS plate structure support
- Performance optimizations
- Integration with visualization tools
- Additional metadata validation options

## Code Style Guidelines

### Follow Idiomatic Python Best Practices

- Use pythonic patterns and conventions
- Follow PEP 8 style guidelines (enforced by ruff)
- Write clear, readable code that speaks for itself
- Use meaningful variable and function names
- Follow established patterns in the existing codebase

### Comments Policy

**DO NOT leave excessive comments in code.**

- Write self-documenting code with clear names and structure
- Only add comments when absolutely necessary to explain complex logic or non-obvious decisions
- Prefer docstrings for functions/classes over inline comments
- Trust that the code itself tells the story

### Code Quality Standards

- All code must pass pre-commit hooks (ruff, mypy, etc.)
- Follow the existing project structure and patterns
- Use type hints appropriately (mypy strict mode enabled)
- Write tests for new functionality
- Keep functions and classes focused and single-purpose

## Development Workflow

1. Read `plan.md` to understand context
2. Check existing code patterns before implementing
3. Write clean, self-documenting code
4. Ensure all linting and type checking passes
5. Use uv for environment management: `uv run python`, `uv run pytest`

## Git Workflow

**NEVER use indiscriminate git adds like `git add -A` or `git add .`**

- Always be specific with git add commands
- Add files individually or by directory: `git add file1.py file2.py` or `git add src/`
- Review changes with `git status` and `git diff` before staging
- This prevents accidentally committing unintended files

## Key References

- OME-NGFF spec: <https://ngff.openmicroscopy.org/latest/>
- ngff-zarr docs: <https://ngff-zarr.readthedocs.io/>
- xarray-ome-ngff (coordinate logic reference): <https://github.com/JaneliaSciComp/xarray-ome-ngff>
