"""Validation checks: what is wrong with a library, reported as findings.

A check is a function that takes a loaded library and returns findings. Every check is listed in
``CHECKS``, and ``run_checks`` loads a library, runs each check in order, and returns the findings
sorted so that two runs on the same files print the same lines.

To add a check, write a function with the ``Check`` signature and append it to ``CHECKS``.

A file that cannot be loaded is itself a finding. The other files are still checked, so a check
must expect a library that lacks some records. ``Library.resources`` holds only the resources
whose metadata loaded, while ``Catalog.resources`` still lists every cataloged id.
"""

import hashlib
import json
import re
from collections import defaultdict
from collections.abc import Callable, Iterator
from dataclasses import asdict, dataclass
from pathlib import Path, PurePosixPath
from typing import Literal
from urllib.parse import urlsplit

from kb.catalog import (
    BOOKS_DIR,
    CATALOG_FILE,
    CHAPTERS_DIR,
    LICENSE_FILE,
    METADATA_FILE,
    TOPIC_INDEX_FILE,
    TOPICS_DIR,
    ChapterFile,
    EvidenceKind,
    GitSource,
    Library,
    MirrorStatus,
    Resource,
    TopicFile,
    load_catalog,
    load_chapters,
    load_resource,
    load_topics,
)
from kb.evidence import blob_permalink
from kb.fidelity import check_book
from kb.frontmatter import split_frontmatter
from kb.gate import evaluate
from kb.indexes import STALE_FIX, quote_permitted, stale_files
from kb.readpath import (
    CHAPTERS_INDEX,
    CODE_FENCE,
    QUOTE_LINE,
    RESOLVE_POINTER,
    ReadPathError,
    check_text,
    cited_ids,
    load_index,
    opening_fence,
)
from kb.schema import LoadError, SchemaName, parse_yaml, read_text

__all__ = ["CHECKS", "NO_COVERAGE_SENTENCE", "SCOPE_LABEL", "Check", "Finding", "run_checks"]

SCOPE_LABEL = "**Scope (editorial).**"
"""What the first paragraph of a topic body starts with. It marks the library's own words."""

NO_COVERAGE_SENTENCE = (
    "No mirrored chapter covers this topic yet, and the books listed below are read at their "
    "official sources."
)
"""The one paragraph that may stand without a citation in a topic with no mirrored chapter."""

_LINK = re.compile(r"\]\(\s*([^)\s]+)[^)]*\)")
_NOT_A_FILE_LINK = ("http:", "https:", "mailto:", "#")
_HEADING = re.compile(r" {0,3}#{1,6}(?:\s|$)")
_LIST_ITEM = re.compile(r"\s*(?:[-*+]|\d+[.)])\s+(.*)")
# A reading-list item that points somewhere and claims nothing is a link alone, or the
# instruction to resolve the id of a book whose text is not in the library.
_LINK_POINTER = re.compile(r"\[[^\]]*\]\([^)\s]+\)")
_EXCERPT_LENGTH = 80

# The canonical copy of each skill, which most agents read, and the directory one agent reads
# instead, which holds a link to each canonical folder.
_SKILLS_DIR = ".agents/skills"
_LINKED_SKILLS_DIR = ".claude/skills"
_SKILL_FILE = "SKILL.md"
_SKILL_KEYS = frozenset({"name", "description"})


@dataclass(frozen=True)
class Finding:
    """One thing that is wrong with a library.

    Attributes:
        rule: Short kebab-case id of the rule that was broken, such as ``gate-status``.
        file: Path of the file or directory at fault, relative to the library root, with forward
            slashes.
        message: What is wrong, on one line.
        fix: What to do about it, on one line.
        line: Line of the file the finding is about, counted from 1, or ``None`` when the
            finding is about the whole file.
    """

    rule: str
    file: str
    message: str
    fix: str
    line: int | None = None

    def to_text(self) -> str:
        """Format the finding as two lines for a person to read.

        Returns:
            ``[rule] file: message`` or ``[rule] file:line: message``, then a line that holds two
            spaces, ``fix:``, and the fix hint.
        """
        location = self.file if self.line is None else f"{self.file}:{self.line}"
        return f"[{self.rule}] {location}: {self.message}\n  fix: {self.fix}"

    def to_json(self) -> str:
        """Format the finding as one line of JSON.

        Returns:
            A JSON object with the keys ``rule``, ``file``, ``message``, ``fix``, and ``line``, in
            that order. ``line`` is ``null`` when the finding has no line.
        """
        return json.dumps(asdict(self), ensure_ascii=False)


type Check = Callable[[Library], list[Finding]]
"""A check takes a loaded library, which may lack records that failed to load."""


def run_checks(root: Path) -> list[Finding]:
    """Load the library at a root and run every registered check on it.

    A file that cannot be read, parsed, or validated becomes a finding, and the files that still
    load are checked. When the catalog itself cannot be loaded, that is the only finding.

    Args:
        root: The library root, which is the directory that holds ``catalog.yaml``.

    Returns:
        Every finding, sorted by file, then line, then rule. The list is empty for a library
        with nothing wrong.
    """
    library, findings = _load(root)
    if library is not None:
        for check in CHECKS:
            findings.extend(check(library))
    return sorted(
        findings,
        key=lambda finding: (finding.file, finding.line or 0, finding.rule, finding.message),
    )


