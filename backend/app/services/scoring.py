"""Combines static analysis findings and test coverage into a single
0-100 health score.

This is a deliberately simple, transparent formula (not a black box) so
contributors can audit and tune it: start at 100, subtract a
severity-weighted penalty per finding, then apply a coverage modifier.
The exact weights are intentionally easy to find and change in one
place — see `app/api/routes/scans.py` for where they're defined, and
feel free to open an issue if you think they should be different.
"""

from __future__ import annotations

from app.models.scan import Finding, Severity

DEFAULT_SEVERITY_PENALTY = {
    Severity.LOW: 2,
    Severity.MEDIUM: 5,
    Severity.HIGH: 12,
}

NO_COVERAGE_DATA_PENALTY = 10  # flat penalty when coverage wasn't measured


def compute_health_score(
    findings: list[Finding],
    test_coverage_pct: float | None,
    severity_penalty: dict[Severity, int] | None = None,
) -> float:
    weights = severity_penalty or DEFAULT_SEVERITY_PENALTY
    score = 100.0

    for finding in findings:
        score -= weights.get(finding.severity, 5)

    if test_coverage_pct is None:
        score -= NO_COVERAGE_DATA_PENALTY
    else:
        # Below 50% coverage, apply an additional proportional penalty
        # on top of the missing-data penalty's absence; above 50% no
        # extra penalty is applied beyond what findings already cost.
        if test_coverage_pct < 50:
            score -= (50 - test_coverage_pct) * 0.3

    return max(0.0, min(100.0, round(score, 1)))
