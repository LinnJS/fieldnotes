"""The GitHub client and the evidence capture, driven by recorded responses."""

import http.client
import io
import json
import urllib.error
import urllib.request
from collections.abc import Mapping
from datetime import UTC, datetime
from email.message import Message
from pathlib import Path
from typing import Any

import evidence as evidence_command
import pytest
from kb.evidence import LicenseLine, capture, license_lines, render
from kb.upstream import (
    GitHubClient,
    NotFoundError,
    RateLimitedError,
    Response,
    TreeEntry,
    UpstreamError,
    fetch_with_urllib,
    token_from_environment,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "github"

REPOSITORY = "alchaincyf/loop-engineering-orange-book"
COMMIT = "829aa6084cd68680e7f389bbde9dcaebda7a43e6"
BLOB_BASE = f"https://github.com/{REPOSITORY}/blob/{COMMIT}"

LICENSE_BLOB = "ee690880bf3c5d502623b427ce7e21381b0c986f"
README_BLOB = "fc4050c0f8c73bcbb8131085228eb6cbb5b2af05"
README_ZH_BLOB = "0572ff1511f188eb843cc5c8c4f54bffa6b716bc"
ENGLISH_PDF_BLOB = "d9624d19bafb87314ad7d86e40560a365d475851"
CHINESE_PDF_BLOB = "fa841400d12a1ca5cc9f589202687fbd56963fb5"

ENGLISH_STATEMENT = (
    "[MIT License](LICENSE) — free to use, copy, modify, and distribute, including "
    "commercially. Attribution appreciated but not required."
)
# The fullwidth punctuation is the upstream README's own, so the linter's warning does not apply.
CHINESE_STATEMENT = (
    "[MIT License](LICENSE) — 可自由使用、复制、修改、分发，包括商用。注明出处更好，但不强制。"  # noqa: RUF001
)

ALL_RECORDINGS = (
    "repository",
    "branch-head",
    "tree",
    "license",
    "readme-en",
    "readme-zh",
    "not-found",
    "rate-limited",
)


class RecordedFetch:
    """Answers each request with the recorded response for its URL and keeps the requests."""

    def __init__(self, *names: str) -> None:
        self.requests: list[tuple[str, dict[str, str]]] = []
        self._responses: dict[str, Response] = {}
        for name in names:
            recording = json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))
            if "text_file" in recording:
                body = (FIXTURES / recording["text_file"]).read_bytes()
            else:
                body = json.dumps(recording["json"], ensure_ascii=False).encode("utf-8")
            self._responses[recording["url"]] = Response(
                status=recording["status"], headers=recording["headers"], body=body
            )

    def __call__(self, url: str, headers: Mapping[str, str]) -> Response:
        self.requests.append((url, dict(headers)))
        return self._responses[url]


@pytest.fixture
def fetch() -> RecordedFetch:
    return RecordedFetch(*ALL_RECORDINGS)


def test_repository_reports_the_default_branch(fetch: RecordedFetch) -> None:
    repository = GitHubClient(fetch).repository(REPOSITORY)

    assert repository.full_name == REPOSITORY
    assert repository.default_branch == "main"


def test_branch_head_is_the_commit_the_branch_points_at(fetch: RecordedFetch) -> None:
    assert GitHubClient(fetch).branch_head(REPOSITORY, "main") == COMMIT


def test_tree_lists_file_paths_with_blob_shas_and_sizes(fetch: RecordedFetch) -> None:
    entries = GitHubClient(fetch).tree(REPOSITORY, COMMIT)

    assert TreeEntry(path="LICENSE", blob_sha=LICENSE_BLOB, size=1022) in entries
    assert (
        TreeEntry(
            path="Loop-Engineering橙皮书-v261020.pdf",
            blob_sha=CHINESE_PDF_BLOB,
            size=5208049,
        )
        in entries
    )
    assert (
        TreeEntry(
            path="screenshots/page-toc.png",
            blob_sha="b09a22b0840e4f9d57baa3dce8e7cd9deae9b91c",
            size=67151,
        )
        in entries
    )


