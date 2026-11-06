# Visual Analysis — the Fitting Room

A component is not judged on its demo site. It is judged installed into **this**
page, with **this** theme, **this** content and **this** viewport.

## Building the draft

- One draft route per candidate, inside a throwaway copy of the project or a
  preview folder. The real source route is never modified.
- Reuse the project's real theme tokens, fonts and dark/light setting, and the
  page's real content. A candidate judged under a foreign theme is judged wrong.
- Same viewport for all three candidates: 1440 px and 390 px.
- If the candidate's value is motion, add one mid-animation frame, and open the
  two finalists live (motion, hover, reduced-motion) rather than judging from a
  still.

## Scoring sheet (0–10 each)

- `visual`: typography hierarchy, spacing rhythm, colour discipline, detail
  polish.
- `fit`: does it answer this brief, this audience, this project type.
- `motion`: easing quality, purpose of the animation, reduced-motion behaviour.
- `a11y`: contrast, focus visibility, semantics visible in render and markup.
- `consistency`: could this sit beside the project's existing screens without
  looking imported.

## Presentation

- Show the three drafts side by side, one honest paragraph each, and a
  suggested order with the reason.
- Stop there. The user picks; the agent does not.
- The winner (or two finalists) is the only thing that gets installed.

## Cost discipline

- Render at most 3 candidates per request — the search + gate already earned
  that shortlist.
- One screenshot round first. Re-render only after a token or content
  adaptation changes the result.
- Cache the verdict by item content hash and the project path, so the next run
  respects the user's earlier choice.

## Capture and verdict store

```bash
python3 scripts/uiforge.py render <url-a> <url-b> <url-c> \
  --out previews/hero --width 1440 --width 390 --wait-ms 800 --json
python3 scripts/uiforge.py verdict "@ns/item" --sha256 <item.sha256> \
  --project . --chosen yes --note "why the user picked it"
```

`render` runs the Playwright CLI (`npx playwright screenshot`), writes one PNG
per candidate and viewport into `--out`, and reports
`playwright_browser_missing` with the install hint when Chromium is not there.
Building the three draft routes stays with the agent; `render` never composes a
component into the project.

`verdict` stores the user's choice under `data/verdicts/`, keyed by project
path and item hash. The next run reads it and must not re-propose a rejected
look without saying that it was rejected before.

## Evidence

Never screenshot the registry's own demo as evidence: demos are styled to sell,
with content and spacing the installed result will not have. Keep the draft
screenshot, the item hash and the user's choice as the verdict record.