def _load(root: Path) -> tuple[Library | None, list[Finding]]:
    """Load what can be loaded, and report each file that cannot as a finding."""
    try:
        catalog = load_catalog(root)
    except LoadError as error:
        return None, [_load_finding(root, error, "catalog")]

    findings: list[Finding] = []
    resources: list[Resource] = []
    chapters: list[ChapterFile] = []
    for resource_id in catalog.resources:
        # A cataloged id with no metadata file is reported once, by the catalog check.
        if (root / BOOKS_DIR / resource_id / METADATA_FILE).is_file():
            try:
                resources.append(load_resource(root, resource_id))
            except LoadError as error:
                findings.append(_load_finding(root, error, "resource"))
        try:
            chapters.extend(load_chapters(root, resource_id))
        except LoadError as error:
            findings.append(_load_finding(root, error, "chapter"))
    topics: tuple[TopicFile, ...] = ()
    try:
        topics = load_topics(root)
    except LoadError as error:
        findings.append(_load_finding(root, error, "topic"))

    library = Library(
        root=root,
        catalog=catalog,
        resources=tuple(resources),
        chapters=tuple(chapters),
        topics=topics,
    )
    return library, findings


def _load_finding(root: Path, error: LoadError, schema: SchemaName) -> Finding:
    where = f"{error.json_path}: " if error.json_path else ""
    return Finding(
        rule="invalid-file",
        file=error.path.relative_to(root).as_posix(),
        # A schema message can quote a multi-line value, and a finding's message is one line.
        message=" ".join(f"{where}{error.message}".split()),
        fix=f"Correct the file so that it parses and satisfies schemas/{schema}.schema.json.",
    )


def _metadata_path(resource_id: str) -> str:
    return f"{BOOKS_DIR}/{resource_id}/{METADATA_FILE}"


def _check_gate_status(library: Library) -> list[Finding]:
    findings: list[Finding] = []
    for resource in library.resources:
        decision = evaluate(resource, library.catalog.license_allowlist)
        if not decision.permits(resource.mirror_status):
            findings.append(
                Finding(
                    rule="gate-status",
                    file=_metadata_path(resource.id),
                    message=(
                        f"The mirror_status is {resource.mirror_status.value}, and the license "
                        f"gate allows {decision.allowed.value} at most. {decision.reason}"
                    ),
                    fix=(
                        f"Set mirror_status to {decision.allowed.value} and remove the book's "
                        "mirrored files, or correct the license record if it is wrong."
                    ),
                )
            )
    return findings


def _check_gate_content(library: Library) -> list[Finding]:
    """Report every file in the directory of a book that is not mirrored, except its metadata.

    This is the control that keeps unlicensed text out of the library, so it reads the directory
    on disk and does not trust what the loader happened to parse.
    """
    findings: list[Finding] = []
    for resource in library.resources:
        if resource.mirror_status is MirrorStatus.MIRRORED:
            continue
        book = library.root / BOOKS_DIR / resource.id
        # Path.walk does not follow symlinks and lists each one as a file, so a link to content
        # kept elsewhere is reported as well.
        for directory, _, file_names in book.walk():
            for file_name in file_names:
                path = directory / file_name
                if path == book / METADATA_FILE:
                    continue
                findings.append(
                    Finding(
                        rule="gate-content",
                        file=path.relative_to(library.root).as_posix(),
                        message=(
                            f"The file is in the directory of {resource.id}, whose mirror_status "
                            f"is {resource.mirror_status.value}. Only a mirrored book may hold "
                            f"anything besides {METADATA_FILE}."
                        ),
                        fix=(
                            "Remove the file. A book's files may be committed only after its "
                            "license record passes the gate and its mirror_status is mirrored."
                        ),
                    )
                )
    return findings


def _check_mirrored_book_files(library: Library) -> list[Finding]:
    """Report every file in a mirrored book's directory that its record does not account for.

    A mirrored book holds its metadata, its license file, its pinned source file, and one
    Markdown file per chapter. The license decision covers the pinned edition alone, so any
    other file, such as a second edition or a translation, is text nobody decided on. A
    symlink is reported wherever it sits, because its content is kept somewhere else.
    """
    findings: list[Finding] = []
    for resource in library.resources:
        if resource.mirror_status is not MirrorStatus.MIRRORED:
            continue
        book = library.root / BOOKS_DIR / resource.id
        expected = {book / METADATA_FILE, book / LICENSE_FILE}
        pinned = resource.pinned_source
        if pinned is not None and pinned.local_path is not None:
            expected.add(book / pinned.local_path)
        for directory, _, file_names in book.walk():
            for file_name in sorted(file_names):
                path = directory / file_name
                is_chapter = directory == book / CHAPTERS_DIR and path.suffix == ".md"
                if (path in expected or is_chapter) and not path.is_symlink():
                    continue
                findings.append(
                    Finding(
                        rule="book-unexpected-file",
                        file=path.relative_to(library.root).as_posix(),
                        message=(
                            f"The file is in the directory of the mirrored book {resource.id} "
                            f"and is not its {METADATA_FILE}, its {LICENSE_FILE}, its pinned "
                            f"source file, or a chapter under {CHAPTERS_DIR}/."
                        ),
                        fix=(
                            "Remove the file. A mirrored book holds only the pinned edition "
                            "that its license record was decided on."
                        ),
                    )
                )
    return findings


def _git_blob_id(data: bytes) -> str:
    """Return the id Git gives a file with these bytes, which is how a license record names it."""
    return hashlib.sha1(b"blob %d\0" % len(data) + data, usedforsecurity=False).hexdigest()


