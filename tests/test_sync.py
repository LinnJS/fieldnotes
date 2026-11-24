"""The upstream check, driven by recorded responses on a small library built for each test."""

import dataclasses
import hashlib
import http.client
import json
import re
import urllib.request
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest
import sync as sync_command
import yaml
from kb.catalog import EditionPattern, NewestEdition, Resource, load_resource
from kb.sync import (
    LICENSE_FINDING_MARKER,
    BookResult,
    BookState,
    Classification,
    Finding,
    FindingKind,
    VersionComparison,
    compare,
    render_report,
)
from kb.upstream import Response, TreeEntry, fetch_with_urllib

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "github"
SYNC_WORKFLOW = Path(__file__).resolve().parent.parent / ".github" / "workflows" / "sync.yml"
API = "https://api.github.com/repos"

LOOP = "loop-engineering-orange-book"
HARNESS = "harness-engineering-orange-book"
HERMES = "hermes-agent-orange-book"
CURSOR = "cursor-orange-book"

LOOP_REPOSITORY = f"alchaincyf/{LOOP}"
HARNESS_REPOSITORY = f"alchaincyf/{HARNESS}"
HERMES_REPOSITORY = f"alchaincyf/{HERMES}"
CURSOR_URL = "https://www.huasheng.ai/orange-books/cursor/"

LOOP_HEAD = "829aa6084cd68680e7f389bbde9dcaebda7a43e6"
HARNESS_HEAD = "a5c33b9159750cbf2bb9a7c3e37ae40c18aa7e71"
HERMES_HEAD = "b6e53a8e11e00c8b14b2f72d6b4f1ce71fef6692"
# The recordings under sync/ serve these invented commits as the heads after one upstream push.
LOOP_NEXT = "1" * 40
HARNESS_NEXT = "2" * 40

LICENSE_BLOB = "ee690880bf3c5d502623b427ce7e21381b0c986f"
ENGLISH_PDF = "Loop-Engineering-The-Complete-Guide-v260615.pdf"
ENGLISH_PDF_BLOB = "d9624d19bafb87314ad7d86e40560a365d475851"
CHINESE_PDF = "Loop-Engineering橙皮书-v261020.pdf"
CHINESE_PDF_BLOB = "fa841400d12a1ca5cc9f589202687fbd56963fb5"
HARNESS_README_BLOB = "f42afb46eb7bb5ef9bd3e9b6304ef72ef01d8617"
HARNESS_STATEMENT = (
    "This work is shared for educational purposes. Please credit the author when referencing."
)

LOOP_HEAD_URL = f"{API}/{LOOP_REPOSITORY}/git/ref/heads/main"
HARNESS_HEAD_URL = f"{API}/{HARNESS_REPOSITORY}/git/ref/heads/main"
HERMES_HEAD_URL = f"{API}/{HERMES_REPOSITORY}/git/ref/heads/main"

# Every repository answers with the head commit its metadata records.
BASELINE = ("branch-head", "sync/harness-head", "sync/hermes-head")
# Loop Engineering has a new head. A tree recording is added to these for each scenario.
LOOP_MOVED = (*BASELINE, "sync/loop-head-moved", "repository")
# Harness Engineering has a new head. A README recording is added to these for each scenario.
HARNESS_MOVED = (
    *BASELINE,
    "sync/harness-head-moved",
    "sync/harness-repository",
    "sync/harness-tree-moved",
)

UNCHANGED_LOOP = {"classification": "unchanged", "findings": [], "head_commit": LOOP_HEAD}
UNCHANGED_HARNESS = {"classification": "unchanged", "findings": [], "head_commit": HARNESS_HEAD}
UNCHANGED_HERMES = {"classification": "unchanged", "findings": [], "head_commit": HERMES_HEAD}

BASELINE_REPORT = f"""\
# Upstream report

Summary: 0 changed, 0 moved, 0 gone, 0 error, 3 unchanged, 1 not checked.

This report records what each upstream repository shows. Writing it changes no book.

## Changed

None.

## Moved

None.

## Gone

None.

## Error

None.

## Unchanged

- `{LOOP}` ({LOOP_REPOSITORY}) at `{LOOP_HEAD}`
- `{HARNESS}` ({HARNESS_REPOSITORY}) at `{HARNESS_HEAD}`
- `{HERMES}` ({HERMES_REPOSITORY}) at `{HERMES_HEAD}`

## Not checked

- `{CURSOR}` ({CURSOR_URL}): The book has no repository to check.
"""


class RecordedFetch:
    """Answers each request with the recorded response for its URL and keeps the requests.

    A later recording replaces an earlier one for the same URL, so a scenario lists the baseline
    first and then what differs.
    """

    def __init__(self, *names: str) -> None:
        self.requests: list[str] = []
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
        self.requests.append(url)
        return self._responses[url]


def _git_book(
    resource_id: str,
    head_commit: str,
    editions: list[dict[str, str]],
    patterns: dict[str, str],
    newest: dict[str, str],
    license_record: dict[str, Any],
) -> dict[str, Any]:
    return _book(
        resource_id,
        upstream={
            "kind": "git",
            "repository": f"alchaincyf/{resource_id}",
            "default_branch": "main",
            "head_commit": head_commit,
        },
        editions=editions,
        patterns=patterns,
        newest=newest,
        license_record={
            "verified_on": "2026-11-20",
            "departs_from_template": False,
            "locations_checked": [],
            "commit": head_commit,
            **license_record,
        },
    )


