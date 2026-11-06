# ui-forge

> Skill chính thức của shadcn dạy agent dùng component; ui-forge quyết định chọn component nào, nó có free không, và có hợp với web đang code không.

An agent skill for picking **which** shadcn component to use when the ecosystem
has 500+ registries and most directories mix free and paid.

- **Free-first by default.** Registries with paid or freemium gates are removed
  before ranking, with HTTP evidence in `skill/data/licenses.json`.
- **Compatibility is measured, not guessed.** A numeric gate (0–10) reads the
  real primitive base from `files[].content`, checks Tailwind, tokens,
  dependencies and paywalls.
- **Fit beats fame.** Ranking follows the brief and the project's own theme;
  visual scoring reproduces the published example exactly.

ui-forge depends on the official shadcn skill for CLI knowledge. It does not
reteach it, and it does not build an MCP — the official CLI/MCP owns transport.

## Install

```bash
npx skills add shadcn/ui
npx skills add KaiyoDev/ui-forge
```

Then ask, in the repository you are working on:

> Tìm cho tôi 3 hero section free hợp với landing page hiện tại, kiểm tra compatibility rồi dựng Fitting Room để tôi chọn.

## How it works

`skill/SKILL.md` is the procedure an agent follows (fingerprint → brief →
discover → search → gate → Fitting Room → install → verify). All deterministic
work is a stdlib-only Python CLI with JSON output:

```bash
python3 skill/scripts/uiforge.py discover --json --free-only
python3 skill/scripts/uiforge.py search "hero" --json
python3 skill/scripts/uiforge.py inspect "@magicui/hero-video-dialog" --project . --json
python3 skill/scripts/uiforge.py evaluate candidates.json --profile landing --inspect report.json --json
```

Requires Python 3.12+ (tested on 3.12 and 3.14). `inspect` uses the official
`shadcn info --json` when Node is available; pass `--no-cli` for a
metadata-only fingerprint.

## Data

`skill/data/licenses.json` is probed evidence, not a directory claim. Coverage
on 2026-11-06: **486 of 539 registries** (462 `free`, 16 `freemium`, 6 `paid`,
2 `unknown`), each with item URLs and real HTTP statuses. Registries not in the
dataset are treated as `unknown` and flagged. Refresh with
`python3 tools/probe_licenses.py`; see `CONTRIBUTING.md` to add a single line.

## Status

v2.1.0, pre-release. The CLI, license dataset, gate and Fitting Room capture
are tested by `tests/smoke.py` (offline fixtures, CI on Python 3.12/3.14).
Playwright is optional: `render` needs `npx playwright install chromium` and
reports a clear error when it is missing.

## License

MIT.
