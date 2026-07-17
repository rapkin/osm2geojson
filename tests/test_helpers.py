"""Tests for overpass_call retry behavior (no real network access)."""

import pytest
import requests

from osm2geojson import helpers
from osm2geojson.helpers import overpass_call


class FakeResponse:
    def __init__(self, status_code, text="ok"):
        self.status_code = status_code
        self.text = text


@pytest.fixture
def transport(monkeypatch):
    """Queue of responses/exceptions for requests.post; records call count."""
    state = {"queue": [], "calls": 0, "sleeps": []}

    def fake_post(*args, **kwargs):
        state["calls"] += 1
        item = state["queue"].pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    monkeypatch.setattr(helpers.requests, "post", fake_post)
    monkeypatch.setattr(helpers, "sleep", state["sleeps"].append)
    return state


def test_success_needs_single_call(transport):
    transport["queue"] = [FakeResponse(200, "data")]
    assert overpass_call("out;") == "data"
    assert transport["calls"] == 1
    assert transport["sleeps"] == []


def test_client_error_fails_fast(transport):
    """A 400 (malformed query) can never succeed - no retries, no sleeps."""
    transport["queue"] = [FakeResponse(400)]
    with pytest.raises(requests.exceptions.HTTPError, match="400"):
        overpass_call("out;")
    assert transport["calls"] == 1
    assert transport["sleeps"] == []


@pytest.mark.parametrize("status", [429, 503])
def test_transient_status_is_retried(transport, status):
    transport["queue"] = [FakeResponse(status), FakeResponse(200, "data")]
    assert overpass_call("out;", retry_delay=0.1) == "data"
    assert transport["calls"] == 2
    assert transport["sleeps"] == [0.1]


def test_connection_error_is_retried(transport):
    transport["queue"] = [requests.exceptions.ConnectionError(), FakeResponse(200, "data")]
    assert overpass_call("out;", retry_delay=0) == "data"
    assert transport["calls"] == 2


def test_timeout_is_retried_and_reraised(transport):
    transport["queue"] = [requests.exceptions.Timeout(), requests.exceptions.Timeout()]
    with pytest.raises(requests.exceptions.Timeout):
        overpass_call("out;", retries=1, retry_delay=0)
    assert transport["calls"] == 2


def test_retries_zero_disables_retrying(transport):
    transport["queue"] = [FakeResponse(503)]
    with pytest.raises(requests.exceptions.HTTPError, match="503"):
        overpass_call("out;", retries=0)
    assert transport["calls"] == 1