def test_tree_leaves_directories_out(fetch: RecordedFetch) -> None:
    paths = [entry.path for entry in GitHubClient(fetch).tree(REPOSITORY, COMMIT)]

    assert len(paths) == 12
    assert "screenshots" not in paths


def test_file_text_is_the_raw_file_at_the_commit(fetch: RecordedFetch) -> None:
    text = GitHubClient(fetch).file_text(REPOSITORY, COMMIT, "LICENSE")

    assert text == (FIXTURES / "license.txt").read_text(encoding="utf-8")
    url, headers = fetch.requests[-1]
    assert url == f"https://api.github.com/repos/{REPOSITORY}/contents/LICENSE?ref={COMMIT}"
    assert headers["Accept"] == "application/vnd.github.raw+json"


def test_missing_repository_raises_not_found_with_the_repository_name(
    fetch: RecordedFetch,
) -> None:
    with pytest.raises(NotFoundError) as raised:
        GitHubClient(fetch).repository("alchaincyf/no-such-orange-book")

    assert raised.value.repository == "alchaincyf/no-such-orange-book"
    assert "alchaincyf/no-such-orange-book" in str(raised.value)
    assert isinstance(raised.value, UpstreamError)


def test_exhausted_rate_limit_raises_with_the_reset_time(fetch: RecordedFetch) -> None:
    with pytest.raises(RateLimitedError) as raised:
        GitHubClient(fetch).repository("alchaincyf/hermes-agent-orange-book")

    assert raised.value.reset_at == datetime(2026, 11, 21, 0, 0, 0, tzinfo=UTC)
    assert "2026-11-21T00:00:00+00:00" in str(raised.value)
    assert isinstance(raised.value, UpstreamError)


def test_every_request_names_the_client_and_the_api_version(fetch: RecordedFetch) -> None:
    GitHubClient(fetch).repository(REPOSITORY)

    _, headers = fetch.requests[0]
    assert headers["User-Agent"]
    assert headers["X-GitHub-Api-Version"] == "2022-11-28"
    assert "Authorization" not in headers


def test_a_token_is_sent_as_a_bearer_credential_and_never_shown(fetch: RecordedFetch) -> None:
    client = GitHubClient(fetch, token="recorded-secret")

    with pytest.raises(NotFoundError) as raised:
        client.repository("alchaincyf/no-such-orange-book")

    _, headers = fetch.requests[0]
    assert headers["Authorization"] == "Bearer recorded-secret"
    assert "recorded-secret" not in repr(client)
    assert "recorded-secret" not in str(raised.value)


def test_token_comes_from_the_environment_when_one_is_set() -> None:
    assert token_from_environment({"GITHUB_TOKEN": "first", "GH_TOKEN": "second"}) == "first"
    assert token_from_environment({"GH_TOKEN": "second"}) == "second"
    assert token_from_environment({"GITHUB_TOKEN": ""}) is None
    assert token_from_environment({}) is None


REQUEST_URL = f"https://api.github.com/repos/{REPOSITORY}"


class CutShortBody:
    """A response body whose connection ends before the announced length has arrived."""

    def read(self) -> bytes:
        raise http.client.IncompleteRead(b'{"full_name"', 4096)

    def close(self) -> None:
        return None


def _answer_with(monkeypatch: pytest.MonkeyPatch, outcome: BaseException) -> None:
    """Make every request end in ``outcome`` without opening a connection."""

    def urlopen(request: urllib.request.Request, timeout: float) -> Any:
        raise outcome

    monkeypatch.setattr(urllib.request, "urlopen", urlopen)


@pytest.mark.parametrize(
    "failure",
    [
        ConnectionResetError(54, "Connection reset by peer"),
        http.client.RemoteDisconnected("Remote end closed connection without response"),
        http.client.IncompleteRead(b"", 4096),
        http.client.BadStatusLine("garbage"),
        urllib.error.URLError("no route to host"),
        TimeoutError("timed out"),
    ],
    ids=lambda failure: type(failure).__name__,
)
def test_connection_that_fails_before_an_answer_arrives_raises_an_upstream_error(
    monkeypatch: pytest.MonkeyPatch, failure: Exception
) -> None:
    _answer_with(monkeypatch, failure)

    with pytest.raises(UpstreamError, match="try again") as raised:
        fetch_with_urllib(REQUEST_URL, {})

    assert raised.value.__cause__ is failure


