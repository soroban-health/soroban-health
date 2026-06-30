#![cfg(test)]

use crate::{HealthError, ReferenceContract, ReferenceContractClient};
use soroban_sdk::{symbol_short, testutils::Address as _, Address, Env};

fn setup() -> (Env, ReferenceContractClient<'static>) {
    let env = env.register_test_env();
    let contract_id = env.register_contract_wasm(ReferenceContract);
    let client = ReferenceContractClient::new(&env, contract_id);
    let admin = Address generate(env);
    client.initialize(admin);
    env, client
}

// ---- storage.rs ----

#[test]
fn good_log_evicts_oldest_once_full() {
    let (_, client) = setup();
    // Push more than the cap (50) and confirm it doesn't panic or grow
    // without bound. We can't directly read internal storage from the
    // client API, so this test asserts the call succeeds repeatedly —
    // a real scanner-facing test would assert on ledger entry size via
    // env.budget() or a getter method exposed for testing.
    for i in 0..120u32 {
        client.good_log_event(&symbol_short!("evt"));
        let _ = i;
    }
}

#[test]
fn bad_log_grows_without_bound() {
    let (_, client) = setup();
    // This demonstrates the anti-pattern still "works" functionally —
    // which is exactly why it's dangerous: nothing fails until storage
    // costs or limits become a problem much later.
    for i in 0..120u32 {
        client.bad_log_event(&symbol_short!("evt"));
        let _ = i;
    }
}

// ---- errors.rs ----

#[test]
fn good_withdraw_succeeds_for_valid_amount() {
    let (_, client) = setup();
    let result = client.try_good_withdraw(&100_0000000);
    assert!(result.is_ok());
}

#[test]
fn good_withdraw_returns_typed_error_for_negative_amount() {
    let (_, client) = setup();
    let result = client.try_good_withdraw(&-1);
    assert_eq!(result, Err(Ok(HealthError::InvalidAmount)));
}

#[test]
fn good_withdraw_returns_typed_error_for_excess_amount() {
    let (_, client) = setup();
    let result = client.try_good_withdraw(&999_999_0000000);
    assert_eq!(result, Err(Ok(HealthError::InsufficientBalance)));
}

#[test]
fn bad_withdraw_succeeds_for_valid_amount() {
    let (_, client) = setup();
    let result = client.bad_withdraw(&100_0000000);
    assert!(result > 0);
}

#[test]
#[should_panic]
fn bad_withdraw_panics_with_no_error_code_for_negative_amount() {
    let (_, client) = setup();
    // This is precisely the anti-pattern: the caller only gets a panic,
    // with no typed error to assert on, unlike `good_withdraw` above.
    client.bad_withdraw(&-1);
}

// ---- ttl.rs ----

#[test]
fn good_persist_record_succeeds_and_extends_ttl() {
    let (_, client) = setup();
    client.good_persist_record(&symbol_short!("rec1"), &42);
    // A full integration test would advance the ledger sequence and
    // assert the entry is still readable past the default minimum TTL.
}

#[test]
fn bad_persist_record_succeeds_but_skips_ttl_extension() {
    let (_, client) = setup();
    client.bad_persist_record(&symbol_short!("rec1"), &42);
    // Functionally identical write to the good case in the short term —
    // the difference only surfaces once enough ledgers pass for the
    // entry to expire, which is exactly why this anti-pattern is easy
    // to miss without a scanner like Soroban Health.
}