def _book(
    resource_id: str,
    upstream: dict[str, str],
    editions: list[dict[str, Any]],
    patterns: dict[str, str],
    newest: dict[str, str],
    license_record: dict[str, Any],
) -> dict[str, Any]:
    return {
        "id": resource_id,
        "type": "book",
        "collection": "orange-books",
        "title": {"original": resource_id, "english": resource_id, "english_official": True},
        "author": {"name": "HuaShu", "native_name": None, "url": None},
        "translator": None,
        "languages": ["zh"],
        "official_urls": {"site": None, "repository": None, "hosted_editions": []},
        "site_slug": None,
        "upstream": upstream,
        "editions": editions,
        "edition_patterns": patterns,
        "newest_editions": newest,
        "license": license_record,
        "permissions": {
            "redistribution": "unclear",
            "adaptation": "unclear",
            "commercial_use": "unclear",
            "attribution_required": False,
            "share_alike": False,
            "third_party_rights": False,
        },
        "mirror_status": "reference-only",
    }


def _pdf(language: str, version: str, path: str, blob_sha: str) -> dict[str, str]:
    return {
        "language": language,
        "version": version,
        "format": "pdf",
        "path": path,
        "blob_sha": blob_sha,
    }


BOOKS: tuple[dict[str, Any], ...] = (
    _git_book(
        LOOP,
        LOOP_HEAD,
        editions=[
            _pdf("en", "v260615", ENGLISH_PDF, ENGLISH_PDF_BLOB),
            _pdf("zh", "v261020", CHINESE_PDF, CHINESE_PDF_BLOB),
        ],
        # The book has no Japanese edition. The pattern says what one would be named.
        patterns={
            "en": r"^Loop-Engineering-The-Complete-Guide-(?P<version>v\d+(?:\.\d+)*)\.pdf$",
            "zh": r"^Loop-Engineering橙皮书-(?P<version>v\d+(?:\.\d+)*)\.pdf$",
            "ja": r"^Loop-Engineering-ja-(?P<version>v\d+(?:\.\d+)*)\.pdf$",
        },
        newest={"en": "v260615", "zh": "v261020"},
        license_record={
            "spdx": "MIT",
            "evidence": "license-file",
            "statement": "MIT License",
            "permalink": f"https://github.com/{LOOP_REPOSITORY}/blob/{LOOP_HEAD}/LICENSE",
            "blob_sha": LICENSE_BLOB,
        },
    ),
    _git_book(
        HARNESS,
        HARNESS_HEAD,
        editions=[
            _pdf(
                "en",
                "v260411",
                "Harness-Engineering-The-Complete-Guide-v260411.pdf",
                "7f3dab7a5759916b44ee7f4270ec0a657c05d894",
            ),
            _pdf(
                "zh",
                "v260411",
                "Harness-Engineering-v260411-zh.pdf",
                "3a95ab9608b3dacac2e6c1f737c5fd5d016bb277",
            ),
        ],
        patterns={
            "en": r"^Harness-Engineering-The-Complete-Guide-(?P<version>v\d+(?:\.\d+)*)\.pdf$",
            "zh": r"^Harness-Engineering-(?P<version>v\d+(?:\.\d+)*)-zh\.pdf$",
        },
        newest={"en": "v260411", "zh": "v260411"},
        license_record={
            "spdx": None,
            "evidence": "readme-statement",
            "statement": HARNESS_STATEMENT,
            "permalink": (
                f"https://github.com/{HARNESS_REPOSITORY}/blob/{HARNESS_HEAD}/README.md?plain=1#L78"
            ),
            "blob_sha": HARNESS_README_BLOB,
        },
    ),
    _git_book(
        HERMES,
        HERMES_HEAD,
        editions=[],
        patterns={},
        newest={},
        license_record={
            "spdx": "MIT",
            "evidence": "license-file",
            "statement": "MIT License",
            "permalink": f"https://github.com/{HERMES_REPOSITORY}/blob/{HERMES_HEAD}/LICENSE",
            "blob_sha": LICENSE_BLOB,
        },
    ),
    _book(
        CURSOR,
        upstream={"kind": "url", "url": CURSOR_URL},
        editions=[],
        patterns={},
        newest={},
        license_record={
            "spdx": None,
            "evidence": "none",
            "statement": None,
            "permalink": None,
            "blob_sha": None,
            "commit": None,
            "verified_on": "2026-11-20",
            "departs_from_template": False,
            "locations_checked": [CURSOR_URL],
        },
    ),
)


