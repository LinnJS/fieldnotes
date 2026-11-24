"""A small typed client for the parts of the GitHub REST API that the library reads.

The client answers four questions about an upstream repository: what its default branch is, which
commit a branch points at, which files a commit holds, and what one of those files says. Every
answer is read at an explicit branch or commit, so a caller can tie what it records to a commit.

The function that performs the HTTP request is a parameter. Commands pass nothing and get
``fetch_with_urllib``. Tests pass a function that returns recorded responses, so they run offline.

A token is optional. When one is given it is sent as a bearer credential and appears in no error
message and no representation of the client.
"""

import http.client
import json
import os
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from urllib.parse import quote

__all__ = [
    "API_ROOT",
    "API_VERSION",
    "Fetch",
    "GitHubClient",
    "NotFoundError",
    "RateLimitedError",
    "Repository",
    "Response",
    "TreeEntry",
    "UpstreamError",
    "fetch_with_urllib",
    "token_from_environment",
]

API_ROOT = "https://api.github.com"
API_VERSION = "2022-11-28"
USER_AGENT = "resource-library-tools"
TOKEN_VARIABLES = ("GITHUB_TOKEN", "GH_TOKEN")
TIMEOUT_SECONDS = 30

_JSON = "application/vnd.github+json"
_RAW = "application/vnd.github.raw+json"


class UpstreamError(Exception):
    """GitHub could not be reached or gave an answer the client cannot use."""


class NotFoundError(UpstreamError):
    """GitHub answered 404 for a repository, or for a branch, commit, or path inside it.

    Attributes:
        repository: The repository that was asked about, as ``owner/name``.
    """

    def __init__(self, repository: str, what: str) -> None:
        """Build the error.

        Args:
            repository: The repository that was asked about, as ``owner/name``.
            what: What was asked for, with the repository named in it.
        """
        self.repository = repository
        super().__init__(
            f"GitHub found nothing for {what}. Check the owner/name spelling. "
            "A private repository also answers this way when no token with access is set."
        )


class RateLimitedError(UpstreamError):
    """GitHub refused the request because the rate limit is used up.

    Attributes:
        reset_at: When GitHub will accept requests again, in UTC.
    """

    def __init__(self, reset_at: datetime) -> None:
        """Build the error."""
        self.reset_at = reset_at
        super().__init__(
            f"The GitHub rate limit is used up until {reset_at.isoformat()}. Wait until then, "
            f"or set {TOKEN_VARIABLES[0]} or {TOKEN_VARIABLES[1]} for the higher limit."
        )


@dataclass(frozen=True)
class Response:
    """One HTTP response.

    Attributes:
        status: The HTTP status code.
        headers: The response headers with lowercase names.
        body: The response body.
    """

    status: int
    headers: Mapping[str, str]
    body: bytes


type Fetch = Callable[[str, Mapping[str, str]], Response]
"""Performs one GET request. It takes the URL and the request headers.

It returns the response for every HTTP status, including 4xx and 5xx, and raises
``UpstreamError`` only when no response arrives.
"""


@dataclass(frozen=True)
class Repository:
    """What the client reads from a repository's metadata.

    Attributes:
        full_name: The repository as ``owner/name``, spelled the way GitHub spells it.
        default_branch: The branch the repository publishes on.
    """

    full_name: str
    default_branch: str


@dataclass(frozen=True)
class TreeEntry:
    """One file in a commit's tree.

    Attributes:
        path: Path of the file from the repository root.
        blob_sha: Git blob id of the file's content.
        size: Size of the file in bytes.
    """

    path: str
    blob_sha: str
    size: int


def fetch_with_urllib(url: str, headers: Mapping[str, str]) -> Response:
    """Perform one GET request over the network.

    Args:
        url: The URL to request.
        headers: The request headers. An ``Authorization`` header is not sent on after a
            redirect.

    Returns:
        The response, whatever its HTTP status.

    Raises:
        UpstreamError: No complete response arrived, for example because the network is down,
            the connection was reset, or the body was cut short.
    """
    # urllib copies the ordinary headers of a request onto the request that follows a redirect,
    # to whatever host it names. The token goes only to the address that was asked for.
    ordinary = {name: value for name, value in headers.items() if name.lower() != "authorization"}
    request = urllib.request.Request(url, headers=ordinary, method="GET")
    for name, value in headers.items():
        if name.lower() == "authorization":
            request.add_unredirected_header(name, value)
    try:
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as reply:
                return Response(reply.status, _lowercase(reply.headers.items()), reply.read())
        except urllib.error.HTTPError as error:
            return Response(error.code, _lowercase(error.headers.items()), error.read())
    # urllib wraps only a failure to send the request in URLError, which is an OSError, as a
    # timeout is. A reset connection or a body cut short while the answer is read arrives as a
    # plain OSError or an HTTPException, and reading the body of an error answer can fail the
    # same way, so that read sits inside this handler too.
    except (OSError, http.client.HTTPException) as error:
        raise UpstreamError(
            f"GitHub could not be reached, or its answer did not arrive whole: {error}. "
            "Check the network connection and try again."
        ) from error


def token_from_environment(environ: Mapping[str, str] | None = None) -> str | None:
    """Return the GitHub token set in the environment, if any.

    ``GITHUB_TOKEN`` is read first and ``GH_TOKEN`` second. An empty value counts as unset.

    Args:
        environ: The environment to read. The process environment is used when it is omitted.

    Returns:
        The token, or ``None`` when neither variable holds one.
    """
    source = os.environ if environ is None else environ
    for variable in TOKEN_VARIABLES:
        token = source.get(variable)
        if token:
            return token
    return None


