"""HTTP helpers for ui-forge. Standard library only.

Every failure is normalised into :class:`FetchError` with a stable ``code`` so
the CLI can print a machine-readable error and callers can branch on it
(for example ``http_401`` means "paywall", never "retry").
"""
import json
import urllib.error
import urllib.request

USER_AGENT = "ui-forge/0.2 (+https://github.com/KaiyoDev/ui-forge)"


class FetchError(Exception):
    """A network/transport failure with a stable machine-readable code."""

    def __init__(self, code, message, url=None, status=None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.url = url
        self.status = status

    def as_dict(self):
        return {"code": self.code, "message": self.message, "url": self.url, "status": self.status}


def _request(url, timeout, headers):
    merged = {"User-Agent": USER_AGENT, "Accept": "application/json, text/plain, */*"}
    merged.update(headers or {})
    return urllib.request.Request(url, headers=merged)


def fetch_bytes(url, timeout=30, headers=None):
    """Fetch a URL and return raw bytes, raising FetchError on any failure."""
    req = _request(url, timeout, headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read()
    except urllib.error.HTTPError as exc:
        raise FetchError("http_%d" % exc.code, "HTTP %d for %s" % (exc.code, url), url, exc.code)
    except urllib.error.URLError as exc:
        raise FetchError("network_error", "cannot reach %s: %s" % (url, exc.reason), url)
    except TimeoutError:
        raise FetchError("timeout", "timed out fetching %s" % url, url)
    except OSError as exc:
        raise FetchError("network_error", "cannot reach %s: %s" % (url, exc), url)


def fetch_json_any(url, timeout=30, headers=None):
    """Fetch a URL and parse it as JSON of any top-level type."""
    raw = fetch_bytes(url, timeout=timeout, headers=headers)
    try:
        return json.loads(raw.decode("utf-8", "replace"))
    except ValueError as exc:
        raise FetchError("bad_json", "response from %s is not JSON: %s" % (url, exc), url)


def fetch_json(url, timeout=30, headers=None):
    """Fetch a URL and parse it as a JSON object."""
    data = fetch_json_any(url, timeout=timeout, headers=headers)
    if not isinstance(data, dict):
        raise FetchError("bad_payload", "response from %s is not a JSON object" % url, url)
    return data


def fetch_json_candidates(urls, timeout=30, headers=None):
    """Try URLs in order. Only move on for 'not here' failures (404/415/bad JSON).

    A 401/402/403 stops immediately: that is a paywall signal, not a wrong URL.
    Returns ``(data, url_used, failures)`` where failures lists
    ``{"url", "code", "message"}`` for the URLs that were skipped.
    """
    failures = []
    for url in urls:
        try:
            return fetch_json(url, timeout=timeout, headers=headers), url, failures
        except FetchError as exc:
            if exc.code in ("http_404", "http_415", "bad_json", "bad_payload"):
                failures.append({"url": url, "code": exc.code, "message": exc.message})
                continue
            raise
    if failures:
        last = failures[-1]
        raise FetchError(last["code"], last["message"], last["url"])
    raise FetchError("no_url", "no candidate URL to fetch")


def http_status(url, timeout=25, headers=None):
    """Return the HTTP status code for a URL without parsing the body."""
    req = _request(url, timeout, headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            resp.read(1)
            return resp.status
    except urllib.error.HTTPError as exc:
        return exc.code
    except Exception as exc:  # noqa: BLE001 - evidence gathering must not explode
        raise FetchError("network_error", "cannot reach %s: %s" % (url, exc), url)
