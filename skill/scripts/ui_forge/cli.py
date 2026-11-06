"""ui-forge command line.

Four deterministic commands, one engine: ``discover``, ``search``, ``inspect``,
``evaluate``. Every command supports ``--json`` with a stable schema, because
the skill is instructed to read JSON and never to parse human text.
"""
import argparse
import json
import os
import sys

from . import __version__, discover as discover_mod, evaluate as evaluate_mod
from . import index as index_mod, inspect as inspect_mod, licenses, net, render as render_mod, search as search_mod


def _default_data_dir():
    override = os.environ.get("UIFORGE_DATA_DIR")
    if override:
        return os.path.abspath(override)
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.abspath(os.path.join(here, "..", "..", "data"))


def _default_project():
    cwd = os.getcwd()
    if os.path.exists(os.path.join(cwd, "components.json")):
        return cwd
    return None


def _emit(payload, as_json, renderer=None):
    if as_json:
        json.dump(payload, sys.stdout, indent=2, ensure_ascii=False)
        sys.stdout.write("\n")
    elif renderer is not None:
        renderer(payload)
    else:
        json.dump(payload, sys.stdout, indent=2, ensure_ascii=False)
        sys.stdout.write("\n")


def _print_error(exc, as_json, schema, code="runtime_error", status=1):
    if as_json:
        json.dump({"schema": schema, "ok": False, "error": exc}, sys.stdout, indent=2, ensure_ascii=False)
        sys.stdout.write("\n")
    else:
        sys.stderr.write("error: %s\n" % (exc.get("message") if isinstance(exc, dict) else exc))
        hint = exc.get("hint") if isinstance(exc, dict) else None
        if hint:
            sys.stderr.write("hint: %s\n" % hint)
    return status


# ----------------------------------------------------------------- rendering
def _render_discover(payload):
    print("# registries: %d total, %d healthy, %d items" % (
        payload["total_registries"], payload["healthy"], payload["total_items"]))
    print("# free-only: %s | excluded by license: %d" % (
        payload["filters"]["free_only"], payload["excluded_by_license_count"]))
    for row in payload["registries"]:
        flag = "?" if row["license"]["flagged"] else " "
        print("%-22s health %-4s items %-6s %s%s" % (
            row["name"], row["health"], row["items"], flag, row["license"]["status"]))
    for warning in payload["warnings"]:
        print("# warning: %s" % warning)


def _render_search(payload):
    print("# query: %r | %d candidates | license: %s | source: %s" % (
        payload["query"], payload["count"],
        "free-first" if payload["free_only"] else "all", payload["source"]))
    for position, row in enumerate(payload["results"], 1):
        mark = " (license unknown)" if row["license"]["flagged"] else ""
        print("%d. %s/%s  [%s, health %s]%s" % (
            position, row["registry"], row["name"],
            row["type"].split(":")[-1], row["health"]["score"], mark))
        print("   %s" % row["add_command"])
        if row["description"]:
            print("   %s" % row["description"].strip().split("\n")[0][:160])
    for row in payload["excluded"][:3]:
        print("# excluded: %s/%s -> %s" % (row["registry"], row["name"], row["reason"]))
    for warning in payload["warnings"]:
        print("# warning: %s" % warning)


def _render_inspect(payload):
    item = payload.get("item")
    if item:
        print("# %s (%s)" % (item.get("title") or item.get("name"), item.get("type")))
        print("# %s" % payload.get("url"))
    gate = payload["gate"]
    print("# verdict: %s | compat_risk %.1f / 10" % (gate["verdict"], gate["compat_risk"]))
    if gate["excluded"]:
        print("# EXCLUDED: %s" % gate["exclude_reason"])
    for reason in gate["reasons"]:
        print("- [%s] %s (weight %.1f)" % (reason["severity"], reason["detail"], reason["weight"]))
    for unknown in gate["unknowns"]:
        print("? %s" % unknown)


def _render_evaluate(payload):
    print("# profile: %s" % payload["profile"])
    for row in payload["ranking"]:
        print("%d. %s  fit-score %s" % (row["rank"], row["name"], row["score"]))
    for row in payload["disqualified"]:
        print("# disqualified: %s -> %s" % (row["name"], row.get("exclude_reason")))
    for warning in payload["warnings"]:
        print("# warning: %s" % warning)


def _render_render(payload):
    print("# Fitting Room capture -> %s" % payload["out_dir"])
    for row in payload["candidates"]:
        if row["ok"]:
            print("- %s" % row["label"])
            for shot in row["screenshots"]:
                print("    %dpx  %s" % (shot["width"], shot["path"]))
        else:
            error = row.get("error") or {}
            print("- %s  FAILED  %s: %s" % (row["label"], error.get("code"), error.get("message")))
            if error.get("hint"):
                print("    hint: %s" % error["hint"])


