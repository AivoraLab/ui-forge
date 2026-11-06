"""Fit ranking: profile weights applied deterministically.

The agent supplies the subjective axis scores; this module supplies the
arithmetic, the profile weights (unchanged from v1 by design) and the
compatibility penalty. ``compat_risk`` can come straight from an inspect report,
so nobody has to retype it by hand.
"""
import json

SCHEMA = "ui-forge/evaluate/v1"
AXES = ("visual", "fit", "motion", "a11y", "consistency")
PROFILES = {
    "landing": {"visual": .35, "fit": .25, "motion": .20, "a11y": .05, "consistency": .05, "health": .10},
    "saas": {"visual": .15, "fit": .30, "motion": .05, "a11y": .20, "consistency": .20, "health": .10},
    "portfolio": {"visual": .30, "fit": .20, "motion": .30, "a11y": .05, "consistency": .05, "health": .10},
    "admin": {"visual": .05, "fit": .25, "motion": .00, "a11y": .30, "consistency": .30, "health": .10},
}
COMPAT_WEIGHT = 0.3


class CandidateError(ValueError):
    def __init__(self, code, message, candidate=None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.candidate = candidate

    def as_dict(self):
        return {"code": self.code, "message": self.message, "candidate": self.candidate}


def _number(candidate, key, low, high):
    value = candidate.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise CandidateError(
            "invalid_axis",
            "candidate %r needs a numeric %r in [%s, %s]; got %r"
            % (candidate.get("name"), key, low, high, value),
            candidate.get("name"),
        )
    if not (low <= value <= high):
        raise CandidateError(
            "axis_out_of_range",
            "candidate %r has %s=%r outside [%s, %s]"
            % (candidate.get("name"), key, value, low, high),
            candidate.get("name"),
        )
    return float(value)


def _load_report(path):
    try:
        with open(path, "r", encoding="utf-8") as handle:
            report = json.load(handle)
    except OSError as exc:
        raise CandidateError("inspect_unreadable", "cannot read inspect report %s: %s" % (path, exc))
    except ValueError as exc:
        raise CandidateError("inspect_bad_json", "inspect report %s is not JSON: %s" % (path, exc))
    gate = report.get("gate") if isinstance(report, dict) else None
    if not isinstance(gate, dict) or not isinstance(gate.get("compat_risk"), (int, float)):
        raise CandidateError("inspect_bad_schema", "%s is not a ui-forge inspect report (no gate.compat_risk)" % path)
    return report


def _report_for(candidate, reports):
    if candidate.get("inspect"):
        return _load_report(candidate["inspect"])
    if isinstance(candidate.get("inspect_report"), dict):
        return candidate["inspect_report"]
    target = candidate.get("target") or candidate.get("name")
    for report in reports:
        if report.get("target") in (target, candidate.get("name")):
            return report
    return None


def evaluate(candidates, profile="saas", reports=None):
    """Rank candidates. Raises CandidateError on bad input; never scores silently."""
    if profile not in PROFILES:
        raise CandidateError("unknown_profile", "profile must be one of %s" % ", ".join(sorted(PROFILES)))
    if not isinstance(candidates, list) or not candidates:
        raise CandidateError("empty_candidates", "candidates must be a non-empty JSON array")
    weights = PROFILES[profile]
    reports = [r for r in (reports or []) if isinstance(r, dict)]

    ranked = []
    disqualified = []
    for index, candidate in enumerate(candidates):
        if not isinstance(candidate, dict):
            raise CandidateError("invalid_candidate", "candidate #%d is not an object" % (index + 1))
        name = candidate.get("name")
        if not isinstance(name, str) or not name.strip():
            raise CandidateError("invalid_candidate", "candidate #%d has no name" % (index + 1))
        scores = {axis: _number(candidate, axis, 0, 10) for axis in AXES}
        health = _number(candidate, "health", 0, 100)
        report = _report_for(candidate, reports)
        if report is not None:
            compat_risk = float(report["gate"]["compat_risk"])
            compat_source = "inspect"
            excluded = bool(report["gate"].get("excluded"))
            exclude_reason = report["gate"].get("exclude_reason")
            item_sha256 = (report.get("item") or {}).get("sha256")
        else:
            compat_risk = _number(candidate, "compat_risk", 0, 10)
            compat_source = "input"
            excluded = False
            exclude_reason = None
            item_sha256 = None

        health10 = health / 10.0
        score = sum(weights[key] * (health10 if key == "health" else scores.get(key, 0)) for key in weights)
        score -= COMPAT_WEIGHT * compat_risk
        row = {
            "name": name,
            "score": round(score, 2),
            "axes": scores,
            "health": health,
            "health10": round(health10, 4),
            "compat_risk": round(compat_risk, 1),
            "compat_source": compat_source,
            "item_sha256": item_sha256,
        }
        if excluded:
            row["excluded"] = True
            row["exclude_reason"] = exclude_reason
            disqualified.append(row)
        else:
            ranked.append(row)

    ranked.sort(key=lambda row: (-row["score"], row["name"]))
    for position, row in enumerate(ranked, 1):
        row["rank"] = position
    disqualified.sort(key=lambda row: (-row["score"], row["name"]))
    return {
        "schema": SCHEMA,
        "profile": profile,
        "weights": weights,
        "count": len(ranked),
        "ranking": ranked,
        "disqualified": disqualified,
        "warnings": (
            ["compat_risk came from input for %d candidate(s); pass an inspect report to remove hand-entry" % sum(
                1 for row in ranked + disqualified if row["compat_source"] == "input")]
            if any(row["compat_source"] == "input" for row in ranked + disqualified) else []
        ),
    }
