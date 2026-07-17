#!/usr/bin/env python3
"""Compare osm2geojson output against osmtogeojson (JS) for the same OSM input.

For each input file the script runs osm2geojson in-process and osmtogeojson
via node (tests/tools/osmtogeojson_runner.js, dependency auto-installed into
tests/tools/node_modules), matches features by (element type, id) and reports
per feature whether the geometries are:

  * identical - topologically equal (shapely .equals(); ring/vertex order and
    Polygon vs single-polygon MultiPolygon wrapping are ignored)
  * close     - same geometry type, Hausdorff distance <= --tolerance degrees
  * DIFFERENT - anything else (also: features present on only one side)

Each divergence is additionally assessed as expected (a known intentional
difference between the two libraries - see explain_difference and
tests/test_osmtogeojson_compat.py - with the reason stated) or UNEXPECTED.

Both converters are also benchmarked: --runs timed conversions each (parse +
convert from the input string, after one untimed warmup), reported as medians.

Usage:
    python tests/tools/compare_osmtogeojson.py tests/data/map.osm
    python tests/tools/compare_osmtogeojson.py --runs 10 --html report.html tests/data/*.json

Requires node/npm. Exit code is 0 when every feature is identical, close, or
an expected (known intentional) difference.
"""

import argparse
import html
import json
import statistics
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

from shapely.geometry import shape


TOOLS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS_DIR.parents[1]))

from osm2geojson import json2geojson, xml2geojson  # noqa: E402


# ---------------------------------------------------------------- converters


def input_type(path):
    return "json" if path.suffix == ".json" else "xml"


def ensure_js_deps():
    if (TOOLS_DIR / "node_modules" / "osmtogeojson").exists():
        return
    print("installing osmtogeojson into tests/tools/node_modules ...", file=sys.stderr)
    subprocess.run(
        ["npm", "install", "--no-fund", "--no-audit"],
        cwd=TOOLS_DIR,
        check=True,
        capture_output=True,
        text=True,
    )


def run_js(files, runs):
    """Convert + benchmark all files in one node process. -> {path: result}"""
    config = {
        "runs": runs,
        "files": [{"path": str(p), "type": input_type(p)} for p in files],
    }
    proc = subprocess.run(
        ["node", str(TOOLS_DIR / "osmtogeojson_runner.js")],
        input=json.dumps(config),
        capture_output=True,
        text=True,
        timeout=600,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"osmtogeojson runner failed:\n{proc.stderr.strip()}")
    return {r["path"]: r for r in json.loads(proc.stdout)["results"]}


def run_py(path, runs):
    """Convert + benchmark one file with osm2geojson. -> (geojson, times_ms)"""
    text = path.read_text()
    if input_type(path) == "json":
        convert = lambda: json2geojson(json.loads(text))  # noqa: E731
    else:
        convert = lambda: xml2geojson(text)  # noqa: E731
    geojson = convert()  # warmup; also the output used for comparison
    times_ms = []
    for _ in range(runs):
        t0 = time.perf_counter()
        convert()
        times_ms.append((time.perf_counter() - t0) * 1000)
    return geojson, times_ms


# ---------------------------------------------------------------- comparison


def feature_key(feature):
    props = feature.get("properties") or {}
    return (props.get("type"), str(props.get("id")))


def index_features(collection):
    idx = {}
    for feature in collection.get("features", []):
        idx.setdefault(feature_key(feature), []).append(feature)
    return idx


def to_shape(geometry):
    if geometry is None:
        return None
    try:
        return shape(geometry)
    except Exception:
        return None  # e.g. osmtogeojson can emit literal null coordinates


def unwrap(geom):
    if geom.geom_type in ("MultiPolygon", "MultiLineString", "MultiPoint") and len(geom.geoms) == 1:
        return geom.geoms[0]
    return geom