def _check_license_file(library: Library) -> list[Finding]:
    """Report each mirrored book whose license file is missing or is not the recorded one.

    Every export prints this file as the terms the book is offered under. The record names the
    upstream file by its Git blob id, so a file with other bytes is not the text that the
    license decision was made on.
    """
    findings: list[Finding] = []
    for resource in library.resources:
        if resource.mirror_status is not MirrorStatus.MIRRORED:
            continue
        file = f"{BOOKS_DIR}/{resource.id}/{LICENSE_FILE}"
        path = library.root / file
        if not path.is_file():
            findings.append(
                Finding(
                    rule="gate-license-file",
                    file=file,
                    message=f"The mirrored book {resource.id} has no {LICENSE_FILE} file.",
                    fix=(
                        "Add the upstream license text under this name, copied from the "
                        "permalink in the book's license record."
                    ),
                )
            )
            continue
        recorded = resource.license.blob_sha
        found = _git_blob_id(path.read_bytes())
        if found != recorded:
            findings.append(
                Finding(
                    rule="gate-license-file",
                    file=file,
                    message=(
                        f"The file has the Git blob id {found}, and license.blob_sha in "
                        f"{_metadata_path(resource.id)} records {recorded}."
                    ),
                    fix=(
                        "Restore the file byte for byte from the permalink in the book's "
                        "license record. If upstream changed its license, capture the evidence "
                        "again and have the owner review the record."
                    ),
                )
            )
    return findings


def _check_license_evidence(library: Library) -> list[Finding]:
    """Report each record whose license evidence does not agree with the rest of the record.

    The gate compares ``license.commit`` with the pinned source commit and reads nothing else of
    the evidence. The permalink is what a person opened and what the site prints as the proof,
    so it must be the link to a file of the upstream repository at the recorded commit. A link
    to a fork, to another commit, or to another host is evidence about something else. A
    pinned source in another repository than upstream is text the evidence does not cover, and
    a license file is not a README.

    A record with no evidence, or with an upstream that is not a Git repository, holds none of
    these fields to compare.
    """
    findings: list[Finding] = []
    for resource in library.resources:
        terms = resource.license
        upstream = resource.upstream
        if terms.evidence is EvidenceKind.NONE or not isinstance(upstream, GitSource):
            continue
        problems: list[str] = []
        if terms.permalink is not None and terms.commit is not None:
            expected = blob_permalink(upstream.repository, terms.commit, "")
            if not terms.permalink.startswith(expected):
                problems.append(
                    f"license.permalink is {terms.permalink}, and a file of upstream.repository "
                    f"at license.commit has a link that starts with {expected}"
                )
            elif terms.evidence is EvidenceKind.LICENSE_FILE and PurePosixPath(
                urlsplit(terms.permalink).path
            ).name.lower().startswith("readme"):
                problems.append(
                    "license.evidence is license-file, and license.permalink names a README: "
                    f"{terms.permalink}"
                )
        pinned = resource.pinned_source
        if pinned is not None and pinned.repository != upstream.repository:
            problems.append(
                f"pinned_source.repository is {pinned.repository}, and upstream.repository is "
                f"{upstream.repository}"
            )
        findings.extend(
            Finding(
                rule="gate-evidence",
                file=_metadata_path(resource.id),
                message=f"The license evidence of {resource.id} contradicts itself. {problem}.",
                fix=(
                    "Capture the evidence again with scripts/evidence.py at the pinned commit, "
                    "copy the permalink, the commit, and the blob id from its output, and have "
                    "the owner review the record."
                ),
            )
            for problem in problems
        )
    return findings


def _check_catalog_consistency(library: Library) -> list[Finding]:
    """Report where the catalog, the book directories, and the collections disagree."""
    findings: list[Finding] = []
    catalog = library.catalog
    for resource_id in catalog.resources:
        if not (library.root / BOOKS_DIR / resource_id / METADATA_FILE).is_file():
            findings.append(
                Finding(
                    rule="catalog-missing-book",
                    file=CATALOG_FILE,
                    message=(
                        f"The catalog lists {resource_id}, and {_metadata_path(resource_id)} "
                        "does not exist."
                    ),
                    fix=(
                        "Create that metadata file, or remove the id from the resources list "
                        f"in {CATALOG_FILE}."
                    ),
                )
            )

    books = library.root / BOOKS_DIR
    if books.is_dir():
        for directory in books.iterdir():
            if directory.is_dir() and directory.name not in catalog.resources:
                findings.append(
                    Finding(
                        rule="catalog-unlisted-book",
                        file=f"{BOOKS_DIR}/{directory.name}",
                        message=(f"The directory is not listed under resources in {CATALOG_FILE}."),
                        fix=(
                            f"Add {directory.name} to the resources list in {CATALOG_FILE}, or "
                            "remove the directory."
                        ),
                    )
                )

    declared = [collection.id for collection in catalog.collections]
    for resource in library.resources:
        if resource.collection not in declared:
            findings.append(
                Finding(
                    rule="catalog-unknown-collection",
                    file=_metadata_path(resource.id),
                    message=(
                        f"The collection {resource.collection} is not declared in "
                        f"{CATALOG_FILE}, which declares: {', '.join(declared)}."
                    ),
                    fix=(
                        f"Set collection to a declared id, or add the collection to {CATALOG_FILE}."
                    ),
                )
            )
    return findings


def _check_duplicate_chapter_ids(library: Library) -> list[Finding]:
    files_by_id: defaultdict[str, list[str]] = defaultdict(list)
    for chapter_file in library.chapters:
        files_by_id[chapter_file.chapter.id].append(chapter_file.path.as_posix())
    return [
        Finding(
            rule="chapter-duplicate-id",
            file=files[0],
            message=(
                f"The chapter id {chapter_id} is used by {len(files)} files: {', '.join(files)}."
            ),
            fix="Change the id in every file but one, so that each chapter id names one file.",
        )
        for chapter_id, files in files_by_id.items()
        if len(files) > 1
    ]


