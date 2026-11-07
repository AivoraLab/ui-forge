---
name: ui-forge
description: Choose which shadcn component to use when the ecosystem has 500+ registries and most directories mix free and paid. Use when the user is building or editing a web project and needs a component (hero, pricing, dashboard block, form, nav) that is free and fits the project's existing stack and theme; when they ask where to find shadcn components, whether a registry is paid, or which of several components fits their site; or when a candidate must be checked for Radix/Base UI mismatch, Tailwind version, token collisions, dependencies, or a paywall before installing.
---

# ui-forge

Find the component that **fits**. Not the prettiest, not the most famous.

The official shadcn skill (`npx skills add shadcn/ui`) teaches an agent how to
use the CLI, compose components and read `shadcn info --json`. ui-forge depends
on that knowledge: it does not repeat it. ui-forge decides **which** component,
**whether it is free**, and **whether it fits the site being edited**.

## Setup (once per machine)

One command installs ui-forge everywhere the `skills` CLI detects an agent —
Claude Code, Codex, Pi, Cursor, Gemini CLI and friends — plus the shared
`~/.agents/skills` directory that the DSH harness reads:

```bash
npx skills add AivoraLab/ui-forge -g -a '*' -y
```

The official shadcn skill is a **dependency, not a prerequisite**. Check for it
before the first component request and install it yourself when missing — never
make the user run a second command:

```bash
npx skills add shadcn/ui -g -a '*' -y
```

If that fails (offline, no npm), continue with the ui-forge CLI, use `--no-cli`
for the fingerprint, and say plainly that the official knowledge source was
unavailable. Never claim it is installed.

## Three rules, in order

1. **Fit beats fame.** Rank by fit to this project and this brief, never by
   stars, demo polish or registry size.
2. **Free-first is a hard rule.** Default to free components only. Paid and
   freemium registries are excluded at the gate and reported with evidence.
   Show them only when the user explicitly asks for paid options.
3. **The agent narrows, the user decides.** The agent produces up to 3
   candidates with a suggested order; the user picks the look in the Fitting
   Room. Never install the winner before the user has chosen.

## Pipeline (fixed order)

Run every command through the bundled CLI, always with `--json`, and read the
JSON. Never scrape HTML, never reimplement search in the agent.

```bash
UIFORGE="python3 scripts/uiforge.py"   # from the skill directory
```

### 1. Fingerprint the target

```bash
npx shadcn@latest info --json          # official source of truth
$UIFORGE discover --json               # registries, free-first
```

Read the project's theme tokens (`--background`, `--primary`, `--radius`,
fonts, dark/light) and take one screenshot of an existing page. Together they
are the "reference sample" every candidate is measured against.

### 2. Brief

From the user's need plus the fingerprint, write down: component type,
must-have behaviour, and fit profile (`landing`, `saas`, `portfolio`, `admin`).

### 3. Discovery

```bash
$UIFORGE discover --json --limit 20
```

Free-only by default. License truth comes from `data/licenses.json`: **486 of
539 registries carry evidence** (462 free, 16 freemium, 6 paid, 2 unknown) as of
2026-11-06. Paid and freemium registries are removed with the URL that proved
the gate. Registries with no evidence stay but are flagged
`license.flagged = true`; say so when you use them, and never call them free.

### 4. Search

```bash
$UIFORGE search "hero" --json --limit 8
```

`shadcn search` is the primary source; the per-registry index is only a cache.
Keep at most **8** candidates. `registry:example` demo items are filtered out.

### 5. Hard gate — where a famous name dies

```bash
$UIFORGE inspect "@magicui/hero-video-dialog" --project . --json
```

The gate scans `files[].content` (not metadata) for the real primitive base,
checks Tailwind major, token collisions, registry dependencies and license
evidence, and returns a numeric `gate.compat_risk` from 0 to 10 plus the reason
and evidence for every point. Rules:

