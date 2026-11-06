<div align="center">

# ui-forge

**Pick the shadcn component that fits — not the one with the most stars.**

[English](README.md) · [Tiếng Việt](README.vi.md)

[![checks](https://github.com/AivoraLab/ui-forge/actions/workflows/checks.yml/badge.svg)](https://github.com/AivoraLab/ui-forge/actions/workflows/checks.yml)
[![smoke](https://github.com/AivoraLab/ui-forge/actions/workflows/smoke.yml/badge.svg)](https://github.com/AivoraLab/ui-forge/actions/workflows/smoke.yml)
[![license: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![python 3.12+](https://img.shields.io/badge/python-3.12%2B-3776AB.svg)](https://www.python.org/)
[![status: v2.1.0](https://img.shields.io/badge/status-v2.1.0-success.svg)](docs/roadmap.md)

An agent skill that answers one question before an agent installs anything:

> *Is this component free, and does it actually fit the site I am building?*

</div>

---

The shadcn ecosystem has **539 public registries** and **154k+ components**. Most
directories mix free and paid items to sell a Pro tier, and item metadata carries
no license field. The official shadcn skill teaches an agent *how to use*
components; ui-forge decides **which** one to use, **whether it is free**, and
**whether it matches the project**.

> **Positioning:** the official shadcn skill teaches the agent to use component;
> ui-forge decides which component to pick, whether it is free, and whether it
> fits the site you are coding.

ui-forge depends on the official shadcn skill for CLI knowledge. It does not
reteach it, and it ships no MCP server — the official CLI/MCP owns transport.

## Contents

- [Why ui-forge](#why-ui-forge)
- [Quick start](#quick-start)
- [How it works](#how-it-works)
- [Commands](#commands)
- [License dataset](#license-dataset)
- [Compatibility gate](#compatibility-gate)
- [Fitting Room](#fitting-room)
- [JSON contracts](#json-contracts)
- [Repository layout](#repository-layout)
- [Development and CI](#development-and-ci)
- [Trust and safety](#trust-and-safety)
- [Contributing](#contributing)
- [License](#license)

## Why ui-forge

| Problem | What ui-forge does |
| --- | --- |
| Directories list free and paid components side by side | `discover` and `search` drop paid/freemium registries **before** ranking, with HTTP evidence |
| "Pretty" is subjective and full of demos | The agent scores the brief and the project's theme; the user picks in a Fitting Room |
| Radix vs Base UI, Tailwind v3 vs v4 break installs | A numeric gate reads the real primitive base from `files[].content` and returns `compat_risk` 0–10 |
| Registries silent-fail, 401, or ignore a query | Errors are surfaced with evidence; paywalls (401/402/403) are excluded, never retried |

**Fit beats fame.** A famous registry that is paid, Base-UI-only, or visually
wrong loses to a quieter one that matches the page.

## Quick start

```bash
# 1. the official shadcn skill: CLI knowledge and project conventions
npx skills add shadcn/ui

# 2. ui-forge: the decision layer
npx skills add AivoraLab/ui-forge
```

Then, in the repository you are working on, ask your agent:

> Find 3 free hero sections that fit this landing page, check compatibility, then
> build a Fitting Room so I can choose.

## How it works

```
fingerprint → brief → discover → search → compatibility gate
      → Fitting Room (≤ 3 drafts) → install winner → verify & learn
```

1. **Fingerprint** — `shadcn info --json` plus theme tokens: framework, Tailwind
   version, primitive base (`radix` / `base` / `aria`), aliases, installed
   components.
2. **Brief** — the agent turns the page and constraints into a short fit brief.
3. **Discover** — 24-hour cached registry index, free-first by default.
4. **Search** — official `shadcn search` is the source of truth, capped at 8
   registries; the index scan is only a fallback/cache.
5. **Compatibility gate** — item JSON plus `files[].content`: primitive base,
   Tailwind, CSS-variable collisions, `registryDependencies`, license. Produces
   `compat_risk` 0–10 and a `pass` / `warn` / `fail` verdict.
6. **Fitting Room** — at most 3 survivors are composed into drafts of the real
   page with the same theme, content and viewport (1440 and 390). The user picks.
7. **Install & adapt** — only the winner is installed; its files are re-read for
   network, telemetry or obfuscated code.
8. **Verify & learn** — build/typecheck, screenshot against the draft, and save
   the verdict keyed by item hash.

## Commands

One stdlib-only CLI. Every command has `--json` with a stable schema.

| Command | Purpose | Example |
| --- | --- | --- |
| `discover` | List registries, free-first | `uiforge.py discover --free-only --json` |
| `search` | Find components across registries | `uiforge.py search "hero" --json` |
| `inspect` | Compatibility gate for one item | `uiforge.py inspect "@magicui/hero-video-dialog" --project . --json` |
| `evaluate` | Fit ranking from agent-scored candidates | `uiforge.py evaluate candidates.json --profile landing --inspect report.json --json` |
| `render` | Fitting Room screenshots (optional Playwright) | `uiforge.py render https://localhost:3000/draft/1 --out .ui-forge/previews` |
| `verdict` | Remember the user's choice for this project | `uiforge.py verdict "@magicui/hero-video-dialog" --project . --sha256 <hash> --chosen yes` |

Run the launcher directly from a repository checkout:

```bash
python3 skill/scripts/uiforge.py search "pricing" --json --limit 8
```

Requires **Python 3.12+** (tested on 3.12 and 3.14). Node is optional:
`inspect` uses `shadcn info --json` when available; pass `--no-cli` for a
metadata-only fingerprint.

## License dataset

`skill/data/licenses.json` is the project's moat: probed evidence, not a
directory claim. Neither the registry index nor item JSON exposes a license, so
the only honest source is what the registry actually serves.

Coverage on **2026-11-06: 486 of 539 registries**.

| Status | Count | Meaning |
| --- | ---: | --- |
| `free` | 462 | every sampled item answered `200` |
| `freemium` | 16 | some items `200`, some paywalled (`401`/`402`/`403`) |
| `paid` | 6 | every sampled item paywalled |
| `unknown` | 2 | probed, but no usable evidence |

- Registries outside the dataset are `unknown`: **kept but flagged**, never
  described as free.
- `402 Payment Required` is treated as a paywall, not a transient error.
- Evidence older than ~90 days should be presented as stale, with its date.
- Refresh (contributor, from a checkout — never in CI, never during a component
  request):

```bash
python3 tools/probe_licenses.py --only-missing --include-degraded
python3 tests/check_licenses.py
```

Adding one registry is a one-entry PR; see [CONTRIBUTING.md](CONTRIBUTING.md).

## Compatibility gate

`inspect` resolves the item, reads every `files[].content`, recurses one level
into `registryDependencies`, and scores:

| Signal | Weight |
| --- | ---: |
| Primitive base mismatch (Radix vs Base UI vs React Aria) | 4.0 |
| Conflicting primitive imports inside one item | 3.0 |
| Tailwind major mismatch | 3.0 |
| CSS variable collision | 1.5 each, capped at 3.0 |
| Missing npm dependency | 0.5 each, capped at 2.0 |
| Registry dependency tree (3–5 / more than 5) | 1.0 / 2.0 |
| License unknown | 0.5 |
| Paywalled item (`401`/`402`/`403`) | 10.0, excluded |

Verdict: `pass` under 3.0, `warn` at 3.0+, `fail` at 6.0+ or excluded. `evaluate
--inspect` reads this number instead of asking the agent to retype it, so the
ranking cannot silently drift.

## Fitting Room

Screenshots are evidence, not decoration. ui-forge renders **at most 3**
candidates, at **1440 and 390**, and refuses more. `render` only captures URLs —
the agent builds the draft routes in a throwaway copy; it never composes
components into the user's project just to test them.

Playwright is optional and checked lazily:

```bash
npx playwright install chromium   # only needed for `render`
```

Missing browsers produce `playwright_browser_missing` with that hint — the skill
must report it, not fake a screenshot.

## JSON contracts

Every payload carries a schema id and is safe to pipe into `jq`:

| Schema | Command |
| --- | --- |
| `ui-forge/discover/v1` | `discover` |
| `ui-forge/search/v1` | `search` |
| `ui-forge/inspect/v1` | `inspect` |
| `ui-forge/evaluate/v1` | `evaluate` |
| `ui-forge/render/v1` | `render` |
| `ui-forge/verdicts/v1` | `verdict` store |

Exit codes: `0` success, `2` usage or validation error, `1` runtime failure.
Human-readable output is the default; `--json` is the machine contract.

## Repository layout

```
skill/
  SKILL.md                 the procedure an agent follows
  skill.yaml               skill metadata
  references/              registry, evaluation, visual and gate references
  scripts/uiforge.py       CLI launcher
  scripts/ui_forge/        net · index · licenses · shadcn · project
                           inspect · search · discover · evaluate
                           render · cli
  data/licenses.json       probed license evidence (committed)
tools/probe_licenses.py    maintainer batch probe (network; never in CI)
tests/                     offline smoke tests + dataset/skill validators
examples/                  frozen example sheets and candidate inputs
docs/                      concept, how-it-works, architecture, roadmap
```

Runtime caches (`registries-cache.json`, `fingerprint-cache.json`, `verdicts/`,
`previews/`) are gitignored; only `licenses.json` is committed.

## Development and CI

```bash
python3 tests/smoke.py          # offline, no network, 11 tests
python3 tests/check_licenses.py # dataset schema and evidence rules
python3 tests/check_skill.py    # frontmatter, command surface, no MCP
```

| Workflow | Runs |
| --- | --- |
| `checks` | lint/compile, license dataset, skill surface on Python 3.12/3.14 |
| `smoke` | the offline suite on Python 3.12 and 3.14 |

Both run on every push and pull request. Weights and the published example
numbers (`8.14 / 7.97 / 7.16` landing, `8.06 / 7.92 / 7.09` admin) are frozen;
changing them requires an RFC.

## Trust and safety

Components are third-party code. ui-forge never re-hosts them, and `inspect`
flags `fetch` / axios / WebSocket calls, analytics, and dynamic code evaluation
in `files[].content` before installation. Preview URLs in a Fitting Room are
local drafts — do not treat a registry demo as evidence of fit.

## Contributing

Issues and PRs are welcome. The highest-value contribution is **one license
entry with real HTTP evidence**; batch probes are a maintainer task, run from a
checkout. Please keep the CLI stdlib-only, preserve the JSON schemas, and run
the three checks above before opening a PR. See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

[MIT](LICENSE) © AivoraLab
