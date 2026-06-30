# Contributing to Soroban Health

Thanks for considering a contribution. This project is part of the Stellar open-source ecosystem and welcomes contributors of all experience levels — many issues are scoped to be completed in a single sitting.

## Ground rules

- Be respectful and constructive in issues, PRs, and reviews.
- Open an issue before starting non-trivial work, so we can align on approach before you invest time.
- Keep PRs focused — one logical change per PR is easier to review and merge quickly.

## Workflow

1. **Fork** the repository and clone your fork.
2. **Create a branch** off `main`: `git checkout -b fix/short-description`.
3. **Make your change.** Follow the existing code style in the relevant folder:
   - Rust: `cargo fmt` and `cargo clippy` must pass.
   - Python: `ruff` and `black` must pass.
   - TypeScript: `eslint` and `prettier` must pass.
4. **Add or update tests** for any behavior change. PRs without tests for new logic will be asked to add them.
5. **Run the test suite locally** before opening a PR:
   ```bash
   # contract
   cd contract && cargo test

   # backend
   cd backend && pytest

   # frontend
   cd frontend && npm test
   ```
6. **Open a Pull Request** against `main`. Reference the issue number (e.g. `Closes #12`) in the description.
7. A maintainer will review, may request changes, and will merge once it meets project standards.

## Picking an issue

- Issues labeled `good first issue` are scoped for newcomers to the codebase.
- Issues labeled `help wanted` are open and unassigned — comment to claim one before starting.
- If you're contributing via a Drips Wave or GrantFox cycle, please still follow this same PR flow; the bounty tracking happens automatically once your PR is merged and the issue is marked resolved.

## Reporting bugs / requesting features

Please use the issue templates under `.github/ISSUE_TEMPLATE/` — they make sure we have what we need to respond quickly.

## Code of Conduct

This project follows the [Code of Conduct](CODE_OF_CONDUCT.md). By participating, you agree to uphold it.
