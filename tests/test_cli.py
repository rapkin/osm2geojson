"""Tests for the osm2geojson CLI (python -m osm2geojson)."""

import json
import re
import subprocess
import sys
from pathlib import Path

from osm2geojson import xml2geojson
from tests.utils import DATA_DIR, read_data_file


REPO_ROOT = Path(__file__).resolve().parents[1]


def run_cli(*args):
    return subprocess.run(
        [sys.executable, "-m", "osm2geojson", *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=REPO_ROOT,
        timeout=60,
    )


def test_cli_output_keeps_unicode_readable(tmp_path):
    """Non-ASCII tag values must be written as UTF-8 text, not \\uXXXX escapes."""
    out_file = tmp_path / "map.geojson"
    result = run_cli(str(Path(DATA_DIR) / "map.osm"), str(out_file))
    assert result.returncode == 0, result.stderr

    text = out_file.read_text(encoding="utf-8")
    assert "Драгоманова вулиця" in text
    assert "\\u0" not in text

    # and the content still matches the library output
    assert json.loads(text) == xml2geojson(read_data_file("map.osm"))


def test_cli_stdout_output():
    result = run_cli(str(Path(DATA_DIR) / "node.osm"), "-")
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["type"] == "FeatureCollection"


def test_data_files_have_no_unicode_escapes():
    """Checked-in expected outputs stay human-readable (see test_cli above)."""
    escape = re.compile(r"\\u[0-9a-fA-F]{4}")
    offenders = [
        path.name
        for path in Path(DATA_DIR).glob("*.geojson")
        if escape.search(path.read_text(encoding="utf-8"))
    ]
    assert not offenders, f"files with \\uXXXX escapes: {offenders}"
