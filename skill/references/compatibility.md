# Compatibility Gate

`uiforge inspect <@namespace/item|item-url> --project <dir> --json` answers the
question before anything is installed. Metadata alone is not enough: the real
primitive base lives in `files[].content`, and so do network calls and
obfuscation.

## What is checked, and what it costs

| Signal | Evidence | Weight |
| --- | --- | --- |
| Base mismatch | item imports `@radix-ui/*` but project is Base UI (or the reverse) | 4.0 |
| Base conflict | item imports both Radix and Base UI | 3.0 |
| Project base unknown | fingerprint could not determine the base | 1.0 |
| Tailwind major mismatch | item v3 config vs v4 CSS-first project, or reverse | 3.0 |
| Token collision | item `cssVars` redefine existing project variables | 1.5 each, cap 3.0 |
| Missing npm deps | declared deps not installed and not provided by the item | 0.5 each, cap 2.0 |
| Registry deps | 3–5 transitive items / more than 5 | 1.0 / 2.0 |
| License unknown | status `unknown` in `data/licenses.json` | 0.5 |
| License paywall | item URL answered 401/402/403 | 10.0, excluded |

`gate.compat_risk` is the sum, capped at 10, one decimal. Verdict:
`pass` < 3, `warn` ≥ 3, `fail` ≥ 6 or excluded. `gate.reasons[]` carries the
code, weight, detail and evidence URL for each point; `gate.unknowns[]` lists
what could not be verified. Report those unknowns to the user instead of
rounding them away.

## Order of operations

1. Resolve the target. Project `components.json` registries are consulted
   first; then the 539 index. 401/402/403 is a paywall: stop, record it, never
   retry.
2. Fingerprint the project with `shadcn info --json` (fallback: components.json
   style, installed packages, CSS detection). Style prefix maps the base:
   `base-*` → Base UI, `aria-*` → React Aria, `new-york`/`default` → Radix.
3. Scan `files[].content` for imports, base signals, internal imports and
   security flags (`network_fetch`, `network_axios`, `network_websocket`,
   `analytics`, `dynamic_code`).
4. Recurse one level (max 4) into `registryDependencies`; fetch each dep, add
   its risk and its `cssVars` to the collision check.
5. Compute the numeric risk. `evaluate --inspect` reads it from the report;
   never let the agent retype a risk number.

## Known limits

- A dependency that does not exist on npm (e.g. the bogus `cn` in
  `@uiable/button`) cannot be detected by npm existence alone: `cn` is also a
  real package. The gate flags `missing deps` but treats it as low weight.
- Tailwind detection is a heuristic. A missing `tailwind` block is not proof
  of v4; it only means the item carries no v3 config.
- Recursion is depth 1 by design. Deep transitive trees are reported, not
  fully explored.

## After install

- Build and typecheck the project.
- Read the installed files once for unexpected network calls or telemetry.
- Screenshot the real page and compare it with the Fitting Room draft.
