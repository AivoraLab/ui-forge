"""Search the ecosystem, cheaply and free-first.

The shadcn CLI is the ecosystem's search engine, so it is the primary source.
The per-registry item index is only a cache/fallback: it is fast to read and it
still answers when `shadcn search` is unavailable. Results are always annotated
with license truth from ``data/licenses.json``; the free-first rule is applied
here, not left to the agent.
"""
import re
import time
from concurrent.futures import ThreadPoolExecutor

from . import index as index_mod
from . import licenses, net, shadcn

DEFAULT_POOL = 8
DEFAULT_TYPES = ("ui", "block", "component", "hook")
EXAMPLE_TYPES = ("example", "style", "theme", "lib", "file")
# A registry that does not honour `-q` returns its whole catalogue. Verified
# with @keyline: `-q hero` returned 13,536 items whose titles never mention
# "hero". If most of a registry's batch does not contain a query term, keep
# only the locally matching rows and say so.
IGNORED_QUERY_RATIO = 0.5
IGNORED_QUERY_MIN_ITEMS = 3
SCHEMA = "ui-forge/search/v1"


def query_terms(query):
    return [term for term in re.split(r"[^a-z0-9]+", (query or "").lower()) if len(term) >= 2]


def _haystack(item):
    return " ".join(
        str(item.get(key) or "") for key in ("name", "title", "description")
    ).lower()


def relevance_guard(items, query):
    """Drop rows returned by registries that ignore the query string.

    `shadcn search` runs server-side per registry. Some registries answer with
    the whole catalogue regardless of `-q`, so an unfiltered "hero" search can
    surface "chevron-up" icons. This guard is only applied to CLI results
    (the index fallback already substring-filters); registries whose batch
    mostly matches are left untouched.
    """
    terms = query_terms(query)
    if not terms or not items:
        return items, []
    groups = {}
    for item in items:
        namespace = item.get("registry") or ""
        if not namespace and item.get("addCommandArgument"):
            namespace = item["addCommandArgument"].split("/", 1)[0]
        groups.setdefault(namespace, []).append(item)
    kept = []
    warnings = []
    for namespace, group in groups.items():
        matched = [item for item in group if any(term in _haystack(item) for term in terms)]
        if len(group) >= IGNORED_QUERY_MIN_ITEMS and len(matched) < IGNORED_QUERY_RATIO * len(group):
            warnings.append(
                "%s ignored the query (`-q` returned its catalogue); kept %d/%d locally matched items"
                % (namespace, len(matched), len(group))
            )
            kept.extend(matched)
        else:
            kept.extend(group)
    return kept, warnings


def _type_name(value):
    if not value:
        return ""
    return value.split(":", 1)[-1]


def _wanted_types(types):
    if not types:
        return set(DEFAULT_TYPES)
    return {_type_name(t).lower() for t in types}


def _license_row(license_db, namespace, free_only):
    info = licenses.lookup(license_db, namespace)
    kept = info["status"] in licenses.FREE_OK
    if free_only and not kept:
        reason = "license_%s: free-first rule (evidence: %s)" % (
            info["status"],
            (info.get("evidence") or [{}])[0].get("url", "see licenses.json"),
        )
    else:
        reason = None
    return {
        "status": info["status"],
        "kept": kept,
        "flagged": info["status"] == "unknown",
        "reason": reason,
        "checked_at": info.get("checked_at"),
        "evidence_count": info.get("evidence_count", 0),
    }


def _pool_from_index(data_dir, limit, free_only, license_db, min_health, refresh, timeout):
    document = index_mod.load(data_dir, refresh=refresh, timeout=timeout)
    pool = []
    skipped_license = 0
    for registry in document["registries"]:
        if index_mod.health_status(registry) != "healthy":
            continue
        if index_mod.health_score(registry) < min_health:
            continue
        namespace = registry.get("name")
        if free_only and not licenses.kept_in_free_only(license_db, namespace):
            skipped_license += 1
            continue
        pool.append(registry)
    pool.sort(key=lambda r: (index_mod.health_score(r), index_mod.item_count(r)), reverse=True)
    warnings = list(document.get("warnings") or [])
    if skipped_license:
        warnings.append(
            "%d registries omitted from the default pool by the free-first rule; name them explicitly to include them" % skipped_license
        )
    return pool[:limit], document, warnings


