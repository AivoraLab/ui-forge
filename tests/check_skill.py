#!/usr/bin/env python3
"""Check the skill surface that agents actually load.

Three failure modes this catches before release:
  - SKILL.md without YAML frontmatter does not register in Claude Code / Codex.
  - a stdlib module name inside skill/scripts shadows the real one (the 3.14 crash).
  - the advertised command surface drifts away from the CLI.
"""
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(ROOT, "skill", "scripts", "uiforge.py")
SKILL = os.path.join(ROOT, "skill", "SKILL.md")
COMMANDS = ("discover", "search", "inspect", "evaluate", "render", "verdict")
STDLIB_GUARD = ("inspect", "ast", "json", "types", "typing", "logging", "platform")


def fail(message):
    print("skill: %s" % message, file=sys.stderr)
    return 1


def check_frontmatter():
    with open(SKILL, "r", encoding="utf-8") as handle:
        text = handle.read()
    if not text.startswith("---\n"):
        return fail("SKILL.md must start with YAML frontmatter (---)")
    end = text.find("\n---", 4)
    if end == -1:
        return fail("SKILL.md frontmatter is not closed")
    block = text[4:end]
    for key in ("name:", "description:"):
        match = re.search(r"^%s\s*(\S.*)$" % re.escape(key), block, re.MULTILINE)
        if not match or not match.group(1).strip():
            return fail("SKILL.md frontmatter needs a non-empty %s" % key.rstrip(":"))
    if len(re.search(r"^description:\s*(.*)$", block, re.MULTILINE).group(1)) < 40:
        return fail("SKILL.md description is too short to route the skill")
    return 0


def check_commands():
    for command in COMMANDS:
        proc = subprocess.run(
            [sys.executable, SCRIPT, command, "--help"],
            capture_output=True, text=True, encoding="utf-8", timeout=120,
        )
        if proc.returncode != 0:
            return fail("%s --help exited %d\n%s" % (command, proc.returncode, proc.stderr.strip()))
    proc = subprocess.run(
        [sys.executable, SCRIPT, "--version"],
        capture_output=True, text=True, encoding="utf-8", timeout=120,
    )
    if proc.returncode != 0 or "ui-forge 2.1.0" not in proc.stdout:
        return fail("--version must print 'ui-forge 2.1.0' (got %r)" % proc.stdout.strip())
    return 0


def check_no_shadowing():
    scripts = os.path.join(ROOT, "skill", "scripts")
    for name in STDLIB_GUARD:
        path = os.path.join(scripts, name + ".py")
        if os.path.exists(path):
            return fail("%s shadows the stdlib module of the same name" % path)
    return 0


def check_no_mcp():
    pattern = re.compile(r"^\s*(?:import|from)\s+mcp\b|FastMCP", re.MULTILINE)
    for dirpath, dirnames, filenames in os.walk(os.path.join(ROOT, "skill", "scripts")):
        dirnames[:] = [name for name in dirnames if name != "__pycache__"]
        for filename in filenames:
            if not filename.endswith(".py"):
                continue
            path = os.path.join(dirpath, filename)
            with open(path, "r", encoding="utf-8", errors="replace") as handle:
                if pattern.search(handle.read()):
                    return fail("%s implements an MCP server; ui-forge ships a CLI only" % path)
    return 0


def main():
    problems = 0
    for check in (check_frontmatter, check_no_shadowing, check_no_mcp, check_commands):
        problems += check()
    if problems:
        return 1
    print("skill: frontmatter, command surface and CLI-only packaging valid")
    return 0


if __name__ == "__main__":
    sys.exit(main())
