"""Fingerprint the target project.

The official shadcn skill already answers "what is this project?" with
``shadcn info --json``: framework, Tailwind version, primitive base, aliases,
resolved paths, installed components. ui-forge uses that as the source of
truth and falls back to reading ``components.json`` / ``package.json`` / the
Tailwind CSS entry when the CLI is unavailable, so the gate still works in
CI and in projects where Node is not installed.
"""
import json
import os
import re
import tempfile
import time

from . import shadcn

CACHE_NAME = "fingerprint-cache.json"
# The cache entry is keyed by a signature of the exact files it was derived
# from (components.json, package.json, tsconfig, the Tailwind CSS entry), so
# a long TTL is safe: any edit to those files invalidates it immediately.
CACHE_TTL = 86400
STYLE_BASE = re.compile(r"^(radix|base|aria)-")
CSS_TOKEN = re.compile(r"(--[a-zA-Z0-9_-]+)\s*:\s*([^;]+);")
TAILWIND_V4 = re.compile(r"@import\s+[\"']tailwindcss[\"']|@theme\b")
BASE_DEPS = {
    "base": ("@base-ui/", "@base-ui-components/"),
    "aria": ("react-aria-components", "@react-aria/", "@react-stately/"),
    "radix": ("@radix-ui/", "radix-ui"),
}


def _read_json(path):
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def style_base(style):
    """Map a components.json style to a primitive base, with a reason."""
    if not style:
        return None, "no components.json style"
    match = STYLE_BASE.match(style)
    if match:
        return match.group(1), "components.json style=%s" % style
    if style in ("default", "new-york"):
        return "radix", "legacy style=%s predates primitive bases and is Radix" % style
    return None, "unrecognised style %s" % style


def deps_base(dependencies):
    """Infer primitive base(s) from installed package names."""
    found = {}
    for name in dependencies:
        for base, prefixes in BASE_DEPS.items():
            for prefix in prefixes:
                if name == prefix or (prefix.endswith("/") and name.startswith(prefix)):
                    found.setdefault(base, []).append(name)
    return found


def _major(spec):
    if not isinstance(spec, str):
        return None
    match = re.search(r"(\d+)", spec)
    return int(match.group(1)) if match else None


def read_tokens(css_path):
    if not css_path or not os.path.exists(css_path):
        return {}
    try:
        with open(css_path, "r", encoding="utf-8", errors="replace") as handle:
            text = handle.read()
    except OSError:
        return {}
    tokens = {}
    for name, value in CSS_TOKEN.findall(text):
        tokens.setdefault(name, value.strip()[:120])
    return tokens


def _css_path(root, components):
    relative = ((components.get("tailwind") or {}).get("css") or "").strip() or "src/app/globals.css"
    return os.path.join(root, relative.replace("/", os.sep))


def _signature(root, css_path):
    files = [
        os.path.join(root, "components.json"),
        os.path.join(root, "package.json"),
        os.path.join(root, "tsconfig.json"),
        os.path.join(root, "jsconfig.json"),
    ]
    if css_path:
        files.append(css_path)
    signature = {}
    for path in files:
        try:
            stat = os.stat(path)
            signature[path] = [int(stat.st_mtime_ns), stat.st_size]
        except OSError:
            signature[path] = None
    return signature


def _cache_load(data_dir, root, signature):
    path = os.path.join(data_dir, CACHE_NAME)
    try:
        with open(path, "r", encoding="utf-8") as handle:
            cached = json.load(handle)
    except (OSError, ValueError):
        return None
    entry = (cached.get("entries") or {}).get(root)
    if not isinstance(entry, dict):
        return None
    if time.time() - float(entry.get("saved_at") or 0) > CACHE_TTL:
        return None
    if entry.get("signature") != signature:
        return None
    return entry.get("fingerprint")


def _cache_save(data_dir, root, signature, fingerprint):
    path = os.path.join(data_dir, CACHE_NAME)
    try:
        with open(path, "r", encoding="utf-8") as handle:
            cached = json.load(handle)
        if not isinstance(cached, dict):
            cached = {}
    except (OSError, ValueError):
        cached = {}
    entries = cached.get("entries")
    if not isinstance(entries, dict):
        entries = {}
    entries[root] = {"saved_at": time.time(), "signature": signature, "fingerprint": fingerprint}
    if len(entries) > 100:
        for stale in sorted(entries, key=lambda key: entries[key].get("saved_at") or 0)[:-100]:
            entries.pop(stale, None)
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        fd, tmp = tempfile.mkstemp(prefix=".fingerprint-", suffix=".json", dir=os.path.dirname(path))
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump({"entries": entries}, handle)
        os.replace(tmp, path)
    except OSError:
        pass