def _from_cli(query, registry_names, limit, timeout):
    """Ask the official CLI once per registry, in parallel.

    A single call with eight registries returns one registry's slice first
    (verified: 24 rows all from @keyline), so a query-ignoring registry can
    crowd out relevant hits from the rest. One bounded parallel call per
    registry keeps every registry represented and lets the relevance guard
    judge each registry separately.
    """
    if len(registry_names) == 1:
        result = shadcn.search(query, registry_names, max(limit * 3, 24), timeout=timeout)
        if not result.get("ok"):
            return None, result
        items = (result.get("data") or {}).get("items") or []
        return items, result

    def one(namespace):
        return namespace, shadcn.search(query, [namespace], max(limit, 12), timeout=timeout)

    items = []
    errors = []
    command = None
    any_ok = False
    workers = min(len(registry_names), 6)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for namespace, result in pool.map(one, registry_names):
            command = command or result.get("command")
            if result.get("ok"):
                any_ok = True
                items.extend((result.get("data") or {}).get("items") or [])
            else:
                errors.append({"registry": namespace, "error": result.get("error")})
    if not any_ok:
        first = errors[0]["error"] if errors else {"code": "shadcn_failed", "message": "shadcn search failed"}
        return None, {"ok": False, "data": None, "command": command, "error": first, "errors": errors}
    return items, {"ok": True, "data": {"items": items}, "command": command, "errors": errors}


def _from_index(data_dir, query, registry_names, limit, timeout):
    """Fallback: substring match over each registry's published item index."""
    registries = index_mod.by_name(index_mod.cached(data_dir))
    needle = query.strip().lower()
    hits = []
    warnings = []
    scanned = 0
    for namespace in registry_names:
        registry = registries.get(namespace)
        if not registry:
            warnings.append("%s is not in the cached index; skipped" % namespace)
            continue
        url = index_mod.url_template(registry)
        if not url or "{name}" not in url:
            warnings.append("%s has no usable item-index URL template; skipped" % namespace)
            continue
        # Registry index convention: everything before {name}, then registry.json.
        index_url = url.replace("{style}", "new-york").split("{name}")[0].rstrip("/") + "/registry.json"
        try:
            document = net.fetch_json_any(index_url, timeout=timeout)
        except net.FetchError as exc:
            warnings.append("%s item index unavailable (%s)" % (namespace, exc.code))
            continue
        items = document.get("items") if isinstance(document, dict) else document
        if not isinstance(items, list):
            warnings.append("%s item index has no items array; skipped" % namespace)
            continue
        scanned += 1
        for item in items:
            if not isinstance(item, dict):
                continue
            haystack = " ".join(str(item.get(key) or "") for key in ("name", "title", "description")).lower()
            if needle and needle not in haystack:
                continue
            hits.append({
                "name": item.get("name"),
                "title": item.get("title") or item.get("name"),
                "type": item.get("type") or "",
                "description": item.get("description") or "",
                "registry": namespace,
                "addCommandArgument": "%s/%s" % (namespace, item.get("name")),
            })
            if len(hits) >= limit * 3:
                break
    warnings.append("index fallback scanned %d registry indices; use `shadcn search` for relevance ranking" % scanned)
    return hits, {"ok": True, "data": None, "command": None}, warnings


