"""Lightweight static analysis for known Soroban anti-patterns.

This is intentionally a regex/line-scan based checker rather than a full
Rust AST parser (e.g. via `syn`). That's a deliberate v0 scope decision:
it ships something useful immediately and is honest about being heuristic
rather than exhaustive. A natural "good first issue" / "medium" upgrade
path is swapping this for an AST-based pass — see the open issues.

Each check below returns zero or more `Finding`s for a single file's
source text. `scan_source_tree` aggregates across a directory of `.rs`
files.
"""

from __future__ import annotations

import re
from pathlib import Path

from app.models.scan import Finding, FindingType, Severity

# A bare `panic!(...)` or `panic!("...")`, but NOT `panic_with_error!(...)`.
_BARE_PANIC_RE = re.compile(r"(?<!_with_error)\bpanic!\s*\(")

# A `.set(...)` on persistent storage not immediately followed (within a
# few lines) by a call to `.extend_ttl(`. This is a heuristic, not a
# guarantee — see module docstring.
_PERSISTENT_SET_RE = re.compile(r"\.storage\(\)\.persistent\(\)\.set\(")
_EXTEND_TTL_RE = re.compile(r"\.extend_ttl\(")

# A `.push_back(` / `.push(` call inside a function body that has no
# nearby `.len()` comparison or `.remove(` eviction call. Heuristic.
_PUSH_RE = re.compile(r"\.(push_back|push)\(")
_LEN_GUARD_RE = re.compile(r"\.len\(\)\s*(>=|>)\s*\w+")
_EVICT_RE = re.compile(r"\.remove\(")

_LOOKAROUND_WINDOW = 5  # lines to look before/after a hit when checking context


def _lines_with_context(lines: list[str], idx: int, window: int) -> list[str]:
    start = max(0, idx - window)
    end = min(len(lines), idx + window + 1)
    return lines[start:end]


def check_bare_panic(file_path: str, source: str) -> list[Finding]:
    findings: list[Finding] = []
    for i, line in enumerate(source.splitlines(), start=1):
        if _BARE_PANIC_RE.search(line):
            findings.append(
                Finding(
                    type=FindingType.BARE_PANIC_USED,
                    severity=Severity.MEDIUM,
                    file=file_path,
                    line=i,
                    message=(
                        "Bare `panic!` used instead of a typed error "
                        "(`panic_with_error!` or a `Result<_, E>` return). "
                        "Callers cannot match on a specific error code."
                    ),
                )
            )
    return findings


def check_missing_ttl_extension(file_path: str, source: str) -> list[Finding]:
    findings: list[Finding] = []
    lines = source.splitlines()
    for i, line in enumerate(lines):
        if _PERSISTENT_SET_RE.search(line):
            context = _lines_with_context(lines, i, _LOOKAROUND_WINDOW)
            if not any(_EXTEND_TTL_RE.search(ctx_line) for ctx_line in context):
                findings.append(
                    Finding(
                        type=FindingType.MISSING_TTL_EXTENSION,
                        severity=Severity.HIGH,
                        file=file_path,
                        line=i + 1,
                        message=(
                            "Persistent storage write with no nearby "
                            "`extend_ttl` call. This entry may expire and "
                            "be archived earlier than expected."
                        ),
                    )
                )
    return findings


def check_unbounded_growth(file_path: str, source: str) -> list[Finding]:
    findings: list[Finding] = []
    lines = source.splitlines()
    for i, line in enumerate(lines):
        if _PUSH_RE.search(line):
            context = _lines_with_context(lines, i, _LOOKAROUND_WINDOW)
            has_guard = any(_LEN_GUARD_RE.search(c) for c in context)
            has_evict = any(_EVICT_RE.search(c) for c in context)
            if not (has_guard and has_evict):
                findings.append(
                    Finding(
                        type=FindingType.UNBOUNDED_STORAGE_GROWTH,
                        severity=Severity.HIGH,
                        file=file_path,
                        line=i + 1,
                        message=(
                            "Collection append with no nearby length cap + "
                            "eviction. Storage may grow without bound as "
                            "the contract is used."
                        ),
                    )
                )
    return findings


