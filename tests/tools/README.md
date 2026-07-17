# tests/tools — osmtogeojson comparison tooling

Tools for checking osm2geojson against [osmtogeojson](https://github.com/tyrasd/osmtogeojson)
(the JS converter used by overpass-turbo), which osm2geojson aims to stay
compatible with.

## compare_osmtogeojson.py

Runs the same OSM input through both converters, compares every feature's
geometry, benchmarks both sides, and optionally writes a self-contained HTML
report.

```bash
# one file, console output only
venv/bin/python tests/tools/compare_osmtogeojson.py tests/data/map.osm

# everything in tests/data, with an HTML report
venv/bin/python tests/tools/compare_osmtogeojson.py --html report.html \
    tests/data/*.osm tests/data/*.json
```

Requirements: the project venv (shapely) plus node/npm on PATH. On first run
the pinned `osmtogeojson` version from `package.json` is npm-installed into
`tests/tools/node_modules` (gitignored) automatically.

### What it does

* **Inputs**: `.osm`/`.xml` files go through `xml2geojson`, `.json` (Overpass
  API responses) through `json2geojson`. The JS side runs in a single node
  process (`osmtogeojson_runner.js`) with `flatProperties: false`, so features
  can be matched by (element type, id). `osmtogeojson-fixtures.json` is
  skipped automatically — it is recorded test data, not an OSM input.
* **Geometry verdict** per feature, compared with shapely:
  * `identical` — topologically equal (`.equals()`; ring/vertex order and
    Polygon vs single-polygon MultiPolygon wrapping are ignored)
  * `close` — same geometry type and Hausdorff distance ≤ `--tolerance`
    (default 1e-7°, roughly 1 cm)
  * `different` — anything else, including features present on only one side
* **Assessment**: each divergence is classified as *expected* (a known
  intentional difference between the libraries, with the reason stated) or
  *UNEXPECTED*. The rules live in `explain_difference()` and mirror
  `KNOWN_DIFFERENCES` in `tests/test_osmtogeojson_compat.py`:
  * relations whose `type` tag is not multipolygon/boundary/route/waterway:
    osm2geojson emits a merged feature, osmtogeojson emits none
  * relation-member ways without own tags in full-geometry (`out geom`)
    responses: osm2geojson filters them (`filter_used_refs`), osmtogeojson
    emits them as duplicate standalone features
  * invalid or degenerate geometry (null coordinates, zero-area rings):
    osmtogeojson emits it verbatim, osm2geojson only outputs valid GeoJSON
  * `close` verdicts — within tolerance by definition (typically the same
    vertices assembled into rings differently)

  **On new data, "UNEXPECTED" is the actionable signal** — either a bug in
  osm2geojson or a new intentional difference that should be added to the
  rules (and to the compat suite).
* **Benchmark**: `--runs` (default 5) timed conversions per converter per
  file — parse + convert from the input string, after one untimed warmup —
  reported as medians. JS timings exclude node startup. Sub-0.05 ms medians
  are treated as timer noise (no ratio is reported).
* **Per-file status**: `OK` (all identical/close), `KNOWN DIFFERENCES` (all
  divergence explained), `DIVERGED` (something unexpected), `ERROR` (either
  converter failed; other files still run).

### Options

| Flag | Meaning |
|------|---------|
| `--tolerance DEG` | max Hausdorff distance to call geometries `close` (default 1e-7) |
| `--runs N` | timed conversion runs per converter per file (default 5) |
| `--html PATH` | write an HTML report (summary table with timing bars, per-file detail tables; light/dark aware, no external assets) |
| `-v, --verbose` | also list identical features on the console |

Exit code is 0 when every feature is identical, close, or an expected
difference — so the script can gate CI or a release check.

## osmtogeojson_runner.js

Helper used by the script above: reads a JSON config on stdin, converts and
benchmarks all files in one node process, writes results to stdout. Not meant
to be run by hand.

## extract_osmtogeojson_fixtures.js

Extractor that produces `tests/data/osmtogeojson-fixtures.json` from
osmtogeojson's own test suite (running it against the same osmtogeojson
version regenerates the checked-in file byte-identically); see the header
comment in the file and the docstring of `tests/test_osmtogeojson_compat.py`. It resolves the library and
its test suite relative to its own location, so copy it into an osmtogeojson
checkout and run it there:

```bash
git clone https://github.com/tyrasd/osmtogeojson && cd osmtogeojson
npm install
cp /path/to/osm2geojson/tests/tools/extract_osmtogeojson_fixtures.js .
node extract_osmtogeojson_fixtures.js \
    /path/to/osm2geojson/tests/data/osmtogeojson-fixtures.json
```
