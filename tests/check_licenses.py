#!/usr/bin/env python3
"""Validate skill/data/licenses.json before a contribution is merged.

Offline on purpose: this checks structure and that the recorded HTTP statuses
are internally consistent. Re-probing the URLs is the contributor's job, as
described in CONTRIBUTING.md.
"""
import datetime
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATASET = os.path.join(ROOT, "skill", "data", "licenses.json")
STATUSES = {"free", "freemium", "paid", "unknown"}
PAYWALL = {401, 402, 403}
SCHEMA = "ui-forge/licenses/v1"


def is_date(value):
    try:
        datetime.date.fromisoformat(value)
        return True
    except (TypeError, ValueError):
        return False


def entry_problems(entry, index):
    where = "entry %d (%s)" % (index, entry.get("registry") if isinstance(entry, dict) else "?")
    problems = []
    if not isinstance(entry, dict):
        return ["entry %d is not an object" % index]
    registry = entry.get("registry")
    if not isinstance(registry, str) or not registry.startswith("@") or " " in registry:
        problems.append("%s: registry must be a namespace such as @magicui" % where)
    status = entry.get("status")
    if status not in STATUSES:
        problems.append("%s: status must be one of %s" % (where, sorted(STATUSES)))
        return problems
    evidence = entry.get("evidence")
    if not isinstance(evidence, list):
        problems.append("%s: evidence must be a list" % where)
        evidence = []
    codes = []
    for position, item in enumerate(evidence):
        if not isinstance(item, dict):
            problems.append("%s: evidence[%d] is not an object" % (where, position))
            continue
        url = item.get("url")
        code = item.get("http_status")
        if not isinstance(url, str) or not url.startswith(("http://", "https://")):
            problems.append("%s: evidence[%d].url must be an http(s) URL" % (where, position))
        if type(code) is not int:
            problems.append("%s: evidence[%d].http_status must be an integer" % (where, position))
        else:
            codes.append(code)
    if status == "free":
        if 200 not in codes:
            problems.append("%s: free needs at least one HTTP 200 evidence row" % where)
        if any(code in PAYWALL for code in codes):
            problems.append("%s: free has paywall evidence; use freemium instead" % where)
    elif status == "freemium":
        if 200 not in codes or not any(code in PAYWALL for code in codes):
            problems.append("%s: freemium needs both 200 and 401/402/403 evidence" % where)
    elif status == "paid":
        if not codes:
            problems.append("%s: paid needs evidence, not a guess" % where)
        elif any(code not in PAYWALL for code in codes):
            problems.append("%s: paid must cite only 401/402/403 evidence; use freemium instead" % where)
    if status != "unknown":
        for key in ("scope", "method"):
            value = entry.get(key)
            if not isinstance(value, str) or not value.strip():
                problems.append("%s: %s is required for a checked status" % (where, key))
        if not is_date(entry.get("checked_at")):
            problems.append("%s: checked_at must be an ISO date (YYYY-MM-DD)" % where)
    if entry.get("item_count") is not None and type(entry.get("item_count")) is not int:
        problems.append("%s: item_count must be an integer or null" % where)
    return problems


def main():
    try:
        with open(DATASET, "r", encoding="utf-8") as handle:
            document = json.load(handle)
    except (OSError, ValueError) as exc:
        print("licenses: cannot read %s: %s" % (DATASET, exc), file=sys.stderr)
        return 1
    if not isinstance(document, dict):
        print("licenses: top level must be an object", file=sys.stderr)
        return 1
    if document.get("schema") != SCHEMA:
        print("licenses: schema must be %s" % SCHEMA, file=sys.stderr)
        return 1
    entries = document.get("entries")
    if not isinstance(entries, list) or not entries:
        print("licenses: entries must be a non-empty list", file=sys.stderr)
        return 1

    problems = []
    names = []
    for index, entry in enumerate(entries):
        problems.extend(entry_problems(entry, index))
        if isinstance(entry, dict) and isinstance(entry.get("registry"), str):
            names.append(entry["registry"])
    duplicates = sorted({name for name in names if names.count(name) > 1})
    if duplicates:
        problems.append("duplicate registries: %s" % ", ".join(duplicates))
    if names != sorted(names):
        problems.append("entries must stay sorted by registry name (see CONTRIBUTING.md)")

    counts = {}
    for entry in entries:
        if isinstance(entry, dict):
            counts[entry.get("status")] = counts.get(entry.get("status"), 0) + 1
    summary = ", ".join("%s %d" % (status, counts[status]) for status in sorted(counts))
    if problems:
        for problem in problems:
            print("licenses: %s" % problem, file=sys.stderr)
        return 1
    print("licenses: %d entries valid (%s)" % (len(entries), summary))
    return 0


if __name__ == "__main__":
    sys.exit(main())