def _check_chapter_order(library: Library) -> list[Finding]:
    """Report each chapters directory whose order values are not exactly 1 to n."""
    # Chapters are grouped by the directory they sit in. A chapter whose frontmatter names
    # another resource is a separate finding and must not hide a gap here.
    orders_by_directory: defaultdict[str, list[int]] = defaultdict(list)
    for chapter_file in library.chapters:
        orders_by_directory[chapter_file.path.parent.as_posix()].append(chapter_file.chapter.order)
    findings: list[Finding] = []
    for directory, orders in orders_by_directory.items():
        expected = list(range(1, len(orders) + 1))
        if sorted(orders) != expected:
            findings.append(
                Finding(
                    rule="chapter-order",
                    file=directory,
                    message=(
                        f"The chapter order values are {_listed(sorted(orders))}, and they must "
                        f"be {_listed(expected)}."
                    ),
                    fix=(
                        "Renumber the order field of the chapters, and the number each file "
                        f"name starts with, to run from 1 to {len(orders)} with no gap and no "
                        "repeat."
                    ),
                )
            )
    return findings


def _listed(numbers: list[int]) -> str:
    return ", ".join(str(number) for number in numbers)


def _check_chapter_location(library: Library) -> list[Finding]:
    """Report each chapter whose file name or directory disagrees with its frontmatter."""
    findings: list[Finding] = []
    for chapter_file in library.chapters:
        chapter = chapter_file.chapter
        file = chapter_file.path.as_posix()
        expected_name = f"{chapter.order:02d}-{chapter.slug}.md"
        if chapter_file.path.name != expected_name:
            findings.append(
                Finding(
                    rule="chapter-filename",
                    file=file,
                    message=(
                        f"The file name must be {expected_name}, from the order {chapter.order} "
                        f"and the id {chapter.id} in the frontmatter."
                    ),
                    fix=(
                        "Rename the file, or correct the order in the frontmatter. Change the "
                        "id only if it has never been published."
                    ),
                )
            )
        directory = chapter_file.path.parent.parent.name
        if chapter.resource != directory:
            findings.append(
                Finding(
                    rule="chapter-resource",
                    file=file,
                    message=(
                        f"The frontmatter names the resource {chapter.resource}, and the file "
                        f"is in the directory of {directory}."
                    ),
                    fix=(
                        f"Move the file to {BOOKS_DIR}/{chapter.resource}/chapters/, or correct "
                        "the resource and the id in the frontmatter."
                    ),
                )
            )
    return findings


def _check_links(library: Library) -> list[Finding]:
    """Report each relative link whose target does not exist.

    The links of every chapter body, every topic body, and the topic landing page are checked.
    """
    findings: list[Finding] = []
    documents: list[ChapterFile | TopicFile] = [*library.chapters, *library.topics]
    pages = [
        (document.path, document.body, _lines_above(library, document)) for document in documents
    ]
    landing_page = _landing_page(library)
    if landing_page is not None:
        pages.append((*landing_page, 0))
    for page, body, lines_above in pages:
        directory = (library.root / page).parent
        for index, target in _link_targets(body):
            if target.startswith(_NOT_A_FILE_LINK):
                continue
            target_file = target.partition("#")[0].partition("?")[0]
            if not (directory / target_file).exists():
                findings.append(
                    Finding(
                        rule="link-missing-target",
                        file=page.as_posix(),
                        line=lines_above + index + 1,
                        message=f"The link target {target} does not exist.",
                        fix=(
                            "Correct the path, which is read from the directory of this file, "
                            "or remove the link."
                        ),
                    )
                )
    return findings


def _landing_page(library: Library) -> tuple[Path, str] | None:
    """Return the path and the text of the topic landing page, or ``None`` when there is none.

    The landing page is not a topic document and has no frontmatter, so the whole file is its
    body and its first line is line 1.
    """
    path = Path(TOPICS_DIR) / TOPIC_INDEX_FILE
    if not (library.root / path).is_file():
        return None
    return path, (library.root / path).read_text(encoding="utf-8")


def _lines_above(library: Library, document: ChapterFile | TopicFile) -> int:
    """Count the lines of a file that come before its body, which is the tail of the file."""
    text = (library.root / document.path).read_text(encoding="utf-8")
    return text.count("\n") - document.body.count("\n")


def _link_targets(body: str) -> Iterator[tuple[int, str]]:
    """Yield the line index and target of each inline link outside fenced code blocks."""
    open_fence: str | None = None
    for index, line in enumerate(body.split("\n")):
        fence = CODE_FENCE.match(line)
        if open_fence is None:
            open_fence = opening_fence(line)
            if open_fence is not None:
                continue
            for link in _LINK.finditer(line):
                yield index, link[1]
        # A block closes on a bare fence of the same character that is at least as long.
        elif fence and fence[1].startswith(open_fence) and not line[fence.end() :].strip():
            open_fence = None


