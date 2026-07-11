"""Tests for the static analyzer.

These tests run the analyzer against small inline snippets that mirror
the patterns in `contract/reference/src/*.rs`, confirming the scanner
flags the `bad_*` style and does not flag the `good_*` style.
"""

from app.models.scan import FindingType
from app.services.analyzer import (
    check_bare_panic,
    check_missing_ttl_extension,
    check_unbounded_growth,
)

GOOD_ERROR_SNIPPET = """
pub fn good_checked_withdraw(_env: &Env, amount: i128) -> Result<i128, HealthError> {
    if amount <= 0 {
        return Err(HealthError::InvalidAmount);
    }
    Ok(BALANCE - amount)
}
"""

BAD_ERROR_SNIPPET = """
pub fn bad_unchecked_withdraw(_env: &Env, amount: i128) -> i128 {
    if amount <= 0 {
        panic!("amount must be positive");
    }
    BALANCE - amount
}
"""

GOOD_TTL_SNIPPET = """
pub fn good_persist_with_extension(env: &Env, key: Symbol, value: u64) {
    env.storage().persistent().set(&key, &value);
    env.storage().persistent().extend_ttl(&key, MIN_TTL_LEDGERS, EXTEND_TO_LEDGERS);
}
"""

BAD_TTL_SNIPPET = """
pub fn bad_persist_without_extension(env: &Env, key: Symbol, value: u64) {
    env.storage().persistent().set(&key, &value);
}
"""

GOOD_GROWTH_SNIPPET = """
pub fn good_append_bounded(env: &Env, label: Symbol) {
    let mut log: Vec<Symbol> = env.storage().persistent().get(&DataKey::GoodLog).unwrap_or_else(|| Vec::new(env));
    if log.len() >= MAX_LOG_ENTRIES {
        log.remove(0);
    }
    log.push_back(label);
    env.storage().persistent().set(&DataKey::GoodLog, &log);
}
"""

BAD_GROWTH_SNIPPET = """
pub fn bad_append_unbounded(env: &Env, label: Symbol) {
    let mut log: Vec<Symbol> = env.storage().persistent().get(&DataKey::BadLog).unwrap_or_else(|| Vec::new(env));
    log.push_back(label);
    env.storage().persistent().set(&DataKey::BadLog, &log);
}
"""

# A `push_back` mention that isn't a real AST node — a regex/line-scan
# would misflag these, which is the exact false positive issue #8 names.
FALSE_POSITIVE_GROWTH_COMMENT_SNIPPET = """
pub fn no_real_push(env: &Env, label: Symbol) {
    // log.push_back(label) is just a comment, not real code
    let _ = (env, label);
}
"""

FALSE_POSITIVE_GROWTH_STRING_SNIPPET = """
pub fn log_event(env: &Env) {
    env.events().publish((), "log.push_back(label) called");
}
"""

FALSE_POSITIVE_PANIC_SNIPPET = """
pub fn safe_fn(env: &Env) {
    // don't do this: panic!(x)
    let msg = "call panic!(x) to abort";
    let _ = (env, msg);
}
"""

# Two short, adjacent functions — a ±5-line text window (the old heuristic)
# would let bump_b's unrelated extend_ttl call satisfy write_a's check.
# Function-scoping must still flag write_a's unguarded `.set(`.
ADJACENT_FUNCTIONS_SNIPPET = """
pub fn write_a(env: &Env, key: Symbol, value: u64) {
    env.storage().persistent().set(&key, &value);
}
pub fn bump_b(env: &Env, other_key: Symbol) {
    env.storage().persistent().extend_ttl(&other_key, MIN_TTL_LEDGERS, EXTEND_TO_LEDGERS);
}
"""

# `.set(` and `.extend_ttl(` more than 5 lines apart but in the *same*
# function — function-scoping must NOT flag this (the old ±5-line window
# would have incorrectly reported this as missing).
FAR_APART_SAME_FUNCTION_SNIPPET = """
pub fn write_then_bump(env: &Env, key: Symbol, value: u64) {
    env.storage().persistent().set(&key, &value);
    let a = 1;
    let b = 2;
    let c = 3;
    let d = 4;
    let e = 5;
    env.storage().persistent().extend_ttl(&key, MIN_TTL_LEDGERS, EXTEND_TO_LEDGERS);
}
"""


def test_bare_panic_flagged_in_bad_snippet():
    findings = check_bare_panic("errors.rs", BAD_ERROR_SNIPPET)
    assert len(findings) == 1
    assert findings[0].type == FindingType.BARE_PANIC_USED


