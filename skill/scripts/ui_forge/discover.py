"""Registry discovery, free-first by default.

Reads the official registry index (cached for 24h) and annotates every row with
license truth from ``data/licenses.json``. Paid and freemium registries are
dropped unless explicitly asked for; unknown ones stay but are flagged.
"""
from . import index as index_mod
from . import licenses

SCHEMA = "ui-forge/discover/v1"


def discover(data_dir, limit=20, min_health=0.0, free_only=True, refresh=False,
             timeout=30, status="healthy", license_db=None):
    document = index_mod.load(data_dir, refresh=refresh, timeout=timeout)
    license_db = license_db if license_db is not None else licenses.load(data_dir)
    registries = document["registries"]

    rows = []
    excluded = []
    for registry in registries:
        namespace = registry.get("name")
        status_value = index_mod.health_status(registry)
        score = index_mod.health_score(registry)
        license_info = licenses.lookup(license_db, namespace)
        kept_by_license = licenses.kept_in_free_only(license_db, namespace)

        # License is a hard rule and is decided before any health filter, so a
        # paywalled registry is always reported with its evidence instead of
        # silently disappearing because it is also degraded.
        if free_only and not kept_by_license:
            paywall = next(
                (e for e in (license_info.get("evidence") or []) if e.get("http_status") in (401, 402, 403)),
                None,
            )
            if paywall:
                reason = "%s - evidence HTTP %s at %s" % (
                    license_info["status"], paywall["http_status"], paywall["url"],
                )
            else:
                reason = "%s - see licenses.json evidence" % license_info["status"]
            excluded.append({
                "registry": namespace,
                "status": license_info["status"],
                "health": score,
                "health_status": status_value,
                "items": index_mod.item_count(registry),
                "reason": reason,
            })
            continue

        if status and status != "any" and status_value != status:
            continue
        if score < min_health:
            continue

        row = index_mod.normalize(registry)
        row["license"] = {
            "status": license_info["status"],
            "flagged": license_info["status"] == "unknown",
            "checked_at": license_info.get("checked_at"),
            "evidence_count": license_info.get("evidence_count", 0),
        }
        rows.append(row)

    rows.sort(key=lambda row: (row["health"], row["items"]), reverse=True)
    total_items = sum(index_mod.item_count(r) for r in registries)
    healthy = sum(1 for r in registries if index_mod.health_status(r) == "healthy")
    return {
        "schema": SCHEMA,
        "source": document["source"],
        "from_cache": document["from_cache"],
        "stale": document["stale"],
        "age_seconds": document["age_seconds"],
        "total_registries": len(registries),
        "healthy": healthy,
        "total_items": total_items,
        "filters": {"min_health": min_health, "status": status, "free_only": free_only, "limit": limit},
        "count": len(rows[:limit]),
        "registries": rows[:limit],
        "excluded_by_license": excluded[:10],
        "excluded_by_license_count": len(excluded),
        "warnings": list(document.get("warnings") or []),
    }