def _check_fidelity(library: Library) -> list[Finding]:
    """Compare each chapter of a mirrored book with a fresh extraction of its source file.

    A mirrored book must hold its pinned source file, because the comparison runs offline. A
    source file that is not recorded, is missing, or has another SHA-256 than the metadata is
    one finding, and no chapter of that book is compared.

    The frontmatter of a chapter is compared too, because the indexes and every citation are
    written from it. A chapter with a field that is not what the pinned source and the
    extracted section give is one finding, which names every such field.

    Text of the source that fits no role rule is in no section, so every chapter can match its
    section while part of the book is left out. That is one finding for the book.
    """
    findings: list[Finding] = []
    for resource in library.resources:
        if resource.mirror_status is not MirrorStatus.MIRRORED:
            continue
        chapters = library.chapters_of(resource.id)
        report = check_book(library.root, resource, chapters)
        if report.error is not None:
            file = report.error.file
            findings.append(
                Finding(
                    rule="fidelity-source",
                    file=_metadata_path(resource.id) if file is None else file.as_posix(),
                    message=report.error.message,
                    fix=report.error.fix,
                )
            )
            continue
        findings.extend(
            Finding(
                rule="fidelity-chapter",
                file=chapter_file.path.as_posix(),
                message=result.message,
                fix=(
                    "Restore the wording of the source in the chapter. If the chapter is right "
                    "and the extraction is wrong, list the words under accepted_differences in "
                    f"{_metadata_path(resource.id)} with the chapter id and a reason."
                ),
            )
            for chapter_file, result in zip(chapters, report.results, strict=True)
            if not result.passed
        )
        findings.extend(
            Finding(
                rule="fidelity-frontmatter",
                file=chapter_file.path.as_posix(),
                message=(
                    f"The frontmatter of the chapter {result.chapter} does not describe its "
                    f"source. In it, {'; '.join(result.frontmatter)}."
                ),
                fix=(
                    "Restore the value the pinned source gives. `uv run python "
                    f"scripts/ingest.py --book {resource.id}` writes each chapter with the "
                    f"right frontmatter to build/ingest/{resource.id}/. If the book moved to "
                    "a new edition, ingest that edition and do not edit the field alone."
                ),
            )
            for chapter_file, result in zip(chapters, report.results, strict=True)
            if result.frontmatter
        )
        findings.extend(
            Finding(
                rule="fidelity-missing-chapter",
                file=_metadata_path(resource.id),
                message=(
                    f'The source file of {resource.id} has the section "{title}", and no '
                    "chapter of the book holds it."
                ),
                fix=(
                    f"Run `uv run python scripts/ingest.py --book {resource.id} --write` to add "
                    "the chapter. A book is mirrored in full or not at all."
                ),
            )
            for title in report.missing
            # One chapter file that does not load keeps every chapter of its book out of the
            # library. That file is a finding of its own, and it would make every section
            # look as if it had no chapter.
            if _chapters_loaded(library, resource.id)
        )
        if report.unmatched:
            first = report.unmatched[0]
            findings.append(
                Finding(
                    rule="fidelity-unmatched-text",
                    file=_metadata_path(resource.id),
                    message=(
                        f"Text of the source file of {resource.id} fits no role rule in "
                        f"{len(report.unmatched)} places, so it is in no section and no chapter "
                        f"holds it. The first is on page {first.page}: {first.text.strip()!r}"
                    ),
                    fix=(
                        "Add a role rule for its font size to extraction_profile.roles, or list "
                        "its page under excluded_pages when the page is not part of the book's "
                        f"text. `uv run python scripts/ingest.py --book {resource.id}` prints "
                        "every span with its page, size, and indent."
                    ),
                )
            )
    return findings


def _check_index_freshness(library: Library) -> list[Finding]:
    """Report each committed generated file that is missing or is not what the build writes.

    The read commands trust the indexes, so an index that lags the library files would give an
    agent a wrong path, license, or edition.
    """
    return [
        Finding(
            rule="index-stale",
            file=stale.path,
            message=(
                "The generated file does not exist."
                if stale.missing
                else "The generated file differs from what the build writes for this library."
            ),
            fix=STALE_FIX,
        )
        for stale in stale_files(library)
    ]


def _check_topic_location(library: Library) -> list[Finding]:
    """Report each topic document whose file name is not its id."""
    findings: list[Finding] = []
    for topic_file in library.topics:
        expected_name = f"{topic_file.topic.id}.md"
        if topic_file.path.name != expected_name:
            findings.append(
                Finding(
                    rule="topic-filename",
                    file=topic_file.path.as_posix(),
                    message=(
                        f"The file name must be {expected_name}, from the id "
                        f"{topic_file.topic.id} in the frontmatter."
                    ),
                    fix="Rename the file, or correct the id in the frontmatter.",
                )
            )
    return findings


