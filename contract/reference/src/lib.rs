//! Soroban Health Reference Contract
//!
//! This contract is NOT meant to be deployed in production. It exists as a
//! fixture: every module pairs a "good" implementation with a "bad" one that
//! demonstrates a real-world anti-pattern. The Soroban Health scanner is
//! tested against this contract to confirm it correctly flags the `bad_*`
//! functions and does NOT flag the `good_*` functions.
//!
//! See each module for the specific anti-pattern it demonstrates:
//! - `storage`   — unbounded storage growth vs. bounded storage with eviction
//! - `errors`    — `panic!` vs. typed `panic_with_error!`
//! - `ttl`       — missing TTL extension vs. correctly extended persistent storage

#![no_std]

mod errors;
mod storage;
mod ttl;

use soroban_sdk::{contract, contractimpl, Address, Env, Symbol};

pub use errors::HealthError;

#[contract]
pub struct ReferenceContract;

#[contractimpl]
impl ReferenceContract {
    /// One-time setup. Stores the contract administrator address.
    pub fn initialize(env: Env, admin: Address) {
        admin.require_auth();
        storage::set_admin(&env, &admin);
    }

    // ---- Storage anti-pattern pair ----

    /// GOOD: bounded log, evicts oldest entry once the cap is reached.
    pub fn good_log_event(env: Env, label: Symbol) {
        storage::good_append_bounded(&env, label);
    }

    /// BAD: appends forever with no cap — storage (and rent cost) grows
    /// without bound as the contract is used. This is what the scanner
    /// should flag as `unbounded_storage_growth`.
    pub fn bad_log_event(env: Env, label: Symbol) {
        storage::bad_append_unbounded(&env, label);
    }

    // ---- Error-handling anti-pattern pair ----

    /// GOOD: returns a typed, documented error instead of panicking blindly.
    pub fn good_withdraw(env: Env, amount: i128) -> Result<i128, HealthError> {
        errors::good_checked_withdraw(&env, amount)
    }

    /// BAD: uses a bare `panic!` with a string, which produces an opaque
    /// failure with no error code callers can match on. This is what the
    /// scanner should flag as `bare_panic_used`.
    pub fn bad_withdraw(env: Env, amount: i128) -> i128 {
        errors::bad_unchecked_withdraw(&env, amount)
    }

    // ---- TTL anti-pattern pair ----

    /// GOOD: writes to persistent storage and immediately extends its TTL,
    /// so it doesn't unexpectedly expire and get archived.
    pub fn good_persist_record(env: Env, key: Symbol, value: u64) {
        ttl::good_persist_with_extension(&env, key, value);
    }

    /// BAD: writes to persistent storage but never extends the TTL. The
    /// entry will eventually expire and become inaccessible without
    /// warning. This is what the scanner should flag as `missing_ttl_extension`.
    pub fn bad_persist_record(env: Env, key: Symbol, value: u64) {
        ttl::bad_persist_without_extension(&env, key, value);
    }
}

#[cfg(test)]
mod test;