def compare_geometries(py_geom, js_geom, tolerance):
    """Return (verdict, detail) where verdict is identical/close/different."""
    if py_geom is not None and py_geom == js_geom:
        # structurally identical GeoJSON; also dodges GEOS-version-dependent
        # .equals() results on degenerate geometry (e.g. zero-length lines)
        return "identical", ""
    s_py, s_js = to_shape(py_geom), to_shape(js_geom)
    if s_py is None or s_js is None:
        if s_py is s_js:
            return "identical", "both empty"
        return (
            "different",
            f"py={py_geom and py_geom['type']} js={'invalid/null' if js_geom else None}",
        )
    if s_py.geom_type != s_js.geom_type:
        s_py, s_js = unwrap(s_py), unwrap(s_js)
    if s_py.equals(s_js):
        return "identical", ""
    if s_py.geom_type != s_js.geom_type:
        return "different", f"type py={s_py.geom_type} js={s_js.geom_type}"
    distance = max(s_py.hausdorff_distance(s_js), s_js.hausdorff_distance(s_py))
    if distance <= tolerance:
        return "close", f"hausdorff={distance:.2e}"
    return "different", f"hausdorff={distance:.2e}"


# relation types both libraries assemble into real geometry; anything else is
# a known behavioral difference (osm2geojson still emits a merged feature)
GEOMETRIC_RELATION_TYPES = {"multipolygon", "boundary", "route", "waterway"}

# tags that don't make an element a feature of its own (osmtogeojson's
# uninterestingTags)
UNINTERESTING_TAGS = {
    "source",
    "source_ref",
    "source:ref",
    "history",
    "attribution",
    "created_by",
    "tiger:county",
    "tiger:tlid",
    "tiger:upload_uuid",
}


def explain_difference(verdict, detail, py_feat, js_feat):
    """Reason string if this divergence is a known/intentional one, else None.

    Mirrors the intentional differences documented in
    tests/test_osmtogeojson_compat.py (KNOWN_DIFFERENCES).
    """
    if verdict == "close":
        return (
            "geometries agree within tolerance (typically same vertices, different ring assembly)"
        )
    if detail == "missing in osmtogeojson" and py_feat:
        props = py_feat.get("properties") or {}
        rel_type = (props.get("tags") or {}).get("type")
        if props.get("type") == "relation" and rel_type not in GEOMETRIC_RELATION_TYPES:
            return (
                f"relation type {rel_type!r} is non-geometric: osm2geojson emits a merged"
                " feature for it, osmtogeojson emits none"
            )
        return None
    if detail == "missing in osm2geojson" and js_feat:
        props = js_feat.get("properties") or {}
        tags = props.get("tags") or {}
        if (
            props.get("type") == "way"
            and not (set(tags) - UNINTERESTING_TAGS)
            and props.get("relations")
        ):
            return (
                "relation-member way without own tags: osm2geojson filters it out"
                " (filter_used_refs); osmtogeojson duplicates members of full-geometry"
                " responses as standalone features"
            )
        geom = to_shape(js_feat.get("geometry"))
        if geom is None:
            return (
                "osmtogeojson emitted invalid geometry (e.g. null coordinates);"
                " osm2geojson only outputs valid GeoJSON"
            )
        if geom.geom_type in ("Polygon", "MultiPolygon") and geom.area == 0:
            return (
                "osmtogeojson emitted a zero-area polygon; osm2geojson refuses degenerate geometry"
            )
        return None
    return None


def compare_collections(py_result, js_result, tolerance):
    """-> (counts dict, [(verdict, feature label, detail, expected-reason), ...])"""
    py_idx, js_idx = index_features(py_result), index_features(js_result)
    counts = {"identical": 0, "close": 0, "different": 0}
    rows = []
    for key in sorted(set(py_idx) | set(js_idx), key=str):
        label = f"{key[0]}/{key[1]}"
        py_feats, js_feats = py_idx.get(key, []), js_idx.get(key, [])
        if not py_feats or not js_feats:
            side = "osm2geojson" if js_feats else "osmtogeojson"
            counts["different"] += 1
            detail = f"missing in {side}"
            reason = explain_difference(
                "different",
                detail,
                py_feats[0] if py_feats else None,
                js_feats[0] if js_feats else None,
            )
            rows.append(("different", label, detail, reason))
            continue
        if len(py_feats) != len(js_feats):
            counts["different"] += 1
            rows.append(
                ("different", label, f"feature count py={len(py_feats)} js={len(js_feats)}", None)
            )
            continue
        for py_feat, js_feat in zip(py_feats, js_feats):
            verdict, detail = compare_geometries(
                py_feat.get("geometry"), js_feat.get("geometry"), tolerance
            )
            counts[verdict] += 1
            reason = None
            if verdict != "identical":
                reason = explain_difference(verdict, detail, py_feat, js_feat)
            rows.append((verdict, label, detail, reason))
    return counts, rows