def _check_topic_references(library: Library) -> list[Finding]:
    """Report each topic reference that names an unknown book or a chapter that is not mirrored.

    A reference may name any cataloged book. It may name a chapter only when the book's text is
    in the library and the book has a chapter with that id.
    """
    allowlist = library.catalog.license_allowlist
    loaded = {resource.id: resource for resource in library.resources}
    findings: list[Finding] = []
    for topic_file in library.topics:
        topic = topic_file.topic
        file = topic_file.path.as_posix()
        for reference in topic.references:
            if reference.resource not in library.catalog.resources:
                findings.append(
                    Finding(
                        rule="topic-reference-resource",
                        file=file,
                        message=(
                            f"The topic {topic.id} references the resource "
                            f"{reference.resource}, which {CATALOG_FILE} does not list."
                        ),
                        fix=(
                            "Use the id of a cataloged resource, which is its directory name "
                            f"under {BOOKS_DIR}/, or remove the reference."
                        ),
                    )
                )
                continue
            resource = loaded.get(reference.resource)
            # A cataloged book whose metadata did not load is a finding of its own, and nothing
            # is known here about whether it is mirrored.
            if reference.chapter is None or resource is None:
                continue
            if not quote_permitted(resource, allowlist):
                findings.append(
                    Finding(
                        rule="topic-reference-not-mirrored",
                        file=file,
                        message=(
                            f"The topic {topic.id} references the chapter {reference.chapter} "
                            f"of {resource.id}, whose mirror_status is "
                            f"{resource.mirror_status.value}. A reference may name a chapter "
                            "only of a mirrored book that the license gate allows."
                        ),
                        fix=(
                            "Remove the chapter key, so that the reference names the book "
                            "alone and its text is read at the official source."
                        ),
                    )
                )
                continue
            chapter_ids = {
                chapter_file.chapter.id for chapter_file in library.chapters_of(resource.id)
            }
            # One chapter file that does not load keeps every chapter of its book out of the
            # library. That file is a finding of its own, and the ids of the book are not
            # known until it is corrected.
            if reference.chapter not in chapter_ids and _chapters_loaded(library, resource.id):
                findings.append(
                    Finding(
                        rule="topic-reference-chapter",
                        file=file,
                        message=(
                            f"The topic {topic.id} references the chapter {reference.chapter}, "
                            f"and {resource.id} has no chapter with that id."
                        ),
                        fix=(
                            f"Use a chapter id that {CHAPTERS_INDEX} lists for {resource.id}, "
                            "or remove the chapter key."
                        ),
                    )
                )
    return findings


def _chapters_loaded(library: Library, resource_id: str) -> bool:
    """Say whether every chapter file in a book's directory is among the loaded chapters."""
    loaded = {chapter_file.path for chapter_file in library.chapters}
    directory = library.root / BOOKS_DIR / resource_id / CHAPTERS_DIR
    return all(path.relative_to(library.root) in loaded for path in directory.glob("*.md"))


def _check_topic_citations(library: Library) -> list[Finding]:
    """Run the citation checker over the body of each topic document and the landing page.

    The checker reads the committed indexes, as ``scripts/check_citations.py`` does. Indexes
    that cannot be read, or that list a chapter file that is gone, are findings of the index
    freshness check, and the citations are checked once the indexes are rebuilt.
    """
    try:
        index = load_index(library.root)
    except ReadPathError:
        return []
    pages = [
        (topic_file.path, topic_file.body, _lines_above(library, topic_file))
        for topic_file in library.topics
    ]
    landing_page = _landing_page(library)
    if landing_page is not None:
        pages.append((*landing_page, 0))
    findings: list[Finding] = []
    for path, body, lines_above in pages:
        try:
            problems = check_text(index, body)
        except ReadPathError:
            continue
        findings.extend(
            Finding(
                rule="topic-citation",
                file=path.as_posix(),
                line=lines_above + problem.line,
                message=problem.message,
                fix=(
                    "Cite a mirrored chapter by an id that scripts/resolve.py prints, and copy "
                    "each quote from the chapter file word for word."
                ),
            )
            for problem in problems
        )
    return findings


_ParagraphKind = Literal["prose", "quote", "table", "code", "heading"]


@dataclass(frozen=True)
class _Paragraph:
    """One paragraph, list item, fenced block, or long heading of a topic page.

    Attributes:
        first: Index of its first line in the body, counted from 0.
        last: Index of its last line.
        text: Its lines joined by single spaces.
        kind: What it is. A ``quote`` is a run of lines that are all lines of a Markdown block
            quote, and a ``table`` is a run of lines that all open with a pipe. A ``code``
            paragraph is one fenced block with its fences. A ``heading`` is one heading line.
    """

    first: int
    last: int
    text: str
    kind: _ParagraphKind


def _paragraph(first: int, lines: list[str], kind: _ParagraphKind | None = None) -> _Paragraph:
    """Build a paragraph from its lines, and tell a quote and a table from prose by them."""
    if kind is None:
        kind = "prose"
        if all(QUOTE_LINE.match(line) for line in lines):
            kind = "quote"
        elif all(line.lstrip().startswith("|") for line in lines):
            kind = "table"
    return _Paragraph(
        first=first,
        last=first + len(lines) - 1,
        text=" ".join(" ".join(lines).split()),
        kind=kind,
    )


def _paragraphs(body: str) -> Iterator[_Paragraph]:
    """Split a topic page into paragraphs, where each list item is a paragraph of its own.

    A fenced block is one paragraph, and one that never closes runs to the end of the page. A
    heading is a paragraph only when it is longer than ``_EXCERPT_LENGTH`` characters, which is
    longer than a title and long enough to hold a statement. Text in either place is published
    like any other, so it is held to the same rule. Blank lines and shorter headings separate
    paragraphs and belong to none.
    """
    open_fence: str | None = None
    first = 0
    lines: list[str] = []
    for index, line in enumerate(body.split("\n")):
        if open_fence is not None:
            lines.append(line)
            fence = CODE_FENCE.match(line)
            # A block closes on a bare fence of the same character that is at least as long.
            if fence and fence[1].startswith(open_fence) and not line[fence.end() :].strip():
                yield _paragraph(first, lines, "code")
                open_fence = None
                lines = []
            continue
        opened = opening_fence(line)
        heading = _HEADING.match(line) is not None
        separator = opened is not None or heading or not line.strip()
        if lines and (separator or _LIST_ITEM.match(line)):
            yield _paragraph(first, lines)
            lines = []
        if opened is not None:
            open_fence = opened
            first = index
            lines = [line]
        elif heading:
            if len(line.strip()) > _EXCERPT_LENGTH:
                yield _paragraph(index, [line], "heading")
        elif line.strip():
            if not lines:
                first = index
            lines.append(line)
    if lines:
        yield _paragraph(first, lines, "code" if open_fence is not None else None)