def test_bare_panic_not_flagged_in_good_snippet():
    findings = check_bare_panic("errors.rs", GOOD_ERROR_SNIPPET)
    assert findings == []


def test_missing_ttl_flagged_in_bad_snippet():
    findings = check_missing_ttl_extension("ttl.rs", BAD_TTL_SNIPPET)
    assert len(findings) == 1
    assert findings[0].type == FindingType.MISSING_TTL_EXTENSION


def test_missing_ttl_not_flagged_when_extend_ttl_present():
    findings = check_missing_ttl_extension("ttl.rs", GOOD_TTL_SNIPPET)
    assert findings == []


def test_unbounded_growth_flagged_in_bad_snippet():
    findings = check_unbounded_growth("storage.rs", BAD_GROWTH_SNIPPET)
    assert len(findings) == 1
    assert findings[0].type == FindingType.UNBOUNDED_STORAGE_GROWTH


def test_unbounded_growth_not_flagged_when_capped_and_evicted():
    findings = check_unbounded_growth("storage.rs", GOOD_GROWTH_SNIPPET)
    assert findings == []


def test_unbounded_growth_ignores_push_back_in_comment():
    findings = check_unbounded_growth(
        "storage.rs", FALSE_POSITIVE_GROWTH_COMMENT_SNIPPET
    )
    assert findings == []


def test_unbounded_growth_ignores_push_back_in_string_literal():
    findings = check_unbounded_growth(
        "storage.rs", FALSE_POSITIVE_GROWTH_STRING_SNIPPET
    )
    assert findings == []


def test_bare_panic_ignores_panic_in_comment_and_string():
    findings = check_bare_panic("errors.rs", FALSE_POSITIVE_PANIC_SNIPPET)
    assert findings == []


def test_missing_ttl_flags_across_short_adjacent_functions():
    findings = check_missing_ttl_extension("ttl.rs", ADJACENT_FUNCTIONS_SNIPPET)
    assert len(findings) == 1
    assert findings[0].type == FindingType.MISSING_TTL_EXTENSION


def test_missing_ttl_not_flagged_when_extend_ttl_is_far_from_set():
    findings = check_missing_ttl_extension("ttl.rs", FAR_APART_SAME_FUNCTION_SNIPPET)
    assert findings == []


def test_dependency_drift_flagged_when_versions_mismatch():
    files = {
        "Cargo.toml": '[dependencies]\nsoroban-sdk = "21.7.0"',
        "Cargo.lock": '[[package]]\nname = "soroban-sdk"\nversion = "20.5.0"',
    }
    from app.services.analyzer import check_dependency_version_drift

    findings = check_dependency_version_drift(files)
    assert len(findings) == 1
    assert findings[0].type == FindingType.DEPENDENCY_VERSION_DRIFT
    assert findings[0].severity == "medium"
    assert "21.7.0" in findings[0].message
    assert "20.5.0" in findings[0].message


def test_dependency_drift_not_flagged_when_versions_match():
    files = {
        "Cargo.toml": '[dependencies]\nsoroban-sdk = "21.7.0"',
        "Cargo.lock": '[[package]]\nname = "soroban-sdk"\nversion = "21.7.0"',
    }
    from app.services.analyzer import check_dependency_version_drift

    findings = check_dependency_version_drift(files)
    assert findings == []


def test_dependency_drift_flagged_when_lock_missing():
    files = {
        "Cargo.toml": '[dependencies]\nsoroban-sdk = "21.7.0"',
    }
    from app.services.analyzer import check_dependency_version_drift

    findings = check_dependency_version_drift(files)
    assert len(findings) == 1
    assert findings[0].type == FindingType.DEPENDENCY_VERSION_DRIFT
    assert findings[0].severity == "low"
    assert "missing or not provided" in findings[0].message


def test_dependency_drift_handles_table_syntax():
    files = {
        "Cargo.toml": '[dependencies]\nsoroban-sdk = { version = "21.7.0", features = ["testutils"] }',
        "Cargo.lock": '[[package]]\nname = "soroban-sdk"\nversion = "20.5.0"',
    }
    from app.services.analyzer import check_dependency_version_drift

    findings = check_dependency_version_drift(files)
    assert len(findings) == 1
    assert findings[0].type == FindingType.DEPENDENCY_VERSION_DRIFT


def test_dependency_drift_skipped_when_no_cargo_toml():
    files = {"Cargo.lock": '[[package]]\nname = "soroban-sdk"\nversion = "20.5.0"'}
    from app.services.analyzer import check_dependency_version_drift

    findings = check_dependency_version_drift(files)
    assert findings == []
