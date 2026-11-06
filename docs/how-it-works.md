# How ui-forge works

A walkthrough of one request, stage by stage. For the same flow executed on
live data, read [examples/hero-ai-saas.md](../examples/hero-ai-saas.md).

Request used throughout: *"Build a hero section for an AI SaaS website, modern
style, beautiful animation."*

## 1. Fingerprint

The target project, not the registry, defines "fits".

```bash
npx shadcn@latest info --json
python3 skill/scripts/uiforge.py discover --json
```

`shadcn info --json` is the official fingerprint: framework, Tailwind major,
primitive base (Radix / Base UI / React Aria), aliases, installed components.
`project.py` falls back to `components.json`, installed packages and the CSS
file when the CLI is unavailable. Read the theme tokens and screenshot one
existing page — that is the reference sample.

## 2. Brief

Write down what "good" means here: component type, must-have behaviour, fit
profile (`landing`, `saas`, `portfolio`, `admin`). This brief is the contract
every later score refers back to.

## 3. Discovery — free-first

`discover` fetches the official index (`ui.shadcn.com/r/registries.json`, cache
24 h) and joins it with `data/licenses.json`. There is no hardcoded registry
list anywhere else.

Paid and freemium registries are removed **before** ranking, with the HTTP
evidence that proved it. Unknown registries stay but are flagged; say so when
you use them.

## 4. Search

```bash
python3 skill/scripts/uiforge.py search "hero" --json --limit 8
```

`shadcn search` is the primary source; per-registry item indexes are a cache
(`--index-only` forces them, which is what the offline tests use). Demo items
(`registry:example`) are filtered. Output is capped at 8 candidates.

## 5. Compatibility Gate

```bash
python3 skill/scripts/uiforge.py inspect "@magicui/hero-video-dialog" --project . --json
```

The gate reads the real item JSON and scans `files[].content` — the primitive
base does not live in metadata. It emits a numeric `gate.compat_risk` (0–10)
with one reason and evidence URL per point:

- base mismatch (Radix item, Base UI project) 4.0,
- Tailwind major mismatch 3.0,
- token collisions 1.5 each,
- missing dependencies, registry dependency trees, unknown license.

A paywall (HTTP 401/402/403) is a license signal: excluded, risk 10, never retried.
3 survivors at most move on.

## 6. Fitting Room

The three survivors are composed into draft routes of the **real** page — same
theme tokens, same content, same viewport; the source route is untouched.
Screenshots at 1440 and 390 are captured by:

```bash
python3 skill/scripts/uiforge.py render <url-a> <url-b> <url-c> \
  --out previews/hero --width 1440 --width 390 --json
```

`render` only captures (Playwright CLI). The agent shows the three drafts,
adds one honest paragraph each, suggests an order — and the user picks. Only
the winner, or two finalists, is opened live to judge motion and hover.

## 7. Fit Ranking

```bash
python3 skill/scripts/uiforge.py evaluate candidates.json --profile landing \
  --inspect inspect-a.json --inspect inspect-b.json --json
```

The agent supplies only the five subjective axes; the CLI applies fixed profile
weights, folds registry health in at 10%, and subtracts `0.3 × compat_risk`
read from the gate. The arithmetic is reproducible: the published example
still gives landing 8.14 / 7.97 / 7.16 and admin 8.06 / 7.92 / 7.09.

## 8. Install & Verify

The winner installs through the shadcn CLI into the real project. The agent
adapts tokens and copy, runs the build, reads the installed files once for
network calls or telemetry, and screenshots the real page next to the chosen
draft. Drift is reported, not smoothed over. The user's choice is stored:

```bash
python3 skill/scripts/uiforge.py verdict "@magicui/hero-video-dialog" \
  --sha256 <item.sha256> --project . --chosen yes --note "why"
```

The next run respects that choice instead of re-proposing a rejected look.