def fingerprint(root, use_cli=True, data_dir=None, refresh=False, cli_timeout=None):
    """Return a stable fingerprint dict for the project at ``root``."""
    root = os.path.abspath(root)
    components = _read_json(os.path.join(root, "components.json"))
    package = _read_json(os.path.join(root, "package.json"))
    css_path = _css_path(root, components)
    signature = _signature(root, css_path)

    if data_dir and not refresh:
        cached = _cache_load(data_dir, root, signature)
        if isinstance(cached, dict):
            cached = dict(cached)
            cached["from_cache"] = True
            return cached

    warnings = []
    dependencies = {}
    dependencies.update(package.get("dependencies") or {})
    dependencies.update(package.get("devDependencies") or {})

    cli_attempted = bool(use_cli)
    cli_result = {"attempted": cli_attempted, "ok": False, "command": None, "error": None}
    cli_info = {}
    if use_cli:
        result = shadcn.info(root, timeout=cli_timeout or shadcn.DEFAULT_TIMEOUT)
        cli_result["command"] = result.get("command")
        if result.get("ok") and isinstance(result.get("data"), dict):
            cli_info = result["data"]
            cli_result["ok"] = True
        else:
            cli_result["error"] = (result.get("error") or {}).get("message") or "shadcn info failed"

    config = cli_info.get("config") or {}
    project_info = cli_info.get("project") or {}

    # --- primitive base -----------------------------------------------------
    base = None
    base_source = None
    base_evidence = []
    cli_base = config.get("base")
    if cli_base in ("radix", "base", "aria"):
        base = cli_base
        base_source = "shadcn info --json"
        base_evidence.append("shadcn info config.base=%s" % cli_base)

    style = components.get("style") or config.get("style")
    style_derived, style_reason = style_base(style)
    if base is None and style_derived:
        base = style_derived
        base_source = "components.json style"
        base_evidence.append(style_reason)
    if base is None:
        found = deps_base(dependencies)
        if len(found) == 1:
            base = next(iter(found))
            base_source = "installed packages"
            base_evidence.append("installed: %s" % ", ".join(sorted(found[base])[:5]))
        elif len(found) > 1:
            warnings.append("installed packages reference more than one primitive base: %s" % ", ".join(sorted(found)))
            base_evidence.append("conflicting bases in installed packages: %s" % ", ".join(sorted(found)))
    if base is None:
        base_source = "unknown"
        base_evidence.append("no components.json style and no primitive packages found")
    if cli_base in ("radix", "base", "aria") and style_derived and cli_base != style_derived:
        warnings.append("shadcn info base=%s disagrees with style=%s (base=%s); trusting shadcn info" % (cli_base, style, style_derived))

    # --- tailwind major -----------------------------------------------------
    tailwind_version = None
    tailwind_source = None
    cli_tailwind = project_info.get("tailwindVersion")
    if cli_tailwind in ("v3", "v4"):
        tailwind_version = cli_tailwind
        tailwind_source = "shadcn info --json"
    if tailwind_version is None:
        css_text = ""
        if css_path and os.path.exists(css_path):
            try:
                with open(css_path, "r", encoding="utf-8", errors="replace") as handle:
                    css_text = handle.read()
            except OSError:
                css_text = ""
        if TAILWIND_V4.search(css_text):
            tailwind_version = "v4"
            tailwind_source = "tailwind css entry imports tailwindcss"
        else:
            major = _major(dependencies.get("tailwindcss"))
            if major == 4:
                tailwind_version = "v4"
                tailwind_source = "package.json tailwindcss=%s" % dependencies.get("tailwindcss")
            elif major == 3:
                tailwind_version = "v3"
                tailwind_source = "package.json tailwindcss=%s" % dependencies.get("tailwindcss")
            elif os.path.exists(os.path.join(root, "tailwind.config.js")) or os.path.exists(os.path.join(root, "tailwind.config.ts")):
                tailwind_version = "v3"
                tailwind_source = "tailwind.config present"
    if tailwind_version is None:
        warnings.append("could not determine the project's Tailwind major version")

    if not components:
        warnings.append("components.json not found at %s" % root)
    if not package:
        warnings.append("package.json not found at %s" % root)

    fingerprint_data = {
        "root": root,
        "framework": project_info.get("framework") or ("next/vite" if dependencies.get("next") or dependencies.get("vite") else None),
        "typescript": project_info.get("typescript", bool(dependencies.get("typescript"))),
        "base": base,
        "base_source": base_source,
        "base_evidence": base_evidence,
        "tailwind_version": tailwind_version,
        "tailwind_source": tailwind_source,
        "style": style,
        "css_path": css_path if css_path and os.path.exists(css_path) else None,
        "tokens": read_tokens(css_path),
        "installed": dependencies,
        "registries": components.get("registries") or {},
        "icon_library": components.get("iconLibrary") or config.get("iconLibrary"),
        "cli": cli_result,
        "warnings": warnings,
        "from_cache": False,
    }
    if data_dir:
        _cache_save(data_dir, root, signature, fingerprint_data)
    return fingerprint_data
