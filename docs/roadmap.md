# Roadmap

## v2.0 — The decision layer (now)

- [x] P0: git init, `SKILL.md` frontmatter, Python 3.14 shadowing bug fixed
      (`inspect.py` removed, package launcher), offline smoke tests + CI
- [x] P1: four scripts merged into one stdlib-only CLI with stable `--json`
      contracts; `shadcn search` is the primary source
- [x] P2: real compatibility gate — numeric `compat_risk` from
      `files[].content`, `evaluate --inspect` reads it
- [x] P3: `data/licenses.json` seeded from HTTP probes; `discover --free-only`
      excludes paid/freemium with evidence
- [x] P4: Fitting Room capture (`render`, 1440/390) and verdict store
      (`verdict`, per project + item hash); draft-route composition stays with
      the agent
- [x] P5: README (two install commands + one prompt), CONTRIBUTING license path,
      docs on disk

## v2.1.1 — Gate latency (shipped as 2.1.1)

- [x] `inspect` runs against one shared wall-clock deadline (`--deadline`,
      default 120 s): the fingerprint CLI call, the item fetch and the
      registryDependency fetches no longer stack private timeouts
      (previously up to 180 s + a dozen × 30 s, in silence)
- [x] Per-stage progress lines on stderr; expiry is a typed
      `deadline_exceeded` error or a `partial: true` report naming the stage
- [x] Fetched item JSON is cached for 24 h in the data directory
      (`fetch-cache/`); repeat inspections are near-instant
- [x] registryDependencies are fetched in parallel (order preserved)
- [x] Project fingerprint cache TTL raised 10 min → 24 h (it is keyed by a
      signature of the source files, so edits still invalidate it at once)

## v2.1 — Coverage (shipped as 2.1.0)

- [x] Extend `licenses.json`: 486/539 registries probed (462 free, 16 freemium,
      6 paid, 2 unknown) via `tools/probe_licenses.py`
- [ ] Record `freemium` scope details (which item families are gated)
- [ ] Deepen `registryDependencies` recursion behind a flag (currently depth 1)
- [ ] Pairwise scoring experiment (concept.md RFC question 1)

## v2.2 — Fitting Room automation

- [ ] Scaffold the draft routes into a real project non-destructively
      (preview folder or throwaway copy, project source untouched)
- [ ] Mid-animation frame capture for motion-led candidates
- [ ] Side-by-side contact sheet in one image

## v1.0 — Portability proof

- [ ] Tested install guides: Claude Code, Codex, OpenCode, Pi
- [ ] Demo video: one request, brief to verified install, no cuts
- [ ] Second ecosystem spike (concept.md RFC question 6)

Milestones are discussion topics, not promises. Reorder them in issues.
