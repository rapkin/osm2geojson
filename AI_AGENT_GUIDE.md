# AI Agent Development Guide

**Target Audience**: AI Coding Assistants (Claude, GPT-4, Cursor, etc.)
**Last Updated**: 2025-10-16
**Project**: osm2geojson - OSM to GeoJSON Converter

> **Quick Reference**: See [`.cursorrules`](.cursorrules) for compact reference
> **Human Docs**: See [CONTRIBUTING.md](CONTRIBUTING.md) for developer guide

---

## 🎯 Quick Context

You are working on **osm2geojson**, a Python library that converts OpenStreetMap (OSM) data and Overpass API responses into GeoJSON format. The library handles complex geometry processing, including multipolygons, relations, and area detection.

### Core Purpose
Transform OSM XML/JSON → Shapely Geometries → GeoJSON Features

### Tech Stack
- **Language**: Python 3.8+
- **Key Libraries**: Shapely (geometry), Requests (HTTP)
- **Tools**: Ruff (lint/format), pytest (test), mypy (types)
- **Build**: pyproject.toml (PEP 621), `python -m build`
- **Commands**: All via `Makefile` - **always use `make` commands**

---

## 🚀 Essential Commands

**Always use Make commands** - they're the project standard:

```bash
make setup          # One-time setup (install deps + hooks)
make all            # Format, lint, type-check, test (run before committing)
make format         # Auto-format with Ruff
make lint           # Check code quality
make test           # Run test suite
make test-coverage  # Tests with coverage report
```

### Command Priority
1. **Before any commit**: `make all`
2. **After editing code**: `make format`
3. **To verify changes**: `make test`

---

## 📁 Project Structure

```
osm2geojson/
├── osm2geojson/              # Main package
│   ├── __init__.py          # Public API exports
│   ├── main.py              # Core conversion logic ⭐
│   ├── parse_xml.py         # XML parsing utilities
│   ├── helpers.py           # Helper functions
│   ├── __main__.py          # CLI interface
│   ├── *.json               # Config files (area keys, polygon features)
├── tests/                    # Test suite
│   ├── conftest.py          # Pytest fixtures
│   ├── test_main.py         # Main conversion tests
│   ├── test_parse_xml.py    # XML parser tests
│   ├── test_polygon_logic.py # Polygon detection tests
│   └── data/                # Test data (OSM/JSON/GeoJSON pairs)
├── pyproject.toml           # Project config ⭐⭐⭐
├── Makefile                 # Development commands
├── CONTRIBUTING.md          # Contributor guide
├── DEVELOPMENT_QUICKSTART.md # Command reference
└── AI_AGENT_GUIDE.md        # This file
```

**⭐ = Critical files to understand**

---

## 🧠 Key Concepts

### 1. Shape Objects
The internal data structure used throughout:

```python
shape_obj = {
    'shape': Point|LineString|Polygon|MultiPolygon,  # Shapely geometry
    'properties': {
        'type': 'node'|'way'|'relation',
        'id': int,
        'tags': {...},  # OSM tags
        # ... other metadata
    }
}
```

### 2. Polygon Detection
Complex logic determines if an OSM feature should be a polygon. **Precedence order**:

1. ✅ `area=no` → **NEVER** polygon (highest priority)
2. ✅ `area=yes` → **ALWAYS** polygon
3. ✅ `type=multipolygon` → polygon
4. 🔍 **Blacklist check** → If tag/value is blacklisted, NOT polygon
5. 🔍 **Whitelist check** → If tag/value is whitelisted, IS polygon
6. 🔍 **"all" rule check** → If tag has "all" rule, IS polygon
7. ❌ **Default** → NOT polygon

**Location**: `is_geometry_polygon()` in `main.py:396`

### 3. Coordinate System
- OSM: `lon, lat` (longitude first)
- GeoJSON: `lon, lat` (same)
- Shapely: `x, y` (which is lon, lat)
- **Always use**: `[lon, lat]` or `Point(lon, lat)`

### 4. References Index
OSM data uses references between elements (ways reference nodes, relations reference ways/nodes):

```python
refs_index = {
    'node/123': {...},    # Node object
    'way/456': {...},     # Way object
    'relation/789': {...} # Relation object
}
```

Built by `build_refs_index()`, used throughout for lookups.

---

## 📝 Code Style Guide

### Type Hints (Gradual Adoption)
```python
# DO add type hints to new functions
def process_element(el: dict, refs_index: dict, raise_on_failure: bool = False) -> Optional[dict]:
    ...

# Use Optional for nullable types
def get_ref(ref_el: dict, refs_index: dict, silent: bool = False) -> Optional[dict]:
    ...

# Complex types
from typing import List, Dict, Optional, Any
def parse_members(members: List[dict]) -> Dict[str, Any]:
    ...
```

