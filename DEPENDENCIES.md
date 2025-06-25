# Dependency Management

This project supports both modern and traditional Python dependency management approaches:

## For Users

- **Modern Approach**: Use `pip install git+https://github.com/jsbattig/code-indexer.git` (dependencies automatically resolved from `pyproject.toml`)
- **Traditional Approach**: Use `pip install -r requirements.txt` for production dependencies only

## For Developers

- **Modern Approach (Recommended)**: `pip install -e ".[dev]"` (includes dev dependencies from `pyproject.toml`)
- **Traditional Approach**: `pip install -r requirements-dev.txt && pip install -e .`

## Files

- `pyproject.toml` - Modern Python project configuration (primary source of truth)
- `requirements.txt` - Production dependencies (generated from pyproject.toml)
- `requirements-dev.txt` - Development dependencies (includes requirements.txt + dev tools)

Both approaches install the same dependencies. Use whichever fits your workflow better.