def test_body_that_is_cut_short_raises_an_upstream_error(monkeypatch: pytest.MonkeyPatch) -> None:
    class Reply:
        status = 200
        headers = Message()

        def __enter__(self) -> "Reply":
            return self

        def __exit__(self, *exception: object) -> None:
            return None

        def read(self) -> bytes:
            return CutShortBody().read()

    monkeypatch.setattr(urllib.request, "urlopen", lambda request, timeout: Reply())

    with pytest.raises(UpstreamError, match="try again"):
        fetch_with_urllib(REQUEST_URL, {})


def test_error_answer_whose_body_is_cut_short_raises_an_upstream_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    refused = urllib.error.HTTPError(
        REQUEST_URL,
        502,
        "Bad Gateway",
        Message(),
        CutShortBody(),  # type: ignore[arg-type]  # Only read and close are called on the body.
    )
    _answer_with(monkeypatch, refused)

    with pytest.raises(UpstreamError, match="try again"):
        fetch_with_urllib(REQUEST_URL, {})


def test_error_answer_is_returned_with_its_status_headers_and_body(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    headers = Message()
    headers["X-RateLimit-Remaining"] = "59"
    body = b'{"message": "Not Found"}'
    _answer_with(
        monkeypatch,
        urllib.error.HTTPError(REQUEST_URL, 404, "Not Found", headers, io.BytesIO(body)),
    )

    assert fetch_with_urllib(REQUEST_URL, {}) == Response(
        status=404, headers={"x-ratelimit-remaining": "59"}, body=body
    )


def test_capture_finds_the_lines_under_english_and_chinese_license_headings(
    fetch: RecordedFetch,
) -> None:
    captured = capture(GitHubClient(fetch), REPOSITORY, ref=COMMIT)

    statements = {
        (line.path, line.number): line for line in captured.readme_lines if line.heading is not None
    }
    assert sorted(statements) == [("README.md", 29), ("README_zh.md", 29)]

    english = statements["README.md", 29]
    assert english.heading == "## License"
    assert english.text == ENGLISH_STATEMENT
    assert english.blob_sha == README_BLOB
    assert english.permalink == f"{BLOB_BASE}/README.md?plain=1#L29"

    chinese = statements["README_zh.md", 29]
    assert chinese.heading == "## 许可"
    assert chinese.text == CHINESE_STATEMENT
    assert chinese.blob_sha == README_ZH_BLOB
    assert chinese.permalink == f"{BLOB_BASE}/README_zh.md?plain=1#L29"


def test_capture_reports_the_commit_the_license_file_and_the_editions(
    fetch: RecordedFetch,
) -> None:
    captured = capture(GitHubClient(fetch), REPOSITORY)

    assert captured.default_branch == "main"
    assert captured.head_commit == COMMIT
    assert captured.commit == COMMIT

    (license_file,) = captured.license_files
    assert license_file.path == "LICENSE"
    assert license_file.blob_sha == LICENSE_BLOB
    assert license_file.permalink == f"{BLOB_BASE}/LICENSE"
    assert license_file.text == (FIXTURES / "license.txt").read_text(encoding="utf-8")

    assert [(edition.path, edition.format, edition.blob_sha) for edition in captured.editions] == [
        ("Loop-Engineering-The-Complete-Guide-v260615.pdf", "pdf", ENGLISH_PDF_BLOB),
        ("Loop-Engineering橙皮书-v261020.pdf", "pdf", CHINESE_PDF_BLOB),
    ]


class ExtraFilesClient(GitHubClient):
    """Reads the recorded repository with more files at the root of its tree."""

    def __init__(self, fetch: RecordedFetch, extra: Mapping[str, str]) -> None:
        super().__init__(fetch)
        self._extra = extra

    def tree(self, repository: str, commit: str) -> tuple[TreeEntry, ...]:
        added = tuple(TreeEntry(path=path, blob_sha="0e" * 20, size=1) for path in self._extra)
        return (*super().tree(repository, commit), *added)

    def file_text(self, repository: str, commit: str, path: str) -> str:
        if path in self._extra:
            return self._extra[path]
        return super().file_text(repository, commit, path)


def test_capture_lists_license_files_under_every_common_name(fetch: RecordedFetch) -> None:
    extra = {
        "LICENCE.md": "Licence text.",
        "COPYING.md": "Copying text.",
        "UNLICENSE": "Unlicense text.",
        "fonts/LICENSE-CC-BY.md": "Font license text.",
        "LICENSES.md": "A list of licenses, not one.",
        "licensed-photo.png": "not text",
    }

    captured = capture(ExtraFilesClient(fetch, extra), REPOSITORY)

    assert sorted(license_file.path for license_file in captured.license_files) == [
        "COPYING.md",
        "LICENCE.md",
        "LICENSE",
        "UNLICENSE",
        "fonts/LICENSE-CC-BY.md",
    ]


SAMPLE_README = """\
# A Book

Released under a permissive license, as the last section says.

## 版权

版权归作者所有。

### 细则

转载请注明出处。

## Install

```bash
# License
make install
```

## 授权 / 协议

仅供学习。
"""


def test_license_lines_follow_a_heading_until_the_next_heading_of_its_level() -> None:
    assert license_lines(SAMPLE_README) == (
        LicenseLine(
            number=3,
            heading=None,
            text="Released under a permissive license, as the last section says.",
        ),
        LicenseLine(number=7, heading="## 版权", text="版权归作者所有。"),
        LicenseLine(number=9, heading="## 版权", text="### 细则"),
        LicenseLine(number=11, heading="## 版权", text="转载请注明出处。"),
        LicenseLine(number=16, heading=None, text="# License"),
        LicenseLine(number=22, heading="## 授权 / 协议", text="仅供学习。"),
    )


def test_rendered_capture_gives_each_fact_with_its_blob_sha_and_permalink(
    fetch: RecordedFetch,
) -> None:
    report = render(capture(GitHubClient(fetch), REPOSITORY, ref=COMMIT))

    assert f"Repository: {REPOSITORY}\n" in report
    assert "Default branch: main\n" in report
    assert f"Head commit: {COMMIT}\n" in report
    assert f"Evidence commit: {COMMIT}\n" in report
    assert f"{LICENSE_BLOB}  {1022:>10}  LICENSE\n" in report
    assert f"Permalink: {BLOB_BASE}/LICENSE\n" in report
    assert 'of this book and associated files (the "Work"), to deal in the Work without\n' in report
    assert f"L29: {ENGLISH_STATEMENT}\n" in report
    assert f"{BLOB_BASE}/README.md?plain=1#L29\n" in report
    assert f"L29: {CHINESE_STATEMENT}\n" in report
    assert f"{ENGLISH_PDF_BLOB}  pdf   Loop-Engineering-The-Complete-Guide-v260615.pdf\n" in report
    assert report == render(capture(GitHubClient(fetch), REPOSITORY, ref=COMMIT))


def test_command_prints_the_capture_and_succeeds(
    fetch: RecordedFetch, capsys: pytest.CaptureFixture[str]
) -> None:
    status = evidence_command.main([REPOSITORY, "--ref", COMMIT], fetch=fetch)

    assert status == 0
    assert capsys.readouterr().out == render(capture(GitHubClient(fetch), REPOSITORY, ref=COMMIT))


def test_command_fails_with_advice_when_the_repository_is_missing(
    fetch: RecordedFetch, capsys: pytest.CaptureFixture[str]
) -> None:
    status = evidence_command.main(["alchaincyf/no-such-orange-book"], fetch=fetch)

    assert status == 1
    message = capsys.readouterr().err
    assert "alchaincyf/no-such-orange-book" in message
    assert "owner/name" in message
