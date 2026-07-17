// Convert and benchmark OSM files with osmtogeojson in a single node process,
// so timings measure the conversion itself and not interpreter startup.
//
// stdin:  {"runs": N, "files": [{"path": "...", "type": "xml"|"json"}, ...]}
// stdout: {"results": [{"path": "...", "geojson": {...}, "times_ms": [...]}, ...]}
//
// Each timed run covers parse (DOMParser / JSON.parse) + conversion, matching
// what the Python side times for xml2geojson/json2geojson. One untimed warmup
// run precedes the measurements (JIT).
"use strict";
const fs = require("fs");
const osmtogeojson = require("osmtogeojson");
const { DOMParser } = require("@xmldom/xmldom");

const config = JSON.parse(fs.readFileSync(0, "utf8"));
const runs = config.runs || 1;

const results = config.files.map(({ path, type }) => {
  try {
    const text = fs.readFileSync(path, "utf8");
    // structured properties ({type, id, tags, ...}) like the 2.x default and
    // the CLI's -e flag, so features can be matched by (type, id)
    const opts = { flatProperties: false };
    const convert = () =>
      type === "xml"
        ? osmtogeojson(new DOMParser().parseFromString(text, "text/xml"), opts)
        : osmtogeojson(JSON.parse(text), opts);

    const geojson = convert(); // warmup; also the output used for comparison
    const times_ms = [];
    for (let i = 0; i < runs; i++) {
      const t0 = process.hrtime.bigint();
      convert();
      times_ms.push(Number(process.hrtime.bigint() - t0) / 1e6);
    }
    return { path, geojson, times_ms };
  } catch (e) {
    return { path, error: String(e && e.message ? e.message : e) };
  }
});

process.stdout.write(JSON.stringify({ results }));
