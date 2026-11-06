"""Registry index: fetch, cache for 24h, normalise. Standard library only.

The single source of truth is the official shadcn registry index
(https://ui.shadcn.com/r/registries.json). ui-forge never hardcodes a registry
list; it caches this document and reads health/item counts from it.
"""
import json
import os
import tempfile
import time

from .net import FetchError, fetch_json_any

INDEX_URL = "https://ui.shadcn.com/r/registries.json"
CACHE_NAME = "registries-cache.json"
TTL_SECONDS = 24 * 3600


def cache_path(data_dir):
    return os.path.join(data_dir, CACHE_NAME)


def _read_cache(path):
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as handle:
            cached = json.load(handle)
    except (OSError, ValueError):
        return None
    if not isinstance(cached, dict) or not isinstance(cached.get("registries"), list):
        return None
    return cached


def cached(data_dir):
    """Registries from the local cache only; never touches the network."""
    cached_doc = _read_cache(cache_path(data_dir))
    return (cached_doc or {}).get("registries") or []


def _write_cache(path, source, registries):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    payload = {"fetched_at": time.time(), "source": source, "registries": registries}
    fd, tmp = tempfile.mkstemp(prefix=".registries-", suffix=".json", dir=os.path.dirname(path))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass


def load(data_dir, refresh=False, index_url=None, timeout=30):
    """Return the registry list plus metadata about where it came from.

    Failure of the network never destroys a usable cache: an expired cache is
    returned with ``stale=True`` and a warning instead of crashing the command.
    """
    source = index_url or INDEX_URL
    path = cache_path(data_dir)
    cached = _read_cache(path)
    warnings = []

    if cached and not refresh:
        age = time.time() - float(cached.get("fetched_at") or 0)
        if age < TTL_SECONDS:
            return {
                "source": cached.get("source") or source,
                "fetched_at": cached.get("fetched_at"),
                "from_cache": True,
                "stale": False,
                "age_seconds": int(age),
                "registries": cached["registries"],
                "warnings": warnings,
            }

    try:
        document = fetch_json_any(source, timeout=timeout)
        # The live index is a bare array; some snapshots wrap it in an object.
        registries = document.get("registries") if isinstance(document, dict) else document
        if not isinstance(registries, list):
            raise FetchError("bad_payload", "registry index has no registries array", source)
        _write_cache(path, source, registries)
        return {
            "source": source,
            "fetched_at": time.time(),
            "from_cache": False,
            "stale": False,
            "age_seconds": 0,
            "registries": registries,
            "warnings": warnings,
        }
    except FetchError as exc:
        if cached:
            warnings.append(
                "registry index refresh failed (%s); using stale cache from %s"
                % (exc.code, time.strftime("%Y-%m-%d %H:%M", time.localtime(cached.get("fetched_at") or 0)))
            )
            return {
                "source": cached.get("source") or source,
                "fetched_at": cached.get("fetched_at"),
                "from_cache": True,
                "stale": True,
                "age_seconds": int(time.time() - float(cached.get("fetched_at") or 0)),
                "registries": cached["registries"],
                "warnings": warnings,
            }
        raise


def health_score(registry):
    try:
        return float((registry.get("health") or {}).get("score") or 0)
    except (TypeError, ValueError):
        return 0.0


def health_status(registry):
    return (registry.get("health") or {}).get("status") or "unknown"


def item_count(registry):
    try:
        return int((registry.get("ranking") or {}).get("itemCount") or 0)
    except (TypeError, ValueError):
        return 0


def url_template(registry):
    return (registry.get("url") or "").strip()


def by_name(registries):
    return {r.get("name"): r for r in registries if r.get("name")}


def find(registries, name):
    return by_name(registries).get(name)


def top(registries, limit, min_health=0.0):
    pool = [r for r in registries if health_score(r) >= min_health]
    pool.sort(key=lambda r: (health_score(r), item_count(r)), reverse=True)
    return pool[:limit]


def item_url(registry, item, style=None):
    """Build the item URL from the registry's template.

    ``{name}`` is always substituted. ``{style}`` (used by 17 registries) is
    substituted with the project's shadcn style when known. Some templates are
    extensionless (e.g. @magicui); callers get a second candidate with
    ``.json`` appended by :func:`item_url_candidates`.
    """
    template = url_template(registry)
    if not template or "{name}" not in template:
        return None
    url = template.replace("{name}", item).replace("{style}", style or "new-york")
    return url


def item_url_candidates(registry, item, style=None):
    url = item_url(registry, item, style)
    if not url:
        return []
    urls = [url]
    if not url.split("?", 1)[0].endswith(".json"):
        urls.append(url + ".json")
    return urls


def normalize(registry, license_info=None):
    """Small, stable row shape shared by the CLI and downstream callers."""
    row = {
        "name": registry.get("name"),
        "url": url_template(registry),
        "homepage": registry.get("homepage"),
        "description": registry.get("description") or "",
        "health": round(health_score(registry), 1),
        "status": health_status(registry),
        "items": item_count(registry),
    }
    if license_info is not None:
        row["license"] = license_info
    return row
