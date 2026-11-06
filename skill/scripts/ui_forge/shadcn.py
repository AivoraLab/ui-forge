"""Locate and run the official shadcn CLI.

ui-forge deliberately owns no transport of its own for search: the shadcn CLI
is the ecosystem's search engine, so ui-forge calls it and treats its output
as the source of truth. A local ``shadcn`` binary is preferred; ``npx`` is the
fallback. Everything degrades gracefully when neither exists.
"""
import json
import os
import re
import shutil
import subprocess

ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
DEFAULT_TIMEOUT = 180
_CACHE = {}


def _npx():
    for name in ("npx", "npx.cmd"):
        path = shutil.which(name)
        if path:
            return path
    return None


def _node():
    for name in ("node", "node.exe"):
        path = shutil.which(name)
        if path:
            return path
    return None


def _npm_cache_dir():
    env = os.environ.get("npm_config_cache")
    if env:
        return env
    npm = shutil.which("npm") or shutil.which("npm.cmd")
    if npm:
        try:
            proc = subprocess.run(
                [npm, "config", "get", "cache"],
                capture_output=True, text=True, timeout=15, shell=False,
            )
            value = (proc.stdout or "").strip().splitlines()
            if proc.returncode == 0 and value:
                return value[-1].strip()
        except (OSError, subprocess.SubprocessError):
            pass
    if os.name == "nt" and os.environ.get("LOCALAPPDATA"):
        return os.path.join(os.environ["LOCALAPPDATA"], "npm-cache")
    return os.path.join(os.path.expanduser("~"), ".npm")


def _cached_shadcn_entry():
    """Path to the shadcn entry already unpacked by a previous npx run.

    `npx shadcn@latest` costs ~5 s per call on Windows while the same entry
    point invoked with `node` costs ~0.5 s, so a per-registry search would
    otherwise spend most of its time in npm's resolver. This only uses the
    package after npx itself has installed it; unavailable means fall back to
    npx.
    """
    if "entry" in _CACHE:
        return _CACHE["entry"]
    entry = None
    root = os.path.join(_npm_cache_dir(), "_npx")
    candidates = []
    if os.path.isdir(root):
        for name in os.listdir(root):
            package = os.path.join(root, name, "node_modules", "shadcn")
            package_json = os.path.join(package, "package.json")
            entry_js = os.path.join(package, "dist", "index.js")
            if not (os.path.exists(package_json) and os.path.exists(entry_js)):
                continue
            try:
                with open(package_json, "r", encoding="utf-8") as handle:
                    meta = json.load(handle)
            except (OSError, ValueError):
                continue
            if meta.get("name") != "shadcn":
                continue
            candidates.append((os.path.getmtime(package_json), entry_js))
    if candidates:
        candidates.sort(reverse=True)
        entry = candidates[0][1]
    _CACHE["entry"] = entry
    return entry


def command():
    """Return (argv_prefix, display_name) for the best available CLI."""
    local = shutil.which("shadcn")
    if local:
        return [local], "shadcn"
    node = _node()
    if node:
        entry = _cached_shadcn_entry()
        if entry:
            return [node, entry], "node shadcn (npm cache)"
    npx = _npx()
    if npx:
        return [npx, "--yes", "shadcn@latest"], "npx shadcn@latest"
    return None, None


def available():
    argv, display = command()
    return {"available": bool(argv), "command": display}


def _extract_json(text):
    text = ANSI.sub("", text or "").strip()
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end <= start:
        return None
    try:
        return json.loads(text[start:end + 1])
    except ValueError:
        return None


def run(args, cwd=None, timeout=DEFAULT_TIMEOUT, expect_json=True):
    """Run the shadcn CLI. Returns a result dict, never raises."""
    argv, display = command()
    if not argv:
        return {
            "ok": False,
            "data": None,
            "command": None,
            "error": {
                "code": "shadcn_missing",
                "message": "the shadcn CLI is not installed and npx is unavailable",
                "hint": "install Node.js/npm, or install the CLI in the target project",
            },
        }
    env = dict(os.environ)
    env.update({"NO_COLOR": "1", "FORCE_COLOR": "0", "CI": "1"})
    try:
        proc = subprocess.run(
            argv + list(args),
            cwd=cwd or None,
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout,
            shell=False,
        )
    except subprocess.TimeoutExpired:
        return {
            "ok": False,
            "data": None,
            "command": display,
            "error": {"code": "shadcn_timeout", "message": "shadcn timed out after %ss" % timeout},
        }
    except OSError as exc:
        return {
            "ok": False,
            "data": None,
            "command": display,
            "error": {"code": "shadcn_exec_error", "message": str(exc)},
        }
    stdout = proc.stdout or ""
    stderr = proc.stderr or ""
    if proc.returncode != 0:
        detail = (stderr.strip() or stdout.strip())[-1200:]
        return {
            "ok": False,
            "data": None,
            "command": display,
            "error": {
                "code": "shadcn_failed",
                "message": "shadcn exited with code %d" % proc.returncode,
                "detail": detail,
            },
            "raw": stdout,
        }
    if not expect_json:
        return {"ok": True, "data": None, "command": display, "raw": stdout, "stderr": stderr}
    data = _extract_json(stdout)
    if data is None:
        return {
            "ok": False,
            "data": None,
            "command": display,
            "error": {
                "code": "shadcn_bad_json",
                "message": "shadcn did not print parseable JSON",
                "detail": (stdout.strip() or stderr.strip())[-800:],
            },
            "raw": stdout,
        }
    return {"ok": True, "data": data, "command": display, "stderr": stderr}


def info(project_dir, timeout=DEFAULT_TIMEOUT):
    """`shadcn info --json` for one project."""
    return run(["info", "--json"], cwd=project_dir, timeout=timeout)


def search(query, registries, limit, timeout=DEFAULT_TIMEOUT):
    """`shadcn search <registries...> -q <query> --json -l <limit>`."""
    args = ["search"]
    args.extend(registries)
    args.extend(["-q", query, "--json", "-l", str(limit)])
    return run(args, timeout=timeout)