# ---------------------------------------------------------------- reporting


def file_status(result):
    """-> 'ok' | 'known' (all divergence explained) | 'diverged' | 'error'"""
    if result["error"]:
        return "error"
    if result["counts"]["different"] == 0:
        return "ok"
    if result["unexpected"] == 0:
        return "known"
    return "diverged"


def print_console(result, verbose):
    if result["error"]:
        print(f"{result['path']}: ERROR - {result['error']}")
        return
    counts, total = result["counts"], sum(result["counts"].values())
    status = {"ok": "OK", "known": "KNOWN DIFFERENCES", "diverged": "DIVERGED"}[file_status(result)]
    print(
        f"{result['path']}: {status} - {total} features: "
        f"{counts['identical']} identical, {counts['close']} close, {counts['different']} different"
        f" | py {result['py_ms']:.1f}ms vs js {result['js_ms']:.1f}ms"
    )
    for verdict, label, detail, reason in result["rows"]:
        if verbose or verdict != "identical":
            suffix = f" ({detail})" if detail else ""
            if verdict != "identical":
                suffix += f" - expected: {reason}" if reason else " - UNEXPECTED"
            print(f"  {verdict.upper():9}  {label}{suffix}")


HTML_STYLE = """
:root {
  color-scheme: light;
  --page: #f9f9f7; --surface: #fcfcfb;
  --ink: #0b0b0b; --ink-2: #52514e; --muted: #898781;
  --grid: #e1e0d9; --border: rgba(11,11,11,0.10);
  --py: #2a78d6; --js: #008300;
  --good: #0ca30c; --warn: #fab219; --crit: #d03b3b;
}
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    color-scheme: dark;
    --page: #0d0d0d; --surface: #1a1a19;
    --ink: #ffffff; --ink-2: #c3c2b7; --muted: #898781;
    --grid: #2c2c2a; --border: rgba(255,255,255,0.10);
    --py: #3987e5; --js: #008300;
  }
}
:root[data-theme="dark"] {
  color-scheme: dark;
  --page: #0d0d0d; --surface: #1a1a19;
  --ink: #ffffff; --ink-2: #c3c2b7; --muted: #898781;
  --grid: #2c2c2a; --border: rgba(255,255,255,0.10);
  --py: #3987e5; --js: #008300;
}
body { margin: 0; padding: 24px; background: var(--page); color: var(--ink);
       font: 14px/1.5 system-ui, -apple-system, "Segoe UI", sans-serif; }
main { max-width: 1000px; margin: 0 auto; }
h1 { font-size: 20px; margin: 0 0 4px; }
h2 { font-size: 15px; margin: 28px 0 8px; }
.sub { color: var(--ink-2); margin: 0 0 20px; }
.card { background: var(--surface); border: 1px solid var(--border);
        border-radius: 8px; padding: 4px 12px; overflow-x: auto; }
table { border-collapse: collapse; width: 100%; }
th { text-align: left; color: var(--muted); font-weight: 500; font-size: 12px; }
th, td { padding: 6px 8px; border-bottom: 1px solid var(--grid); white-space: nowrap; }
a { color: inherit; text-decoration: none; }
a:hover { text-decoration: underline; }
tr:last-child td { border-bottom: none; }
tbody tr:hover { background: color-mix(in srgb, var(--ink) 4%, transparent); }
td.num { text-align: right; font-variant-numeric: tabular-nums; }
th.num { text-align: right; }
.chip { display: inline-block; padding: 1px 8px; border-radius: 999px;
        font-size: 12px; font-weight: 600; border: 1px solid; }
.chip.ok   { color: var(--good); border-color: var(--good); }
.chip.bad  { color: var(--crit); border-color: var(--crit); }
.chip.warn { color: var(--warn); border-color: var(--warn); }
.swatch { display: inline-block; width: 10px; height: 10px; border-radius: 3px;
          margin-right: 6px; vertical-align: baseline; }
.barcell { min-width: 120px; }
.bar { display: flex; align-items: center; gap: 6px; }
.bar .track { flex: 1; height: 10px; }
.bar .fill { display: block; height: 10px; border-radius: 0 4px 4px 0; min-width: 2px; }
.bar .val { font-variant-numeric: tabular-nums; color: var(--ink-2); min-width: 56px;
            text-align: right; }
.legend { display: flex; gap: 18px; margin: 10px 2px; color: var(--ink-2); font-size: 13px; }
.detail { color: var(--ink-2); white-space: normal; }
.mono { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 13px; }
footer { color: var(--muted); font-size: 12px; margin-top: 24px; }
"""


