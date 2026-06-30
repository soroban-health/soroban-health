//! Demonstrates the "bare panic used" anti-pattern.
//!
//! Soroban treats any `panic!` as a contract trap: the transaction fails,
//! but callers (and off-chain indexers) get no structured information
//! about *why*. Typed errors via `panic_with_error!` (or a `Result`
//! return type, as used here) let callers match on a specific error code
//! and let test suites assert on the failure reason instead of a string.

use soroban_sdk::{contracterror, Env};

#[contracterror]
#[derive(Copy, Clone, Debug, Eq, PartialEq, PartialOrd, Ord)]
#[repr(u32)]
pub enum HealthError {
    InsufficientBalance = 1,
    InvalidAmount = 2,
}

const BALANCE: i128 = 1_000_0000000; // toy fixed balance for demonstration

/// GOOD: validates input and returns a typed error instead of panicking.
/// Callers (and tests) can match on `HealthError::InvalidAmount` /
/// `HealthError::InsufficientBalance` directly.
pub fn good_checked_withdraw(_env: &Env, amount: i128) -> Result<i128, HealthError> {
    if amount <= 0 {
        return Err(HealthError::InvalidAmount);
    }
    if amount > BALANCE {
        return Err(HealthError::InsufficientBalance);
    }
    Ok(BALANCE - amount)
}

/// BAD: uses bare `panic!` with string messages for both validation
/// failures. This compiles fine and "works" in the happy path, but on
/// failure the caller only sees a generic trap with no error code to
/// match on — exactly the pattern Soroban Health's scanner flags as
/// `bare_panic_used`.
pub fn bad_unchecked_withdraw(_env: &Env, amount: i128) -> i128 {
    if amount <= 0 {
        panic!("amount must be positive"); // <-- bare panic: flagged by scanner
    }
    if amount > BALANCE {
        panic!("insufficient balance"); // <-- bare panic: flagged by scanner
    }
    BALANCE - amount
}