def search(query, data_dir, registries=None, limit=8, types=None, free_only=True,
           min_health=0.0, pool=DEFAULT_POOL, refresh=False, timeout=60,
           index_fallback=True, force_index=False, license_db=None):
    """Return up to ``limit`` annotated candidates for ``query``."""
    started = time.time()
    license_db = license_db if license_db is not None else licenses.load(data_dir)
    wanted = _wanted_types(types)
    warnings = []

    explicit = bool(registries)
    if explicit:
        names = [r if r.startswith("@") or r in ("@shadcn",) else "@" + r for r in registries]
        document = None
    else:
        pool_registries, document, pool_warnings = _pool_from_index(
            data_dir, pool, free_only, license_db, min_health, refresh, timeout
        )
        names = [r["name"] for r in pool_registries]
        warnings.extend(pool_warnings)

    if free_only:
        names = [n for n in names if licenses.kept_in_free_only(license_db, n)]

    source = "shadcn-cli"
    cli_result = None
    items = None
    fallback_warnings = []
    if not names:
        items = []
        warnings.append("no registries left to search after the free-first filter")
    elif force_index:
        source = "index-scan"
        items, cli_result, fallback_warnings = _from_index(data_dir, query, names, limit, timeout)
        warnings.extend(fallback_warnings)
    else:
        try:
            items, cli_result = _from_cli(query, names, limit, timeout)
        except Exception as exc:  # defensive: subprocess wrappers never raise, this is a bug guard
            items = None
            cli_result = {"ok": False, "error": {"code": "search_exception", "message": str(exc)}}
        if items is None:
            if not index_fallback:
                items = []
                warnings.append("shadcn search unavailable and index fallback is disabled")
            else:
                source = "index-scan"
                if cli_result and cli_result.get("error"):
                    warnings.append("shadcn search unavailable: %s" % cli_result["error"].get("message"))
                items, cli_result, fallback_warnings = _from_index(data_dir, query, names, limit, timeout)
                warnings.extend(fallback_warnings)
        elif cli_result and cli_result.get("errors"):
            failed = [row["registry"] for row in cli_result["errors"]]
            warnings.append(
                "shadcn search failed for %d registries: %s" % (len(failed), ", ".join(failed))
            )

    if source == "shadcn-cli" and items:
        items, guard_warnings = relevance_guard(items, query)
        warnings.extend(guard_warnings)

    health = {}
    for registry in index_mod.cached(data_dir):
        health[registry.get("name")] = registry

    seen = set()
    results = []
    excluded = []
    for item in items or []:
        namespace = item.get("registry") or ""
        name = item.get("name") or ""
        if not namespace and item.get("addCommandArgument"):
            namespace = item["addCommandArgument"].split("/", 1)[0]
        if not name:
            continue
        if namespace not in names:
            # The CLI can return namespaces beyond those requested (aliases,
            # nested registries); keep only what was asked for.
            continue
        type_name = _type_name(item.get("type"))
        license_row = _license_row(license_db, namespace, free_only)
        if type_name in EXAMPLE_TYPES and type_name not in wanted:
            excluded.append({"registry": namespace, "name": name, "reason": "type_%s: not a component candidate" % type_name})
            continue
        if wanted and type_name not in wanted:
            excluded.append({"registry": namespace, "name": name, "reason": "type_%s: not requested" % type_name})
            continue
        if free_only and not license_row["kept"]:
            excluded.append({"registry": namespace, "name": name, "reason": license_row["reason"]})
            continue
        key = (namespace, name)
        if key in seen:
            continue
        seen.add(key)
        registry = health.get(namespace) or {}
        results.append({
            "registry": namespace,
            "name": name,
            "title": item.get("title") or name,
            "type": item.get("type") or "",
            "description": item.get("description") or "",
            "add_command": "npx shadcn@latest add %s/%s" % (namespace, name),
            "license": license_row,
            "health": {"score": round(index_mod.health_score(registry), 1), "status": index_mod.health_status(registry)},
        })
        if len(results) >= limit:
            break

    return {
        "schema": SCHEMA,
        "query": query,
        "registries": names,
        "limit": limit,
        "types": sorted(wanted),
        "free_only": free_only,
        "source": source,
        "cli": {
            "command": (cli_result or {}).get("command"),
            "ok": bool((cli_result or {}).get("ok")),
            "error": (cli_result or {}).get("error"),
            "failed_registries": [row.get("registry") for row in (cli_result or {}).get("errors") or []],
        },
        "count": len(results),
        "results": results,
        "excluded": excluded[:20],
        "warnings": warnings,
        "elapsed_ms": int((time.time() - started) * 1000),
    }