def _fmt_ms(value_ms):
    return f"{value_ms:.2f}" if value_ms < 1 else f"{value_ms:.1f}"


def _bar(value_ms, max_ms, color_var, times):
    pct = 100 * value_ms / max_ms if max_ms else 0
    runs = ", ".join(f"{t:.2f}" for t in times)
    return (
        f'<div class="bar" title="runs (ms): {html.escape(runs)}">'
        f'<span class="track"><span class="fill" style="width:{pct:.1f}%;'
        f'background:var(--{color_var})"></span></span>'
        f'<span class="val">{_fmt_ms(value_ms)} ms</span></div>'
    )


STATUS_CHIPS = {
    "ok": '<span class="chip ok">&#10003; match</span>',
    "known": '<span class="chip warn">&#8776; known diffs</span>',
    "diverged": '<span class="chip bad">&#10007; diverged</span>',
}


def build_html(results, tolerance, runs):
    n_features = sum(sum(r["counts"].values()) for r in results)
    statuses = [file_status(r) for r in results]
    tallies = ", ".join(
        f"{statuses.count(s)} {label}"
        for s, label in [
            ("ok", "match"),
            ("known", "known differences"),
            ("diverged", "diverged"),
            ("error", "errored"),
        ]
        if statuses.count(s)
    )

    summary_rows = []
    for r in results:
        if r["error"]:
            summary_rows.append(
                f"<tr><td class='mono'>{html.escape(r['name'])}</td>"
                f"<td><span class='chip warn'>&#9888; error</span></td>"
                f"<td colspan='6' class='detail'>{html.escape(r['error'])}</td></tr>"
            )
            continue
        c = r["counts"]
        status = STATUS_CHIPS[file_status(r)]
        # ratio on sub-0.05ms medians is timer noise, not a benchmark
        if min(r["py_ms"], r["js_ms"]) >= 0.05:
            ratio = f"{r['py_ms'] / r['js_ms']:.1f}&times;"
        else:
            ratio = "&ndash;"
        name = html.escape(r["name"])
        has_detail = any(row[0] != "identical" for row in r["rows"])
        name_cell = f"<a href='#f{r['index']}'>{name}</a>" if has_detail else name
        row_max = max(r["py_ms"], r["js_ms"])  # bars compare converters per row
        summary_rows.append(
            f"<tr><td class='mono'>{name_cell}</td>"
            f"<td>{status}</td>"
            f"<td class='num'>{c['identical']}</td>"
            f"<td class='num'>{c['close'] or ''}</td>"
            f"<td class='num'>{c['different'] or ''}</td>"
            f"<td class='barcell'>{_bar(r['py_ms'], row_max, 'py', r['py_times'])}</td>"
            f"<td class='barcell'>{_bar(r['js_ms'], row_max, 'js', r['js_times'])}</td>"
            f"<td class='num'>{ratio}</td></tr>"
        )

    detail_sections = []
    for r in results:
        listed = [row for row in r["rows"] if row[0] != "identical"]
        if not listed:
            continue
        chip = {"close": "warn", "different": "bad"}
        rows = []
        for v, label, detail, reason in listed:
            if reason:
                assessment = f"<span class='chip ok'>expected</span> {html.escape(reason)}"
            else:
                assessment = "<span class='chip bad'>unexpected</span>"
            rows.append(
                f"<tr><td><span class='chip {chip[v]}'>{'&#8776; close' if v == 'close' else '&#10007; different'}</span></td>"
                f"<td class='mono'>{html.escape(label)}</td>"
                f"<td class='detail'>{html.escape(detail)}</td>"
                f"<td class='detail'>{assessment}</td></tr>"
            )
        detail_sections.append(
            f"<h2 id='f{r['index']}'>{html.escape(r['name'])} &mdash; "
            f"{len(listed)} non-identical feature(s)</h2>"
            f"<div class='card'><table><thead><tr><th>verdict</th><th>feature</th>"
            f"<th>detail</th><th>assessment</th></tr></thead><tbody>{''.join(rows)}</tbody></table></div>"
        )

    generated = datetime.now().strftime("%Y-%m-%d %H:%M")
    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>osm2geojson vs osmtogeojson</title>