ALL_CHECKS = (check_bare_panic, check_missing_ttl_extension, check_unbounded_growth)


def check_dependency_version_drift(files: dict[str, str]) -> list[Finding]:
    """Check if the pinned soroban-sdk version matches the locked version.
    
    This requires cross-referencing Cargo.toml (where the version is pinned)
    with Cargo.lock (where the exact version is locked). Since Cargo.lock is
    often .gitignored, we handle its absence gracefully.
    """
    toml_version = None
    toml_file_path = None
    lock_version = None
    lock_file_path = None

    # First, find the pinned version in any Cargo.toml
    for file_path, source in files.items():
        if file_path.endswith("Cargo.toml"):
            for line in source.splitlines():
                line = line.strip()
                if line.startswith("soroban-sdk =") or line.startswith("soroban-sdk="):
                    val = line.split("=", 1)[1].strip()
                    if val.startswith('"'):
                        toml_version = val.strip('"')
                        toml_file_path = file_path
                        break
                    elif val.startswith('{'):
                        import re
                        m = re.search(r'version\s*=\s*"([^"]+)"', val)
                        if m:
                            toml_version = m.group(1)
                            toml_file_path = file_path
                            break
            if toml_version:
                break

    # If we couldn't find a concrete pinned version, we can't check for drift
    if not toml_version:
        return []

    # Next, look for a Cargo.lock file and extract the locked version
    for file_path, source in files.items():
        if file_path.endswith("Cargo.lock"):
            import re
            blocks = source.split('[[package]]')
            for block in blocks:
                if 'name = "soroban-sdk"' in block:
                    m = re.search(r'version\s*=\s*"([^"]+)"', block)
                    if m:
                        lock_version = m.group(1)
                        lock_file_path = file_path
                        break
            if lock_version:
                break

    if not lock_version:
        return [
            Finding(
                type=FindingType.DEPENDENCY_VERSION_DRIFT,
                severity=Severity.LOW,
                file=toml_file_path or "Cargo.toml",
                line=1,
                message=(
                    "Cargo.lock is missing or not provided. Cannot verify if the "
                    f"locked soroban-sdk version matches the pinned version ({toml_version})."
                ),
            )
        ]

    if toml_version != lock_version:
        return [
            Finding(
                type=FindingType.DEPENDENCY_VERSION_DRIFT,
                severity=Severity.MEDIUM,
                file=lock_file_path or "Cargo.lock",
                line=1,
                message=(
                    f"Dependency version drift detected. Cargo.toml pins soroban-sdk to "
                    f"'{toml_version}', but Cargo.lock resolves it to '{lock_version}'."
                ),
            )
        ]

    return []

def scan_file(file_path: str, source: str) -> list[Finding]:
    findings: list[Finding] = []
    for check in ALL_CHECKS:
        findings.extend(check(file_path, source))
    return findings


def scan_source_tree(root: Path) -> list[Finding]:
    """Scan every relevant file under `root` and return aggregated findings."""
    findings: list[Finding] = []
    
    # We need to collect all files for cross-file checks like dependency drift
    all_files: dict[str, str] = {}
    
    for file_path in sorted(root.rglob("*")):
        if file_path.is_file() and (file_path.suffix == ".rs" or file_path.name in ("Cargo.toml", "Cargo.lock")):
            try:
                source = file_path.read_text(encoding="utf-8", errors="replace")
                all_files[str(file_path.relative_to(root))] = source
            except Exception:
                pass

    # Run per-file checks on .rs files
    for path, source in all_files.items():
        if path.endswith(".rs"):
            findings.extend(scan_file(path, source))
            
    # Run cross-file checks
    findings.extend(check_dependency_version_drift(all_files))
            
    return findings
