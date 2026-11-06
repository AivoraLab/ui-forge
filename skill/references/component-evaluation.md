# Component Evaluation — Fit Profiles

Fit beats fame. The agent supplies the subjective axes; the CLI applies fixed
profile weights and subtracts `0.3 × compat_risk` read from the gate.

## Profiles

| Profile | visual | fit | motion | a11y | consistency | health |
| --- | --- | --- | --- | --- | --- | --- |
| landing | .35 | .25 | .20 | .05 | .05 | .10 |
| saas | .15 | .30 | .05 | .20 | .20 | .10 |
| portfolio | .30 | .20 | .30 | .05 | .05 | .10 |
| admin | .05 | .25 | .00 | .30 | .30 | .10 |

A landing hero may trade consistency for impact; an admin panel is judged on
usability and never on flair.

## Inputs and validation

```bash
$UIFORGE evaluate examples/candidates-hero.json --profile landing \
  --inspect inspect-magicui.json --inspect inspect-aceternity.json --json
```

Every axis is required and must be numeric in range: 0–10 for the five
subjective axes, 0–100 for health. Out-of-range or missing values exit 2 with
a message naming the candidate and axis. No silent zeroes.

`compat_risk` is not supplied by the agent. Pass `--inspect` for each
candidate; the CLI reads `gate.compat_risk` and `gate.excluded`. An excluded
candidate is listed under `disqualified`, never scored.

## Interpreting the output

- `ranking[]` is sorted by score, then name (stable, reproducible).
- The example sheet must keep producing landing 8.14 / 7.97 / 7.16 and admin
  8.06 / 7.92 / 7.09. If it does not, the arithmetic changed — that is a bug,
  not a tuning opportunity.
- The score orders the shortlist; it does not choose the winner. The Fitting
  Room and the user decide.

## Hard gates before scoring

- Paid or freemium without an explicit user request: out.
- Base mismatch or Tailwind major mismatch: out, unless the user accepts a
  migration.
- Health not healthy and no recent successful check: flag, score health low.
- License `unknown`: allowed but flagged; say so to the user.

## Do not change the weights

The weights are part of the product contract. A change needs an RFC with the
reproduced example numbers before and after.
