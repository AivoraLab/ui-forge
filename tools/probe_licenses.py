#!/usr/bin/env python3
"""Batch-probe every indexed registry and extend skill/data/licenses.json.

For each registry: read its published item index, sample first/middle/last
usable items, fetch those item URLs, and classify:

  200 only            -> free
  200 + 401/402/403  -> freemium
  only 401/402/403   -> paid
  no usable probe     -> unknown (with the reason in the note)

Existing verified entries are never overwritten. Output is sorted by registry
name, matching CONTRIBUTING.md.
"""
import argparse
import datetime
import json
import os
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "skill", "scripts"))

from ui_forge import index as index_mod  # noqa: E402

DATA_DIR = os.path.join(ROOT, "skill", "data")
DATASET = os.path.join(DATA_DIR, "licenses.json")
RAW = os.path.join(ROOT, ".tmp", "probe", "batch-results.json")
UA = "ui-forge-license-probe/2.0 (+https://github.com/KaiyoDev/ui-forge)"
PAYWALL = {401, 402, 403}
USABLE_TYPES = {"registry:ui", "registry:block", "registry:component", "registry:hook"}
LOCK = threading.Lock()
DONE = [0]


def http_code(url, timeout):
    request = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            response.read(64)
            return response.status, None
    except urllib.error.HTTPError as exc:
        return exc.code, None
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return None, str(exc)


def item_index_url(registry):
    template = index_mod.url_template(registry)
    if not template or "{name}" not in template:
        return None
    return template.replace("{style}", "new-york").split("{name}")[0].rstrip("/") + "/registry.json"


