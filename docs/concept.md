# ui-forge — Concept

Status: **RFC / idea-first.** This document is the product spec the community
is invited to argue with, refine, and build against.

## The problem

Every coding agent today does UI the same broken way:

1. It writes components from memory, producing the same generic layouts.
2. Or it uses a search tool, picks the most popular result, and pastes it in —
   whether or not it fits the product being built.

Meanwhile the shadcn ecosystem has quietly become enormous: **539 public
registries** in the official index (checked 2026-11-06), tens of thousands of
components and blocks, most of them invisible to an agent that only knows
`button` and `card` from the official set.

The missing piece is not search. Search exists. The missing piece is
**judgement**: discovery, evaluation, and selection driven by the design
being built.

## The product

ui-forge is an **Agent Skill** (not an app, not a SaaS, not an MCP server)
that gives any compatible agent a repeatable method:

| Role the agent plays | What it does |
|---|---|
| UI Researcher | Discovers registries and components it has never heard of |
| Designer | Writes a Fit Brief, renders candidates, scores them visually |
| Frontend Engineer | Checks compatibility, installs, customizes, verifies |

### The one principle

> **Do not find the prettiest component. Find the component that fits.**

Popularity is a weak signal. A famous, polished hero can be wrong for an
admin panel; an unknown block can be exactly right for a specific SaaS
dashboard. Fit is defined by the brief, scored against renders, and weighted
by project type (see the profiles in `skill/references/component-evaluation.md`).

### Three rules

1. **Fit beats fame.** Rank by the brief and the project, never by stars.
2. **Free-first is a hard rule.** Paid and freemium registries are excluded at
   the gate and reported with HTTP evidence. The official index and item JSON
   carry no license field, so ui-forge maintains `skill/data/licenses.json` —
   a community dataset with a URL and status code for every claim. That
   dataset is the defensible part: search is a solved commodity.
3. **The agent narrows, the user decides.** The agent produces at most 3
   candidates and a suggested order; the user picks the look in the Fitting
   Room.

## The pipeline

```text
Fingerprint → Fit Brief → Discovery → Search → Compatibility Gate
            → Fitting Room → Fit Ranking → Install → Verify
```

Two rules shape everything:

1. **Cheap before expensive.** Index metadata, item JSON and dependency
   checks cost almost nothing. Rendering and screenshots cost real time and
   tokens, so they run last and only on 3 survivors.
2. **Judge renders, not listings.** A registry demo page is marketing.
   A candidate is only scored from a screenshot of itself, rendered inside
   the target project's theme.

## What already exists (and why ui-forge is different)

- Registry catalogs and discovery skills exist — they stop at search.
- shadcn's own CLI and MCP server exist — they are transport, not judgement.
- Design skills (anti-slop, style direction) exist — they judge what the
  agent writes, not what the ecosystem already offers.

ui-forge sits in the empty layer between "the ecosystem has it" and
"the agent installs it": **evaluation and selection**. The official shadcn
skill teaches an agent how to use a component; ui-forge decides which one,
whether it is free, and whether it fits the site being edited. It depends on
the official skill's knowledge instead of re-teaching it.

## Non-goals

- Not a component library. ui-forge ships no components.
- Not a registry. It consumes the official index and registry indexes.
- Not a hosted service. Everything runs locally in the agent's environment.
- Not shadcn-only forever — the method (brief → discover → gate → render →
  rank) should port to other registry-based ecosystems. shadcn is first
  because its registry protocol is open and its ecosystem is largest.

## Open questions (RFC)

These are genuinely undecided. Issues and PRs arguing a position are the
most valuable contributions right now.

1. **Visual scoring rubric.** Are the five axes (visual, fit, motion, a11y,
   consistency) the right ones? Should scores be absolute or pairwise
   ("A vs B, which fits better")? Pairwise is cheaper for vision models and
   may be more reliable — but harder to cache.
2. **Preview harness.** One shared Vite harness with per-candidate routes,
   or a fresh scratch project per candidate? Isolation vs speed.
3. **Cache format.** JSON files today. When does the learning cache
   (verdicts keyed by item content hash) outgrow files and earn SQLite?
4. **Trust.** Third-party registry code lands in user codebases. How much
   static inspection (network calls, telemetry, obfuscation) belongs in the
   compatibility gate before install?
5. **Registries without indexes.** CLI fallback works but is slower and
   needs a configured project. Is a community-maintained supplemental index
   worth it, or does that reintroduce the hardcoded-list problem?
6. **Beyond shadcn.** Which ecosystem is the second target — and does the
   Fit Brief / profile model survive the move?
