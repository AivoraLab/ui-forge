"""Screenshot capture for the Fitting Room, plus the per-project verdict store.

The draft routes themselves are built by the agent inside the target project
(see ``references/visual-analysis.md``); this module owns the deterministic
parts: capture at the two fixed viewports, and remembering what the user chose.

Playwright is optional. It is invoked through the Node CLI so the skill keeps
its "Python standard library only" rule.
"""
import datetime
import hashlib
import json
import os
import shutil
import subprocess

SCHEMA = "ui-forge/render/v1"
VERDICTS_SCHEMA = "ui-forge/verdicts/v1"
DEFAULT_WIDTHS = (1440, 390)
DEFAULT_HEIGHT = 900
PLAYWRIGHT_PACKAGE = os.environ.get("UI_FORGE_PLAYWRIGHT", "playwright")


def _now():
    return datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat()


def _slug(text):
    clean = "".join(ch if ch.isalnum() or ch in "-_." else "-" for ch in text)
    return clean.strip("-.") or "item"


def _npx():
    return shutil.which("npx") or shutil.which("npx.cmd")


def capture(url, out_dir, widths=DEFAULT_WIDTHS, height=DEFAULT_HEIGHT,
            wait_ms=0, timeout=120, label=None):
    """Screenshot one preview URL at each width. Returns a result record."""
    npx = _npx()
    result = {
        "url": url,
        "label": label or url,
        "screenshots": [],
        "ok": False,
        "error": None,
    }
    if not npx:
        result["error"] = {
            "code": "node_missing",
            "message": "npx was not found on PATH",
            "hint": "install Node.js 20+ and run: npx playwright install chromium",
        }
        return result

    os.makedirs(out_dir, exist_ok=True)
    command_base = [npx, "--yes", PLAYWRIGHT_PACKAGE, "screenshot", "--full-page"]
    if wait_ms:
        command_base.append("--wait-for-timeout=%d" % int(wait_ms))

    for width in widths:
        path = os.path.join(out_dir, "%s-%d.png" % (_slug(result["label"]), int(width)))
        command = command_base + [
            "--viewport-size=%d,%d" % (int(width), int(height)),
            url,
            path,
        ]
        try:
            proc = subprocess.run(
                command, capture_output=True, text=True, timeout=timeout,
                encoding="utf-8", errors="replace",
            )
        except subprocess.TimeoutExpired:
            result["error"] = {
                "code": "render_timeout",
                "message": "playwright screenshot timed out after %ss" % timeout,
                "hint": "check the preview server, then retry",
            }
            return result
        stderr = (proc.stderr or "").strip()
        if proc.returncode != 0 or not os.path.exists(path):
            lowered = stderr.lower()
            if "executable doesn't exist" in lowered or "browsertype.launch" in lowered:
                result["error"] = {
                    "code": "playwright_browser_missing",
                    "message": "Playwright is installed but its Chromium build is not",
                    "hint": "run: npx playwright install chromium",
                }
            else:
                result["error"] = {
                    "code": "render_failed",
                    "message": stderr.splitlines()[-1] if stderr else "playwright exited %d" % proc.returncode,
                    "hint": "run the command below once to diagnose:\n  " + " ".join(command),
                }
            return result
        result["screenshots"].append({"width": int(width), "path": os.path.abspath(path)})

    result["ok"] = True
    return result


def render(urls, out_dir, widths=DEFAULT_WIDTHS, height=DEFAULT_HEIGHT,
           wait_ms=0, timeout=120, labels=None):
    if len(urls) > 3:
        raise ValueError("the Fitting Room takes at most 3 candidates")
    labels = labels or [None] * len(urls)
    results = [
        capture(url, out_dir, widths=widths, height=height, wait_ms=wait_ms,
                timeout=timeout, label=labels[index] if index < len(labels) else None)
        for index, url in enumerate(urls)
    ]
    return {
        "schema": SCHEMA,
        "generated_at": _now(),
        "out_dir": os.path.abspath(out_dir),
        "widths": [int(w) for w in widths],
        "height": int(height),
        "count": len(results),
        "ok": all(row["ok"] for row in results),
        "candidates": results,
    }


# --- verdict store -------------------------------------------------------

def _verdicts_path(data_dir, project):
    root = os.path.abspath(project or ".")
    digest = hashlib.sha256(root.encode("utf-8")).hexdigest()[:12]
    return os.path.join(data_dir, "verdicts", "%s-%s.json" % (_slug(os.path.basename(root)), digest))


def load_verdicts(data_dir, project):
    path = _verdicts_path(data_dir, project)
    try:
        with open(path, "r", encoding="utf-8") as handle:
            document = json.load(handle)
    except (OSError, ValueError):
        return {"schema": VERDICTS_SCHEMA, "project": os.path.abspath(project or "."), "choices": []}
    document.setdefault("schema", VERDICTS_SCHEMA)
    document.setdefault("project", os.path.abspath(project or "."))
    document.setdefault("choices", [])
    return document


def save_verdict(data_dir, project, item, sha256, chosen, note=None):
    document = load_verdicts(data_dir, project)
    choices = [choice for choice in document["choices"] if choice.get("item") != item]
    choices.append({
        "item": item,
        "sha256": sha256,
        "chosen": bool(chosen),
        "note": note,
        "chosen_at": _now(),
    })
    document["choices"] = choices
    document["updated_at"] = _now()
    path = _verdicts_path(data_dir, project)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as handle:
        json.dump(document, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    os.replace(tmp, path)
    return document
