"""Tests for github_fetch, exercised against a real (not mocked) gzip tar
archive shaped like GitHub's tarball-endpoint response, via httpx.MockTransport
so no real network call happens."""

import httpx
import pytest

from app.services import github_fetch
from app.services.github_fetch import (
    GitHubFetchError,
    InvalidRepoUrlError,
    NoScannableFilesError,
    ParsedGitHubRepo,
    RepoFetchTimeoutError,
    RepoNotFoundError,
    RepoTooLargeError,
    TooManyFilesError,
    fetch_repo_files,
    parse_github_repo_url,
)
from tests.conftest import _make_tarball

VALID_URLS = [
    "https://github.com/owner/repo",
    "https://github.com/owner/repo/",
    "https://github.com/owner/repo.git",
    "http://github.com/owner/repo",
    "https://github.com/owner/repo/tree/main",
    "https://github.com/owner/repo/tree/feature/foo",
]

INVALID_URLS = [
    "https://gitlab.com/owner/repo",
    "https://github.com/owner",
    "https://github.com/owner/repo/blob/main/README.md",
    "https://github.com/owner/repo/issues/1",
    "not a url",
    "",
]


@pytest.mark.parametrize("url", VALID_URLS)
def test_parse_github_repo_url_accepts_valid_forms(url):
    parsed = parse_github_repo_url(url)
    assert parsed.owner == "owner"
    assert parsed.repo == "repo"


def test_parse_github_repo_url_extracts_ref():
    assert (
        parse_github_repo_url("https://github.com/owner/repo/tree/main").ref == "main"
    )
    assert (
        parse_github_repo_url("https://github.com/owner/repo/tree/feature/foo").ref
        == "feature/foo"
    )
    assert parse_github_repo_url("https://github.com/owner/repo").ref is None


@pytest.mark.parametrize("url", INVALID_URLS)
def test_parse_github_repo_url_rejects_invalid_forms(url):
    with pytest.raises(InvalidRepoUrlError):
        parse_github_repo_url(url)


def _client_with_handler(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_fetch_repo_files_happy_path():
    tarball = _make_tarball(
        {
            "lib.rs": b"pub fn f() {}",
            "Cargo.toml": b'[package]\nname = "x"',
            "README.md": b"not scannable",
            "nested/dir/other.rs": b"pub fn g() {}",
        }
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=tarball)

    client = _client_with_handler(handler)
    files = fetch_repo_files(ParsedGitHubRepo("owner", "repo", None), client)

    assert set(files) == {"lib.rs", "Cargo.toml", "nested/dir/other.rs"}
    assert files["lib.rs"] == "pub fn f() {}"


def test_fetch_repo_files_not_found():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404)

    client = _client_with_handler(handler)
    with pytest.raises(RepoNotFoundError):
        fetch_repo_files(ParsedGitHubRepo("owner", "missing", None), client)


def test_fetch_repo_files_timeout():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("timed out")

    client = _client_with_handler(handler)
    with pytest.raises(RepoFetchTimeoutError):
        fetch_repo_files(ParsedGitHubRepo("owner", "repo", None), client)


def test_fetch_repo_files_no_scannable_files():
    tarball = _make_tarball({"README.md": b"nothing to scan here"})

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=tarball)

    client = _client_with_handler(handler)
    with pytest.raises(NoScannableFilesError):
        fetch_repo_files(ParsedGitHubRepo("owner", "repo", None), client)


def test_fetch_repo_files_enforces_tarball_size_cap(monkeypatch):
    tarball = _make_tarball({"lib.rs": b"pub fn f() {}" * 100})
    monkeypatch.setattr(github_fetch, "MAX_TARBALL_BYTES", 10)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=tarball)

    client = _client_with_handler(handler)
    with pytest.raises(RepoTooLargeError):
        fetch_repo_files(ParsedGitHubRepo("owner", "repo", None), client)


def test_fetch_repo_files_enforces_decompressed_size_cap(monkeypatch):
    tarball = _make_tarball({"lib.rs": b"pub fn f() {}" * 100})
    monkeypatch.setattr(github_fetch, "MAX_DECOMPRESSED_BYTES", 10)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=tarball)

    client = _client_with_handler(handler)
    with pytest.raises(RepoTooLargeError):
        fetch_repo_files(ParsedGitHubRepo("owner", "repo", None), client)


def test_fetch_repo_files_enforces_max_files_cap(monkeypatch):
    tarball = _make_tarball({"a.rs": b"1", "b.rs": b"2", "c.rs": b"3"})
    monkeypatch.setattr(github_fetch, "MAX_FILES", 1)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=tarball)

    client = _client_with_handler(handler)
    with pytest.raises(TooManyFilesError):
        fetch_repo_files(ParsedGitHubRepo("owner", "repo", None), client)


def test_fetch_repo_files_wraps_other_http_errors():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    client = _client_with_handler(handler)
    with pytest.raises(GitHubFetchError):
        fetch_repo_files(ParsedGitHubRepo("owner", "repo", None), client)


def test_fetch_repo_files_uses_ref_in_url():
    captured_urls = []
    tarball = _make_tarball({"lib.rs": b"pub fn f() {}"})

    def handler(request: httpx.Request) -> httpx.Response:
        captured_urls.append(str(request.url))
        return httpx.Response(200, content=tarball)

    client = _client_with_handler(handler)
    fetch_repo_files(ParsedGitHubRepo("owner", "repo", "v1.0.0"), client)

    assert captured_urls == ["https://api.github.com/repos/owner/repo/tarball/v1.0.0"]
