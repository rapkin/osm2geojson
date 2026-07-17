# Changelog

Notable changes to osm2geojson. See `MIGRATION_NOTES.md` for upgrade help.

## 1.0.0 (unreleased)

First stable release. Output now closely matches osmtogeojson 3.0.0-beta.5
(the JS converter used by overpass-turbo), verified by a recorded
compatibility suite replaying osmtogeojson's own tests.

### ⚠️ Breaking: converted GeoJSON changed

The Python API is compatible apart from the items below, but the GeoJSON
produced for the same input is not:

- **More features**: nodes with own interesting tags (POIs) and elements
  referenced by relations (e.g. admin_centre nodes) are no longer filtered
  out; bbox-only (`out bb`) responses produce Polygon fallbacks.
- **Different geometry types**: `type=boundary` relations are assembled as
  MultiPolygon (was MultiLineString); an unclosed way tagged `area=yes` stays
  a LineString (was self-closed into a Polygon).
- **Different attribution**: old-style multipolygons (tags on the single
  outer way) are attributed to the outer way, like osmtogeojson.
- **Fewer duplicates**: elements returned twice by overlapping Overpass
  queries collapse into one feature.

### ⚠️ Breaking: API changes

- Converter options are keyword-only (`json2geojson(data, filter_used_refs=False)`).
- Converters no longer mutate the input data.
- `log_level` defaults to `None`: the library no longer reconfigures its
  logger on every call; use `logging.getLogger("osm2geojson")`.
- `ConversionError` replaces bare `Exception` for `raise_on_failure=True`.
- `overpass_call` accepts keyword-only `endpoint`, `timeout`, `retries`,
  `retry_delay`, and retries only what can succeed: rate limiting (429),
  transient server errors (5xx), timeouts and connection errors are retried;
  client errors like 400 fail immediately (previously every non-200 was
  retried and network errors were not).
- Removed `read_data_file` and `retry_request_multi` from the public API.

### Fixed

- `filter_used_refs` compared ids across id-spaces, so a used node could
  delete an unrelated way/relation with the same numeric id.
- `out center` / `out bb` responses: `<center>` is parsed from XML and
  way-level `<bounds>` are kept.
- Nodes without coordinates and member geometry containing null no longer
  crash the conversion; tainted ways degrade to partial geometry instead of
  being dropped.
- Overpass API requests send an identifying User-Agent (overpass-api.de
  rejects generic clients with 406) and use a request timeout.
- CLI output keeps non-ASCII text (names, addresses) as readable UTF-8
  instead of \\uXXXX escapes, and file I/O uses UTF-8 explicitly regardless
  of the platform locale (stdout included - Windows consoles default to a
  legacy code page).
- The CLI module ran at import time (no `if __name__ == "__main__"` guard),
  so importing `osm2geojson.__main__` executed the converter and exited the
  interpreter; the `osm2geojson` console script only worked by accident.
- `--reader auto` now also sniffs the file content (`<` vs `{`) when the
  extension is not recognized, and a missing input file gets a proper error
  message instead of an argparse traceback.

### Added

- Compatibility test suite against osmtogeojson's recorded fixtures
  (`tests/test_osmtogeojson_compat.py`), with intentional differences
  pinned and explained.
- Comparison/benchmark tool (`tests/tools/compare_osmtogeojson.py`): runs
  any OSM file through both converters, classifies every geometry difference
  as expected (with reason) or unexpected, and writes an HTML report.
- `py.typed` marker: type checkers now use the package's annotations.

## 0.3.2 and earlier

See the git history and GitHub releases:
https://github.com/rapkin/osm2geojson/releases