def _is_pointer(paragraph: _Paragraph) -> bool:
    """Say whether a paragraph is a list item that only points at a chapter file or a book."""
    item = _LIST_ITEM.fullmatch(paragraph.text)
    if item is None:
        return False
    return bool(_LINK_POINTER.fullmatch(item[1]) or RESOLVE_POINTER.fullmatch(item[1]))


def _names_mirrored_chapter(cited_id: str, mirrored_chapters: set[str], unknown: set[str]) -> bool:
    """Say whether a cited id names a chapter of a book whose text may be quoted.

    Args:
        cited_id: The id a citation token names.
        mirrored_chapters: The ids of the loaded chapters of every book that may be quoted.
        unknown: The ids of the books that may be quoted and whose chapters did not all load.
    """
    resource_id, slash, _ = cited_id.partition("/")
    return cited_id in mirrored_chapters or (bool(slash) and resource_id in unknown)


def _uncited(
    paragraphs: list[_Paragraph], cited: set[int], exempt: Callable[[_Paragraph], bool]
) -> Iterator[_Paragraph]:
    """Yield each paragraph that holds no counted citation token and is not exempt.

    The token of a block quote may also sit on the first line of the next paragraph, which is
    where the citation checker accepts it. A fenced block takes its token there as well,
    because a token inside the block is an example and not a citation.

    Args:
        paragraphs: The paragraphs of one page, in order.
        cited: The lines of the page that hold a counted token, counted from 1.
        exempt: Says whether a paragraph may stand without a token.
    """
    for number, paragraph in enumerate(paragraphs):
        last = paragraph.last
        if paragraph.kind in ("quote", "code") and number + 1 < len(paragraphs):
            last = paragraphs[number + 1].first
        if cited.intersection(range(paragraph.first + 1, last + 2)):
            continue
        if not exempt(paragraph):
            yield paragraph


def _uncited_finding(
    file: str, line: int, where: str, paragraph: _Paragraph, may_stand: str
) -> Finding:
    """Build the finding for one paragraph that names no mirrored chapter."""
    excerpt = paragraph.text
    if len(excerpt) > _EXCERPT_LENGTH:
        excerpt = f"{excerpt[:_EXCERPT_LENGTH]}..."
    return Finding(
        rule="topic-uncited-paragraph",
        file=file,
        line=line,
        message=(
            f"A paragraph of {where} holds no citation token that names a mirrored chapter: "
            f"{excerpt}"
        ),
        fix=(
            "End the paragraph with a [cite:<chapter-id>] token for the mirrored chapter it "
            "draws on, or remove it. A token that names a book alone, or a book that is not "
            "mirrored, does not count. A fenced block takes its token on the next line that "
            f"has text, and a heading longer than {_EXCERPT_LENGTH} characters is read as a "
            f"paragraph, so shorten it. {may_stand}"
        ),
    )


def _check_topic_bodies(library: Library) -> list[Finding]:
    """Report each topic page that breaks the rule on what a topic may say in its own words.

    The first paragraph of a topic body is the scope statement and starts with ``SCOPE_LABEL``.
    Every other paragraph and list item holds a citation token that names a chapter of a book
    whose text may be quoted, with two exceptions. A list item that is only a link, or only the
    instruction to resolve a book id, points somewhere and claims nothing.
    ``NO_COVERAGE_SENTENCE`` may stand alone in a topic that references no mirrored chapter.

    A fenced block and a heading longer than ``_EXCERPT_LENGTH`` characters are paragraphs under
    this rule. The landing page ``topics/index.md`` is held to it too. Its first paragraph is
    the library's own introduction, and its table rows and pointer list items stand without a
    token.

    A token that names a book alone does not count, and neither does a token for a book that is
    not mirrored, because a paragraph could then report what a book says with no chapter in the
    library to hold it to.
    """
    allowlist = library.catalog.license_allowlist
    quotable = {
        resource.id for resource in library.resources if quote_permitted(resource, allowlist)
    }
    mirrored_chapters = {
        chapter_file.chapter.id
        for resource_id in quotable
        for chapter_file in library.chapters_of(resource_id)
    }
    # One chapter file that does not load keeps every chapter of its book out of the library.
    # That file is a finding of its own, and until it is corrected any chapter id of the book
    # is taken as one of its chapters.
    unknown = {
        resource_id for resource_id in quotable if not _chapters_loaded(library, resource_id)
    }

    def cited_lines(body: str) -> set[int]:
        return {
            line
            for line, ids in cited_ids(body).items()
            if any(
                _names_mirrored_chapter(cited_id, mirrored_chapters, unknown) for cited_id in ids
            )
        }

    findings: list[Finding] = []
    for topic_file in library.topics:
        topic = topic_file.topic
        file = topic_file.path.as_posix()
        lines_above = _lines_above(library, topic_file)
        covered = any(
            reference.chapter and reference.resource in quotable for reference in topic.references
        )
        paragraphs = list(_paragraphs(topic_file.body))
        # A long heading above the scope statement is a paragraph, and it is not the statement.
        scope = next((paragraph for paragraph in paragraphs if paragraph.kind != "heading"), None)
        if scope is None or not scope.text.startswith(SCOPE_LABEL):
            findings.append(
                Finding(
                    rule="topic-scope",
                    file=file,
                    line=lines_above + scope.first + 1 if scope else None,
                    message=(
                        f"The body of the topic {topic.id} does not open with its scope "
                        f"statement, which is a paragraph that starts with {SCOPE_LABEL}"
                    ),
                    fix=(
                        f"Start the first paragraph below the title with {SCOPE_LABEL} and "
                        "define the topic there in two or three sentences of the library's own "
                        "words."
                    ),
                )
            )

        def stands(
            paragraph: _Paragraph, scope: _Paragraph | None = scope, covered: bool = covered
        ) -> bool:
            if paragraph is scope or _is_pointer(paragraph):
                return True
            return paragraph.text == NO_COVERAGE_SENTENCE and not covered

        findings.extend(
            _uncited_finding(
                file,
                lines_above + paragraph.first + 1,
                f"the topic {topic.id} after its scope statement",
                paragraph,
                "A list item may stand without a token only as a link alone or as the resolve "
                "instruction for a book id.",
            )
            for paragraph in _uncited(paragraphs, cited_lines(topic_file.body), stands)
        )
    landing_page = _landing_page(library)
    if landing_page is not None:
        path, body = landing_page
        paragraphs = list(_paragraphs(body))
        first = next((paragraph for paragraph in paragraphs if paragraph.kind == "prose"), None)
        findings.extend(
            _uncited_finding(
                path.as_posix(),
                paragraph.first + 1,
                "the topic landing page after its first",
                paragraph,
                "On the landing page a table row may stand without a token, and so may a list "
                "item that is a link alone or the resolve instruction for a book id.",
            )
            for paragraph in _uncited(
                paragraphs,
                cited_lines(body),
                lambda paragraph: (
                    paragraph is first or paragraph.kind == "table" or _is_pointer(paragraph)
                ),
            )
        )
    return findings


