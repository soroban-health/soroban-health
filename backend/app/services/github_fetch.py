"""Fetches a public GitHub repo's Rust/Cargo source over the GitHub REST API
(the tarball endpoint), rather than shelling out to `git clone`. This avoids
a `git` binary dependency and the argument-injection surface of building a
shell command around a user-supplied `repo_url`; parsing the URL into
owner/repo/ref via a strict whitelist regex and only ever using those
parsed, validated pieces to build our own GitHub API URL means there is no
untrusted string reaching a shell or being interpolated into anything
unsafe.

Scoped to github.com specifically, matching the issue this implements
("GitHub integration") — not a generic git-hosting client.
"""

from __future__ import annotations

import gzip
import io
import re
import tarfile
from dataclasses import dataclass

import httpx

GITHUB_API_BASE = "https://api.github.com"

# Caps that bound memory/time spent on a single scan request. Each is
# enforced independently and as early as possible — see fetch_repo_files.
MAX_TARBALL_BYTES = 25 * 1024 * 1024  # compressed download cap
MAX_DECOMPRESSED_BYTES = 150 * 1024 * 1024  # cap on bytes read out of gzip
MAX_FILES = 3000  # cap on matching files kept

FETCH_TIMEOUT = httpx.Timeout(10.0, connect=5.0)

_GITHUB_REPO_URL_RE = re.compile(
    r"^https?://github\.com/"
    r"(?P<owner>[A-Za-z0-9][A-Za-z0-9-]{0,38})/"
    r"(?P<repo>[A-Za-z0-9._-]+?)"
    r"(?:\.git)?"
    r"(?:/tree/(?P<ref>[A-Za-z0-9._/-]+))?"
    r"/?$"
)


@dataclass(frozen=True)
class ParsedGitHubRepo:
    owner: str
    repo: str
    ref: str | None


class GitHubFetchError(Exception):
    """Base class for repo-fetch failures; the route layer (see
    app/api/routes/scans.py) maps each subclass below to a specific HTTP
    status."""


class InvalidRepoUrlError(GitHubFetchError):
    pass


class RepoNotFoundError(GitHubFetchError):
    pass


class RepoFetchTimeoutError(GitHubFetchError):
    pass


class RepoTooLargeError(GitHubFetchError):
    def __init__(self, limit_bytes: int) -> None:
        super().__init__(
            f"Repository exceeds the {limit_bytes // (1024 * 1024)}MB fetch/decompression cap"
        )
        self.limit_bytes = limit_bytes


class TooManyFilesError(GitHubFetchError):
    def __init__(self, limit: int) -> None:
        super().__init__(f"Repository has more than {limit} scannable files")
        self.limit = limit


class NoScannableFilesError(GitHubFetchError):
    pass


def parse_github_repo_url(repo_url: str) -> ParsedGitHubRepo:
    match = _GITHUB_REPO_URL_RE.match(repo_url.strip())
    if not match:
        raise InvalidRepoUrlError(
            "repo_url must be a github.com repository URL, e.g. "
            "https://github.com/owner/repo (optionally with a trailing "
            "'.git', '/', or '/tree/<branch>')"
        )
    return ParsedGitHubRepo(
        owner=match.group("owner"), repo=match.group("repo"), ref=match.group("ref")
    )


class _CappedReader:
    """Wraps a binary stream and raises RepoTooLargeError once more than
    `limit` bytes have been read from it, cumulatively. This is the actual
    zip-bomb defense: tarfile must decompress every byte to walk from one
    header to the next, even for members it discards, so the cap has to
    live at this layer, not just on the files kept."""

    def __init__(self, fileobj, limit: int) -> None:
        self._fileobj = fileobj
        self._limit = limit
        self._read = 0

    def read(self, size: int = -1) -> bytes:
        chunk = self._fileobj.read(size)
        self._read += len(chunk)
        if self._read > self._limit:
            raise RepoTooLargeError(self._limit)
        return chunk


def _is_scannable(rel_path: str) -> bool:
    return rel_path.endswith(".rs") or rel_path.rsplit("/", 1)[-1] in (
        "Cargo.toml",
        "Cargo.lock",
    )


def _download_tarball(url: str, client: httpx.Client) -> bytes:
    buffer = bytearray()
    try:
        with client.stream("GET", url, timeout=FETCH_TIMEOUT) as response:
            if response.status_code == 404:
                raise RepoNotFoundError(url)
            response.raise_for_status()
            for chunk in response.iter_bytes():
                buffer.extend(chunk)
                if len(buffer) > MAX_TARBALL_BYTES:
                    raise RepoTooLargeError(MAX_TARBALL_BYTES)
    except httpx.TimeoutException as exc:
        raise RepoFetchTimeoutError(url) from exc
    except httpx.HTTPStatusError as exc:
        raise GitHubFetchError(
            f"GitHub returned {exc.response.status_code} fetching {url}"
        ) from exc
    return bytes(buffer)


def _extract_scannable_files(tarball_bytes: bytes) -> dict[str, str]:
    files: dict[str, str] = {}
    gz = gzip.GzipFile(fileobj=io.BytesIO(tarball_bytes))
    capped = _CappedReader(gz, MAX_DECOMPRESSED_BYTES)
    try:
        with tarfile.open(fileobj=capped, mode="r|") as tar:
            for member in tar:
                if not member.isfile():
                    continue
                # Strip the tarball's single top-level "<owner>-<repo>-<sha>/"
                # directory prefix.
                parts = member.name.split("/", 1)
                if len(parts) != 2:
                    continue
                rel_path = parts[1]
                if not _is_scannable(rel_path):
                    continue
                extracted = tar.extractfile(member)
                if extracted is None:
                    continue
                files[rel_path] = extracted.read().decode("utf-8", errors="replace")
                if len(files) > MAX_FILES:
                    raise TooManyFilesError(MAX_FILES)
    except tarfile.TarError as exc:
        raise GitHubFetchError(f"Could not read repository archive: {exc}") from exc
    return files


def fetch_repo_files(repo: ParsedGitHubRepo, client: httpx.Client) -> dict[str, str]:
    """Fetch a public GitHub repo's tarball and return its .rs/Cargo.toml/
    Cargo.lock files as {relative_path: contents}, in the same shape
    check_dependency_version_drift/scan_file already consume."""
    ref_segment = f"/{repo.ref}" if repo.ref else ""
    url = f"{GITHUB_API_BASE}/repos/{repo.owner}/{repo.repo}/tarball{ref_segment}"

    files = _extract_scannable_files(_download_tarball(url, client))
    if not files:
        raise NoScannableFilesError(f"{repo.owner}/{repo.repo}")
    return files
