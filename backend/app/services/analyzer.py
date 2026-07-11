"""Static analysis for known Soroban anti-patterns, backed by a
`tree-sitter-rust` parse of the actual Rust AST rather than the previous
regex/line-window heuristics.

Each check below still returns zero or more `Finding`s for a single file's
source text, and `ALL_CHECKS`/`scan_file`/`scan_source_tree` are unchanged —
only *how* a hit is located changed (real AST nodes instead of scanning
source lines), so a `push_back` or `panic!` mentioned inside a comment or
string literal can no longer be misflagged.

"Nearby" (e.g. does a `.set()` have an `extend_ttl()` call to go with it)
now means *the enclosing function*, not a fixed line window — this also
fixes a false negative the old heuristic had: two short functions sitting
close together (common inside a `#[contractimpl] impl Contract { ... }`
block) could have an unrelated call in the next function satisfy the
window, hiding a real finding. The tradeoff: a TTL/eviction call that lives
in a sibling helper function (not the same `function_item`) still won't be
picked up — that's a call-graph analysis problem, out of scope here.
"""

from __future__ import annotations

from pathlib import Path

import tree_sitter_rust as tsrust
from tree_sitter import Language, Node, Parser, Query, QueryCursor

from app.models.scan import Finding, FindingType, Severity

_LANGUAGE = Language(tsrust.language())
_PARSER = Parser(_LANGUAGE)

_MACRO_INVOCATION_QUERY = Query(
    _LANGUAGE, "(macro_invocation macro: (identifier) @name)"
)

_METHOD_CALL_QUERY = Query(
    _LANGUAGE,
    "(call_expression function: (field_expression field: (field_identifier) @method))",
)

# Matches `<something>.persistent().set(...)` regardless of what precedes
# `.persistent()` (usually `env.storage()`).
_PERSISTENT_SET_QUERY = Query(
    _LANGUAGE,
    """
    (call_expression
      function: (field_expression
        value: (call_expression
          function: (field_expression field: (field_identifier) @receiver))
        field: (field_identifier) @method))
    """,
)

# Matches `<something>.len() >= X` / `<something>.len() > X`.
_LEN_COMPARISON_QUERY = Query(
    _LANGUAGE,
    """
    (binary_expression
      left: (call_expression function: (field_expression field: (field_identifier) @len_field))
      operator: _ @op
      right: (_))
    """,
)


def _parse(source: str) -> Node:
    return _PARSER.parse(source.encode("utf-8")).root_node


def _text(node: Node) -> str:
    return node.text.decode("utf-8") if node.text is not None else ""


def _enclosing_function(node: Node) -> Node | None:
    current = node.parent
    while current is not None and current.type != "function_item":
        current = current.parent
    return current


def _method_names_in(scope: Node) -> set[str]:
    names: set[str] = set()
    for _, captures in QueryCursor(_METHOD_CALL_QUERY).matches(scope):
        for method_node in captures.get("method", []):
            names.add(_text(method_node))
    return names


def _has_len_guard(scope: Node) -> bool:
    for _, captures in QueryCursor(_LEN_COMPARISON_QUERY).matches(scope):
        if _text(captures["op"][0]) in (">=", ">"):
            return True
    return False


def check_bare_panic(file_path: str, source: str) -> list[Finding]:
    root = _parse(source)
    findings: list[Finding] = []
    for _, captures in QueryCursor(_MACRO_INVOCATION_QUERY).matches(root):
        name_node = captures["name"][0]
        if _text(name_node) != "panic":
            continue
        findings.append(
            Finding(
                type=FindingType.BARE_PANIC_USED,
                severity=Severity.MEDIUM,
                file=file_path,
                line=name_node.start_point[0] + 1,
                message=(
                    "Bare `panic!` used instead of a typed error "
                    "(`panic_with_error!` or a `Result<_, E>` return). "
                    "Callers cannot match on a specific error code."
                ),
            )
        )
    return findings


def check_missing_ttl_extension(file_path: str, source: str) -> list[Finding]:
    root = _parse(source)
    findings: list[Finding] = []
    for _, captures in QueryCursor(_PERSISTENT_SET_QUERY).matches(root):
        method_node = captures["method"][0]
        receiver_node = captures["receiver"][0]
        if _text(method_node) != "set" or _text(receiver_node) != "persistent":
            continue
        enclosing = _enclosing_function(method_node)
        if enclosing is not None and "extend_ttl" in _method_names_in(enclosing):
            continue
        findings.append(
            Finding(
                type=FindingType.MISSING_TTL_EXTENSION,
                severity=Severity.HIGH,
                file=file_path,
                line=method_node.start_point[0] + 1,
                message=(
                    "Persistent storage write with no `extend_ttl` call in "
                    "the same function. This entry may expire and be "
                    "archived earlier than expected."
                ),
            )
        )
    return findings


def check_unbounded_growth(file_path: str, source: str) -> list[Finding]:
    root = _parse(source)
    findings: list[Finding] = []
    for _, captures in QueryCursor(_METHOD_CALL_QUERY).matches(root):
        method_node = captures["method"][0]
        if _text(method_node) not in ("push_back", "push"):
            continue
        enclosing = _enclosing_function(method_node)
        if enclosing is None:
            continue
        names = _method_names_in(enclosing)
        if "remove" in names and _has_len_guard(enclosing):
            continue
        findings.append(
            Finding(
                type=FindingType.UNBOUNDED_STORAGE_GROWTH,
                severity=Severity.HIGH,
                file=file_path,
                line=method_node.start_point[0] + 1,
                message=(
                    "Collection append with no length cap + eviction in "
                    "the same function. Storage may grow without bound as "
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
                    elif val.startswith("{"):
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

            blocks = source.split("[[package]]")
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
        if file_path.is_file() and (
            file_path.suffix == ".rs" or file_path.name in ("Cargo.toml", "Cargo.lock")
        ):
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
