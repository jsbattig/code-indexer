# Contributing to CIDX

Thank you for considering contributing to CIDX! This guide will help you set up your development environment and understand our development workflow.

## Development Setup

### Prerequisites

- Python 3.9 or higher
- Git
- VoyageAI API key (for testing semantic search features)

### Initial Setup

1. **Fork and clone the repository**

   ```bash
   git clone https://github.com/YOUR_USERNAME/code-indexer.git
   cd code-indexer
   ```

2. **Install development dependencies**

   ```bash
   pip install -e ".[dev]"
   ```

   This installs CIDX in editable mode with all development dependencies including:
   - pytest (testing framework)
   - mypy (type checking)
   - ruff (linting and formatting)
   - pre-commit (git hooks)

3. **Install pre-commit hooks** (CRITICAL)

   ```bash
   pre-commit install
   ```

   This installs git hooks that automatically check your code before each commit. **All contributors must install these hooks** to ensure code quality.

### Pre-commit Hooks

All commits are automatically validated for:

- **Linting**: Ruff checks for code quality issues and auto-fixes many of them
- **Formatting**: Ruff-format ensures consistent code style (replaces black)
- **Type Checking**: Mypy validates type annotations on `src/` code
- **Standard Checks**: Trailing whitespace, EOF newlines, YAML syntax, etc.

**What happens when you commit:**

```bash
git add my_changes.py
git commit -m "Add feature"
# Pre-commit hooks run automatically
# If checks fail, files are auto-fixed when possible
# Re-stage and commit again:
git add my_changes.py
git commit -m "Add feature"
```

**Manual pre-commit execution:**

```bash
# Run on all files (useful after pulling changes)
pre-commit run --all-files

# Run on staged files only
pre-commit run
```

**Emergency bypass** (use sparingly):

```bash
# Only use for urgent fixes, will be caught in CI
git commit --no-verify -m "emergency fix"
```

## Code Quality Standards

### Perfect Linting

CIDX maintains **zero linting errors**:

- Ruff: 0 errors
- Mypy: 0 errors (on `src/` code)
- Black/Ruff-format: All files formatted consistently

Pre-commit hooks enforce this automatically, but you can check manually:

```bash
# Check linting
ruff check src/ tests/

# Check type errors
mypy src/

# Format code
ruff format src/ tests/
```

### Type Annotations

- All functions in `src/` should have type annotations
- Use `from typing import` for type hints
- Use `cast()` when mypy needs help inferring types
- Tests (`tests/`) don't require full type annotations

### Code Style

- Follow PEP 8 (enforced by ruff)
- Use descriptive variable names
- Keep functions focused and small
- Document complex logic with comments

## Testing

### Running Tests

CIDX has multiple test suites optimized for different scenarios:

```bash
# Fast unit tests (~6-7 minutes)
./fast-automation.sh

# Server-specific tests
./server-fast-automation.sh

# Complete integration tests (~10+ minutes)
./full-automation.sh
```

**During development**, run targeted tests:

```bash
# Run specific test file
pytest tests/unit/test_something.py -v

# Run specific test function
pytest tests/unit/test_something.py::test_function_name -v

# Run tests matching pattern
pytest tests/ -k "test_scip" -v
```

### Writing Tests

- Use pytest for all tests
- Follow existing test patterns in the codebase
- Test files go in `tests/unit/`, `tests/integration/`, or `tests/e2e/`
- Mock external dependencies (VoyageAI API, network calls)
- Aim for >85% code coverage for new features

### Test Organization

- `tests/unit/` - Fast unit tests, no external dependencies
- `tests/integration/` - Tests requiring multiple components
- `tests/e2e/` - End-to-end workflow tests
- `tests/server/` - Server-specific tests

## Development Workflow

### Making Changes

1. **Create a feature branch**

   ```bash
   git checkout -b feature/your-feature-name
   ```

2. **Make your changes**
   - Write code following quality standards
   - Add/update tests as needed
   - Update documentation if needed

3. **Run tests locally**

   ```bash
   ./fast-automation.sh
   ```

4. **Commit your changes**

   ```bash
   git add .
   git commit -m "Add feature: description"
   # Pre-commit hooks run automatically
   ```

5. **Push to your fork**

   ```bash
   git push origin feature/your-feature-name
   ```

6. **Open a Pull Request**
   - Describe what you changed and why
   - Reference any related issues
   - Ensure CI checks pass

### Commit Messages

Use clear, descriptive commit messages:

```
feat: add semantic search caching
fix: resolve SCIP index corruption on Windows
docs: update installation guide for Python 3.12
refactor: simplify query parameter parsing
test: add coverage for temporal search edge cases
```

**Prefixes:**
- `feat:` - New feature
- `fix:` - Bug fix
- `docs:` - Documentation changes
- `refactor:` - Code refactoring
- `test:` - Test additions/changes
- `chore:` - Build/tooling changes

## Pull Request Process

1. **Ensure all checks pass**
   - Pre-commit hooks: ✅
   - Tests: ✅ (fast-automation.sh)
   - Type checking: ✅ (mypy)
   - Linting: ✅ (ruff)

2. **Update documentation**
   - Update README.md if adding user-facing features
   - Add docstrings to new functions/classes
   - Update relevant guides in `docs/`

3. **Keep PRs focused**
   - One feature/fix per PR
   - Split large changes into smaller PRs
   - Avoid mixing refactoring with feature work

4. **Respond to feedback**
   - Address reviewer comments
   - Push additional commits to the same branch
   - Request re-review when ready

## Code Review Guidelines

When reviewing PRs:

- Check code quality and adherence to standards
- Verify tests cover new functionality
- Ensure documentation is updated
- Test locally if needed
- Be constructive and respectful

## Project Structure

```
code-indexer/
├── src/code_indexer/       # Main source code
│   ├── cli.py              # CLI entry point
│   ├── daemon/             # Daemon mode implementation
│   ├── scip/               # SCIP code intelligence
│   ├── server/             # Multi-user server
│   └── services/           # Core services
├── tests/                  # Test suite
│   ├── unit/               # Unit tests
│   ├── integration/        # Integration tests
│   ├── e2e/                # End-to-end tests
│   └── server/             # Server tests
├── docs/                   # Documentation
└── scripts/                # Utility scripts
```

## Getting Help

- **Questions**: Open a [GitHub Discussion](https://github.com/jsbattig/code-indexer/discussions)
- **Bugs**: Report via [GitHub Issues](https://github.com/jsbattig/code-indexer/issues)
- **Features**: Suggest via [GitHub Issues](https://github.com/jsbattig/code-indexer/issues)

## License

By contributing, you agree that your contributions will be licensed under the MIT License.

---

**Thank you for contributing to CIDX!**
