//! Demonstrates the "unbounded storage growth" anti-pattern.
//!
//! Soroban contracts pay rent proportional to the storage they occupy.
//! A contract that appends to a list on every call without ever evicting
//! old entries will see its storage footprint — and therefore its
//! operating cost — grow without bound. This is one of the most common
//! issues flagged in Soroban audits (see Veridise's Soroban security
//! checklist).
//!
//! Note: neither function below calls `extend_ttl`. That's intentional —
//! this module isolates the storage-growth pattern specifically, and the
//! TTL-extension pattern is demonstrated separately in `ttl.rs`. If you
//! run the scanner against this file, you will (correctly) also see
//! `missing_ttl_extension` findings here; that's expected, not a bug in
//! either the contract or the scanner.

use soroban_sdk::{contracttype, Address, Env, Symbol, Vec};

const MAX_LOG_ENTRIES: u32 = 50;

#[derive(Clone)]
#[contracttype]
pub enum DataKey {
    Admin,
    GoodLog,
    BadLog,
}

pub fn set_admin(env: &Env, admin: &Address) {
    env.storage().instance().set(&DataKey::Admin, admin);
}

/// GOOD: caps the log at `MAX_LOG_ENTRIES`. Once full, the oldest entry is
/// evicted before the new one is appended, so storage size is bounded and
/// predictable regardless of how many times this function is called.
pub fn good_append_bounded(env: &Env, label: Symbol) {
    let mut log: Vec<Symbol> = env
        .storage()
        .persistent()
        .get(&DataKey::GoodLog)
        .unwrap_or_else(|| Vec::new(env));

    if log.len() >= MAX_LOG_ENTRIES {
        log.remove(0);
    }
    log.push_back(label);

    env.storage().persistent().set(&DataKey::GoodLog, &log);
}

/// BAD: appends to the log on every call with no cap and no eviction.
/// After enough invocations, this entry becomes large enough to
/// meaningfully increase rent cost, and in the worst case can approach
/// the ledger entry size limit.
pub fn bad_append_unbounded(env: &Env, label: Symbol) {
    let mut log: Vec<Symbol> = env
        .storage()
        .persistent()
        .get(&DataKey::BadLog)
        .unwrap_or_else(|| Vec::new(env));

    log.push_back(label); // <-- no cap, no eviction: unbounded growth

    env.storage().persistent().set(&DataKey::BadLog, &log);
}
