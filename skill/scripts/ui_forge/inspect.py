"""The compatibility gate.

Reads one registry item (and, one level deep, its registryDependencies), scans
the real file contents for primitive-library imports, diffs it against the
target project's fingerprint, and emits a numeric ``compat_risk`` from 0 to 10
plus the evidence behind every point. The point of the gate is to be cheap and
arguable: no rendering, no installing, no guessing.
"""
import hashlib
import json
import os
import re
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlsplit

from . import index as index_mod
from . import licenses, net, project as project_mod
from . import runctx as runctx_mod

IMPORT_RE = re.compile(
    r"""(?:from\s+|import\s*\(\s*|import\s+|require\s*\(\s*)['"]([^'"]+)['"]"""
)
BASE_IMPORT = (
    ("radix", re.compile(r"^(@radix-ui/|radix-ui$)")),
    ("base", re.compile(r"^(@base-ui/|@base-ui-components/)")),
    ("aria", re.compile(r"^(react-aria-components$|@react-aria/|@react-stately/)")),
)
NETWORK_PATTERNS = (
    ("network_fetch", re.compile(r"\bfetch\s*\(")),
    ("network_axios", re.compile(r"\baxios\b")),
    ("network_websocket", re.compile(r"\bnew\s+WebSocket\b|\bEventSource\b")),
    ("analytics", re.compile(r"\b(gtag|posthog|mixpanel|plausible|umami|segment)\b", re.I)),
    ("dynamic_code", re.compile(r"\beval\s*\(|\bnew\s+Function\s*\(")),
)
WEIGHTS = {
    "base_mismatch": 4.0,
    "base_conflict": 3.0,
    "base_project_unknown": 1.0,
    "tailwind_mismatch": 3.0,
    "tailwind_project_unknown": 1.0,
    "token_collision_each": 1.5,
    "token_collision_cap": 3.0,
    "missing_dep_each": 0.5,
    "missing_dep_cap": 2.0,
    "regdeps_3_to_5": 1.0,
    "regdeps_over_5": 2.0,
    "license_unknown": 0.5,
    "license_paywall": 10.0,
}