def _check_skill_exposure(library: Library) -> list[Finding]:
    """Report where the two skill directories differ, and each skill file with a wrong header.

    A skill is a folder under ``.agents/skills/`` that holds a ``SKILL.md``. Each one needs a
    link of the same name under ``.claude/skills/`` that resolves to the folder, so that every
    agent finds the same skills. The frontmatter of a skill file holds ``name``, which equals the
    folder name, and ``description``, and no other key.

    A library with no ``.agents/skills/`` directory ships no skills, and nothing is checked.
    """
    canonical = library.root / _SKILLS_DIR
    if not canonical.is_dir():
        return []
    linked = library.root / _LINKED_SKILLS_DIR
    names = sorted(path.name for path in canonical.iterdir() if path.is_dir())
    findings: list[Finding] = []
    for name in names:
        problem = _skill_file_problem(canonical / name / _SKILL_FILE, name)
        if problem is not None:
            findings.append(
                Finding(
                    rule="skill-exposure",
                    file=f"{_SKILLS_DIR}/{name}/{_SKILL_FILE}",
                    message=problem,
                    fix=(
                        f"Open the file with a frontmatter block that holds name: {name} and a "
                        "description, and no other key."
                    ),
                )
            )
        if (linked / name).resolve() != (canonical / name).resolve():
            findings.append(
                Finding(
                    rule="skill-exposure",
                    file=f"{_LINKED_SKILLS_DIR}/{name}",
                    message=(
                        f"The path is not a link that resolves to {_SKILLS_DIR}/{name}, so an "
                        f"agent that reads only {_LINKED_SKILLS_DIR}/ does not find the skill."
                    ),
                    fix=(
                        "Remove whatever is at the path, then run this from the library root: "
                        f"ln -s ../../{_SKILLS_DIR}/{name} {_LINKED_SKILLS_DIR}/{name}"
                    ),
                )
            )
    if linked.is_dir():
        # A plain file here, such as one the operating system leaves behind, exposes no skill.
        exposed = sorted(
            path.name for path in linked.iterdir() if path.is_symlink() or path.is_dir()
        )
        findings.extend(
            Finding(
                rule="skill-exposure",
                file=f"{_LINKED_SKILLS_DIR}/{name}",
                message=f"The entry has no skill folder of the same name under {_SKILLS_DIR}/.",
                fix=f"Remove the entry, or add the skill as {_SKILLS_DIR}/{name}/{_SKILL_FILE}.",
            )
            for name in exposed
            if name not in names
        )
    return findings


def _skill_file_problem(path: Path, name: str) -> str | None:
    """Say what is wrong with the frontmatter of a skill file, or return ``None``."""
    try:
        frontmatter, _ = split_frontmatter(read_text(path))
        header = parse_yaml(frontmatter, path)
    except LoadError as error:
        return " ".join(error.message.split())
    except ValueError as error:
        return f"The frontmatter could not be found. {error}"
    if not isinstance(header, dict):
        return "The frontmatter is not a mapping of keys to values."
    keys = {str(key) for key in header}
    if keys != _SKILL_KEYS:
        return (
            f"The frontmatter holds the keys {', '.join(sorted(keys)) or 'none'}, and it must "
            "hold exactly name and description."
        )
    if header["name"] != name:
        return f"The frontmatter names the skill {header['name']}, and its folder is {name}."
    return None


CHECKS: list[Check] = [
    _check_gate_status,
    _check_gate_content,
    _check_license_file,
    _check_catalog_consistency,
    _check_duplicate_chapter_ids,
    _check_chapter_order,
    _check_chapter_location,
    _check_links,
    _check_fidelity,
    _check_index_freshness,
    _check_topic_location,
    _check_topic_references,
    _check_topic_citations,
    _check_topic_bodies,
    _check_skill_exposure,
    _check_mirrored_book_files,
    _check_license_evidence,
]
"""Every check, in the order it runs. A new check is one more entry at the end."""