### Docstrings (Google Style)
```python
def way_to_shape(
    way: dict,
    refs_index: dict = None,
    area_keys: Optional[dict] = None,
    raise_on_failure: bool = False
) -> Optional[dict]:
    """Convert an OSM way to a shape object.

    Args:
        way: OSM way element dictionary.
        refs_index: Index of referenced elements.
        area_keys: Custom area key configuration.
        raise_on_failure: Whether to raise exceptions on errors.

    Returns:
        Shape object with geometry and properties, or None if conversion fails.

    Raises:
        Exception: If raise_on_failure is True and conversion fails.
    """
    ...
```

### Error Handling Pattern
```python
def process_something(data, raise_on_failure=False):
    try:
        result = do_work(data)
        return result
    except Exception as e:
        message = f"Failed to process: {e}"
        warning(message)  # Log warning
        if raise_on_failure:
            raise Exception(message)  # Re-raise if requested
        return None  # Graceful failure by default
```

### Logging
```python
from logging import getLogger
logger = getLogger(__name__)

logger.debug('Detailed debug info')    # Verbose
logger.info('Important event')         # Normal
logger.warning('Something unexpected')  # Concerning
logger.error('Failed operation')       # Error
```

---

## 🧪 Testing Strategy

### Test File Pairs
Tests use paired files in `tests/data/`:
- `*.osm` - OSM XML input
- `*.json` - Overpass JSON input
- `*.geojson` - Expected GeoJSON output

**Pattern**: Convert input → Compare to expected output

### Writing Tests

**Using pytest** (preferred for new tests):
```python
def test_feature(get_json_and_geojson):
    """Test that feature X works correctly."""
    data, expected = get_json_and_geojson('test-case-name')
    result = json2geojson(data)
    assert result == expected
```

**Using unittest** (legacy, still supported):
```python
class TestSomething(unittest.TestCase):
    def test_feature(self):
        """Test that feature X works correctly."""
        data, expected = get_json_and_geojson_data('test-case-name')
        result = json2geojson(data)
        self.assertDictEqual(expected, result)
```

### Test Fixtures (pytest)
Available in `tests/conftest.py`:
- `read_data_file(filename)` - Read test data file
- `load_json_data(filename)` - Load JSON file
- `get_osm_and_geojson(name)` - Get OSM XML + GeoJSON pair
- `get_json_and_geojson(name)` - Get JSON + GeoJSON pair

