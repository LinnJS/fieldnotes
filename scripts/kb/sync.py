"""Check what each upstream repository shows today against what the library records.

The library keeps two kinds of fact apart. A book's ``metadata.yaml`` holds what a person pinned:
the head commit they verified, the editions, and the license evidence. ``upstream/state.json``
holds what the last check observed: for each book a classification, the head commit, and the
findings. This module reads the first, writes the second, and never the other way around. It
changes no metadata, chapter, license evidence, or mirror status, so a license change upstream is
reported and cannot change what the library is allowed to mirror.

A book whose head commit is the one its metadata records, or the one the last check observed,
costs one request and is not read further. A book with a new head is compared in full: the
repository's name, the license file, the README statement, and the files that look like editions.

``upstream/report.md`` is the same facts for a person. Neither file carries a date or a time, so
the same upstream state always produces the same bytes.
"""

import json
import posixpath
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

from kb.catalog import (
    EvidenceKind,
    GitSource,
    Resource,
    load_catalog,
    load_resource,
    version_key,
)
from kb.evidence import EDITION_SUFFIXES, LICENSE_FILE_PATTERN, README_PATH
from kb.upstream import (
    TOKEN_VARIABLES,
    GitHubClient,
    NotFoundError,
    RateLimitedError,
    TreeEntry,
    UpstreamError,
)

__all__ = [
    "LICENSE_FINDING_MARKER",
    "README_PATH",
    "REPORT_FILE",
    "STATE_FILE",
    "UPSTREAM_DIR",
    "BookResult",
    "BookState",
    "Classification",
    "Finding",
    "FindingKind",
    "StateError",
    "SyncRun",
    "VersionComparison",
    "check_books",
    "compare",
    "load_state",
    "render_report",
    "render_state",
    "summary_line",
    "sync_library",
    "write_run",
]

UPSTREAM_DIR = "upstream"
STATE_FILE = "state.json"
REPORT_FILE = "report.md"

LICENSE_FINDING_MARKER = "LICENSE-FINDING"
"""Starts every report line that says a book's license terms look different upstream.

Such a line is a nested list item, so it begins with two spaces, a hyphen, a space, this string,
and a space. The sync workflow finds license findings by matching that start of a line. A file
name upstream can hold this string, and then it appears inside a code span later in a line, which
the workflow does not count.
"""

_RATE_LIMITED = (
    "The GitHub rate limit was used up. Run the check again after the limit resets, or set "
    f"{TOKEN_VARIABLES[0]} or {TOKEN_VARIABLES[1]} for the higher limit."
)
_NOT_ATTEMPTED = "Not attempted, because the GitHub rate limit was used up earlier in this run."
_NO_REPOSITORY = "The book has no repository to check."
_ENTRY_KEPT = "The entry from the last successful check is kept."

_REPLACEMENT_CHARACTER = "\ufffd"
_BACKTICK_RUN = re.compile("`+")


class Classification(StrEnum):
    """What one check concluded about one book."""

    CHANGED = "changed"
    MOVED = "moved"
    GONE = "gone"
    ERROR = "error"
    UNCHANGED = "unchanged"
    NOT_CHECKED = "not-checked"


class FindingKind(StrEnum):
    """What kind of difference a finding reports."""

    REPOSITORY_RENAMED = "repository-renamed"
    LICENSE_FILE_CHANGED = "license-file-changed"
    LICENSE_FILE_MISSING = "license-file-missing"
    LICENSE_FILE_ADDITIONAL = "license-file-additional"
    LICENSE_FILE_ADDED = "license-file-added"
    STATEMENT_NOT_FOUND = "statement-not-found"
    NEW_EDITION = "new-edition"
    NEW_TRANSLATION = "new-translation"
    CHANGED_BYTES = "changed-bytes"
    UNCLASSIFIED_FILE = "unclassified-file"


class VersionComparison(StrEnum):
    """How the version of a new edition file compares with the newest recorded one."""

    NEWER = "newer"
    SAME = "same"
    DIFFERENT = "different"