def sample_items(document):
    items = document.get("items") if isinstance(document, dict) else document
    if not isinstance(items, list):
        return []
    names = []
    for item in items:
        if not isinstance(item, dict):
            continue
        name = item.get("name")
        if not isinstance(name, str) or not name:
            continue
        kind = item.get("type") or ""
        if kind in USABLE_TYPES:
            names.append(name)
    if not names:
        names = [item.get("name") for item in items if isinstance(item, dict) and isinstance(item.get("name"), str)]
    names = list(dict.fromkeys(names))
    if not names:
        return []
    if len(names) <= 3:
        return names
    return [names[0], names[len(names) // 2], names[-1]]


def probe_registry(registry, timeout):
    namespace = registry.get("name")
    result = {
        "registry": namespace,
        "health": index_mod.health_score(registry),
        "health_status": index_mod.health_status(registry),
        "item_count": index_mod.item_count(registry),
        "status": "unknown",
        "evidence": [],
        "note": "",
    }
    index_url = item_index_url(registry)
    if not index_url:
        result["note"] = "registry has no usable {name} URL template"
        return result
    code, error = http_code(index_url, timeout)
    if code != 200:
        result["note"] = "item index answered %s" % (code or error)
        return result
    try:
        with urllib.request.urlopen(
            urllib.request.Request(index_url, headers={"User-Agent": UA, "Accept": "application/json"}),
            timeout=timeout,
        ) as response:
            document = json.loads(response.read().decode("utf-8", "replace"))
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
        result["note"] = "item index could not be parsed: %s" % exc
        return result

    samples = sample_items(document)
    if not samples:
        result["note"] = "item index has no sampleable items"
        return result

    codes = []
    for name in samples:
        url = index_mod.item_url_candidates(registry, name, "new-york")
        chosen = None
        status = None
        for candidate in url:
            status, error = http_code(candidate, timeout)
            chosen = candidate
            if status is not None and status not in (404, 415):
                break
        result["evidence"].append({"item": name, "url": chosen or url[0] if url else "", "http_status": status})
        codes.append(status)
        time.sleep(0.05)

    good = [code for code in codes if code == 200]
    wall = [code for code in codes if code in PAYWALL]
    if good and wall:
        result["status"] = "freemium"
        result["note"] = "%d/%d sampled items public; %d answer HTTP %s" % (
            len(good), len(samples), len(wall), "/".join(sorted({str(code) for code in wall})),
        )
    elif good:
        result["status"] = "free"
        result["note"] = "all %d sampled items answer HTTP 200" % len(good) if len(good) == len(samples) else (
            "%d/%d sampled items public; other samples answered %s" % (
                len(good), len(samples), ", ".join(str(code) for code in codes if code != 200),
            )
        )
    elif wall:
        result["status"] = "paid"
        result["note"] = "all %d sampled items answer HTTP %s (paywall or access control)" % (
            len(wall), "/".join(sorted({str(code) for code in wall})),
        )
    else:
        result["note"] = "no sample answered a usable HTTP status: %s" % ", ".join(
            str(code) for code in codes
        )
    return result


def main():
    parser = argparse.ArgumentParser(description="Batch-probe licenses for every indexed registry")
    parser.add_argument("--workers", type=int, default=12)
    parser.add_argument("--timeout", type=float, default=25.0)
    parser.add_argument("--limit", type=int, default=0, help="probe at most N registries (debug)")
    parser.add_argument("--include-degraded", action="store_true")
    parser.add_argument("--only-missing", action="store_true", help="probe only registries absent from licenses.json")
    parser.add_argument("--dry-run", action="store_true", help="probe but do not write licenses.json")
    args = parser.parse_args()

    loaded = index_mod.load(DATA_DIR)
    registries = loaded["registries"]
    if not args.include_degraded:
        registries = [r for r in registries if index_mod.health_status(r) == "healthy"]
    if args.only_missing:
        with open(DATASET, "r", encoding="utf-8") as handle:
            known = {entry["registry"] for entry in json.load(handle)["entries"]}
        registries = [r for r in registries if r.get("name") not in known]
    if args.limit:
        registries = registries[: args.limit]
    print("registries to probe: %d" % len(registries), flush=True)

    results = []
    started = time.time()
    with ThreadPoolExecutor(max_workers=max(1, min(args.workers, 24))) as pool:
        futures = {pool.submit(probe_registry, registry, args.timeout): registry for registry in registries}
        for future in as_completed(futures):
            registry = futures[future]
            try:
                result = future.result()
            except Exception as exc:  # keep going, one bad registry must not stop the batch
                result = {
                    "registry": registry.get("name"),
                    "health": index_mod.health_score(registry),
                    "health_status": index_mod.health_status(registry),
                    "item_count": index_mod.item_count(registry),
                    "status": "unknown",
                    "evidence": [],
                    "note": "probe crashed: %s: %s" % (type(exc).__name__, exc),
                }
            results.append(result)
            with LOCK:
                DONE[0] += 1
                if DONE[0] % 25 == 0 or DONE[0] == len(registries):
                    print("  %d/%d probed (%.0fs)" % (DONE[0], len(registries), time.time() - started), flush=True)

    results.sort(key=lambda row: row.get("registry") or "")
    os.makedirs(os.path.dirname(RAW), exist_ok=True)
    with open(RAW, "w", encoding="utf-8") as handle:
        json.dump({"probed_at": datetime.datetime.now().isoformat(timespec="seconds"), "results": results}, handle, indent=2)
    counts = {}
    for row in results:
        counts[row["status"]] = counts.get(row["status"], 0) + 1
    print("probe summary: %s" % ", ".join("%s %d" % (key, counts[key]) for key in sorted(counts)), flush=True)

    if args.dry_run:
        print("dry run: dataset untouched")
        return 0

    with open(DATASET, "r", encoding="utf-8") as handle:
        document = json.load(handle)
    existing = {entry["registry"]: entry for entry in document["entries"]}
    today = datetime.date.today().isoformat()
    added = 0
    for row in results:
        namespace = row["registry"]
        if not namespace or namespace in existing:
            continue
        if row["status"] == "unknown" and not row["evidence"]:
            # Unknown without any probe is not worth a dataset entry.
            continue
        existing[namespace] = {
            "registry": namespace,
            "status": row["status"],
            "scope": "registry",
            "method": "http_probe",
            "checked_at": today,
            "item_count": row["item_count"],
            "evidence": row["evidence"],
            "note": row["note"],
        }
        added += 1
    document["entries"] = [existing[name] for name in sorted(existing)]
    document["updated_at"] = today
    document["method"] = (
        "HTTP probe of item JSON built from the registry public URL template: "
        "200 = publicly served, 401/402/403 = paywall or access control; three items sampled "
        "(first, middle, last) per registry; statuses are evidence, not guesses."
    )
    directory = os.path.dirname(DATASET)
    handle = tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False, dir=directory, suffix=".tmp")
    try:
        json.dump(document, handle, indent=2, ensure_ascii=False)
        handle.write("\n")
        handle.close()
        os.replace(handle.name, DATASET)
    finally:
        if not handle.closed:
            handle.close()
        if os.path.exists(handle.name):
            try:
                os.unlink(handle.name)
            except OSError:
                pass
    print("licenses.json: %d entries total, %d newly verified" % (len(document["entries"]), added))
    return 0


if __name__ == "__main__":
    sys.exit(main())
