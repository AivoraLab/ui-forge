# Registry Discovery

Verified live on 2026-11-06 against `https://ui.shadcn.com/r/registries.json`
(539 registries, 445 healthy, 154,266 indexed items).

## Source of truth

- The official index is the only registry source. It gives name, homepage, a
  `{name}` URL template, description, health (score 0–100, status, 7d/30d
  availability) and `ranking.itemCount`.
- The index carries **no license field**. Free/paid truth lives in
  `data/licenses.json`: 486 of 539 registries probed on 2026-11-06 (462 free,
  16 freemium, 6 paid, 2 unknown). Registries missing from the dataset are
  treated as `unknown` and flagged, never as free.
- `@shadcn` is not listed in the index: it is a built-in namespace served from
  `https://ui.shadcn.com/r/styles/{style}/{name}.json`.
- 17 index templates contain `{style}`; most do not. Extensionless templates
  (e.g. `https://magicui.design/r/{name}`) serve JSON directly and also accept
  a `.json` suffix.
- Item counts drift (the docs previously said @aceternity 317; the index said
  316 at check time). Trust the live index, not this file.

## What the CLI does

- `uiforge discover --json` fetches the index (cache 24 h,
  `skill/data/registries-cache.json`) and applies the license dataset before
  any ranking. Paid and freemium registries are excluded unless the user asks.
- `uiforge search "hero" --json` calls `shadcn search` first; the item index is
  only a cache. `--index-only` forces the index path, which is what CI uses.
- Search runs one CLI call **per registry**, in parallel (max 6). A single
  multi-registry call returns only the first registry's slice (verified:
  @keyline's 13,536-item catalogue crowded out @magicui's 144 hits). When npx
  has already unpacked the CLI, the cached entry is invoked with `node`
  (~0.5 s per call) instead of re-resolving through npx (~5 s per call).
- Not every registry honours `-q`: @keyline answered `-q hero` with its whole
  catalogue, chevron icons first. The search guard keeps only rows whose
  name/title/description contain a query term for such a registry and reports
  which registries ignored the query. Registries whose batch mostly matches are
  left untouched.
- Registry health is a tiebreaker, never the ranking: a healthy registry can
  still be paid, incompatible or ugly.
- License evidence is refreshed by `tools/probe_licenses.py` from a repository
  checkout (`--only-missing --include-degraded`), never while answering a
  component request and never in CI. Existing entries are not overwritten.

## Limits

- GitHub registries (`owner/repo/item`) are **not** resolvable from the
  community index. `inspect` rejects them with `github_registry_unsupported`;
  pass the item JSON URL instead.
- With no published index the CLI falls back to `<template-root>/registry.json`
  and reports `source: index-fallback`. A fetch failure is reported as a
  failure, not as "registry has no index".
- Do not scrape registry.directory or shadcnregistry.com as a primary source.

## Cache rule

- Index: 24 h and stale-if-error.
- Item verdicts: keyed by SHA-256 of the item JSON (`item.sha256`), so a verdict
  is only recomputed when the component actually changes.