class GitHubClient:
    """Reads repositories through the GitHub REST API.

    Every method raises ``NotFoundError`` when GitHub answers 404, ``RateLimitedError`` when the
    rate limit is used up, and ``UpstreamError`` for any other failure.
    """

    __slots__ = ("_fetch", "_token")

    def __init__(self, fetch: Fetch = fetch_with_urllib, token: str | None = None) -> None:
        """Build a client.

        Args:
            fetch: The function that performs each request.
            token: A GitHub token, or ``None`` to make unauthenticated requests.
        """
        self._fetch = fetch
        self._token = token

    def repository(self, repository: str) -> Repository:
        """Read a repository's metadata.

        Args:
            repository: The repository as ``owner/name``.

        Returns:
            The repository's canonical name and default branch.
        """
        data = self._json(repository, "", f"the repository {repository}")
        return Repository(
            full_name=_text(data, "full_name"),
            default_branch=_text(data, "default_branch"),
        )

    def branch_head(self, repository: str, branch: str) -> str:
        """Read the commit a branch points at.

        Args:
            repository: The repository as ``owner/name``.
            branch: The branch name.

        Returns:
            The full commit SHA at the head of the branch.
        """
        what = f"the branch {branch} of {repository}"
        data = self._json(repository, f"/git/ref/heads/{quote(branch, safe='/')}", what)
        target = data.get("object")
        if not isinstance(target, dict):
            raise UpstreamError(f"GitHub's answer for {what} names no commit.")
        return _text(target, "sha")

    def tree(self, repository: str, commit: str) -> tuple[TreeEntry, ...]:
        """List every file a commit holds.

        Args:
            repository: The repository as ``owner/name``.
            commit: The full commit SHA.

        Returns:
            The files in the order GitHub lists them. Directories and submodules are left out.
        """
        what = f"the commit {commit} of {repository}"
        data = self._json(repository, f"/git/trees/{quote(commit, safe='')}?recursive=1", what)
        # GitHub cuts very large listings short. A partial listing could hide a license file,
        # so it is refused instead of returned.
        if data.get("truncated"):
            raise UpstreamError(
                f"GitHub cut the file listing of {repository} at {commit} short because it is "
                "too large. Read the repository from a clone instead."
            )
        entries = data.get("tree")
        if not isinstance(entries, list):
            raise UpstreamError(f"GitHub's answer for {what} holds no file listing.")
        return tuple(
            TreeEntry(path=_text(entry, "path"), blob_sha=_text(entry, "sha"), size=entry["size"])
            for entry in entries
            if isinstance(entry, dict) and entry.get("type") == "blob"
        )

    def file_text(self, repository: str, commit: str, path: str) -> str:
        """Read a file's text at a commit.

        Args:
            repository: The repository as ``owner/name``.
            commit: The full commit SHA.
            path: Path of the file from the repository root.

        Returns:
            The file's content decoded as UTF-8.
        """
        body = self._get(
            repository,
            f"/contents/{quote(path, safe='/')}?ref={quote(commit, safe='')}",
            f"the file {path} at {commit} in {repository}",
            _RAW,
        )
        try:
            return body.decode("utf-8")
        except UnicodeDecodeError as error:
            raise UpstreamError(
                f"The file {path} in {repository} at {commit} is not UTF-8 text."
            ) from error

    def _json(self, repository: str, suffix: str, what: str) -> dict[str, Any]:
        body = self._get(repository, suffix, what, _JSON)
        try:
            data = json.loads(body)
        except ValueError as error:
            raise UpstreamError(f"GitHub's answer for {what} is not JSON.") from error
        if not isinstance(data, dict):
            raise UpstreamError(f"GitHub's answer for {what} is not an object.")
        return data

    def _get(self, repository: str, suffix: str, what: str, accept: str) -> bytes:
        headers = {
            "Accept": accept,
            "User-Agent": USER_AGENT,
            "X-GitHub-Api-Version": API_VERSION,
        }
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        response = self._fetch(f"{API_ROOT}/repos/{repository}{suffix}", headers)
        if response.status == 200:
            return response.body
        if response.status == 404:
            raise NotFoundError(repository, what)
        reset_at = _rate_limit_reset(response)
        if reset_at is not None:
            raise RateLimitedError(reset_at)
        raise UpstreamError(
            f"GitHub answered HTTP {response.status} for {what}{_github_message(response.body)}. "
            "Check the arguments, or try again later if GitHub is having trouble."
        )


def _lowercase(headers: list[tuple[str, str]]) -> dict[str, str]:
    return {name.lower(): value for name, value in headers}


def _text(data: dict[str, Any], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str):
        raise UpstreamError(f"GitHub's answer has no text field named {key}.")
    return value


def _rate_limit_reset(response: Response) -> datetime | None:
    """Return when the rate limit resets, or ``None`` when the response is not a rate-limit one."""
    if response.status not in (403, 429) or response.headers.get("x-ratelimit-remaining") != "0":
        return None
    try:
        return datetime.fromtimestamp(int(response.headers["x-ratelimit-reset"]), UTC)
    except (KeyError, ValueError, OverflowError, OSError):
        return None


def _github_message(body: bytes) -> str:
    """Return GitHub's own error message as a suffix, or an empty string when it gives none."""
    try:
        data = json.loads(body)
    except ValueError:
        return ""
    message = data.get("message") if isinstance(data, dict) else None
    return f": {message.rstrip('.')}" if isinstance(message, str) else ""