def _render_verdict(payload):
    print("# verdicts for %s" % payload["project"])
    for choice in payload["choices"]:
        print("- %s  %s  %s" % (choice["item"], "chosen" if choice["chosen"] else "rejected",
                                choice.get("chosen_at", "")))


# ------------------------------------------------------------------- parser
def build_parser():
    parser = argparse.ArgumentParser(
        prog="uiforge",
        description="Find shadcn components that are free and fit the project you are editing.",
    )
    parser.add_argument("--version", action="version", version="ui-forge %s" % __version__)
    parser.add_argument("--data-dir", default=None, help="where licenses.json and caches live")
    parser.add_argument("--json", action="store_true", help="machine-readable output (stable schema)")
    subparsers = parser.add_subparsers(dest="command", required=True)

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--json", action="store_true", default=argparse.SUPPRESS)
    common.add_argument("--data-dir", default=argparse.SUPPRESS)

    discover_parser = subparsers.add_parser("discover", parents=[common],
                                            help="list registries, free-first")
    discover_parser.add_argument("--limit", type=int, default=20)
    discover_parser.add_argument("--min-health", type=float, default=0.0)
    discover_parser.add_argument("--status", default="healthy",
                                 choices=["healthy", "degraded", "unhealthy", "any"])
    discover_parser.add_argument("--free-only", dest="free_only", action="store_true", default=True)
    discover_parser.add_argument("--all", dest="free_only", action="store_false")
    discover_parser.add_argument("--refresh", action="store_true")
    discover_parser.add_argument("--timeout", type=int, default=30)

    search_parser = subparsers.add_parser("search", parents=[common],
                                          help="search components, free-first")
    search_parser.add_argument("query")
    search_parser.add_argument("--registry", action="append", default=[],
                               help="registry namespace (repeatable); default = healthiest free pool")
    search_parser.add_argument("--limit", type=int, default=8)
    search_parser.add_argument("--pool", type=int, default=search_mod.DEFAULT_POOL)
    search_parser.add_argument("--type", action="append", default=[],
                               help="ui, block, component, hook (repeatable)")
    search_parser.add_argument("--free-only", dest="free_only", action="store_true", default=True)
    search_parser.add_argument("--all", dest="free_only", action="store_false")
    search_parser.add_argument("--no-index-fallback", dest="index_fallback",
                               action="store_false", default=True)
    search_parser.add_argument("--index-only", action="store_true",
                               help="skip `shadcn search` and scan registry indices (offline/testing)")
    search_parser.add_argument("--refresh", action="store_true")
    search_parser.add_argument("--timeout", type=int, default=60)

    inspect_parser = subparsers.add_parser("inspect", parents=[common],
                                           help="compatibility gate for one item")
    inspect_parser.add_argument("target", help="@namespace/item or a full item JSON URL")
    inspect_parser.add_argument("--project", default=None)
    inspect_parser.add_argument("--no-recurse", dest="recurse", action="store_false", default=True)
    inspect_parser.add_argument("--no-cli", dest="use_cli", action="store_false", default=True,
                                help="fingerprint the project without calling `shadcn info`")
    inspect_parser.add_argument("--max-regdeps", type=int, default=4)
    inspect_parser.add_argument("--refresh-index", action="store_true")
    inspect_parser.add_argument("--timeout", type=int, default=30)

    evaluate_parser = subparsers.add_parser("evaluate", parents=[common],
                                            help="fit ranking from agent-scored candidates")
    evaluate_parser.add_argument("file")
    evaluate_parser.add_argument("--profile", default="saas", choices=sorted(evaluate_mod.PROFILES))
    evaluate_parser.add_argument("--inspect", action="append", default=[],
                                 help="inspect report JSON; compat_risk is read from it (repeatable)")

    render_parser = subparsers.add_parser("render", parents=[common],
                                          help="Fitting Room screenshots (needs Playwright)")
    render_parser.add_argument("urls", nargs="+", help="preview route URLs, one per candidate (max 3)")
    render_parser.add_argument("--out", required=True, help="screenshot directory")
    render_parser.add_argument("--width", action="append", type=int, default=[],
                               help="viewport width (repeatable; default 1440 and 390)")
    render_parser.add_argument("--height", type=int, default=render_mod.DEFAULT_HEIGHT)
    render_parser.add_argument("--wait-ms", type=int, default=0,
                               help="wait before capture, for entry animations")
    render_parser.add_argument("--label", action="append", default=[],
                               help="candidate label for the file name (repeatable)")
    render_parser.add_argument("--timeout", type=int, default=120)

    verdict_parser = subparsers.add_parser("verdict", parents=[common],
                                           help="remember the user's choice for this project")
    verdict_parser.add_argument("item")
    verdict_parser.add_argument("--project", default=None)
    verdict_parser.add_argument("--sha256", required=True,
                                help="item.sha256 from the inspect report")
    verdict_parser.add_argument("--chosen", choices=["yes", "no"], default="yes")
    verdict_parser.add_argument("--note", default=None)

    return parser