<style>{HTML_STYLE}</style></head><body><main>
<h1>osm2geojson vs osmtogeojson</h1>
<p class="sub">{len(results)} file(s), {n_features} features: {tallies} &middot;
geometry tolerance {tolerance:g}&deg; &middot; times are medians of {runs} runs
(parse + convert, after warmup); bars compare the two converters within each row</p>
<div class="legend">
  <span><span class="swatch" style="background:var(--py)"></span>osm2geojson (Python)</span>
  <span><span class="swatch" style="background:var(--js)"></span>osmtogeojson (JS)</span>
</div>
<div class="card"><table>
<thead><tr><th>file</th><th>geometry</th>
<th class="num">identical</th><th class="num">close</th><th class="num">different</th>
<th>osm2geojson</th><th>osmtogeojson</th><th class="num">py &divide; js</th></tr></thead>
<tbody>{"".join(summary_rows)}</tbody></table></div>
{"".join(detail_sections)}
<footer>generated {generated} by tests/tools/compare_osmtogeojson.py</footer>
</main></body></html>
"""


# ---------------------------------------------------------------------- main


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "files", nargs="+", type=Path, help="OSM input files (.osm/.xml or Overpass .json)"
    )
    parser.add_argument(
        "--tolerance",
        type=float,
        default=1e-7,
        help="max Hausdorff distance (degrees) to call geometries 'close' (default 1e-7)",
    )
    parser.add_argument(
        "--runs",
        type=int,
        default=5,
        help="timed conversion runs per converter per file (default 5)",
    )
    parser.add_argument(
        "--html", type=Path, metavar="PATH", help="also write an HTML report to PATH"
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="also list identical features on the console"
    )
    args = parser.parse_args()

    # not OSM data: the recorded compat-suite fixtures live next to the real inputs
    skipped = [p for p in args.files if p.name == "osmtogeojson-fixtures.json"]
    for path in skipped:
        print(f"{path}: SKIPPED - compat-suite fixture file, not an OSM input", file=sys.stderr)
    args.files = [p for p in args.files if p not in skipped]

    ensure_js_deps()
    js_results = run_js(args.files, args.runs)

    results, all_ok = [], True
    for i, path in enumerate(args.files):
        errors = []
        js = js_results.get(str(path)) or {"error": "no result from runner"}
        if js.get("error"):
            errors.append(f"osmtogeojson: {js['error']}")
        try:
            py_geojson, py_times = run_py(path, args.runs)
        except Exception as exc:
            errors.append(f"osm2geojson: {exc}")
        result = {
            "index": i,
            "path": str(path),
            "name": path.name,
            "error": "; ".join(errors) or None,
            "ok": not errors,
            "unexpected": 0,
            "counts": {"identical": 0, "close": 0, "different": 0},
            "rows": [],
            "py_times": [],
            "js_times": [],
            "py_ms": 0.0,
            "js_ms": 0.0,
        }
        if not errors:
            counts, rows = compare_collections(py_geojson, js["geojson"], args.tolerance)
            unexpected = sum(1 for v, _, _, reason in rows if v != "identical" and reason is None)
            result.update(
                ok=unexpected == 0,
                unexpected=unexpected,
                counts=counts,
                rows=rows,
                py_times=py_times,
                js_times=js["times_ms"],
                py_ms=statistics.median(py_times),
                js_ms=statistics.median(js["times_ms"]),
            )
        results.append(result)
        all_ok &= result["ok"]
        print_console(result, args.verbose)

    if args.html:
        args.html.write_text(build_html(results, args.tolerance, args.runs))
        print(f"\nHTML report: {args.html}")
    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
