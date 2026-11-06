# Contributing

The main community contribution is one honest line in
`skill/data/licenses.json`. That file is why ui-forge can say "this registry is
free" without guessing.

## Add a license entry

1. Pick a registry from `https://ui.shadcn.com/r/registries.json` that is
   missing from `skill/data/licenses.json`.
2. Fetch the first, middle and last item JSON from its index (or use
   `python3 skill/scripts/uiforge.py inspect "<registry>/<item>" --json`).
3. Record the real HTTP status for each: `200` = public, `401/402/403` = paywall.
   Do not retry a `401/402/403`; that is the evidence.
4. Add one entry:

```json
{
  "registry": "@example",
  "status": "free",
  "scope": "items",
  "method": "http-probe",
  "checked_at": "2026-11-06",
  "item_count": 123,
  "evidence": [
    { "item": "first-item", "url": "https://example.com/r/first-item.json", "http_status": 200 }
  ],
  "note": "optional, factual"
}
```

Rules:

- `status` is `free` only when sampled items are public. A mix of `200` and
  `401/402/403` is `freemium`. Only `401/402/403` is `paid`. If you did not
  check, it stays `unknown` — never guess.
- `evidence` needs at least one URL with the status you actually observed.
- Do not record a registry you did not probe. Do not copy another directory's
  claim.
- One registry per PR is fine. Keep the JSON sorted by registry name.

## Batch refresh

`tools/probe_licenses.py` does the same probe for whole registries, without
overwriting entries that already exist:

```bash
python3 tools/probe_licenses.py --only-missing --include-degraded
python3 tests/check_licenses.py   # validate before committing
```

It samples first/middle/last item of each published index and writes only
evidence-backed entries; registries with no usable probe stay out of the
dataset. Never run it as part of CI — the network is the contributor's job,
CI only validates what was recorded.

## Code

- Python 3.12+, standard library only. No new runtime dependencies.
- `python3 tests/smoke.py` must pass, offline, before a PR;
  `python3 tests/check_licenses.py` and `python3 tests/check_skill.py` must pass
  too (CI runs all three).
- The four commands keep their `--json` contract: `schema`, stable field names,
  exit code 2 for usage/validation and 1 for runtime failure.
- Do not change `PROFILES` weights or the example numbers in
  `examples/hero-ai-saas.md`.
- Do not add an MCP server. The official shadcn CLI/MCP owns transport.

## Docs

`skill/SKILL.md` is the procedure; `skill/references/*.md` is the detail. If
you change a command or a limit, update both, and keep the verified numbers
dated.
