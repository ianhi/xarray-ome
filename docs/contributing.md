# Contributing Guide

We welcome contributions to xarray-ome! This guide will help you get started.

## Development Setup

### Prerequisites

- Python 3.11 or later
- [uv](https://github.com/astral-sh/uv) for dependency management

### Clone and Setup

```bash
# Clone the repository
git clone https://github.com/your-org/xarray-ome.git
cd xarray-ome

# Install dependencies (uv will create a virtual environment)
uv sync

# Install pre-commit hooks
uv run pre-commit install
```

## Project Structure

```text
xarray-ome/
├── xarray_ome/           # Main package
│   ├── __init__.py       # Package exports
│   ├── reader.py         # Reading functions
│   ├── writer.py         # Writing functions
│   ├── transforms.py     # Coordinate transformations
│   ├── backend.py        # Xarray backend integration
│   └── _store_utils.py   # Store type detection
├── tests/                # Test suite
├── examples/             # Example scripts
├── docs/                 # Documentation
├── plan.md              # Implementation plan
├── AGENTS.md            # AI assistant instructions
└── pyproject.toml       # Project configuration
```

## Development Workflow

### Making Changes

1. **Create a branch** for your feature or fix:

   ```bash
   git checkout -b feature-name
   ```

2. **Make your changes** following our code style guidelines

3. **Run tests**:

   ```bash
   uv run pytest
   ```

4. **Run type checking**:

   ```bash
   uv run mypy xarray_ome/
   ```

5. **Format and lint**:

   ```bash
   uv run ruff check xarray_ome/
   uv run ruff format xarray_ome/
   ```

6. **Commit your changes**:

   ```bash
   git add specific-files.py
   git commit -m "Descriptive commit message"
   ```

Pre-commit hooks will automatically run linting and formatting checks.

## Code Style Guidelines

### Follow Idiomatic Python

- Use pythonic patterns and conventions
- Follow PEP 8 style guidelines (enforced by ruff)
- Write clear, readable, self-documenting code
- Use meaningful variable and function names

### Comments Policy

**DO NOT leave excessive comments in code.**

- Write self-documenting code with clear names and structure
- Only add comments when necessary to explain complex logic
- Prefer docstrings for functions/classes over inline comments
- Trust that the code itself tells the story

### Type Hints

All functions must have type hints:

```python
def open_ome_dataset(
    path: str | Path,
    resolution: int = 0,
    validate: bool = False,
) -> xr.Dataset:
    """Function docstring."""
    ...
```

### Docstrings

Use numpy-style docstrings:

```python
def function_name(param1: str, param2: int) -> bool:
    """
    Short description.

    Longer description if needed.

    Parameters
    ----------
    param1 : str
        Description of param1
    param2 : int
        Description of param2

    Returns
    -------
    bool
        Description of return value

    Raises
    ------
    ValueError
        When this error occurs

    Examples
    --------
    >>> function_name("test", 42)
    True
    """
```

## Git Workflow

### Branch Naming

- `feature/description` - New features
- `fix/description` - Bug fixes
- `docs/description` - Documentation changes
- `refactor/description` - Code refactoring

### Commit Messages

Write clear, descriptive commit messages:

```text
Short summary (50 chars or less)

More detailed explanation if needed. Wrap at 72 characters.

- Bullet points are okay
- Use present tense ("Add feature" not "Added feature")
- Reference issues: "Fixes #123"
```

### Git Best Practices

**NEVER use indiscriminate git adds:**

```bash
# ❌ BAD
git add -A
git add .

# ✅ GOOD
git add file1.py file2.py
git add xarray_ome/reader.py
```

Always review changes before staging:

```bash
git status
git diff
```

## Testing

### Running Tests

```bash
# Run all tests
uv run pytest

# Run specific test file
uv run pytest tests/test_reader.py

# Run with coverage
uv run pytest --cov=xarray_ome --cov-report=html

# Run in parallel
uv run pytest -n auto
```

### Writing Tests

Place tests in the `tests/` directory:

```python
"""Test description."""

import pytest
from xarray_ome import open_ome_dataset


def test_open_dataset_local() -> None:
    """Test opening a local OME-Zarr file."""
    ds = open_ome_dataset("path/to/test.ome.zarr")
    assert "image" in ds.data_vars
    assert ds.dims["x"] > 0


def test_invalid_path() -> None:
    """Test that invalid path raises appropriate error."""
    with pytest.raises(FileNotFoundError):
        open_ome_dataset("nonexistent.ome.zarr")
```

## Documentation

### Building Documentation

```bash
# Install documentation dependencies
uv sync --group docs

# Build documentation
cd docs
make html

# View documentation
open _build/html/index.html
```

### Writing Documentation

- Use MyST Markdown for documentation files
- Include code examples that actually work
- Add docstrings to all public functions and classes
- Keep documentation up-to-date with code changes

## Pull Request Process

1. **Ensure all tests pass** and code is properly formatted
2. **Update documentation** if adding new features
3. **Add tests** for new functionality
4. **Update CHANGELOG.md** if applicable
5. **Create pull request** with clear description
6. **Address review feedback** promptly

### PR Description Template

```markdown
## Description
Brief description of changes

## Type of Change
- [ ] Bug fix
- [ ] New feature
- [ ] Documentation update
- [ ] Code refactoring

## Testing
How was this tested?

## Checklist
- [ ] Tests pass
- [ ] Type checking passes (mypy)
- [ ] Linting passes (ruff)
- [ ] Documentation updated
- [ ] CHANGELOG.md updated
```

## Architecture Guidelines

### Key Principles

1. **Leverage ngff-zarr**: Don't reimplement OME-Zarr spec parsing
2. **Focus on coordinates**: Core value is transforming OME-NGFF transforms ↔ xarray coordinates
3. **Preserve metadata**: Store full OME metadata in attrs for round-tripping
4. **Type safety**: All code must pass mypy strict type checking

### Adding New Features

Before implementing a new feature:

1. **Read `plan.md`** to understand project goals and architecture
2. **Check existing patterns** in the codebase
3. **Consider impact** on API and backward compatibility
4. **Discuss in an issue** if making significant changes

## Release Process

(For maintainers)

1. Update version in `pyproject.toml`
2. Update `CHANGELOG.md`
3. Create git tag: `git tag v0.1.0`
4. Push tag: `git push origin v0.1.0`
5. Build and publish: `uv build && uv publish`

## Getting Help

- **Issues**: [GitHub Issues](https://github.com/your-org/xarray-ome/issues)
- **Discussions**: [GitHub Discussions](https://github.com/your-org/xarray-ome/discussions)
- **Documentation**: [Read the Docs](https://xarray-ome.readthedocs.io/)

## Code of Conduct

We follow the [Contributor Covenant Code of Conduct](https://www.contributor-covenant.org/version/2/0/code_of_conduct/).
Please be respectful and constructive in all interactions.

## License

By contributing, you agree that your contributions will be licensed under the MIT License.
