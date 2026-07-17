"""Helper utilities for osm2geojson."""

import codecs
import os
import urllib
from functools import wraps
from time import sleep
from typing import Any, Callable, TypeVar

import requests


OVERPASS = "https://overpass-api.de/api/interpreter/"
# overpass-api.de rejects generic client User-Agents (e.g. python-requests) with 406,
# and the usage policy asks clients to identify themselves
USER_AGENT = "osm2geojson (+https://github.com/rapkin/osm2geojson)"
dirname = os.path.dirname(os.path.dirname(__file__))

F = TypeVar("F", bound=Callable[..., Any])


def read_data_file(name: str) -> str:
    """Read a test data file and return its contents.

    Args:
        name: Name of the file to read from tests/data directory.

    Returns:
        Contents of the file as a string.
    """
    path = os.path.join(dirname, "tests/data", name)
    with codecs.open(path, "r", encoding="utf-8") as data:
        return data.read()


def retry_request_multi(max_retries: int) -> Callable[[F], F]:
    """Decorator to retry a function multiple times on HTTPError.

    Args:
        max_retries: Maximum number of retry attempts.

    Returns:
        Decorator function.
    """

    def retry(func: F) -> F:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            num_retries = 0
            while num_retries <= max_retries:
                try:
                    ret = func(*args, **kwargs)
                    break
                except requests.exceptions.HTTPError:
                    if num_retries == max_retries:
                        raise
                    num_retries += 1
                    sleep(5)
            return ret

        return wrapper  # type: ignore

    return retry


@retry_request_multi(5)
def overpass_call(query: str, timeout: float = 180) -> str:
    """Call the Overpass API with the given query.

    Args:
        query: Overpass QL query string.
        timeout: Timeout in seconds for the HTTP request (Overpass queries can
            legitimately run long; raise this for heavy queries).

    Returns:
        Response text from the Overpass API.

    Raises:
        requests.exceptions.HTTPError: If the server returns a non-200 status.
        requests.exceptions.Timeout: If the server does not respond in time.
    """
    encoded = urllib.parse.quote(query.encode("utf-8"), safe="~()*!.'")
    r = requests.post(
        OVERPASS,
        data=f"data={encoded}",
        headers={
            "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8",
            "User-Agent": USER_AGENT,
        },
        timeout=timeout,
    )
    if r.status_code != 200:
        raise requests.exceptions.HTTPError(f"Overpass server respond with status {r.status_code}")
    return r.text
