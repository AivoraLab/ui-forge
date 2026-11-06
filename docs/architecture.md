# Architecture

## Shape

ui-forge is a **skill** (instructions + references + one deterministic CLI),
not a daemon, server, plugin or MCP server. Any agent that can read a
`SKILL.md`, run shell commands, view images and browse the web can run it:
Claude Code, Codex, OpenCode, Pi and other Agent Skills runtimes.

```text
skill/
├── SKILL.md                  the method: fingerprint → brief → discover → search → gate → Fitting Room → install → verify
├── references/
│   ├── registry-discovery.md sources, index limits, cache rules
│   ├── component-evaluation.md fit profiles, validation, fixed weights
│   ├── visual-analysis.md    Fitting Room, capture, verdict store
│   └── compatibility.md      gate signals, weights, known limits
├── data/
│   └── licenses.json         community license evidence (committed, not a cache)
└── scripts/
    ├── uiforge.py            launcher
    └── ui_forge/             stdlib-only package
        ├── cli.py            four command contracts + --json
        ├── index.py          official index, 24h cache, stale-if-error
        ├── licenses.py       free / freemium / paid / unknown lookup
        ├── shadcn.py         official CLI bridge (`info`, `search`)
        ├── project.py        fingerprint: base, Tailwind, tokens, aliases
        ├── search.py          shadcn search first, item indexes as cache
        ├── discover.py        free-first registry list
        ├── inspect.py         numeric compatibility gate (0–10)
        ├── evaluate.py       profile-weighted fit ranking
        ├── render.py         Playwright capture + verdict store
        └── net.py            one HTTP policy, no silent failures
```

## Division of labour

- **The CLI does deterministic work only**: fetching, parsing, scanning
  `files[].content`, arithmetic, screenshots, memory. It never decides what
  looks good.
- **The agent does judgement work**: writing the brief, scoring the five
  subjective axes, building the three draft routes, adapting installed code.
- **The user does the final aesthetic choice** in the Fitting Room.
- **The ecosystem does distribution**: the official index, item JSON and the
  shadcn CLI are reused, never reimplemented. No MCP: transport already exists.

## Contracts

Every command returns a stable JSON schema (`ui-forge/<command>/v1`) with
`--json`, and exits 2 for usage/validation errors, 1 for runtime failures.
`inspect` returns `gate.compat_risk` as a number; `evaluate --inspect` reads it,
so the agent never retypes a risk score.

## Data and caching

All state lives in `skill/data/`:

- `licenses.json` — committed evidence: status, checked date, URLs and HTTP
  codes. Community-contributed; unknown stays unknown.
- `registries-cache.json` — official index, 24 h TTL, stale-if-error.
- `fingerprint-cache.json` — project fingerprint, keyed by mtime signature.
- `verdicts/` — the user's choices per project path and item hash.

SQLite is a deliberate non-choice: the skill must copy cleanly between agent
runtimes and machines. Revisit when the verdict store passes roughly a thousand
records (see RFC question 3 in concept.md).

## Trust boundaries

- Registry item code is third-party code entering a user's codebase. The gate
  reads it before install; the install step reads the written files after, and
  flags unexpected network calls, telemetry or obfuscation.
- Scripts make network requests only to endpoints discovered from the official
  index, named by the user, or reached through `shadcn` itself. Nothing phones
  home.
- A paywall (401/403) is recorded as evidence and never retried.
- No credentials are needed for public registries. Private registries go
  through the shadcn CLI's own auth config, never through ui-forge.