_LICENSE_KINDS = frozenset(
    {
        FindingKind.LICENSE_FILE_CHANGED,
        FindingKind.LICENSE_FILE_MISSING,
        FindingKind.LICENSE_FILE_ADDITIONAL,
        FindingKind.LICENSE_FILE_ADDED,
        FindingKind.STATEMENT_NOT_FOUND,
    }
)

# The order of the report's sections, with what needs a person first.
_SECTIONS = (
    (Classification.CHANGED, "Changed"),
    (Classification.MOVED, "Moved"),
    (Classification.GONE, "Gone"),
    (Classification.ERROR, "Error"),
    (Classification.UNCHANGED, "Unchanged"),
    (Classification.NOT_CHECKED, "Not checked"),
)


@dataclass(frozen=True)
class Finding:
    """One difference between what upstream shows and what the metadata records.

    Only the fields that the kind uses are set. The others stay ``None`` and are left out of the
    state file.

    Attributes:
        kind: What kind of difference this is.
        path: Path of the file the finding is about, from the repository root.
        blob_sha: Git blob id the file has upstream now.
        language: Language code of the edition pattern the file matched.
        version: Version the edition pattern captured from the file name.
        recorded_version: Newest version the metadata records for the language.
        comparison: How ``version`` compares with ``recorded_version``.
        repository: Name the repository answers with now, as ``owner/name``.
    """

    kind: FindingKind
    path: str | None = None
    blob_sha: str | None = None
    language: str | None = None
    version: str | None = None
    recorded_version: str | None = None
    comparison: VersionComparison | None = None
    repository: str | None = None


@dataclass(frozen=True)
class BookState:
    """What the last successful check observed for one book. It is one entry of the state file.

    Attributes:
        classification: The check's conclusion. It is never ``error`` or ``not-checked``.
        head_commit: Head of the default branch at the check, or ``None`` for a book that is gone.
        findings: The differences from the metadata, which are empty unless the book changed or
            moved.
    """

    classification: Classification
    head_commit: str | None
    findings: tuple[Finding, ...]


@dataclass(frozen=True)
class BookResult:
    """The outcome of one run for one book. It is one entry of the report.

    Attributes:
        resource_id: Id of the book.
        source: The upstream repository as ``owner/name``, or the page URL of a site-only book.
        classification: The run's conclusion for the book.
        state: The book's state file entry after the run. For an ``error`` it is the entry kept
            from the last successful check. It is ``None`` when the book has no entry.
        message: A sentence for the report that says why the book is gone, failed, or was not
            checked. It is ``None`` otherwise. It never holds a date or a time.
    """

    resource_id: str
    source: str
    classification: Classification
    state: BookState | None
    message: str | None


@dataclass(frozen=True)
class SyncRun:
    """Everything one run produced.

    Attributes:
        results: One result per cataloged book, in catalog order.
        rate_limit: GitHub's rate-limit advice with the reset time, for the person running the
            command. It is ``None`` when the limit was not reached.
    """

    results: tuple[BookResult, ...]
    rate_limit: str | None

    @property
    def state(self) -> dict[str, BookState]:
        """The state file entries after the run, by book id."""
        return {
            result.resource_id: result.state for result in self.results if result.state is not None
        }

    @property
    def all_failed(self) -> bool:
        """Whether at least one book was checked and every checked book ended in ``error``."""
        checked = [
            result.classification
            for result in self.results
            if result.classification is not Classification.NOT_CHECKED
        ]
        return bool(checked) and all(found is Classification.ERROR for found in checked)


class StateError(Exception):
    """The state file exists and is not one this module wrote."""

    def __init__(self, path: Path) -> None:
        """Build the error.

        Args:
            path: The state file.
        """
        self.path = path
        super().__init__(
            f"{path} is not a state file the upstream check wrote. Delete it and run the check "
            "again to record a fresh baseline."
        )