class UsageError(Exception):
    def __init__(self, code, message, hint=None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.hint = hint

    def as_dict(self):
        return {"code": self.code, "message": self.message, "hint": self.hint}


class Resolver:
    """Resolve ``@namespace/item`` targets lazily, so a direct URL needs no index."""

    def __init__(self, data_dir, project=None):
        self.data_dir = data_dir
        self.project = project or {}
        self._index = None
        self._licenses = None

    def registries(self):
        if self._index is None:
            self._index = index_mod.load(self.data_dir)["registries"]
        return self._index

    def license_db(self):
        if self._licenses is None:
            self._licenses = licenses.load(self.data_dir)
        return self._licenses

    def style(self):
        return self.project.get("style") or "new-york"

    def _registry_url(self, namespace):
        # Explicit project configuration wins and costs no network call.
        template = (self.project.get("registries") or {}).get(namespace)
        if template:
            return {"name": namespace, "url": template}
        registry = index_mod.find(self.registries(), namespace)
        if registry:
            return registry
        if namespace == "@shadcn":
            # The official namespace is built into the shadcn CLI/components.json
            # and is not part of the 539-registry community index.
            return {"name": "@shadcn", "url": "https://ui.shadcn.com/r/styles/{style}/{name}.json"}
        return None

    def candidates(self, target):
        target = target.strip()
        if target.startswith("http://") or target.startswith("https://"):
            return [target], "url"
        if "/" not in target:
            raise UsageError(
                "bad_target",
                "expected @namespace/item or a full item JSON URL, got %r" % target,
                "example: @magicui/hero-video-dialog or https://magicui.design/r/hero-video-dialog",
            )
        namespace, item = target.split("/", 1)
        if "/" in item:
            raise UsageError(
                "github_registry_unsupported",
                "GitHub registries (owner/repo/item) are not resolvable from the community index",
                "pass the item JSON URL directly, e.g. inspect https://raw.githubusercontent.com/<owner>/<repo>/HEAD/<path>.json",
            )
        registry = self._registry_url(namespace)
        if not registry:
            raise UsageError(
                "registry_not_in_index",
                "registry %s is not in the official index and no URL template is configured" % namespace,
                "pass the item JSON URL directly, or add the registry to the project's components.json registries",
            )
        urls = index_mod.item_url_candidates(registry, item, self.style())
        return urls, namespace


def _classify_import(name):
    for base, pattern in BASE_IMPORT:
        if pattern.search(name):
            return base
    return None


def scan_files(files):
    """Scan registry-item files for imports, primitive base and risk signals."""
    imports = set()
    base_signals = {"radix": [], "base": [], "aria": []}
    internal = 0
    flags = {}
    total_bytes = 0
    for entry in files:
        content = entry.get("content") or ""
        path = entry.get("path") or entry.get("target") or ""
        total_bytes += len(content.encode("utf-8", "replace"))
        for match in IMPORT_RE.findall(content):
            imports.add(match)
            base = _classify_import(match)
            if base:
                base_signals[base].append({"import": match, "path": path})
            if match.startswith("@/") or match.startswith("~/") or match.startswith("src/"):
                internal += 1
        for code, pattern in NETWORK_PATTERNS:
            if pattern.search(content):
                flags.setdefault(code, []).append(path)
    return {
        "imports": sorted(imports),
        "base_signals": {key: value[:8] for key, value in base_signals.items()},
        "internal_imports": internal,
        "security_flags": flags,
        "bytes": total_bytes,
    }


def _bases_from_deps(dependencies):
    found = set()
    for name in dependencies or []:
        base = _classify_import(name)
        if base:
            found.add(base)
    return found


def _css_var_names(css_vars):
    names = set()
    if not isinstance(css_vars, dict):
        return names
    for key, value in css_vars.items():
        if isinstance(value, dict):
            for name in value:
                names.add(name if name.startswith("--") else "--" + name)
        elif isinstance(value, str) and key.startswith("--"):
            names.add(key)
    return names


def _fetch_registry_dep(resolver, namespace, label, timeout, cache_dir=None):
    """Resolve one registryDependency, one level deep. Returns a record."""
    record = {"target": label, "url": None, "ok": False, "error": None, "deps": [], "base_signals": {}}
    try:
        if label.startswith("http"):
            urls = [label]
        elif label.startswith("@"):
            urls, _ = resolver.candidates(label)
        else:
            urls = resolver.candidates("%s/%s" % (namespace, label))[0]
    except UsageError as exc:
        record["error"] = {"code": exc.code, "message": exc.message}
        return record
    try:
        item, used, _failures = net.fetch_json_candidates(urls, timeout=timeout, cache_dir=cache_dir)
    except net.FetchError as exc:
        record["error"] = {"code": exc.code, "message": exc.message}
        return record
    record["url"] = used
    record["ok"] = True
    record["deps"] = item.get("dependencies") or []
    scanned = scan_files(item.get("files") or [])
    record["base_signals"] = {key: value[:4] for key, value in scanned["base_signals"].items() if value}
    record["bases"] = sorted(
        set(_classify_import(dep) for dep in record["deps"] if _classify_import(dep))
        | set(key for key, value in scanned["base_signals"].items() if value)
    )
    return record


def _paywall_gate(target, url, status, license_info):
    return {
        "schema": "ui-forge/inspect/v1",
        "target": target,
        "url": url,
        "item": None,
        "gate": {
            "verdict": "fail",
            "excluded": True,
            "exclude_reason": "license_paywall: item fetch answered HTTP %s" % status,
            "compat_risk": 10.0,
            "reasons": [{
                "code": "license_paywall",
                "weight": WEIGHTS["license_paywall"],
                "severity": "high",
                "detail": "item JSON answered HTTP %s; treat as paid/private and do not retry" % status,
                "evidence": [{"url": url, "http_status": status}],
            }],
            "unknowns": [],
            "license": license_info,
        },
    }


def _namespace_for_target(target):
    """License lookup key for a target, including the built-in shadcn host."""
    if not target.startswith("http"):
        return target.split("/", 1)[0]
    host = (urlsplit(target).hostname or "").lower()
    if host == "ui.shadcn.com":
        return "@shadcn"
    return ""


def inspect(target, data_dir, project_dir=None, use_cli=True, recurse=True,
            max_regdeps=4, timeout=30, refresh_index=False, ctx=None, cache_dir=None):
    """Run the gate for one target. Returns the inspect report dict.

    ``ctx`` (a runctx.RunContext) bounds the whole run: the fingerprint's
    CLI call, the item fetch and every registryDependency fetch share one
    deadline instead of stacking private timeouts, and progress is logged
    to stderr per stage. If the deadline expires before the item itself is
    fetched, runctx.DeadlineExceeded propagates; after that point the run
    finishes as a partial report (``partial: true``) with the unfinished
    stages named in the gate's unknowns.
    """
    ctx = ctx or runctx_mod.RunContext()
    partial = {"hit": False, "stage": None}

    def note_deadline(stage):
        partial["hit"] = True
        partial["stage"] = stage

    project_fp = None
    if project_dir:
        ctx.log("fingerprint", "reading project (shadcn info, cached 24h by file signature)")
        cli_timeout = ctx.budget("fingerprint", 60) if use_cli else None
        project_fp = project_mod.fingerprint(
            project_dir, use_cli=use_cli, data_dir=data_dir, cli_timeout=cli_timeout)
        ctx.log("fingerprint", "base=%s tailwind=%s%s" % (
            project_fp.get("base"), project_fp.get("tailwind_version"),
            " (cache)" if project_fp.get("from_cache") else ""))
    resolver = Resolver(data_dir, project_fp)
    if refresh_index:
        index_mod.load(data_dir, refresh=True)
    license_info = licenses.lookup(resolver.license_db(), _namespace_for_target(target))
    urls, source = resolver.candidates(target)

    ctx.check("fetch")
    ctx.log("fetch", "%s -> %s" % (target, urls[0] if urls else "?"))
    try:
        item, used_url, failures = net.fetch_json_candidates(
            urls, timeout=ctx.budget("fetch", timeout), cache_dir=cache_dir)
    except net.FetchError as exc:
        if exc.code in ("http_401", "http_402", "http_403"):
            license_info = dict(license_info)
            license_info["status"] = "paid" if license_info.get("status") == "unknown" else license_info["status"]
            return _paywall_gate(target, exc.url or (urls[0] if urls else None), exc.status, license_info)
        raise

    files = item.get("files") or []
    scanned = scan_files(files)
    dependencies = item.get("dependencies") or []
    dev_dependencies = item.get("devDependencies") or []
    registry_deps = item.get("registryDependencies") or []
    item_bases = set(_bases_from_deps(dependencies + dev_dependencies))
    item_bases |= {key for key, value in scanned["base_signals"].items() if value}

    recursive = []
    if recurse and registry_deps:
        namespace = source if source != "url" else ""
        labels = list(registry_deps[:max_regdeps])
        ctx.log("registry_dependencies", "%d to inspect (parallel, cap %d of %d)" % (
            len(labels), max_regdeps, len(registry_deps)))

        def fetch_one(label):
            try:
                budget = ctx.budget("registry_dependencies", timeout)
            except runctx_mod.DeadlineExceeded:
                return {"target": label, "url": None, "ok": False,
                        "error": {"code": "deadline_exceeded",
                                  "message": "run deadline expired before this fetch"},
                        "deps": [], "base_signals": {}}
            return _fetch_registry_dep(resolver, namespace, label, budget, cache_dir=cache_dir)

        if len(labels) == 1:
            recursive = [fetch_one(labels[0])]
        else:
            with ThreadPoolExecutor(max_workers=min(4, len(labels))) as pool:
                recursive = list(pool.map(fetch_one, labels))
        for record in recursive:
            if record.get("ok"):
                item_bases |= set(record.get("bases") or [])
            elif (record.get("error") or {}).get("code") == "deadline_exceeded":
                note_deadline("registry_dependencies")
        ctx.log("registry_dependencies", "done: %d ok, %d failed" % (
            sum(1 for r in recursive if r.get("ok")),
            sum(1 for r in recursive if not r.get("ok"))))

    reasons = []
    unknowns = []

    # --- primitive base -----------------------------------------------------
    if len(item_bases) > 1:
        reasons.append({
            "code": "base_conflict",
            "weight": WEIGHTS["base_conflict"],
            "severity": "high",
            "detail": "item references more than one primitive base: %s" % ", ".join(sorted(item_bases)),
            "evidence": [{"base": base, "imports": scanned["base_signals"].get(base, [])[:3]} for base in sorted(item_bases)],
        })
    elif item_bases:
        item_base = next(iter(item_bases))
        if project_fp:
            project_base = project_fp.get("base")
            if project_base and project_base != item_base:
                reasons.append({
                    "code": "base_mismatch",
                    "weight": WEIGHTS["base_mismatch"],
                    "severity": "high",
                    "detail": "item uses %s primitives but the project is on %s" % (item_base, project_base),
                    "evidence": [{"item_base": item_base, "project_base": project_base,
                                  "imports": scanned["base_signals"].get(item_base, [])[:3],
                                  "project_evidence": project_fp.get("base_evidence")}],
                })
            elif not project_base:
                reasons.append({
                    "code": "base_project_unknown",
                    "weight": WEIGHTS["base_project_unknown"],
                    "severity": "low",
                    "detail": "item uses %s primitives but the project's base could not be determined" % item_base,
                    "evidence": [{"item_base": item_base, "project_evidence": project_fp.get("base_evidence")}],
                })
    else:
        unknowns.append("item imports no primitive library; primitive base is not detectable from files[].content")

    # --- tailwind major -----------------------------------------------------
    item_v3 = bool(item.get("tailwind"))
    item_v4 = "theme" in (item.get("cssVars") or {})
    project_tailwind = (project_fp or {}).get("tailwind_version")
    if item_v3 and project_tailwind == "v4":
        reasons.append({
            "code": "tailwind_major_mismatch",
            "weight": WEIGHTS["tailwind_mismatch"],
            "severity": "high",
            "detail": "item ships a Tailwind v3 `tailwind` config block; project is Tailwind v4 (CSS-first)",
            "evidence": [{"item_tailwind_block": True, "project_tailwind": project_tailwind,
                          "project_source": (project_fp or {}).get("tailwind_source")}],
        })
    elif item_v4 and project_tailwind == "v3":
        reasons.append({
            "code": "tailwind_major_mismatch",
            "weight": WEIGHTS["tailwind_mismatch"],
            "severity": "high",
            "detail": "item defines a Tailwind v4 `theme` cssVars block; project is Tailwind v3",
            "evidence": [{"item_theme_block": True, "project_tailwind": project_tailwind}],
        })
    elif (item_v3 or item_v4) and not project_tailwind:
        reasons.append({
            "code": "tailwind_project_unknown",
            "weight": WEIGHTS["tailwind_project_unknown"],
            "severity": "low",
            "detail": "item carries Tailwind-version-specific styling but the project's Tailwind major is unknown",
            "evidence": [{"item_v3_block": item_v3, "item_v4_theme": item_v4}],
        })
    elif not item_v3 and not item_v4:
        unknowns.append("item carries no Tailwind-version-specific block; major mismatch cannot be detected from metadata")

    # --- token collisions ---------------------------------------------------
    item_vars = _css_var_names(item.get("cssVars") or {})
    project_tokens = {name.lower() for name in ((project_fp or {}).get("tokens") or {})}
    collisions = sorted(name.lower() for name in item_vars if name.lower() in project_tokens)
    if collisions:
        weight = min(WEIGHTS["token_collision_each"] * len(collisions), WEIGHTS["token_collision_cap"])
        reasons.append({
            "code": "token_collision",
            "weight": round(weight, 1),
            "severity": "medium",
            "detail": "item redefines %d token(s) the project already declares: %s" % (len(collisions), ", ".join(collisions[:6])),
            "evidence": [{"tokens": collisions[:12], "project_css": (project_fp or {}).get("css_path")}],
        })
    elif item_vars and not project_tokens:
        unknowns.append("item defines cssVars but the project's token set could not be read")

    # --- dependencies -------------------------------------------------------
    missing = []
    if project_fp:
        installed = project_fp.get("installed") or {}
        for dep in list(dependencies) + list(dev_dependencies):
            if dep.startswith(".") or dep.startswith("/") or dep.startswith("@"):
                if dep.startswith("@/") or dep.startswith("~/"):
                    continue
            if dep.split("@")[0] == "" and dep.startswith("@"):
                continue
            if dep not in installed:
                missing.append(dep)
        if missing:
            weight = min(WEIGHTS["missing_dep_each"] * len(missing), WEIGHTS["missing_dep_cap"])
            reasons.append({
                "code": "missing_deps",
                "weight": round(weight, 1),
                "severity": "medium",
                "detail": "%d declared dependency/dependencies are not installed in the project" % len(missing),
                "evidence": [{"missing": missing[:10],
                              "note": "the shadcn CLI installs declared npm deps on add; some registries also list bookkeeping entries (e.g. cn) here"}],
            })
    else:
        unknowns.append("no --project given; missing dependencies and token collisions were not checked")

    # --- registry dependency weight -----------------------------------------
    if len(registry_deps) > 5:
        reasons.append({
            "code": "heavy_registry_dependencies",
            "weight": WEIGHTS["regdeps_over_5"],
            "severity": "medium",
            "detail": "item pulls in %d registry dependencies" % len(registry_deps),
            "evidence": [{"registryDependencies": registry_deps[:12]}],
        })
    elif len(registry_deps) >= 3:
        reasons.append({
            "code": "registry_dependencies",
            "weight": WEIGHTS["regdeps_3_to_5"],
            "severity": "low",
            "detail": "item pulls in %d registry dependencies" % len(registry_deps),
            "evidence": [{"registryDependencies": registry_deps[:12]}],
        })
    failed_regdeps = [r for r in recursive if not r.get("ok")]
    if failed_regdeps:
        unknowns.append("could not inspect registryDependencies: %s" % ", ".join(r["target"] for r in failed_regdeps))
    if partial["hit"]:
        unknowns.append(
            "run deadline of %ss was reached during %s; this report is partial — "
            "unfinished stages are named above, rerun with a larger --deadline to complete them"
            % (ctx.deadline, partial["stage"]))

    # --- license ------------------------------------------------------------
    status = license_info.get("status", "unknown")
    excluded = False
    exclude_reason = None
    if status in ("paid", "freemium"):
        excluded = True
        exclude_reason = "license_%s: free-first rule excludes this registry (see license evidence)" % status
        reasons.append({
            "code": "license_paywalled",
            "weight": WEIGHTS["license_paywall"],
            "severity": "high",
            "detail": "registry license status is %s; free-first rule excludes it without explicit user approval" % status,
            "evidence": [{"status": status, "checked_at": license_info.get("checked_at"),
                          "evidence": license_info.get("evidence", [])[:3]}],
        })
    elif status == "unknown":
        reasons.append({
            "code": "license_unknown",
            "weight": WEIGHTS["license_unknown"],
            "severity": "low",
            "detail": "no license evidence for this registry; ask the user before installing",
            "evidence": [{"note": license_info.get("note")}],
        })

    compat_risk = round(min(10.0, sum(r["weight"] for r in reasons)), 1)
    if excluded:
        verdict = "fail"
    elif compat_risk >= 6:
        verdict = "fail"
    elif compat_risk >= 3:
        verdict = "warn"
    else:
        verdict = "pass"

    ctx.log("gate", "compat_risk computed from %d reason(s)" % len(reasons))
    canonical = json.dumps(item, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    report = {
        "schema": "ui-forge/inspect/v1",
        "target": target,
        "url": used_url,
        "resolved_from": source,
        "partial": bool(partial["hit"]),
        "timing": {
            "elapsed_seconds": round(ctx.elapsed(), 2),
            "deadline_seconds": ctx.deadline,
            "deadline_stage": partial["stage"],
        },
        "item": {
            "name": item.get("name"),
            "title": item.get("title"),
            "type": item.get("type"),
            "description": item.get("description"),
            "dependencies": dependencies,
            "devDependencies": dev_dependencies,
            "registryDependencies": registry_deps,
            "files": [{"path": f.get("path") or f.get("target"), "type": f.get("type"),
                       "bytes": len((f.get("content") or "").encode("utf-8", "replace"))} for f in files],
            "css_vars": sorted(item_vars),
            "tailwind_block": item_v3,
            "tailwind_theme_block": item_v4,
            "imports": scanned["imports"],
            "base_signals": scanned["base_signals"],
            "item_bases": sorted(item_bases),
            "security_flags": scanned["security_flags"],
            "sha256": hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
        },
        "registry_dependencies_inspected": recursive,
        "project": None if project_fp is None else {
            "root": project_fp.get("root"),
            "framework": project_fp.get("framework"),
            "base": project_fp.get("base"),
            "base_source": project_fp.get("base_source"),
            "base_evidence": project_fp.get("base_evidence"),
            "tailwind_version": project_fp.get("tailwind_version"),
            "tailwind_source": project_fp.get("tailwind_source"),
            "tokens": sorted(project_fp.get("tokens") or {})[:40],
            "cli": project_fp.get("cli"),
            "warnings": project_fp.get("warnings") or [],
        },
        "gate": {
            "verdict": verdict,
            "excluded": excluded,
            "exclude_reason": exclude_reason,
            "compat_risk": compat_risk,
            "reasons": reasons,
            "unknowns": unknowns,
            "license": license_info,
            "weights": WEIGHTS,
        },
        "warnings": (project_fp or {}).get("warnings") or [],
    }
    return report
