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

import re
import tomllib
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


_SDK_CRATE = "soroban-sdk"

# Cargo tables that can carry a version requirement for a crate.
_DEP_TABLES = ("dependencies", "dev-dependencies", "build-dependencies")

_VERSION_RE = re.compile(
    r"^\s*(?P<major>\d+)"
    r"(?:\.(?P<minor>\d+))?"
    r"(?:\.(?P<patch>\d+))?"
    r"(?:-(?P<pre>[0-9A-Za-z.\-]+))?"
    r"(?:\+[0-9A-Za-z.\-]+)?\s*$"
)

_REQ_PART_RE = re.compile(
    r"^\s*(?P<op>\^|~|=|>=|<=|>|<)?\s*(?P<version>[0-9*][0-9A-Za-z.\-+*]*)\s*$"
)

_TOML_DECL_RE = re.compile(rf"^\s*{re.escape(_SDK_CRATE)}\s*=")
_LOCK_DECL_RE = re.compile(rf'^\s*name\s*=\s*"{re.escape(_SDK_CRATE)}"')


def _prerelease_ids(text: str) -> tuple:
    """SemVer pre-release identifiers, as comparable parts: numeric ones
    order numerically and rank below alphanumeric ones (`-2` < `-rc`)."""
    ids = []
    for part in text.split("."):
        if part.isdigit():
            ids.append((0, int(part), ""))
        else:
            ids.append((1, 0, part))
    return tuple(ids)


def _components(text: str) -> tuple[int, int | None, int | None, tuple | None] | None:
    """Split `X[.Y[.Z]][-pre]`, preserving which components were omitted.

    Whether a component was written matters: Cargo reads `~1` as `<2.0.0`
    but `~1.0` as `<1.1.0`, so a missing minor is not an implicit zero.
    """
    match = _VERSION_RE.match(text)
    if match is None:
        return None
    minor, patch, pre = match["minor"], match["patch"], match["pre"]
    return (
        int(match["major"]),
        int(minor) if minor is not None else None,
        int(patch) if patch is not None else None,
        _prerelease_ids(pre) if pre is not None else None,
    )


def _version_key(major: int, minor: int, patch: int, pre: tuple | None) -> tuple:
    """Sortable precedence key. A pre-release ranks below its own release
    (`1.0.0-rc` < `1.0.0`), which the 0/1 flag in position 3 encodes."""
    if pre is None:
        return (major, minor, patch, 1)
    return (major, minor, patch, 0, pre)


def _parse_version(text: str) -> tuple[tuple[int, int, int], tuple] | None:
    """Parse a concrete version into `(base_triple, precedence_key)`.

    Build metadata (`+deadbeef`) is dropped — SemVer gives it no precedence.
    Pre-release tags are kept and ordered, because Cargo treats a
    pre-release as distinct from the release it precedes.
    """
    parsed = _components(text)
    if parsed is None:
        return None
    major, minor, patch, pre = parsed
    base = (major, minor or 0, patch or 0)
    return base, _version_key(base[0], base[1], base[2], pre)


def _parse_part(part: str):
    """Parse one comparator into `(op, major, minor, patch, pre)`.

    Returns the string `"any"` for an unbounded comparator, or None for a
    form this parser does not cover (callers treat None as "can't verify").
    """
    match = _REQ_PART_RE.match(part)
    if match is None:
        return None

    op, raw = match["op"], match["version"]

    if "*" in raw:
        # `1.*` means `>=1.0.0, <2.0.0`; `1.2.*` means `>=1.2.0, <1.3.0`.
        if op not in (None, "^"):
            return None
        trimmed = raw.split("*", 1)[0].rstrip(".")
        if not trimmed:
            return "any"
        parsed = _components(trimmed)
        if parsed is None or parsed[3] is not None:
            return None
        op = "^" if parsed[1] is None else "~"
    else:
        parsed = _components(raw)
        if parsed is None:
            return None
        op = op or "^"  # a bare requirement is a caret requirement

    major, minor, patch, pre = parsed
    return (op, major, minor, patch, pre)


def _part_satisfied(version_key: tuple, comparator: tuple) -> bool:
    op, major, minor, patch, pre = comparator
    floor = _version_key(major, minor or 0, patch or 0, pre)

    if op == ">=":
        return version_key >= floor
    if op == ">":
        return version_key > floor
    if op == "<":
        return version_key < floor
    if op == "<=":
        return version_key <= floor

    def below(major: int, minor: int, patch: int) -> tuple:
        return _version_key(major, minor, patch, None)

    if op == "=":
        if minor is None:
            return floor <= version_key < below(major + 1, 0, 0)
        if patch is None:
            return floor <= version_key < below(major, minor + 1, 0)
        return version_key == floor

    if op == "~":
        if minor is None:
            return floor <= version_key < below(major + 1, 0, 0)
        return floor <= version_key < below(major, minor + 1, 0)

    # Caret: the leftmost non-zero component is what must not change.
    if major > 0:
        return floor <= version_key < below(major + 1, 0, 0)
    if minor is None:
        return floor <= version_key < below(1, 0, 0)
    if minor > 0:
        return floor <= version_key < below(0, minor + 1, 0)
    if patch is None:
        return floor <= version_key < below(0, 1, 0)
    return floor <= version_key < below(0, 0, patch + 1)


