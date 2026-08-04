"""Loading OTLP JSON from a file path or an http(s) collector endpoint.

The one place in `trace` that touches the filesystem or the network for the
raw OTLP payload; everything downstream (parse_otlp, correlate) only ever
sees a plain dict.
"""

from __future__ import annotations

import json
import urllib.request
from urllib.error import URLError


class TraceInputError(Exception):
    """Carries a one-line, user-facing message about a bad OTLP source."""


def load_otlp(source: str) -> dict:
    """Load an OTLP/JSON export from *source*.

    *source* is either an http:// or https:// URL (fetched from a collector
    query endpoint) or a file path (read from disk). Any failure to fetch,
    read or parse is wrapped in a :class:`TraceInputError` naming *source*.
    """
    if source.startswith("http://") or source.startswith("https://"):
        try:
            with urllib.request.urlopen(source, timeout=10) as resp:
                body = resp.read()
        except (URLError, OSError) as exc:
            raise TraceInputError(f"cannot read OTLP input '{source}': {exc}") from exc
    else:
        try:
            with open(source, "rb") as fh:
                body = fh.read()
        except OSError as exc:
            raise TraceInputError(f"cannot read OTLP input '{source}': {exc}") from exc

    try:
        return json.loads(body)
    except json.JSONDecodeError as exc:
        raise TraceInputError(f"not valid OTLP JSON: {source}: {exc}") from exc
