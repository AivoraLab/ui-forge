# Worked example: "Hero section for an AI SaaS website"

A real run of the ui-forge pipeline on live data, 2026-11-06.
Stages 1–4 and 6 below are executed, with real output. Stage 5 (visual
scoring) is shown as the scoring sheet with **illustrative** scores —
the automatic preview harness lands in v0.2 (see roadmap). Nothing in
this file is mocked; where a registry refused us, that is shown too.

## 1. Fit Brief

- Profile: `landing` (AI SaaS marketing page)
- Target: modern, strong headline focus, product visual, purposeful motion
- Constraints: free-tier components only for this run

## 2. Discovery

```bash
$ python3 skill/scripts/discover.py --min-health 85 --limit 8
# 539 registries in index (cache: False), showing 8
@keyline       health  99.0  items  13536
@000h-cojeev   health  99.0  items   1876
@react-bits    health  99.0  items   1274
@watermelon    health  99.0  items   1178
@logoforge     health  99.0  items   1019
@uiable        health  99.0  items    965
@animate-ui    health  99.0  items    789
@hextaui       health  99.0  items    760
```

539 registries, straight from the official index. No hardcoded list.

## 3. Search

```bash
$ python3 skill/scripts/search.py hero \
    --registries @magicui,@tailark,@aceternity,@animate-ui,@kibo-ui,@bundui --limit 15
# query 'hero': 15 candidates (no published index: none)
@magicui/hero-video-dialog            health  98.9
@bundui/hero-sections-01              health  91.4
@bundui/hero-sections-02              health  91.4
@aceternity/parallax-hero-images      health  76.6
@aceternity/hero-parallax             health  76.6
@aceternity/hero-highlight            health  76.6
# …plus 9 more across the six registries
```

Full per-registry indexes behind those numbers: @magicui publishes 260
items, @tailark 476, @aceternity 317 — all searchable without the CLI.

## 4. Compatibility gate — where a famous name dies

```bash
$ python3 skill/scripts/inspect.py @aceternity/hero-highlight
hero-highlight (registry:ui)
  deps: mini-svg-data-uri, motion
  registry deps: none
  files: 1  cssVars: False  tailwind block: False
```

Clean: two small deps, one file, no token redefinitions. **Passes.**

```bash
$ python3 skill/scripts/inspect.py @tailark/hero-section-1
# item fetch blocked with HTTP 401 at https://tailark.com/r/hero-section-1.json
# This registry likely needs auth or a paid license for item files.
```

@tailark's index is public, its item files are not. Under this run's
"free-tier only" constraint, every @tailark candidate is flagged at the
license gate — discovered in seconds, for free, instead of mid-install.
**This is the gate doing its job.**

## 5. Visual scoring (sheet, illustrative scores)

| Candidate | Visual | Fit | Motion | A11y | Consistency |
|---|---|---|---|---|---|
| @aceternity/hero-highlight | 8 | 9 | 7 | 7 | 8 |
| @magicui/hero-video-dialog | 9 | 7 | 8 | 6 | 7 |
| @bundui/hero-sections-01 | 7 | 8 | 5 | 8 | 8 |

In a full run these numbers come from screenshots of each candidate
rendered in the target project's theme — never from demo pages.

## 6. Fit ranking

```bash
$ python3 skill/scripts/evaluate.py candidates.json --profile landing
# profile: landing
1. @magicui/hero-video-dialog  fit-score 8.14
2. @aceternity/hero-highlight  fit-score 7.97
3. @bundui/hero-sections-01   fit-score 7.16

$ python3 skill/scripts/evaluate.py candidates.json --profile admin
# profile: admin
1. @bundui/hero-sections-01   fit-score 8.06
2. @aceternity/hero-highlight  fit-score 7.92
3. @magicui/hero-video-dialog  fit-score 7.09
```

Same candidates, same scores — **the winner flips with the brief.**
Under `landing`, spectacle and motion carry @magicui to a narrow win.
Under `admin`, the exact same component finishes last, and the plainest,
most consistent option wins. That flip is the core principle of ui-forge,
expressed as arithmetic: there is no "best component", there is only
"best for this design".