def _write_yaml(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")


@pytest.fixture
def library(tmp_path: Path) -> Path:
    """A library of three repository books and one site-only book, with one chapter file."""
    root = tmp_path / "library"
    _write_yaml(
        root / "catalog.yaml",
        {
            "library": {
                "name": "sync-test-library",
                "title": "Sync Test Library",
                "description": "A library built for the upstream check tests.",
                "base_url": "https://example.invalid/library/",
                "repository": "https://example.invalid/owner/library",
            },
            "license_allowlist": ["MIT"],
            "collections": [{"id": "orange-books", "title": "AI Orange Books"}],
            "resources": [book["id"] for book in BOOKS],
        },
    )
    for book in BOOKS:
        _write_yaml(root / "books" / book["id"] / "metadata.yaml", book)
    (root / "books" / LOOP / "LICENSE").write_text("MIT License\n", encoding="utf-8")
    chapter = root / "books" / LOOP / "chapters" / "01-what-a-loop-is.md"
    chapter.parent.mkdir()
    chapter.write_text("A chapter the check must never touch.\n", encoding="utf-8")
    return root


def _run(library: Path, *recordings: str, dry_run: bool = False) -> tuple[int, RecordedFetch]:
    fetch = RecordedFetch(*recordings)
    arguments = ["--root", str(library), *(["--dry-run"] if dry_run else [])]
    return sync_command.main(arguments, fetch=fetch), fetch


def _state_text(library: Path) -> str:
    return (library / "upstream" / "state.json").read_text(encoding="utf-8")


def _report(library: Path) -> str:
    return (library / "upstream" / "report.md").read_text(encoding="utf-8")


def _books(library: Path) -> dict[str, Any]:
    books: dict[str, Any] = json.loads(_state_text(library))["books"]
    return books


def _section(report: str, heading: str) -> str:
    """Return the text of one report section, without its heading."""
    _, _, rest = report.partition(f"\n## {heading}\n")
    body, _, _ = rest.partition("\n## ")
    return body.strip()


def _outside_upstream(library: Path) -> dict[str, str]:
    """Hash every file of the library that is not under ``upstream/``."""
    return {
        str(path.relative_to(library)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(library.rglob("*"))
        if path.is_file() and path.relative_to(library).parts[0] != "upstream"
    }


def test_unchanged_heads_record_a_baseline_with_one_request_per_repository(
    library: Path,
) -> None:
    status, fetch = _run(library, *BASELINE)

    assert status == 0
    assert fetch.requests == [LOOP_HEAD_URL, HARNESS_HEAD_URL, HERMES_HEAD_URL]
    expected = {
        "books": {
            LOOP: UNCHANGED_LOOP,
            HARNESS: UNCHANGED_HARNESS,
            HERMES: UNCHANGED_HERMES,
        }
    }
    assert _state_text(library) == json.dumps(expected, indent=2, sort_keys=True) + "\n"
    assert _report(library) == BASELINE_REPORT


def test_unchanged_heads_leave_both_files_byte_identical(library: Path) -> None:
    _run(library, *BASELINE)
    state, report = _state_text(library), _report(library)

    status, fetch = _run(library, *BASELINE)

    assert status == 0
    assert fetch.requests == [LOOP_HEAD_URL, HARNESS_HEAD_URL, HERMES_HEAD_URL]
    assert _state_text(library) == state
    assert _report(library) == report


def test_new_head_with_an_unchanged_tree_updates_the_observed_commit(library: Path) -> None:
    status, fetch = _run(library, *LOOP_MOVED, "sync/loop-tree-same")

    assert status == 0
    assert _books(library)[LOOP] == {
        "classification": "unchanged",
        "findings": [],
        "head_commit": LOOP_NEXT,
    }
    assert f"- `{LOOP}` ({LOOP_REPOSITORY}) at `{LOOP_NEXT}`" in _section(
        _report(library), "Unchanged"
    )
    assert fetch.requests[:3] == [
        LOOP_HEAD_URL,
        f"{API}/{LOOP_REPOSITORY}",
        f"{API}/{LOOP_REPOSITORY}/git/trees/{LOOP_NEXT}?recursive=1",
    ]


def test_file_matching_the_english_pattern_with_a_higher_version_is_a_new_edition(
    library: Path,
) -> None:
    _run(library, *LOOP_MOVED, "sync/loop-tree-new-english-edition")

    assert _books(library)[LOOP] == {
        "classification": "changed",
        "findings": [
            {
                "blob_sha": "0a" * 20,
                "comparison": "newer",
                "kind": "new-edition",
                "language": "en",
                "path": "Loop-Engineering-The-Complete-Guide-v260701.pdf",
                "recorded_version": "v260615",
                "version": "v260701",
            }
        ],
        "head_commit": LOOP_NEXT,
    }
    report = _report(library)
    assert "Summary: 1 changed, 0 moved, 0 gone, 0 error, 2 unchanged, 1 not checked." in report
    assert _section(report, "Changed") == (
        f"- `{LOOP}` ({LOOP_REPOSITORY}) at `{LOOP_NEXT}`\n"
        "  - New `en` edition `v260701`, newer than the recorded `v260615`: "
        f"`Loop-Engineering-The-Complete-Guide-v260701.pdf` (blob `{'0a' * 20}`)."
    )
    assert LICENSE_FINDING_MARKER not in report


def test_known_filename_with_a_different_blob_is_reported_as_changed_bytes(
    library: Path,
) -> None:
    _run(library, *LOOP_MOVED, "sync/loop-tree-changed-bytes")

    assert _books(library)[LOOP]["classification"] == "changed"
    assert _books(library)[LOOP]["findings"] == [
        {"blob_sha": "0b" * 20, "kind": "changed-bytes", "path": ENGLISH_PDF}
    ]
    assert (
        f"  - New bytes under a known filename: `{ENGLISH_PDF}` (blob `{'0b' * 20}`)."
        in _section(_report(library), "Changed")
    )


def test_file_matching_the_pattern_of_a_language_the_book_lacks_is_a_new_translation(
    library: Path,
) -> None:
    _run(library, *LOOP_MOVED, "sync/loop-tree-new-translation")

    assert _books(library)[LOOP]["classification"] == "changed"
    assert _books(library)[LOOP]["findings"] == [
        {
            "blob_sha": "0c" * 20,
            "kind": "new-translation",
            "language": "ja",
            "path": "Loop-Engineering-ja-v260701.pdf",
            "version": "v260701",
        }
    ]
    assert (
        "  - New translation in `ja` at version `v260701`: "
        f"`Loop-Engineering-ja-v260701.pdf` (blob `{'0c' * 20}`)."
        in _section(_report(library), "Changed")
    )


def test_edition_file_matching_no_pattern_is_unclassified_and_other_files_are_ignored(
    library: Path,
) -> None:
    # The recorded tree also adds a PDF under drafts/ and a screenshot, which are not editions.
    _run(library, *LOOP_MOVED, "sync/loop-tree-unclassified")

    assert _books(library)[LOOP]["classification"] == "changed"
    assert _books(library)[LOOP]["findings"] == [
        {
            "blob_sha": "0d" * 20,
            "kind": "unclassified-file",
            "path": "Loop-Engineering-Workbook.pdf",
        }
    ]
    assert (
        "  - Unclassified file that matches no edition pattern: "
        f"`Loop-Engineering-Workbook.pdf` (blob `{'0d' * 20}`)."
        in _section(_report(library), "Changed")
    )


def test_license_file_with_a_different_blob_is_reported_and_nothing_else_is_written(
    library: Path,
) -> None:
    before = _outside_upstream(library)

    status, _ = _run(library, *LOOP_MOVED, "sync/loop-tree-license-changed")

    assert status == 0
    assert _books(library)[LOOP] == {
        "classification": "changed",
        "findings": [{"blob_sha": "0e" * 20, "kind": "license-file-changed", "path": "LICENSE"}],
        "head_commit": LOOP_NEXT,
    }
    assert _section(_report(library), "Changed") == (
        f"- `{LOOP}` ({LOOP_REPOSITORY}) at `{LOOP_NEXT}`\n"
        f"  - {LICENSE_FINDING_MARKER} The license file `LICENSE` changed. "
        f"Its blob is now `{'0e' * 20}`."
    )
    assert _outside_upstream(library) == before
    assert sorted(path.name for path in (library / "upstream").iterdir()) == [
        "report.md",
        "state.json",
    ]


def test_second_license_file_beside_the_unchanged_recorded_one_is_reported(
    library: Path,
) -> None:
    status, _ = _run(library, *LOOP_MOVED, "sync/loop-tree-license-additional")

    assert status == 0
    assert _books(library)[LOOP] == {
        "classification": "changed",
        "findings": [
            {"blob_sha": "1a" * 20, "kind": "license-file-additional", "path": "LICENSE.md"}
        ],
        "head_commit": LOOP_NEXT,
    }
    assert _section(_report(library), "Changed") == (
        f"- `{LOOP}` ({LOOP_REPOSITORY}) at `{LOOP_NEXT}`\n"
        f"  - {LICENSE_FINDING_MARKER} Another license file is present beside the recorded one: "
        f"`LICENSE.md` (blob `{'1a' * 20}`)."
    )


def test_copy_of_the_recorded_license_file_under_another_name_is_not_a_finding(
    library: Path,
) -> None:
    loop = load_resource(library, LOOP)
    tree = _tree(
        ("LICENSE", LICENSE_BLOB),
        ("LICENSE.txt", LICENSE_BLOB),
        (ENGLISH_PDF, ENGLISH_PDF_BLOB),
        (CHINESE_PDF, CHINESE_PDF_BLOB),
    )

    assert compare(loop, LOOP_REPOSITORY, tree, readme=None) == ()


def test_every_license_file_is_reported_as_changed_when_none_has_the_recorded_blob(
    library: Path,
) -> None:
    loop = load_resource(library, LOOP)
    tree = _tree(
        ("COPYING", "1b" * 20),
        ("LICENSE", "0e" * 20),
        (ENGLISH_PDF, ENGLISH_PDF_BLOB),
        (CHINESE_PDF, CHINESE_PDF_BLOB),
    )

    assert compare(loop, LOOP_REPOSITORY, tree, readme=None) == (
        Finding(kind=FindingKind.LICENSE_FILE_CHANGED, path="COPYING", blob_sha="1b" * 20),
        Finding(kind=FindingKind.LICENSE_FILE_CHANGED, path="LICENSE", blob_sha="0e" * 20),
    )


def test_readme_without_the_recorded_statement_is_reported(library: Path) -> None:
    _, fetch = _run(library, *HARNESS_MOVED, "sync/harness-readme-without-statement")

    assert _books(library)[HARNESS] == {
        "classification": "changed",
        "findings": [{"kind": "statement-not-found", "path": "README.md"}],
        "head_commit": HARNESS_NEXT,
    }
    assert _section(_report(library), "Changed") == (
        f"- `{HARNESS}` ({HARNESS_REPOSITORY}) at `{HARNESS_NEXT}`\n"
        f"  - {LICENSE_FINDING_MARKER} The recorded license statement no longer appears in "
        "`README.md`."
    )
    assert f"{API}/{HARNESS_REPOSITORY}/contents/README.md?ref={HARNESS_NEXT}" in fetch.requests


def test_readme_that_still_holds_the_recorded_statement_yields_no_finding(
    library: Path,
) -> None:
    _run(library, *HARNESS_MOVED, "sync/harness-readme-moved")

    assert _books(library)[HARNESS] == {
        "classification": "unchanged",
        "findings": [],
        "head_commit": HARNESS_NEXT,
    }


def test_not_found_classifies_the_book_as_gone_and_leaves_its_metadata_untouched(
    library: Path,
) -> None:
    before = _outside_upstream(library)

    status, _ = _run(library, *BASELINE, "sync/hermes-head-not-found")

    assert status == 0
    assert _books(library) == {
        LOOP: UNCHANGED_LOOP,
        HARNESS: UNCHANGED_HARNESS,
        HERMES: {"classification": "gone", "findings": [], "head_commit": None},
    }
    report = _report(library)
    assert "Summary: 0 changed, 0 moved, 1 gone, 0 error, 2 unchanged, 1 not checked." in report
    assert _section(report, "Gone") == (
        f"- `{HERMES}` ({HERMES_REPOSITORY}): GitHub found nothing for the branch `main`. "
        "The repository or the branch was deleted, renamed, or made private."
    )
    assert _outside_upstream(library) == before


def test_server_error_keeps_the_previous_entry_and_the_other_books_are_still_checked(
    library: Path,
) -> None:
    _run(library, *HARNESS_MOVED, "sync/harness-readme-without-statement")
    harness_before = _books(library)[HARNESS]
    assert harness_before["classification"] == "changed"

    status, fetch = _run(
        library,
        *LOOP_MOVED,
        "sync/loop-tree-same",
        "sync/harness-head-server-error",
    )

    assert status == 0
    assert fetch.requests[-2:] == [HARNESS_HEAD_URL, HERMES_HEAD_URL]
    assert _books(library) == {
        LOOP: {"classification": "unchanged", "findings": [], "head_commit": LOOP_NEXT},
        HARNESS: harness_before,
        HERMES: UNCHANGED_HERMES,
    }
    report = _report(library)
    assert "Summary: 0 changed, 0 moved, 0 gone, 1 error, 2 unchanged, 1 not checked." in report
    assert _section(report, "Changed") == "None."
    assert _section(report, "Error") == (
        f"- `{HARNESS}` ({HARNESS_REPOSITORY}): GitHub answered HTTP 500 for the branch main of "
        f"{HARNESS_REPOSITORY}: Server Error. Check the arguments, or try again later if GitHub "
        "is having trouble. The entry from the last successful check is kept.\n"
        f"  - {LICENSE_FINDING_MARKER} The recorded license statement no longer appears in "
        "`README.md`."
    )


def test_answer_cut_short_for_one_book_keeps_its_entry_and_the_other_books_are_still_checked(
    library: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _run(library, *HARNESS_MOVED, "sync/harness-readme-without-statement")
    harness_before = _books(library)[HARNESS]
    assert harness_before["classification"] == "changed"
    recorded = RecordedFetch(*BASELINE)

    def cut_short(request: urllib.request.Request, timeout: float) -> Any:
        raise http.client.IncompleteRead(b'{"ref"', 4096)

    # The real fetch function runs for one book, on a connection that is replaced here, so no
    # request leaves the machine.
    monkeypatch.setattr(urllib.request, "urlopen", cut_short)

    def fetch(url: str, headers: Mapping[str, str]) -> Response:
        if url == HARNESS_HEAD_URL:
            return fetch_with_urllib(url, headers)
        return recorded(url, headers)

    status = sync_command.main(["--root", str(library)], fetch=fetch)

    assert status == 0
    assert recorded.requests == [LOOP_HEAD_URL, HERMES_HEAD_URL]
    assert _books(library) == {
        LOOP: UNCHANGED_LOOP,
        HARNESS: harness_before,
        HERMES: UNCHANGED_HERMES,
    }
    report = _report(library)
    assert "Summary: 0 changed, 0 moved, 0 gone, 1 error, 2 unchanged, 1 not checked." in report
    error = _section(report, "Error")
    assert error.startswith(f"- `{HARNESS}` ({HARNESS_REPOSITORY}): GitHub could not be reached")
    assert error.endswith(
        "The entry from the last successful check is kept.\n"
        f"  - {LICENSE_FINDING_MARKER} The recorded license statement no longer appears in "
        "`README.md`."
    )


def test_rate_limit_stops_the_run_and_exits_zero_when_a_book_succeeded(
    library: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    status, fetch = _run(library, *BASELINE, "sync/harness-head-rate-limited")

    assert status == 0
    assert fetch.requests == [LOOP_HEAD_URL, HARNESS_HEAD_URL]
    assert _books(library) == {LOOP: UNCHANGED_LOOP}
    report = _report(library)
    assert "Summary: 0 changed, 0 moved, 0 gone, 2 error, 1 unchanged, 1 not checked." in report
    assert _section(report, "Error") == (
        f"- `{HARNESS}` ({HARNESS_REPOSITORY}): The GitHub rate limit was used up. Run the check "
        "again after the limit resets, or set GITHUB_TOKEN or GH_TOKEN for the higher limit.\n"
        f"- `{HERMES}` ({HERMES_REPOSITORY}): Not attempted, because the GitHub rate limit was "
        "used up earlier in this run."
    )
    # The reset time is advice for the person running the command. It stays out of the report,
    # which must not change from one run to the next.
    assert "2026-11-21T00:00:00+00:00" in capsys.readouterr().err
    assert "2026-11-21" not in report


def test_exit_code_is_nonzero_when_every_checked_book_ended_in_error(library: Path) -> None:
    status, fetch = _run(library, *BASELINE, "sync/loop-head-rate-limited")

    assert status == 1
    assert fetch.requests == [LOOP_HEAD_URL]
    assert _books(library) == {}
    assert "Summary: 0 changed, 0 moved, 0 gone, 3 error, 0 unchanged, 1 not checked." in _report(
        library
    )


def test_repository_answering_under_another_name_classifies_the_book_as_moved(
    library: Path,
) -> None:
    _run(
        library,
        *LOOP_MOVED,
        "sync/loop-repository-renamed",
        "sync/loop-tree-same",
    )

    assert _books(library)[LOOP] == {
        "classification": "moved",
        "findings": [
            {"kind": "repository-renamed", "repository": "alchaincyf/loop-engineering-book"}
        ],
        "head_commit": LOOP_NEXT,
    }
    report = _report(library)
    assert "Summary: 0 changed, 1 moved, 0 gone, 0 error, 2 unchanged, 1 not checked." in report
    assert _section(report, "Moved") == (
        f"- `{LOOP}` ({LOOP_REPOSITORY}) at `{LOOP_NEXT}`\n"
        "  - The repository now answers as `alchaincyf/loop-engineering-book`."
    )


def test_second_run_on_the_same_responses_changes_nothing_and_costs_one_request_per_book(
    library: Path,
) -> None:
    recordings = (*LOOP_MOVED, "sync/loop-tree-new-english-edition")
    _run(library, *recordings)
    state, report = _state_text(library), _report(library)
    assert json.loads(state)["books"][LOOP]["classification"] == "changed"

    status, fetch = _run(library, *recordings)

    assert status == 0
    assert _state_text(library) == state
    assert _report(library) == report
    assert fetch.requests == [LOOP_HEAD_URL, HARNESS_HEAD_URL, HERMES_HEAD_URL]


def test_findings_clear_once_the_metadata_records_the_observed_head(library: Path) -> None:
    recordings = (*LOOP_MOVED, "sync/loop-tree-new-english-edition")
    _run(library, *recordings)
    assert _books(library)[LOOP]["classification"] == "changed"
    caught_up = {**BOOKS[0], "upstream": {**BOOKS[0]["upstream"], "head_commit": LOOP_NEXT}}
    _write_yaml(library / "books" / LOOP / "metadata.yaml", caught_up)

    _, fetch = _run(library, *recordings)

    assert _books(library)[LOOP] == {
        "classification": "unchanged",
        "findings": [],
        "head_commit": LOOP_NEXT,
    }
    assert fetch.requests == [LOOP_HEAD_URL, HARNESS_HEAD_URL, HERMES_HEAD_URL]


def test_dry_run_prints_the_report_and_writes_no_file(
    library: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    before = sorted(path for path in library.rglob("*"))

    status, _ = _run(library, *BASELINE, dry_run=True)

    assert status == 0
    assert capsys.readouterr().out == BASELINE_REPORT
    assert sorted(path for path in library.rglob("*")) == before
    assert not (library / "upstream").exists()


def test_state_file_the_command_did_not_write_fails_with_advice(
    library: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    state = library / "upstream" / "state.json"
    state.parent.mkdir()
    state.write_text("<<<<<<< HEAD\n", encoding="utf-8")

    status, fetch = _run(library, *BASELINE)

    assert status == 1
    assert fetch.requests == []
    message = capsys.readouterr().err
    assert str(state) in message
    assert "Delete it" in message
    assert state.read_text(encoding="utf-8") == "<<<<<<< HEAD\n"


def _tree(*entries: tuple[str, str]) -> tuple[TreeEntry, ...]:
    return tuple(TreeEntry(path=path, blob_sha=blob_sha, size=1) for path, blob_sha in entries)


def test_license_file_that_is_no_longer_in_the_tree_is_reported_as_missing(
    library: Path,
) -> None:
    loop = load_resource(library, LOOP)
    tree = _tree((ENGLISH_PDF, ENGLISH_PDF_BLOB), (CHINESE_PDF, CHINESE_PDF_BLOB))

    assert compare(loop, LOOP_REPOSITORY, tree, readme=None) == (
        Finding(kind=FindingKind.LICENSE_FILE_MISSING),
    )


def test_license_file_in_a_book_that_recorded_none_is_reported_as_added(
    library: Path,
) -> None:
    harness = load_resource(library, HARNESS)
    tree = _tree(("LICENSE", "0e" * 20), ("README.md", "0f" * 20), ("vendor/LICENSE", "1e" * 20))

    assert compare(harness, HARNESS_REPOSITORY, tree, readme=f"{HARNESS_STATEMENT}\n") == (
        Finding(kind=FindingKind.LICENSE_FILE_ADDED, path="LICENSE", blob_sha="0e" * 20),
    )


@pytest.mark.parametrize(
    "name", ["LICENCE.md", "COPYING.md", "UNLICENSE", "LICENSE-CC-BY.md", "license_mit.txt"]
)
def test_license_file_under_another_common_name_is_reported_as_added(
    library: Path, name: str
) -> None:
    harness = load_resource(library, HARNESS)
    tree = _tree(
        (name, "0e" * 20),
        ("README.md", "0f" * 20),
        ("LICENSES.md", "1d" * 20),
        (f"vendor/{name}", "1e" * 20),
    )

    assert compare(harness, HARNESS_REPOSITORY, tree, readme=f"{HARNESS_STATEMENT}\n") == (
        Finding(kind=FindingKind.LICENSE_FILE_ADDED, path=name, blob_sha="0e" * 20),
    )


def test_statement_is_not_found_when_the_readme_is_gone(library: Path) -> None:
    harness = load_resource(library, HARNESS)

    assert compare(harness, HARNESS_REPOSITORY, _tree(), readme=None) == (
        Finding(kind=FindingKind.STATEMENT_NOT_FOUND, path="README.md"),
    )


def test_statement_of_several_lines_is_matched_against_stripped_readme_lines(
    library: Path,
) -> None:
    harness = load_resource(library, HARNESS)
    several_lines = dataclasses.replace(
        harness,
        license=dataclasses.replace(harness.license, statement="First line.\n\nThird line.\n"),
    )
    indented = "## License\r\n\r\n  First line.  \r\n\r\nThird line.\r\n"
    interrupted = "## License\n\nFirst line.\nA new second line.\nThird line.\n"

    assert compare(several_lines, HARNESS_REPOSITORY, _tree(), readme=indented) == ()
    assert compare(several_lines, HARNESS_REPOSITORY, _tree(), readme=interrupted) == (
        Finding(kind=FindingKind.STATEMENT_NOT_FOUND, path="README.md"),
    )


def _edition_findings(resource: Resource, path: str) -> tuple[Finding, ...]:
    tree = _tree(("LICENSE", LICENSE_BLOB), (path, "0a" * 20))
    return compare(resource, LOOP_REPOSITORY, tree, readme=None)


def test_new_edition_says_how_its_version_compares_with_the_recorded_one(
    library: Path,
) -> None:
    loop = load_resource(library, LOOP)
    words = dataclasses.replace(
        loop,
        edition_patterns=(EditionPattern("en", r"^Guide-(?P<version>[a-z0-9.]+)\.pdf$"),),
        newest_editions=(NewestEdition("en", "v2.10.0"),),
    )

    def comparison(path: str) -> VersionComparison | None:
        (finding,) = _edition_findings(words, path)
        assert finding.kind is FindingKind.NEW_EDITION
        assert finding.recorded_version == "v2.10.0"
        return finding.comparison

    # Parts compare as numbers, so 10 is above 9 and a date-style version is above a dotted one.
    assert comparison("Guide-v2.11.0.pdf") is VersionComparison.NEWER
    assert comparison("Guide-v261020.pdf") is VersionComparison.NEWER
    assert comparison("Guide-v2.9.3.pdf") is VersionComparison.DIFFERENT
    assert comparison("Guide-final.pdf") is VersionComparison.DIFFERENT
    assert comparison("Guide-v2.10.0.pdf") is VersionComparison.SAME


def _changed(resource_id: str, *findings: Finding) -> BookResult:
    return BookResult(
        resource_id=resource_id,
        source=f"alchaincyf/{resource_id}",
        classification=Classification.CHANGED,
        state=BookState(Classification.CHANGED, LOOP_NEXT, findings),
        message=None,
    )


def test_report_marks_every_license_finding_and_no_other(library: Path) -> None:
    report = render_report(
        (
            _changed(
                "licensed",
                Finding(kind=FindingKind.LICENSE_FILE_CHANGED, path="LICENSE", blob_sha="0e" * 20),
                Finding(kind=FindingKind.LICENSE_FILE_MISSING),
                Finding(
                    kind=FindingKind.LICENSE_FILE_ADDITIONAL, path="COPYING", blob_sha="1a" * 20
                ),
                Finding(kind=FindingKind.LICENSE_FILE_ADDED, path="LICENSE", blob_sha="0e" * 20),
                Finding(kind=FindingKind.STATEMENT_NOT_FOUND, path="README.md"),
            ),
            _changed(
                "edited",
                Finding(kind=FindingKind.CHANGED_BYTES, path="a.pdf", blob_sha="0b" * 20),
                Finding(kind=FindingKind.UNCLASSIFIED_FILE, path="b.pdf", blob_sha="0d" * 20),
                Finding(kind=FindingKind.REPOSITORY_RENAMED, repository="owner/new-name"),
            ),
        )
    )

    marked = [line for line in report.splitlines() if LICENSE_FINDING_MARKER in line]
    assert marked == [
        f"  - {LICENSE_FINDING_MARKER} The license file `LICENSE` changed. "
        f"Its blob is now `{'0e' * 20}`.",
        f"  - {LICENSE_FINDING_MARKER} The recorded license file is no longer in the repository.",
        f"  - {LICENSE_FINDING_MARKER} Another license file is present beside the recorded one: "
        f"`COPYING` (blob `{'1a' * 20}`).",
        f"  - {LICENSE_FINDING_MARKER} A license file was added at `LICENSE` "
        f"(blob `{'0e' * 20}`). The record has none.",
        f"  - {LICENSE_FINDING_MARKER} The recorded license statement no longer appears in "
        "`README.md`.",
    ]


# A file name Git accepts that tries to close its code span, mention an account, start a section,
# forge a license finding, and open an HTML comment that would hide the rest of the report.
HOSTILE_PATH = "x` @octocat\n\n## Unchanged\n\n  - LICENSE-FINDING forged <!--.pdf"


def _findings_of_every_kind(value: str) -> tuple[Finding, ...]:
    """Build one finding of each kind with ``value`` in every field upstream can set."""

    def file(kind: FindingKind) -> Finding:
        return Finding(kind=kind, path=value, blob_sha=value)

    def edition(comparison: VersionComparison, recorded: str | None) -> Finding:
        return dataclasses.replace(
            file(FindingKind.NEW_EDITION),
            language=value,
            version=value,
            recorded_version=recorded,
            comparison=comparison,
        )

    return (
        Finding(kind=FindingKind.REPOSITORY_RENAMED, repository=value),
        file(FindingKind.LICENSE_FILE_CHANGED),
        Finding(kind=FindingKind.LICENSE_FILE_MISSING),
        file(FindingKind.LICENSE_FILE_ADDITIONAL),
        file(FindingKind.LICENSE_FILE_ADDED),
        Finding(kind=FindingKind.STATEMENT_NOT_FOUND, path=value),
        dataclasses.replace(file(FindingKind.NEW_TRANSLATION), language=value, version=value),
        file(FindingKind.CHANGED_BYTES),
        file(FindingKind.UNCLASSIFIED_FILE),
        edition(VersionComparison.NEWER, value),
        edition(VersionComparison.SAME, value),
        edition(VersionComparison.DIFFERENT, value),
        edition(VersionComparison.DIFFERENT, None),
    )


def test_file_name_with_markdown_in_it_stays_inside_one_code_span_on_one_line() -> None:
    def report(path: str) -> list[str]:
        finding = Finding(kind=FindingKind.UNCLASSIFIED_FILE, path=path, blob_sha="0d" * 20)
        return render_report((_changed("book", finding),)).splitlines()

    plain, hostile = report("plain.pdf"), report(HOSTILE_PATH)

    assert len(hostile) == len(plain)
    assert [line for line in hostile if line.startswith("#")] == [
        line for line in plain if line.startswith("#")
    ]
    assert [line for line in hostile if LICENSE_FINDING_MARKER in line] == [
        "  - Unclassified file that matches no edition pattern: "
        "``x` @octocat\ufffd\ufffd## Unchanged\ufffd\ufffd  - LICENSE-FINDING forged <!--.pdf`` "
        f"(blob `{'0d' * 20}`)."
    ]


@pytest.mark.parametrize(
    ("path", "span"),
    [
        ("plain.pdf", "`plain.pdf`"),
        ("a``b`c.pdf", "```a``b`c.pdf```"),
        ("`quoted`", "`` `quoted` ``"),
        ("ends-with`", "`` ends-with` ``"),
        ("tab\there\u202e.pdf", "`tab\ufffdhere\ufffd.pdf`"),
    ],
)
def test_code_span_is_fenced_one_backtick_longer_than_any_run_in_the_value(
    path: str, span: str
) -> None:
    finding = Finding(kind=FindingKind.CHANGED_BYTES, path=path, blob_sha="0b" * 20)

    report = render_report((_changed("book", finding),))

    assert f"  - New bytes under a known filename: {span} (blob `{'0b' * 20}`).\n" in report


def test_no_value_from_upstream_can_add_a_line_a_heading_or_a_license_mark() -> None:
    def report(value: str) -> list[str]:
        changed = BookResult(
            resource_id="book",
            source="alchaincyf/book",
            classification=Classification.CHANGED,
            state=BookState(Classification.CHANGED, value, _findings_of_every_kind(value)),
            message=None,
        )
        failed = BookResult(
            resource_id="other",
            source="alchaincyf/other",
            classification=Classification.ERROR,
            state=None,
            message=f"GitHub answered HTTP 500 for the branch main: {value}.",
        )
        return render_report((changed, failed)).splitlines()

    def marked(lines: list[str]) -> list[int]:
        return [
            number
            for number, line in enumerate(lines)
            if line.startswith(f"  - {LICENSE_FINDING_MARKER} ")
        ]

    plain, hostile = report("plain"), report(HOSTILE_PATH)

    assert len(hostile) == len(plain)
    assert [line for line in hostile if line.startswith("#")] == [
        line for line in plain if line.startswith("#")
    ]
    assert marked(hostile) == marked(plain)
    assert len(marked(plain)) == 5


def test_workflow_looks_for_license_findings_the_way_the_report_starts_them() -> None:
    workflow = SYNC_WORKFLOW.read_text(encoding="utf-8")
    report = render_report((_changed("book", *_findings_of_every_kind(HOSTILE_PATH)),))

    patterns = re.findall(r"grep --quiet '([^']+)' upstream/report\.md", workflow)
    assert patterns == ["^  - LICENSE-FINDING "]
    matched = [line for line in report.splitlines() if re.search(patterns[0], line)]
    assert [line.partition("``")[0] for line in matched] == [
        "  - LICENSE-FINDING The license file ",
        "  - LICENSE-FINDING The recorded license file is no longer in the repository.",
        "  - LICENSE-FINDING Another license file is present beside the recorded one: ",
        "  - LICENSE-FINDING A license file was added at ",
        "  - LICENSE-FINDING The recorded license statement no longer appears in ",
    ]
