"""Tests for the static analyzer.

These tests run the analyzer against small inline snippets that mirror
the patterns in `contract/reference/src/*.rs`, confirming the scanner
flags the `bad_*` style and does not flag the `good_*` style.
"""

import pytest

from app.models.scan import FindingType
from app.services.analyzer import (
    check_bare_panic,
    check_dependency_version_drift,
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


# --- Cargo requirement semantics -------------------------------------------
#
# A Cargo.toml version string is a *requirement*, not a pin: "21.7.0" means
# `^21.7.0` (>=21.7.0, <22.0.0). Drift is the lockfile violating that
# requirement, not the two strings differing — so a routine patch bump must
# stay silent.


def _drift(requirement: str, locked: str) -> list:
    return check_dependency_version_drift(
        {
            "Cargo.toml": f'[dependencies]\nsoroban-sdk = "{requirement}"',
            "Cargo.lock": f'[[package]]\nname = "soroban-sdk"\nversion = "{locked}"',
        }
    )


@pytest.mark.parametrize(
    ("requirement", "locked"),
    [
        ("21.7.0", "21.7.7"),  # caret allows patch bumps — the regression case
        ("21.7.0", "21.9.0"),  # caret allows minor bumps
        ("21", "21.7.7"),
        ("^21.7.0", "21.7.7"),
        ("0.2.3", "0.2.9"),  # 0.x caret pins the minor
        ("0.0.3", "0.0.3"),
        ("~21.7", "21.7.9"),
        ("=21.7.0", "21.7.0"),
        (">=21.0, <22.0", "21.7.7"),
        ("21.*", "21.7.7"),
        ("*", "21.7.7"),
    ],
)
def test_dependency_drift_not_flagged_when_lock_satisfies_requirement(
    requirement, locked
):
    assert _drift(requirement, locked) == []


@pytest.mark.parametrize(
    ("requirement", "locked"),
    [
        ("21.7.0", "22.0.0"),  # major bump breaks caret
        ("21.7.0", "21.6.9"),  # below the floor
        ("0.2.3", "0.3.0"),  # 0.x caret: minor bump is breaking
        ("0.0.3", "0.0.4"),  # 0.0.x caret: patch bump is breaking
        ("~21.7", "21.8.0"),  # tilde pins the minor
        ("=21.7.0", "21.7.7"),  # exact means exact
        (">=21.0, <22.0", "22.1.0"),
        ("21.*", "22.0.0"),
    ],
)
def test_dependency_drift_flagged_when_lock_violates_requirement(requirement, locked):
    findings = _drift(requirement, locked)
    assert len(findings) == 1
    assert findings[0].type == FindingType.DEPENDENCY_VERSION_DRIFT
    assert findings[0].severity == "medium"
    assert requirement in findings[0].message
    assert locked in findings[0].message


def test_dependency_drift_resolves_workspace_inheritance():
    """A member crate saying `{ workspace = true }` carries no version of its
    own — the requirement lives in the workspace root, as in `contract/`."""
    files = {
        "Cargo.toml": '[workspace.dependencies]\nsoroban-sdk = "21.7.0"',
        "reference/Cargo.toml": ("[dependencies]\nsoroban-sdk = { workspace = true }"),
        "Cargo.lock": '[[package]]\nname = "soroban-sdk"\nversion = "22.0.0"',
    }
    findings = check_dependency_version_drift(files)
    assert len(findings) == 1
    assert "21.7.0" in findings[0].message


def test_dependency_drift_reads_dev_dependencies():
    files = {
        "Cargo.toml": (
            '[dev-dependencies]\nsoroban-sdk = { version = "21.7.0", '
            'features = ["testutils"] }'
        ),
        "Cargo.lock": '[[package]]\nname = "soroban-sdk"\nversion = "22.0.0"',
    }
    assert len(check_dependency_version_drift(files)) == 1


def test_dependency_drift_skipped_for_git_dependency():
    """A git dependency has no version requirement to verify."""
    files = {
        "Cargo.toml": (
            "[dependencies]\nsoroban-sdk = { git = "
            '"https://github.com/stellar/rs-soroban-sdk", branch = "main" }'
        ),
        "Cargo.lock": '[[package]]\nname = "soroban-sdk"\nversion = "21.7.7"',
    }
    assert check_dependency_version_drift(files) == []


def test_dependency_drift_skipped_on_malformed_manifest():
    """Repos fetched from GitHub are arbitrary; a broken manifest must not
    fail the scan or produce a bogus finding."""
    files = {
        "Cargo.toml": "[dependencies\nsoroban-sdk = not valid toml",
        "Cargo.lock": '[[package]]\nname = "soroban-sdk"\nversion = "21.7.7"',
    }
    assert check_dependency_version_drift(files) == []


def test_dependency_drift_not_flagged_when_any_locked_version_satisfies():
    """A lockfile can legitimately carry several majors of one crate."""
    files = {
        "Cargo.toml": '[dependencies]\nsoroban-sdk = "21.7.0"',
        "Cargo.lock": (
            '[[package]]\nname = "soroban-sdk"\nversion = "20.5.0"\n\n'
            '[[package]]\nname = "soroban-sdk"\nversion = "21.7.7"'
        ),
    }
    assert check_dependency_version_drift(files) == []


def test_dependency_drift_reports_declaration_line():
    """Findings point at the offending declaration, not line 1."""
    files = {
        "Cargo.toml": '[dependencies]\nsoroban-sdk = "21.7.0"',
        "Cargo.lock": (
            '[[package]]\nname = "other"\nversion = "1.0.0"\n\n'
            '[[package]]\nname = "soroban-sdk"\nversion = "22.0.0"'
        ),
    }
    findings = check_dependency_version_drift(files)
    assert len(findings) == 1
    assert findings[0].file == "Cargo.lock"
    assert findings[0].line == 6


def test_dependency_drift_missing_lock_points_at_manifest():
    files = {"Cargo.toml": '[dependencies]\nsoroban-sdk = "21.7.0"'}
    findings = check_dependency_version_drift(files)
    assert len(findings) == 1
    assert findings[0].severity == "low"
    assert findings[0].file == "Cargo.toml"
    assert findings[0].line == 2


# --- Pre-release versions ---------------------------------------------------
#
# soroban-sdk ships real release candidates (22.0.0-rc.3), and Cargo will not
# select a pre-release unless the requirement opts into one at the same
# major.minor.patch. Treating "22.0.0-rc.1" as plain "22.0.0" would both miss
# real drift and mis-order the two.


@pytest.mark.parametrize(
    ("requirement", "locked"),
    [
        ("=22.0.0-rc.3", "22.0.0-rc.3"),
        ("^22.0.0-rc.1", "22.0.0-rc.2"),  # opts in at the same base
        ("^22.0.0-rc.1", "22.0.0"),  # the release outranks its own rc
        (">=22.0.0-rc.1, <23.0.0", "22.0.0-rc.2"),
        ("21.7.0", "21.7.7+build.5"),  # build metadata carries no precedence
    ],
)
def test_dependency_drift_not_flagged_for_matching_prerelease(requirement, locked):
    assert _drift(requirement, locked) == []


@pytest.mark.parametrize(
    ("requirement", "locked"),
    [
        ("21.7.0", "22.0.0-rc.1"),  # a caret req never opts into a pre-release
        ("21.7.0", "21.8.0-rc.1"),
        ("=22.0.0-rc.3", "22.0.0-rc.4"),
        ("^22.0.0-rc.5", "22.0.0-rc.2"),  # rc.2 sorts below the rc.5 floor
    ],
)
def test_dependency_drift_flagged_for_incompatible_prerelease(requirement, locked):
    findings = _drift(requirement, locked)
    assert len(findings) == 1
    assert findings[0].type == FindingType.DEPENDENCY_VERSION_DRIFT


def test_prerelease_identifiers_order_numerically_below_alphanumeric():
    """SemVer: numeric identifiers compare numerically and rank below
    alphanumeric ones, so rc.10 is newer than rc.9 (not older, as a string
    comparison would have it)."""
    from app.services.analyzer import _satisfies

    assert _satisfies("22.0.0-rc.10", "^22.0.0-rc.9") is True
    assert _satisfies("22.0.0-rc.9", "^22.0.0-rc.10") is False
    assert _satisfies("22.0.0-2", "^22.0.0-rc") is False