def compare(
    resource: Resource, repository: str, tree: Iterable[TreeEntry], readme: str | None
) -> tuple[Finding, ...]:
    """Compare what a repository shows at one commit with what a book's metadata records.

    A license file is a top-level file with a conventional license name. For a book whose
    evidence is a license file, a license file with other content is a finding whether it
    replaced the recorded one or sits beside it. Only a file with an edition format that sits at
    the top level, or in a directory that already holds a recorded edition, takes part in the
    edition comparison. A recorded edition that upstream no longer carries is not a finding.

    Args:
        resource: The book, which must have a Git upstream.
        repository: The name the repository answers with, as ``owner/name``.
        tree: Every file at the commit.
        readme: The text of ``README.md`` at the commit, or ``None`` when it was not read. It is
            used only for a book whose license evidence is a README statement.

    Returns:
        The findings: a rename first, then license findings, then edition findings in tree order.
    """
    entries = tuple(tree)
    findings: list[Finding] = []
    if isinstance(resource.upstream, GitSource) and repository != resource.upstream.repository:
        findings.append(Finding(kind=FindingKind.REPOSITORY_RENAMED, repository=repository))
    findings += _license_findings(resource, entries, readme)
    findings += _edition_findings(resource, entries)
    return tuple(findings)


def check_books(
    resources: Iterable[Resource], previous: Mapping[str, BookState], client: GitHubClient
) -> SyncRun:
    """Check every book once.

    A failure for one book leaves its previous entry in place and does not stop the others. Once
    GitHub reports that the rate limit is used up, no further request is made and the books not
    yet checked end in ``error`` too.

    Args:
        resources: The cataloged books, in catalog order.
        previous: The state file entries of the last run, by book id.
        client: The client to read GitHub through.

    Returns:
        The run, with one result per book.
    """
    results: list[BookResult] = []
    rate_limit: str | None = None
    for resource in resources:
        source = resource.upstream
        if not isinstance(source, GitSource):
            results.append(
                BookResult(
                    resource.id, source.url, Classification.NOT_CHECKED, None, _NO_REPOSITORY
                )
            )
            continue
        kept = previous.get(resource.id)
        message: str | None
        if rate_limit is not None:
            state, message = None, _NOT_ATTEMPTED
        else:
            try:
                state, message = _observe(client, resource, source, kept)
            except RateLimitedError as error:
                # The error's own text names the reset time, which would make the report differ
                # from run to run. The person at the terminal still gets it.
                rate_limit = str(error)
                state, message = None, _RATE_LIMITED
            except UpstreamError as error:
                state, message = None, str(error)
        if state is None:
            results.append(
                BookResult(resource.id, source.repository, Classification.ERROR, kept, message)
            )
        else:
            results.append(
                BookResult(resource.id, source.repository, state.classification, state, message)
            )
    return SyncRun(results=tuple(results), rate_limit=rate_limit)


def load_state(path: Path) -> dict[str, BookState]:
    """Read the state file.

    Args:
        path: The state file.

    Returns:
        The entries by book id. The mapping is empty when the file does not exist.

    Raises:
        StateError: The file exists and is not a state file this module wrote.
    """
    if not path.exists():
        return {}
    try:
        books = json.loads(path.read_text(encoding="utf-8"))["books"]
        return {resource_id: _book_state(entry) for resource_id, entry in books.items()}
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as error:
        raise StateError(path) from error


