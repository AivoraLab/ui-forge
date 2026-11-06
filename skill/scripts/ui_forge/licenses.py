"""The license dataset: data/licenses.json.

This is the one dataset ui-forge ships as data rather than derives. The
official registry index and the registry-item schema carry no license field,
so free / freemium / paid status has to be recorded with evidence: the URL
that was fetched, the HTTP status it answered, and when. Unknown stays
unknown; ui-forge never guesses.
"""
import json
import os

FILE_NAME = "licenses.json"
STATUSES = ("free", "freemium", "paid", "unknown")
FREE_OK = ("free", "unknown")  # unknown is kept, but flagged


def dataset_path(data_dir):
    return os.path.join(data_dir, FILE_NAME)


def load(data_dir):
    """Return {'registries': {...}, 'updated_at': ..., 'warnings': [...]}."""
    path = dataset_path(data_dir)
    warnings = []
    if not os.path.exists(path):
        return {"registries": {}, "updated_at": None, "warnings": [
            "license dataset missing at %s; every registry is treated as unknown" % path
        ]}
    try:
        with open(path, "r", encoding="utf-8") as handle:
            document = json.load(handle)
    except (OSError, ValueError) as exc:
        return {"registries": {}, "updated_at": None, "warnings": [
            "license dataset unreadable (%s); every registry is treated as unknown" % exc
        ]}
    registries = None
    if isinstance(document, dict):
        candidate = document.get("registries")
        if isinstance(candidate, dict):
            registries = candidate
        elif isinstance(candidate, list):
            registries = {entry.get("registry"): entry for entry in candidate if isinstance(entry, dict) and entry.get("registry")}
        elif isinstance(document.get("entries"), list):
            # Accepted shape too: a plain array is easier to contribute to.
            registries = {entry.get("registry"): entry for entry in document["entries"] if isinstance(entry, dict) and entry.get("registry")}
    if not isinstance(registries, dict):
        return {"registries": {}, "updated_at": None, "warnings": [
            "license dataset has no registries map or entries array; every registry is treated as unknown"
        ]}
    for name, entry in registries.items():
        if not isinstance(entry, dict):
            continue
        if entry.get("status") not in STATUSES:
            entry["status"] = "unknown"
            warnings.append("license entry %s had an invalid status; treated as unknown" % name)
    return {"registries": registries, "updated_at": document.get("updated_at"), "warnings": warnings}


def lookup(db, namespace):
    """Return a normalised license record for one registry namespace."""
    entry = (db.get("registries") or {}).get(namespace)
    if not entry:
        return {
            "status": "unknown",
            "evidence": [],
            "evidence_count": 0,
            "checked_at": None,
            "note": "no license evidence recorded for this registry",
        }
    evidence = entry.get("evidence") or []
    return {
        "status": entry.get("status", "unknown"),
        "scope": entry.get("scope"),
        "method": entry.get("method"),
        "checked_at": entry.get("checked_at"),
        "evidence": evidence,
        "evidence_count": len(evidence),
        "note": entry.get("note"),
    }


def kept_in_free_only(db, namespace):
    """True when a registry survives the default free-only filter.

    free and unknown survive (unknown is flagged separately); paid and
    freemium do not, because ui-forge cannot promise the pick is free.
    """
    status = lookup(db, namespace).get("status", "unknown")
    return status in FREE_OK


def short(license_info):
    status = (license_info or {}).get("status", "unknown")
    count = (license_info or {}).get("evidence_count", 0)
    if status == "unknown":
        return "unknown (no license evidence)"
    return "%s (%d evidence record%s)" % (status, count, "" if count == 1 else "s")