def main(argv=None):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    parser = build_parser()
    args = parser.parse_args(argv)
    data_dir = args.data_dir or _default_data_dir()
    as_json = bool(getattr(args, "json", False))

    if args.command == "discover":
        try:
            payload = discover_mod.discover(
                data_dir, limit=args.limit, min_health=args.min_health,
                free_only=args.free_only, refresh=args.refresh, timeout=args.timeout,
                status=args.status,
            )
        except net.FetchError as exc:
            return _print_error(exc.as_dict(), as_json, discover_mod.SCHEMA)
        _emit(payload, as_json, _render_discover)
        return 0

    if args.command == "search":
        try:
            payload = search_mod.search(
                args.query, data_dir, registries=args.registry, limit=args.limit,
                types=args.type, free_only=args.free_only, pool=args.pool,
                refresh=args.refresh, timeout=args.timeout,
                index_fallback=args.index_fallback, force_index=args.index_only,
            )
        except net.FetchError as exc:
            return _print_error(exc.as_dict(), as_json, search_mod.SCHEMA)
        _emit(payload, as_json, _render_search)
        return 0

    if args.command == "inspect":
        project = args.project or _default_project()
        try:
            payload = inspect_mod.inspect(
                args.target, data_dir, project_dir=project, use_cli=args.use_cli,
                recurse=args.recurse, max_regdeps=args.max_regdeps,
                timeout=args.timeout, refresh_index=args.refresh_index,
            )
        except inspect_mod.UsageError as exc:
            return _print_error(exc.as_dict(), as_json, "ui-forge/inspect/v1", status=2)
        except net.FetchError as exc:
            return _print_error(exc.as_dict(), as_json, "ui-forge/inspect/v1")
        except index_mod.FetchError as exc:
            return _print_error(exc.as_dict(), as_json, "ui-forge/inspect/v1")
        _emit(payload, as_json, _render_inspect)
        return 0

    if args.command == "evaluate":
        try:
            with open(args.file, "r", encoding="utf-8") as handle:
                candidates = json.load(handle)
        except OSError as exc:
            return _print_error({"code": "file_unreadable", "message": str(exc)},
                                as_json, evaluate_mod.SCHEMA, status=2)
        except ValueError as exc:
            return _print_error({"code": "file_bad_json", "message": str(exc)},
                                as_json, evaluate_mod.SCHEMA, status=2)
        reports = []
        try:
            for path in args.inspect:
                with open(path, "r", encoding="utf-8") as handle:
                    reports.append(json.load(handle))
            payload = evaluate_mod.evaluate(candidates, profile=args.profile, reports=reports)
        except evaluate_mod.CandidateError as exc:
            return _print_error(exc.as_dict(), as_json, evaluate_mod.SCHEMA, status=2)
        except (OSError, ValueError) as exc:
            return _print_error({"code": "inspect_unreadable", "message": str(exc)},
                                as_json, evaluate_mod.SCHEMA, status=2)
        _emit(payload, as_json, _render_evaluate)
        return 0

    if args.command == "render":
        widths = tuple(args.width) if args.width else render_mod.DEFAULT_WIDTHS
        try:
            payload = render_mod.render(
                args.urls, args.out, widths=widths, height=args.height,
                wait_ms=args.wait_ms, timeout=args.timeout, labels=args.label,
            )
        except ValueError as exc:
            return _print_error({"code": "too_many_candidates", "message": str(exc)},
                                as_json, render_mod.SCHEMA, status=2)
        _emit(payload, as_json, _render_render)
        return 0 if payload["ok"] else 1

    if args.command == "verdict":
        project = args.project or _default_project()
        payload = render_mod.save_verdict(
            data_dir, project, args.item, args.sha256,
            chosen=args.chosen == "yes", note=args.note,
        )
        _emit(payload, as_json, _render_verdict)
        return 0

    parser.error("unknown command")
    return 2