def _satisfies(locked: str, requirement: str) -> bool | None:
    """Whether `locked` satisfies a Cargo requirement, which may be a
    comma-separated conjunction (`>=1.2, <1.5`). None means undecidable."""
    parsed = _parse_version(locked)
    if parsed is None:
        return None
    base, version_key = parsed
    is_prerelease = len(version_key) > 4

    satisfied = True
    opts_into_prerelease = False

    for raw_part in requirement.split(","):
        raw_part = raw_part.strip()
        if not raw_part:
            continue
        comparator = _parse_part(raw_part)
        if comparator is None:
            return None
        if comparator == "any":
            continue

        satisfied = satisfied and _part_satisfied(version_key, comparator)

        # Cargo only selects a pre-release when a comparator opts in at the
        # same major.minor.patch: `^21.7.0` does not match `22.0.0-rc.1`,
        # but `^22.0.0-rc.1` matches `22.0.0-rc.2`.
        _, major, minor, patch, pre = comparator
        if pre is not None and (major, minor or 0, patch or 0) == base:
            opts_into_prerelease = True

    if is_prerelease and not opts_into_prerelease:
        return False
    return satisfied


def _declaration_line(source: str, pattern: re.Pattern[str]) -> int:
    for index, line in enumerate(source.splitlines(), start=1):
        if pattern.search(line):
            return index
    return 1


def _load_toml(source: str) -> dict | None:
    """Parse TOML, returning None for malformed input. Repos fetched from
    GitHub are arbitrary, so one unparseable manifest must not fail a scan."""
    try:
        return tomllib.loads(source)
    except tomllib.TOMLDecodeError:
        return None


def _dependency_tables(data: dict):
    for name in _DEP_TABLES:
        table = data.get(name)
        if isinstance(table, dict):
            yield table
    # `[target.'cfg(...)'.dependencies]`
    target = data.get("target")
    if isinstance(target, dict):
        for cfg in target.values():
            if isinstance(cfg, dict):
                for name in _DEP_TABLES:
                    table = cfg.get(name)
                    if isinstance(table, dict):
                        yield table


def _requirement_from_entry(entry) -> str | None:
    """Pull a version requirement out of a dependency entry, which may be a
    bare string or a table. Git and path dependencies carry no requirement
    to check, and `{ workspace = true }` defers to the workspace root."""
    if isinstance(entry, str):
        return entry
    if isinstance(entry, dict):
        version = entry.get("version")
        if isinstance(version, str):
            return version
    return None


def _manifest_requirement(data: dict) -> str | None:
    for table in _dependency_tables(data):
        entry = table.get(_SDK_CRATE)
        if entry is not None:
            requirement = _requirement_from_entry(entry)
            if requirement is not None:
                return requirement
    return None


def _workspace_requirement(data: dict) -> str | None:
    workspace = data.get("workspace")
    if not isinstance(workspace, dict):
        return None
    table = workspace.get("dependencies")
    if not isinstance(table, dict):
        return None
    entry = table.get(_SDK_CRATE)
    return _requirement_from_entry(entry) if entry is not None else None


