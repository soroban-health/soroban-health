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