- `gate.excluded` is true → drop it. Do not retry a 401/402/403: that is a paywall.
- `compat_risk >= 6` → fail; `>= 3` → warn. Keep only 3 survivors at most.
- Pass `--project` so the gate compares against the actual project. Use
  `--no-cli` only when Node/the shadcn CLI is unavailable.
- GitHub registries (`owner/repo/item`) cannot be resolved from the community
  index; pass the item JSON URL instead.
- The gate runs against a **120 s wall-clock deadline** (`--deadline`,
  0 = none) shared by every stage, prints one progress line per stage to
  stderr, and caches fetched item JSON for 24 h in the data directory, so
  repeat inspections are near-instant. A `deadline_exceeded` error or a
  report with `partial: true` names the stage that ran out of time —
  report it, never sit waiting on a silent inspect.

### 6. Fitting Room — the user decides

Take the 3 survivors into a **draft route of the real page**: same theme, same
real content, same viewport. The project's source route is not modified. Show
the three drafts side by side (screenshot at 1440 and 390), add one paragraph of
honest commentary per candidate, and suggest an order. The user picks. Only the
winner (or two finalists) gets opened live to judge motion and hover.

```bash
$UIFORGE render http://localhost:3000/preview/a http://localhost:3000/preview/b \
  --out previews/hero --width 1440 --width 390 --wait-ms 800 --json
```

`render` only captures; building the three draft routes is your job. If
Playwright is missing it exits 1 with `playwright_browser_missing` and the
install hint — report that instead of faking a screenshot.

Never choose the winner on the user's behalf, and never install before the
choice.

### 7. Install & adapt

```bash
npx shadcn@latest add "@magicui/hero-video-dialog"
```

Install only the chosen item. Adapt its tokens, spacing and copy to the
project's existing design. Then read the installed files: flag unexpected
network calls, telemetry, obfuscated code, or a dependency the gate did not
predict.

### 8. Verify & learn

Build/typecheck, screenshot the real page and compare it with the chosen draft,
and report drift plainly. Save the verdict for this project: item content hash,
the user's choice, and the reason. The next run must respect that taste.

```bash
$UIFORGE verdict "@magicui/hero-video-dialog" --sha256 <item.sha256> \
  --project . --chosen yes --note "user picked it for the hero on 2026-11-06"
```

## License data

`data/licenses.json` is probed evidence, not a directory opinion. Every entry
records `checked_at` and the item URLs that returned 200 (public) or
401/402/403 (paywall).

- Read `license.flagged` before you recommend an item. An `unknown` registry is
  not a free registry: state the uncertainty, do not silently upgrade it.
- Treat evidence older than about 90 days as stale — quote the `checked_at`
  date instead of presenting the status as current fact.
- Do **not** re-probe while answering a component request. Batch probing is a
  maintenance job, and it is slow and rate-limited.
- Maintainers refresh from a repository checkout, never from an installed
  skill: `python3 tools/probe_licenses.py --only-missing --include-degraded`,
  then `python3 tests/check_licenses.py`. The tool never overwrites an existing
  entry, and CI never calls the network.

## Scoring

```bash
$UIFORGE evaluate candidates.json --profile landing --inspect report.json --json
```

The agent supplies only the subjective axes (visual, fit, motion, a11y,
consistency, health). The CLI applies the profile weights and subtracts
`0.3 × compat_risk`; pass `--inspect` so the risk is read from the gate instead
of being retyped. Weights are fixed: do not "improve" them without an RFC.

## Hard limits

- Do not install a component to test it. Use the gate, `shadcn view`, and the
  Fitting Room draft route.
- Do not re-host component code. Store metadata, links and evidence only.
- Do not build or call an MCP server: the official shadcn CLI/MCP already owns
  transport.
- Do not hardcode a registry list anywhere except `data/licenses.json`, which
  is community-contributed evidence, not configuration.
- Never invent a license status or an evidence URL. Unknown stays unknown.
- Do not run the batch license probe as part of a component request; it is a
  maintainer task, not a step in the pipeline.
