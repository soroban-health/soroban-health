"""Combines static analysis findings, test coverage, and on-chain
invocation history into a single 0-100 health score.

This is a deliberately simple, transparent formula (not a black box) so
contributors can audit and tune it: start at 100, subtract a
severity-weighted penalty per finding, apply a coverage modifier, then
apply an on-chain error-rate modifier. The exact weights are intentionally
easy to find and change in one place — see `app/api/routes/scans.py` for
where the severity weights are defined, and feel free to open an issue if
you think they should be different.

On-chain activity (see `app/services/rpc.py`) only ever subtracts, and
only once there's enough sample size to trust the error rate
(`ON_CHAIN_MIN_INVOCATIONS_FOR_PENALTY` recent invocations). Invocation
frequency itself does not adjust the score — there is no baseline for how
much usage is "healthy" (a rarely-used contract isn't worse than a busy
one), so frequency is surfaced in `ScanResult.on_chain_activity` for
humans to read but left out of the formula. A contract with no on-chain
data available — not yet deployed to the configured network, RPC
unreachable, or too few invocations to trust an error rate — gets no
on-chain adjustment at all, unlike `test_coverage_pct=None`: missing
on-chain history isn't itself a red flag the way missing test coverage is.
"""

from __future__ import annotations

from app.models.scan import Finding, OnChainActivity, Severity

DEFAULT_SEVERITY_PENALTY = {
    Severity.LOW: 2,
    Severity.MEDIUM: 5,
    Severity.HIGH: 12,
}

NO_COVERAGE_DATA_PENALTY = 10  # flat penalty when coverage wasn't measured

# A 100%-failing contract (all recent invocations FAILED) costs this many
# points, scaling linearly down to 0 at a 0% error rate. At the scale most
# real contracts sit at (~0%, since clients that simulate before
# submitting reject failing calls before they ever reach the ledger — see
# app/services/rpc.py), this is a no-op; a 25%-failing contract costs 10
# points, comparable to one HIGH-severity static finding (12 points).
ON_CHAIN_ERROR_RATE_PENALTY_SCALE = 40.0

# Below this many recent invocations, an error rate isn't a reliable
# signal (one failed call out of two looks like a 50% error rate) — no
# penalty is applied until there's enough sample size to trust it.
ON_CHAIN_MIN_INVOCATIONS_FOR_PENALTY = 5


def compute_health_score(
    findings: list[Finding],
    test_coverage_pct: float | None,
    severity_penalty: dict[Severity, int] | None = None,
    on_chain_activity: OnChainActivity | None = None,
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

    if (
        on_chain_activity is not None
        and on_chain_activity.available
        and on_chain_activity.invocation_count >= ON_CHAIN_MIN_INVOCATIONS_FOR_PENALTY
    ):
        score -= (
            on_chain_activity.error_rate or 0.0
        ) * ON_CHAIN_ERROR_RATE_PENALTY_SCALE

    return max(0.0, min(100.0, round(score, 1)))
