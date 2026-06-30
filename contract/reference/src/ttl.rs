//! Demonstrates the "missing TTL extension" anti-pattern.
//!
//! Persistent and temporary storage entries on Soroban have a
//! time-to-live (TTL) measured in ledgers. If an entry's TTL is allowed
//! to expire, it is archived and becomes inaccessible until explicitly
//! restored — a common source of "my data just disappeared" bugs.
//! `extend_ttl` should be called whenever a contract writes data it
//! expects to still be there later.

use soroban_sdk::{Env, Symbol};

// Toy TTL bounds for demonstration purposes. Real contracts should size
// these based on expected access patterns and the network's rent economics.
const MIN_TTL_LEDGERS: u32 = 50;
const EXTEND_TO_LEDGERS: u32 = 100;

/// GOOD: writes the value, then immediately extends its TTL so it won't
/// expire before the next expected access.
pub fn good_persist_with_extension(env: &Env, key: Symbol, value: u64) {
    env.storage().persistent().set(&key, &value);
    env.storage()
        .persistent()
        .extend_ttl(&key, MIN_TTL_LEDGERS, EXTEND_TO_LEDGERS);
}

/// BAD: writes the value but never calls `extend_ttl`. The entry will
/// use whatever default/minimum TTL the network assigns and can expire
/// and be archived without warning — exactly the pattern Soroban Health's
/// scanner flags as `missing_ttl_extension`.
pub fn bad_persist_without_extension(env: &Env, key: Symbol, value: u64) {
    env.storage().persistent().set(&key, &value); // <-- no extend_ttl call after write
}
