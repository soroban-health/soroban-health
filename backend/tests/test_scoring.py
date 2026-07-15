from app.models.scan import Finding, FindingType, OnChainActivity, Severity
from app.services.scoring import compute_health_score


def _finding(severity: Severity) -> Finding:
    return Finding(
        type=FindingType.BARE_PANIC_USED,
        severity=severity,
        file="x.rs",
        line=1,
        message="test",
    )


def test_perfect_score_with_no_findings_and_full_coverage():
    score = compute_health_score(findings=[], test_coverage_pct=100.0)
    assert score == 100.0


def test_score_drops_with_high_severity_finding():
    score = compute_health_score(
        findings=[_finding(Severity.HIGH)], test_coverage_pct=100.0
    )
    assert score == 88.0  # 100 - 12


def test_score_penalized_when_coverage_unknown():
    score = compute_health_score(findings=[], test_coverage_pct=None)
    assert score == 90.0  # 100 - 10 (no coverage data penalty)


def test_score_penalized_for_low_coverage():
    score = compute_health_score(findings=[], test_coverage_pct=20.0)
    # 100 - (50 - 20) * 0.3 = 100 - 9 = 91.0
    assert score == 91.0


def test_score_never_goes_below_zero():
    findings = [_finding(Severity.HIGH) for _ in range(20)]
    score = compute_health_score(findings=findings, test_coverage_pct=0.0)
    assert score == 0.0


def test_score_never_exceeds_100():
    score = compute_health_score(findings=[], test_coverage_pct=100.0)
    assert score <= 100.0


def test_onchain_error_rate_penalizes_score():
    activity = OnChainActivity(
        available=True, invocation_count=20, error_count=5, error_rate=0.25
    )
    score = compute_health_score(
        findings=[], test_coverage_pct=100.0, on_chain_activity=activity
    )
    # 100 - (0.25 * 40) = 90.0
    assert score == 90.0


def test_onchain_penalty_skipped_below_invocation_threshold():
    activity = OnChainActivity(
        available=True, invocation_count=1, error_count=1, error_rate=1.0
    )
    score = compute_health_score(
        findings=[], test_coverage_pct=100.0, on_chain_activity=activity
    )
    assert score == 100.0


def test_onchain_penalty_skipped_when_unavailable():
    activity = OnChainActivity(available=False, reason="not deployed to this network")
    score = compute_health_score(
        findings=[], test_coverage_pct=100.0, on_chain_activity=activity
    )
    assert score == 100.0
