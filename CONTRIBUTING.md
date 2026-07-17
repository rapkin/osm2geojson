# Contributing to osm2geojson

Thank you for your interest in contributing to osm2geojson!

**Quick Links**: [AI Guide](AI_AGENT_GUIDE.md) | [Migration Notes](MIGRATION_NOTES.md) | [Release Guide](RELEASE_GUIDE.md) | [Docs Index](docs/README.md)

---

## Quick Reference

```bash
# Setup (one-time)
git clone --recurse-submodules https://github.com/rapkin/osm2geojson.git
cd osm2geojson
make setup              # Install deps + pre-commit hooks

# Daily workflow
make format             # Auto-format code
make lint               # Check code quality
make test               # Run tests
make all                # Run all checks (before committing!)

# Debugging
pytest tests/test_main.py::test_name -vv    # Run specific test
pytest --pdb                                 # Debug on failure
ruff check --diff .                          # See what would change
```

---

## Development Setup

### Prerequisites
- Python 3.8 or higher
- Git

### Installation

```bash
# Clone with submodules
git clone --recurse-submodules https://github.com/rapkin/osm2geojson.git
cd osm2geojson

# Complete setup (one command)
make setup
```

This will:
- Install package in editable mode with dev dependencies
- Install pre-commit hooks (auto-format on commit)

**Manual setup** (if needed):
```bash
pip install -e ".[dev]"
pre-commit install
```

### Verify Installation
```bash
make test              # Should pass all tests
```

---

## Development Workflow

### Making Changes

1. **Create a branch**
   ```bash
   git checkout -b feature/your-feature-name
   # or: git checkout -b fix/bug-description
   ```

2. **Make changes**
   - Edit code
   - Add/update tests
   - Update documentation if needed

3. **Format & test**
   ```bash
   make format        # Auto-format
   make test          # Verify tests pass
   ```

4. **Commit**
   ```bash
   git add .
   git commit -m "feat: your change description"
   # Pre-commit hooks run automatically
   ```

5. **Push & create PR**
   ```bash
   git push origin feature/your-feature-name
   # Then create Pull Request on GitHub
   ```

### Before Committing
**Always run:**
```bash
make all    # Formats, lints, type-checks, and tests
```

### Commit Message Format
```
type: description

Types: feat, fix, docs, style, refactor, test, chore
Examples:
  feat: add support for custom polygon features
  fix: handle empty geometry collections
  docs: update README with new examples
```

---

## Code Quality

All tools are configured in `pyproject.toml`.

### Commands
```bash
make format         # Auto-format with Ruff
make lint           # Lint with Ruff
make type-check     # Type check with mypy
make all            # All checks
```

### Standards
- **Line length**: 100 characters
- **Formatter**: Ruff (replaces Black, isort, flake8)
- **Type hints**: Optional, add to new code
- **Docstrings**: Google style for public functions

---

## Testing

### Running Tests

```bash
# Run all tests
make test
# or: pytest

# With coverage
make test-coverage
# or: pytest --cov=osm2geojson --cov-report=html

# Specific tests
pytest tests/test_main.py                        # File
pytest tests/test_main.py::TestClass::test_name  # Specific test
pytest -k test_barrier                           # By pattern
pytest -vv                                       # Verbose
pytest -s                                        # Show print statements
pytest --pdb                                     # Drop into debugger
```

### Writing Tests

Tests use paired files in `tests/data/`:
- `*.osm` / `*.json` - Input data
- `*.geojson` - Expected output

**Pattern**: Convert input → Compare to expected

**Example with pytest** (preferred):
```python
def test_new_feature(get_json_and_geojson):
    """Test that feature X works correctly."""
    data, expected = get_json_and_geojson('test-case-name')
    result = json2geojson(data)
    assert result == expected
```

**Example with unittest** (legacy, still supported):
```python
def test_new_feature(self):
    data, expected = get_json_and_geojson_data('test-case-name')
    result = json2geojson(data)
    self.assertEqual(expected, result)
```

### Available Fixtures
See `tests/conftest.py` for pytest fixtures:
- `read_data_file(filename)`
- `get_osm_and_geojson(name)`
- `get_json_and_geojson(name)`

### Comparing Against osmtogeojson

osm2geojson aims to stay compatible with [osmtogeojson](https://github.com/tyrasd/osmtogeojson)
(the JS converter used by overpass-turbo). Two layers check this:

- `tests/test_osmtogeojson_compat.py` — replays osmtogeojson's own test suite
  (recorded in `tests/data/osmtogeojson-fixtures.json`); runs as part of `make test`.
- `tests/tools/compare_osmtogeojson.py` — compares and benchmarks both converters
  on arbitrary OSM files and can write an HTML report (requires node/npm):

  ```bash
  venv/bin/python tests/tools/compare_osmtogeojson.py --html report.html \
      tests/data/*.osm tests/data/*.json
  ```

  Useful for checking geometry changes against real data before a release.
  See `tests/tools/README.md` for details.

---

## Code Style

### Type Hints
```python
from typing import Optional, List, Dict

def process_element(
    el: dict,
    refs_index: dict = None,
    raise_on_failure: bool = False
) -> Optional[dict]:
    """Process an OSM element."""
    ...
```

### Docstrings (Google Style)
```python
def function_name(param1: str, param2: int = 0) -> bool:
    """Short description.

    Longer description if needed.

    Args:
        param1: Description of param1.
        param2: Description of param2.

    Returns:
        Description of return value.

    Raises:
        ValueError: When something is invalid.
    """
    ...
```

### Error Handling Pattern
```python
def process(data, raise_on_failure=False):
    try:
        result = do_work(data)
        return result
    except Exception as e:
        message = f"Failed: {e}"
        warning(message)
        if raise_on_failure:
            raise Exception(message)
        return None
```

---

## Project Structure

```
osm2geojson/
├── osm2geojson/          # Main package
│   ├── main.py          # Core conversion logic
│   ├── parse_xml.py     # XML parsing
│   ├── helpers.py       # Helper functions
│   └── __main__.py      # CLI interface
├── tests/               # Test suite
│   ├── conftest.py      # Pytest fixtures
│   ├── test_*.py        # Test files
│   └── data/            # Test data (OSM/JSON/GeoJSON pairs)
├── pyproject.toml       # Project config
└── Makefile             # Development commands
```

**Don't edit**: `osm-polygon-features/`, `id-area-keys/` (git submodules)

---

## Common Tasks

### Update Submodules
```bash
./update-osm-polygon-features.sh
```

### Debugging Tests
```bash
# Verbose output with full tracebacks
pytest tests/test_main.py::test_name -vv --tb=long

# Show print statements
pytest tests/test_main.py::test_name -s

# Drop into debugger on failure
pytest tests/test_main.py::test_name --pdb
```

### Check Linting Issues
```bash
# See what would change
ruff format --diff .

# Auto-fix issues
ruff check --fix .

# Check specific file
ruff check osm2geojson/main.py
```

---

## Pull Request Process

1. **Ensure all checks pass**
   ```bash
   make all
   ```

2. **Update documentation** if needed
   - README.md for API changes
   - Docstrings for new functions
   - This file for workflow changes

3. **Add tests** for new features

4. **Create clear PR description**
   - What changed and why
   - Link related issues
   - Screenshots/examples if applicable

5. **Respond to review feedback**

---

## License

By contributing, you agree that your contributions will be licensed under the MIT License.

## Recognition

All contributors will be recognized in the project. Thank you! 🙏