### osmtogeojson Compatibility
Compatibility with the JS converter [osmtogeojson](https://github.com/tyrasd/osmtogeojson)
is tested by `tests/test_osmtogeojson_compat.py` (part of the normal test run).
To compare/benchmark both converters on arbitrary OSM files (needs node/npm):

```bash
venv/bin/python tests/tools/compare_osmtogeojson.py --html report.html tests/data/*.osm
```

It reports each geometry difference as expected (known intentional difference,
with reason) or UNEXPECTED — treat UNEXPECTED as a bug until proven otherwise.
See `tests/tools/README.md`.

---

## 🔧 Common Tasks

### Task 1: Fix a Bug

1. **Understand the issue**
   ```bash
   # Find related tests
   grep -r "test_name" tests/

   # Run specific test
   pytest tests/test_main.py::test_specific -v
   ```

2. **Write failing test** (if not exists)
   ```python
   def test_bug_fix_for_issue_123():
       """Regression test for issue #123."""
       data = {...}  # Minimal reproduction
       result = json2geojson(data)
       assert result['features'][0]['geometry']['type'] == 'Polygon'
   ```

3. **Fix the code**
   - Edit relevant file in `osm2geojson/`
   - Follow existing patterns
   - Add comments for complex logic

4. **Verify fix**
   ```bash
   make format      # Format code
   make test        # Run all tests
   make all         # Full verification
   ```

### Task 2: Add a Feature

1. **Design the API**
   ```python
   # In osm2geojson/main.py
   def new_feature(data, option=False):
       """New feature description."""
       ...
   ```

2. **Add to public API**
   ```python
   # In osm2geojson/__init__.py
   __all__ = [
       ...,
       'new_feature',  # Add here
   ]
   ```

3. **Write tests first** (TDD approach)
   ```python
   def test_new_feature():
       result = new_feature(test_data)
       assert result == expected
   ```

4. **Implement**
   - Follow existing patterns
   - Add type hints
   - Add docstrings
   - Handle errors gracefully

5. **Document**
   - Update `README.md` if public API
   - Add examples
   - Update CONTRIBUTING.md if needed

### Task 3: Refactor Code

1. **Ensure tests pass**
   ```bash
   make test  # Baseline
   ```

2. **Make changes incrementally**
   - Small, focused commits
   - One thing at a time
   - Keep tests passing

3. **Verify no regression**
   ```bash
   make all   # After each change
   ```

4. **Update documentation**
   - Code comments
   - Docstrings
   - External docs if API changed

---

## ⚠️ Common Pitfalls & Solutions

### Pitfall 1: Pre-commit Hooks Fail

**Symptom**: Can't commit because hooks fail

**Solution**:
```bash
# Fix automatically
make format

# Or bypass (only if absolutely necessary)
git commit --no-verify -m "WIP: work in progress"

# Then fix later
make format
git add .
git commit -m "fix: apply linting"
```

### Pitfall 2: Linting Errors

**Symptom**: `make lint` shows errors

**Solution**:
```bash
# Auto-fix what's possible
ruff check --fix .

# If still failing, errors need manual fix
ruff check .  # See specific issues

# Last resort: add to ignore list in pyproject.toml
```

### Pitfall 3: Test Failures

**Symptom**: `make test` fails

**Solution**:
```bash
# Run specific failing test with verbose output
pytest tests/test_main.py::test_name -vv --tb=short

# Check if test data changed
git diff tests/data/

# Debug with print statements (then remove them)
pytest tests/test_main.py::test_name -s  # -s shows print()
```

### Pitfall 4: Type Checking Errors

**Symptom**: `make type-check` fails

**Solution**:
```bash
# Check specific file
mypy osm2geojson/main.py

# Common fixes:
# - Add type hints: def func(x: int) -> str:
# - Use Optional: Optional[dict] for nullable
# - Add type: ignore comment (last resort)
result = complex_call()  # type: ignore
```

### Pitfall 5: Submodule Issues

**Symptom**: Missing files in `osm-polygon-features/` or `id-area-keys/`

**Solution**:
```bash
# Initialize submodules
git submodule update --init --recursive

# Update to latest
./update-osm-polygon-features.sh
```

---

## 🎨 Best Practices

### DO ✅

- **Use Make commands** for all tasks
- **Run `make all`** before committing
- **Add tests** for new features
- **Follow existing patterns** in the codebase
- **Add type hints** to new functions
- **Write docstrings** for public functions
- **Keep commits atomic** and well-described
- **Handle errors gracefully** with try/except
- **Log warnings** instead of crashing

### DON'T ❌

- **Don't edit submodule files** (osm-polygon-features/, id-area-keys/)
- **Don't commit without testing** (`make test`)
- **pyproject.toml is the single source** for all config (no setup.py)
- **Don't commit** `__pycache__`, `*.pyc`, `dist/`
- **Don't force push** to main/master
- **Don't change too much at once** - small PRs
- **Don't ignore test failures** - fix them
- **Don't skip documentation** updates

---

## 🔍 Debugging Techniques

### Debug Failing Test
```bash
# Verbose output
pytest tests/test_main.py::test_name -vv

# Show print statements
pytest tests/test_main.py::test_name -s

# Drop into debugger on failure
pytest tests/test_main.py::test_name --pdb

# Show locals on failure
pytest tests/test_main.py::test_name --showlocals
```

### Debug Conversion Logic
```python
# Enable debug logging
geojson = xml2geojson(xml_data, log_level='DEBUG')

# Or in code
import logging
logging.basicConfig(level=logging.DEBUG)
```

### Check What Ruff Would Change
```bash
# See diff without applying
ruff format --diff osm2geojson/main.py

# Check specific rules
ruff check --select=E,F osm2geojson/
```

---

## 📚 Additional Resources

### Project Documentation (Read These!)
| File | Purpose | When to Read |
|------|---------|--------------|
| [`.cursorrules`](.cursorrules) | Quick reference | First time, quick checks |
| [CONTRIBUTING.md](CONTRIBUTING.md) | Developer guide + commands | Daily use, understanding workflow |
| [MIGRATION_NOTES.md](MIGRATION_NOTES.md) | Old → New | Migrating from old setup |
| [MODERNIZATION.md](MODERNIZATION.md) | What changed | Understanding updates |

### External Resources
- [Shapely Docs](https://shapely.readthedocs.io/) - Geometry operations
- [OSM Wiki](https://wiki.openstreetmap.org/) - OSM data format
- [GeoJSON Spec](https://geojson.org/) - Output format
- [Ruff Docs](https://docs.astral.sh/ruff/) - Linter configuration

---

## 🤖 AI-Specific Tips

### When Reading Code
1. Start with `osm2geojson/__init__.py` - see public API
2. Read function docstrings first
3. Check tests for usage examples
4. Look at `tests/data/` for real examples

### When Writing Code
1. Always format after editing: `make format`
2. Check existing similar functions first
3. Copy patterns from existing code
4. Add docstrings immediately
5. Run tests frequently: `make test`

### When Stuck
1. Read related tests
2. Check `tests/data/` for examples
3. Search codebase: `grep -r "pattern" osm2geojson/`
4. Look at recent commits: `git log --oneline | head -20`

### Communication Tips
- Be specific about what you changed
- Reference files and line numbers
- Show before/after examples
- Explain "why" not just "what"

---

## ⚡ Checklist Before Committing

```bash
✅ Code formatted: make format
✅ Tests pass: make test
✅ Linting clean: make lint
✅ Type checking: make type-check
✅ All checks: make all
✅ Docs updated (if API changed)
✅ Tests added (if new feature)
✅ Commit message clear
```

**Pro tip**: Just run `make all` - it does everything!

---

**Happy coding! 🚀**

*For questions, check `CONTRIBUTING.md` or open an issue.*
