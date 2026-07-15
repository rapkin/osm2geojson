// Extract (input, output) fixture pairs from osmtogeojson's own test suite by
// running every test case against the real library with a stub mocha runner.
"use strict";
const Module = require("module");
const fs = require("fs");
const path = require("path");

const real = require("./");
const xmldom = require("@xmldom/xmldom");

// Tag DOM documents with their source XML so we can serialize fixtures.
const RealDOMParser = xmldom.DOMParser;
class TaggingDOMParser extends RealDOMParser {
  parseFromString(str, mime) {
    const doc = super.parseFromString(str, mime);
    try { doc.__sourceXml = str; } catch (e) {}
    return doc;
  }
}

const cases = [];
let currentDescribe = "";
let currentCalls = [];

function isDom(x) {
  return x && typeof x === "object" && (x.__sourceXml !== undefined || x.childNodes !== undefined);
}

function describeOpts(opts) {
  if (opts === undefined) return { present: false, keys: [], hasFunctions: false, serializable: null };
  const keys = Object.keys(opts);
  const hasFunctions = keys.some((k) => typeof opts[k] === "function");
  let serializable = null;
  if (!hasFunctions) {
    try { serializable = JSON.parse(JSON.stringify(opts)); } catch (e) {}
  }
  return { present: true, keys, hasFunctions, serializable };
}

function wrapper(data, opts) {
  const rec = { opts: describeOpts(opts) };
  if (isDom(data)) {
    rec.input_type = "xml";
    rec.input = data.__sourceXml !== undefined ? data.__sourceXml : null;
  } else if (typeof data === "string") {
    rec.input_type = "xml";
    rec.input = data;
  } else {
    rec.input_type = "json";
    rec.input = JSON.parse(JSON.stringify(data)); // snapshot before any mutation
  }
  const output = real(data, opts);
  try {
    rec.output = JSON.parse(JSON.stringify(output));
  } catch (e) {
    rec.output = null;
    rec.output_error = String(e);
  }
  currentCalls.push(rec);
  return output;
}
Object.assign(wrapper, real); // static props like uninterestingTags, if referenced

// Redirect the test file's requires to our wrappers.
const origLoad = Module._load;
Module._load = function (request, parent, isMain) {
  if (parent && /osm\.test\.js$/.test(parent.filename || "")) {
    if (request === "../" || request === "..") return wrapper;
    if (request === "@xmldom/xmldom") return Object.assign({}, xmldom, { DOMParser: TaggingDOMParser });
  }
  return origLoad.apply(this, arguments);
};

global.describe = function (name, fn) {
  const prev = currentDescribe;
  currentDescribe = prev ? prev + " / " + name : name;
  fn();
  currentDescribe = prev;
};
global.it = function (name, fn) {
  currentCalls = [];
  let status = "pass", error = null;
  try {
    fn();
  } catch (e) {
    status = "fail";
    error = String(e && e.message ? e.message : e);
  }
  cases.push({ describe: currentDescribe, it: name, status, error, calls: currentCalls });
};

require(path.join(__dirname, "test", "osm.test.js"));

const failed = cases.filter((c) => c.status !== "pass");
console.log("cases:", cases.length, "| js-assertion failures:", failed.length);
failed.forEach((c) => console.log("  FAIL:", c.describe, "/", c.it, "->", c.error));
console.log("total recorded calls:", cases.reduce((n, c) => n + c.calls.length, 0));
fs.writeFileSync(process.argv[2] || "fixtures.json", JSON.stringify(cases, null, 1));