def render_state(state: Mapping[str, BookState]) -> str:
    """Write state entries as the text of the state file.

    Args:
        state: The entries by book id.

    Returns:
        JSON with sorted keys and a two-space indent, ending in a newline.
    """
    books = {
        resource_id: {
            "classification": entry.classification.value,
            "head_commit": entry.head_commit,
            "findings": [_finding_record(finding) for finding in entry.findings],
        }
        for resource_id, entry in state.items()
    }
    return json.dumps({"books": books}, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def summary_line(results: Iterable[BookResult]) -> str:
    """Count the books in each classification.

    Args:
        results: One result per book.

    Returns:
        One sentence that names every classification with its count, in the order of the report's
        sections.
    """
    found = [result.classification for result in results]
    counts = ", ".join(
        f"{found.count(classification)} {title.lower()}" for classification, title in _SECTIONS
    )
    return f"Summary: {counts}."


def render_report(results: Iterable[BookResult]) -> str:
    """Write the results as the Markdown report.

    The report has one section per classification, always in the same order, and lists the books
    of a section in the order given. A license finding starts with ``LICENSE_FINDING_MARKER``.

    The report becomes the body of a pull request, and upstream chooses its file names. Every
    value that comes from a GitHub answer is therefore written as a code span it cannot close,
    with each character that is not printable replaced by U+FFFD, so no such value can start a
    line, a heading, a mention, or a comment.

    Args:
        results: One result per book, in catalog order.

    Returns:
        The report, ending in a newline. The same results always give the same text.
    """
    ordered = tuple(results)
    lines = [
        "# Upstream report",
        "",
        summary_line(ordered),
        "",
        "This report records what each upstream repository shows. Writing it changes no book.",
    ]
    for classification, title in _SECTIONS:
        lines += ["", f"## {title}", ""]
        section = [result for result in ordered if result.classification is classification]
        if not section:
            lines.append("None.")
        for result in section:
            lines += _result_lines(result)
    return "\n".join(lines) + "\n"


def sync_library(root: Path, client: GitHubClient) -> SyncRun:
    """Check every book of a library against its upstream. Nothing is written.

    Args:
        root: The library root, which is the directory that holds ``catalog.yaml``.
        client: The client to read GitHub through.

    Returns:
        The run.

    Raises:
        LoadError: The catalog or a book's metadata cannot be read or is invalid.
        StateError: The state file exists and is not one this module wrote.
    """
    catalog = load_catalog(root)
    resources = [load_resource(root, resource_id) for resource_id in catalog.resources]
    previous = load_state(root / UPSTREAM_DIR / STATE_FILE)
    return check_books(resources, previous, client)


def write_run(root: Path, run: SyncRun) -> None:
    """Write a run's state file and report under the library's ``upstream`` directory.

    Args:
        root: The library root.
        run: The run to write.
    """
    directory = root / UPSTREAM_DIR
    directory.mkdir(exist_ok=True)
    (directory / STATE_FILE).write_text(render_state(run.state), encoding="utf-8")
    (directory / REPORT_FILE).write_text(render_report(run.results), encoding="utf-8")


def _observe(
    client: GitHubClient, resource: Resource, source: GitSource, previous: BookState | None
) -> tuple[BookState, str | None]:
    """Read one repository and return its new state entry with a report sentence, if any."""
    try:
        head = client.branch_head(source.repository, source.default_branch)
    except NotFoundError:
        gone = (
            f"GitHub found nothing for the branch `{source.default_branch}`. The repository or "
            "the branch was deleted, renamed, or made private."
        )
        return BookState(Classification.GONE, None, ()), gone
    # A person verified the metadata at this commit, so there is nothing to compare. This also
    # clears findings once the metadata has caught up with what they reported.
    if head == source.head_commit:
        return BookState(Classification.UNCHANGED, head, ()), None
    if previous is not None and head == previous.head_commit:
        return previous, None

    info = client.repository(source.repository)
    tree = client.tree(source.repository, head)
    readme: str | None = None
    if resource.license.evidence is EvidenceKind.README_STATEMENT and any(
        entry.path == README_PATH for entry in tree
    ):
        readme = client.file_text(source.repository, head, README_PATH)
    findings = compare(resource, info.full_name, tree, readme)

    if any(finding.kind is FindingKind.REPOSITORY_RENAMED for finding in findings):
        classification = Classification.MOVED
    elif findings:
        classification = Classification.CHANGED
    else:
        classification = Classification.UNCHANGED
    return BookState(classification, head, findings), None


def _license_findings(
    resource: Resource, tree: tuple[TreeEntry, ...], readme: str | None
) -> list[Finding]:
    recorded = resource.license
    # Only a file at the root of the repository speaks for the whole repository.
    license_files = [
        entry for entry in tree if "/" not in entry.path and LICENSE_FILE_PATTERN.match(entry.path)
    ]
    findings: list[Finding] = []
    if recorded.evidence is EvidenceKind.LICENSE_FILE:
        different = [entry for entry in license_files if entry.blob_sha != recorded.blob_sha]
        if not license_files:
            findings.append(Finding(kind=FindingKind.LICENSE_FILE_MISSING))
        else:
            # While one file still holds the recorded text, any other license file is a second
            # set of terms beside it, which could cover the book's text differently.
            kind = (
                FindingKind.LICENSE_FILE_CHANGED
                if len(different) == len(license_files)
                else FindingKind.LICENSE_FILE_ADDITIONAL
            )
            findings += [
                Finding(kind, path=entry.path, blob_sha=entry.blob_sha) for entry in different
            ]
    else:
        findings += [
            Finding(FindingKind.LICENSE_FILE_ADDED, path=entry.path, blob_sha=entry.blob_sha)
            for entry in license_files
        ]
    if recorded.evidence is EvidenceKind.README_STATEMENT and not _holds(
        readme, recorded.statement
    ):
        findings.append(Finding(kind=FindingKind.STATEMENT_NOT_FOUND, path=README_PATH))
    return findings


def _holds(readme: str | None, statement: str | None) -> bool:
    """Say whether a README still carries a recorded statement.

    A statement is recorded as the README's lines with surrounding whitespace removed and joined
    by newlines, so the README is put in the same form before the search.
    """
    if readme is None or statement is None:
        return False
    stripped = "\n".join(line.strip() for line in readme.split("\n"))
    return statement.strip() in stripped


def _edition_findings(resource: Resource, tree: tuple[TreeEntry, ...]) -> list[Finding]:
    recorded = {edition.path: edition for edition in resource.editions}
    languages = {edition.language for edition in resource.editions}
    newest = {edition.language: edition.version for edition in resource.newest_editions}
    # The empty name is the top level of the repository.
    directories = {""} | {posixpath.dirname(path) for path in recorded}

    findings: list[Finding] = []
    for entry in tree:
        directory, name = posixpath.split(entry.path)
        if directory not in directories:
            continue
        if posixpath.splitext(name)[1].lower() not in EDITION_SUFFIXES:
            continue
        known = recorded.get(entry.path)
        if known is not None:
            if known.blob_sha != entry.blob_sha:
                findings.append(
                    Finding(FindingKind.CHANGED_BYTES, path=entry.path, blob_sha=entry.blob_sha)
                )
            continue
        findings.append(_new_file_finding(resource, entry, name, languages, newest))
    return findings


def _new_file_finding(
    resource: Resource,
    entry: TreeEntry,
    name: str,
    languages: set[str],
    newest: Mapping[str, str],
) -> Finding:
    """Classify an edition file whose path the metadata does not record."""
    for pattern in resource.edition_patterns:
        match = re.search(pattern.pattern, name)
        if match is None:
            continue
        version = match.group("version")
        if pattern.language not in languages:
            return Finding(
                FindingKind.NEW_TRANSLATION,
                path=entry.path,
                blob_sha=entry.blob_sha,
                language=pattern.language,
                version=version,
            )
        recorded_version = newest.get(pattern.language)
        return Finding(
            FindingKind.NEW_EDITION,
            path=entry.path,
            blob_sha=entry.blob_sha,
            language=pattern.language,
            version=version,
            recorded_version=recorded_version,
            comparison=_compare_versions(version, recorded_version),
        )
    return Finding(FindingKind.UNCLASSIFIED_FILE, path=entry.path, blob_sha=entry.blob_sha)


def _compare_versions(version: str, recorded: str | None) -> VersionComparison:
    if version == recorded:
        return VersionComparison.SAME
    new, old = version_key(version), version_key(recorded or "")
    # A version with no digits cannot be ordered, and neither can one that is not above the
    # recorded one, since upstream uses both dotted and date-style versions.
    if new and old and new > old:
        return VersionComparison.NEWER
    return VersionComparison.DIFFERENT


def _finding_record(finding: Finding) -> dict[str, str]:
    record = {"kind": finding.kind.value}
    for field in ("path", "blob_sha", "language", "version", "recorded_version", "repository"):
        value = getattr(finding, field)
        if value is not None:
            record[field] = value
    if finding.comparison is not None:
        record["comparison"] = finding.comparison.value
    return record


def _book_state(entry: dict[str, Any]) -> BookState:
    return BookState(
        classification=Classification(entry["classification"]),
        head_commit=entry["head_commit"],
        findings=tuple(_finding(record) for record in entry["findings"]),
    )


def _finding(record: dict[str, Any]) -> Finding:
    comparison = record.get("comparison")
    return Finding(
        kind=FindingKind(record["kind"]),
        path=record.get("path"),
        blob_sha=record.get("blob_sha"),
        language=record.get("language"),
        version=record.get("version"),
        recorded_version=record.get("recorded_version"),
        comparison=None if comparison is None else VersionComparison(comparison),
        repository=record.get("repository"),
    )


def _result_lines(result: BookResult) -> list[str]:
    line = f"- `{result.resource_id}` ({result.source})"
    state = result.state
    if result.message is None:
        head = None if state is None else state.head_commit
        lines = [line if head is None else f"{line} at {_code(head)}"]
    elif result.classification is Classification.ERROR and state is not None:
        lines = [f"{line}: {_one_line(result.message)} {_ENTRY_KEPT}"]
    else:
        lines = [f"{line}: {_one_line(result.message)}"]
    if state is not None:
        lines += [f"  - {_describe(finding)}" for finding in state.findings]
    return lines


def _describe(finding: Finding) -> str:
    """Write one finding as a sentence for the report."""
    file = f"{_code(finding.path)} (blob {_code(finding.blob_sha)})"
    match finding.kind:
        case FindingKind.REPOSITORY_RENAMED:
            text = f"The repository now answers as {_code(finding.repository)}."
        case FindingKind.LICENSE_FILE_CHANGED:
            text = (
                f"The license file {_code(finding.path)} changed. "
                f"Its blob is now {_code(finding.blob_sha)}."
            )
        case FindingKind.LICENSE_FILE_MISSING:
            text = "The recorded license file is no longer in the repository."
        case FindingKind.LICENSE_FILE_ADDITIONAL:
            text = f"Another license file is present beside the recorded one: {file}."
        case FindingKind.LICENSE_FILE_ADDED:
            text = f"A license file was added at {file}. The record has none."
        case FindingKind.STATEMENT_NOT_FOUND:
            text = f"The recorded license statement no longer appears in {_code(finding.path)}."
        case FindingKind.NEW_EDITION:
            text = f"{_describe_new_edition(finding)}: {file}."
        case FindingKind.NEW_TRANSLATION:
            text = (
                f"New translation in {_code(finding.language)} at version "
                f"{_code(finding.version)}: {file}."
            )
        case FindingKind.CHANGED_BYTES:
            text = f"New bytes under a known filename: {file}."
        case FindingKind.UNCLASSIFIED_FILE:
            text = f"Unclassified file that matches no edition pattern: {file}."
    return f"{LICENSE_FINDING_MARKER} {text}" if finding.kind in _LICENSE_KINDS else text


def _describe_new_edition(finding: Finding) -> str:
    edition = f"New {_code(finding.language)} edition {_code(finding.version)}"
    if finding.comparison is VersionComparison.NEWER:
        return f"{edition}, newer than the recorded {_code(finding.recorded_version)}"
    if finding.comparison is VersionComparison.SAME:
        return f"{edition}, the recorded version in a new file"
    if finding.recorded_version is None:
        return f"{edition}, with no recorded version to compare with"
    return f"{edition}, a different version from the recorded {_code(finding.recorded_version)}"


def _code(value: str | None) -> str:
    """Write a value that came from a GitHub answer as a Markdown code span it cannot close.

    The fence is one backtick longer than the longest run of backticks in the value, so no run in
    the value ends the span. A value that starts or ends with a backtick is padded with a space
    on each side, which Markdown removes again, so the value's backticks do not join the fence.
    A field that the finding's kind does not use is ``None`` and is written as an empty value.
    """
    text = _one_line(value or "")
    longest = max((len(run) for run in _BACKTICK_RUN.findall(text)), default=0)
    fence = "`" * (longest + 1)
    padding = " " if text.startswith("`") or text.endswith("`") else ""
    return f"{fence}{padding}{text}{padding}{fence}"


def _one_line(text: str) -> str:
    """Replace each character that is not printable, which covers every kind of line break.

    Markdown treats a line break inside a code span as a space only while the paragraph goes on,
    so a value with a line break could otherwise end its list item and start a block of its own.
    """
    return "".join(
        character if character.isprintable() else _REPLACEMENT_CHARACTER for character in text
    )