def check_dependency_version_drift(files: dict[str, str]) -> list[Finding]:
    """Flag a Cargo.lock that resolves soroban-sdk outside what Cargo.toml asks for.

    This is a cross-file check rather than one of `ALL_CHECKS`: it has to
    compare a manifest against a lockfile, while `ALL_CHECKS` runs per-file
    over Rust sources. `scan_file` therefore cannot express it, and callers
    (`scan_source_tree`, `app/api/routes/scans.py`) invoke it separately.

    Drift means *the lockfile violates the requirement*, not that the two
    strings differ. `soroban-sdk = "21.7.0"` is a caret requirement — Cargo
    reads it as `>=21.7.0, <22.0.0` — so resolving to 21.7.7 is correct
    behavior, not drift. Comparing the strings directly (as this check
    originally did) flags every routine patch bump, including this repo's
    own `contract/` workspace.

    Manifests are parsed with `tomllib`, so `{ version = "x", features =
    [...] }` tables, `[dev-dependencies]`, `[target.'cfg(...)'.dependencies]`,
    and workspace inheritance all resolve the way Cargo resolves them
    instead of relying on line-shape heuristics.

    Anything undecidable is silently skipped rather than reported: a git or
    path dependency, a requirement form this parser doesn't cover, or a
    malformed manifest. A false "your dependencies drifted" costs more
    trust than a missed edge case.
    """
    requirement: str | None = None
    requirement_path: str | None = None

    manifests = sorted(path for path in files if path.endswith("Cargo.toml"))

    # A workspace root's `[workspace.dependencies]` is the single source of
    # truth for every member that says `{ workspace = true }`, so it wins.
    # Paths are sorted so the result doesn't depend on dict ordering.
    for path in manifests:
        data = _load_toml(files[path])
        if data is None:
            continue
        found = _workspace_requirement(data)
        if found is not None:
            requirement, requirement_path = found, path
            break

    if requirement is None:
        for path in manifests:
            data = _load_toml(files[path])
            if data is None:
                continue
            found = _manifest_requirement(data)
            if found is not None:
                requirement, requirement_path = found, path
                break

    if requirement is None or requirement_path is None:
        # No concrete requirement anywhere: no soroban-sdk dependency, a
        # git/path dependency, or a workspace member whose root manifest
        # wasn't among the scanned files.
        return []

    locked: list[str] = []
    lock_path: str | None = None
    for path in sorted(p for p in files if p.endswith("Cargo.lock")):
        data = _load_toml(files[path])
        if data is None:
            continue
        packages = data.get("package")
        if not isinstance(packages, list):
            continue
        versions = [
            package["version"]
            for package in packages
            if isinstance(package, dict)
            and package.get("name") == _SDK_CRATE
            and isinstance(package.get("version"), str)
        ]
        if versions:
            locked, lock_path = versions, path
            break

    if not locked or lock_path is None:
        return [
            Finding(
                type=FindingType.DEPENDENCY_VERSION_DRIFT,
                severity=Severity.LOW,
                file=requirement_path,
                line=_declaration_line(files[requirement_path], _TOML_DECL_RE),
                message=(
                    "Cargo.lock is missing or not provided. Cannot verify if the "
                    f"locked {_SDK_CRATE} version matches the pinned "
                    f"requirement ({requirement})."
                ),
            )
        ]

    verdicts = [_satisfies(version, requirement) for version in locked]
    if any(verdict is None for verdict in verdicts):
        return []
    # A lockfile may legitimately carry several majors of one crate; the
    # requirement is met as long as one of them satisfies it.
    if any(verdicts):
        return []

    resolved = ", ".join(f"'{version}'" for version in locked)
    return [
        Finding(
            type=FindingType.DEPENDENCY_VERSION_DRIFT,
            severity=Severity.MEDIUM,
            file=lock_path,
            line=_declaration_line(files[lock_path], _LOCK_DECL_RE),
            message=(
                f"Dependency version drift detected. Cargo.toml requires "
                f"{_SDK_CRATE} '{requirement}', but Cargo.lock resolves it to "
                f"{resolved}, which does not satisfy that requirement."
            ),
        )
    ]


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


def check_wasm_size(
    wasm_size_bytes: int | None,
    threshold_bytes: int = 50 * 1024,
) -> list[Finding]:
    """Checks compiled WASM binary size and flags findings if thresholds are exceeded.

    - Below 50KB: no finding
    - Over 50KB (<= 100KB): MEDIUM severity finding
    - Over 100KB: HIGH severity finding
    """
    if wasm_size_bytes is None:
        return []

    high_threshold = 100 * 1024
    medium_threshold = threshold_bytes

    if wasm_size_bytes > high_threshold:
        size_kb = wasm_size_bytes / 1024
        return [
            Finding(
                type=FindingType.WASM_SIZE_EXCEEDED,
                severity=Severity.HIGH,
                file="<wasm>",
                line=1,
                message=(
                    f"Compiled WASM size of {size_kb:.1f} KB exceeds high threshold of 100 KB. "
                    "Large binaries incur high deploy/storage fees on the Stellar ledger."
                ),
            )
        ]
    elif wasm_size_bytes > medium_threshold:
        size_kb = wasm_size_bytes / 1024
        return [
            Finding(
                type=FindingType.WASM_SIZE_EXCEEDED,
                severity=Severity.MEDIUM,
                file="<wasm>",
                line=1,
                message=(
                    f"Compiled WASM size of {size_kb:.1f} KB exceeds warning threshold of {medium_threshold // 1024} KB. "
                    "Consider optimizing binary size using wasm-opt or cargo-contract."
                ),
            )
        ]

    return []

