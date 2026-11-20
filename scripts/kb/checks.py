"""Validation checks: what is wrong with a library, reported as findings.

A check is a function that takes a loaded library and returns findings. Every check is listed in
``CHECKS``, and ``run_checks`` loads a library, runs each check in order, and returns the findings
sorted so that two runs on the same files print the same lines.

To add a check, write a function with the ``Check`` signature and append it to ``CHECKS``.

A file that cannot be loaded is itself a finding. The other files are still checked, so a check
must expect a library that lacks some records. ``Library.resources`` holds only the resources
whose metadata loaded, while ``Catalog.resources`` still lists every cataloged id.
"""

import json
import re
from collections import defaultdict
from collections.abc import Callable, Iterator
from dataclasses import asdict, dataclass
from pathlib import Path

from kb.catalog import (
    BOOKS_DIR,
    CATALOG_FILE,
    METADATA_FILE,
    ChapterFile,
    Library,
    MirrorStatus,
    Resource,
    TopicFile,
    load_catalog,
    load_chapters,
    load_resource,
    load_topics,
)
from kb.fidelity import check_book
from kb.gate import evaluate
from kb.schema import LoadError, SchemaName

__all__ = ["CHECKS", "Check", "Finding", "run_checks"]

LICENSE_FILE = "LICENSE"

_LINK = re.compile(r"\]\(\s*([^)\s]+)[^)]*\)")
_CODE_FENCE = re.compile(r" {0,3}(`{3,}|~{3,})")
_NOT_A_FILE_LINK = ("http:", "https:", "mailto:", "#")


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


def _check_license_file(library: Library) -> list[Finding]:
    findings: list[Finding] = []
    for resource in library.resources:
        if resource.mirror_status is not MirrorStatus.MIRRORED:
            continue
        if not (library.root / BOOKS_DIR / resource.id / LICENSE_FILE).is_file():
            findings.append(
                Finding(
                    rule="gate-license-file",
                    file=f"{BOOKS_DIR}/{resource.id}/{LICENSE_FILE}",
                    message=f"The mirrored book {resource.id} has no {LICENSE_FILE} file.",
                    fix=(
                        "Add the upstream license text under this name, copied from the "
                        "permalink in the book's license record."
                    ),
                )
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
    """Report each relative link in a chapter or topic body whose target does not exist."""
    findings: list[Finding] = []
    documents: list[ChapterFile | TopicFile] = [*library.chapters, *library.topics]
    for document in documents:
        path = library.root / document.path
        # The body is the tail of the file, so the lines above it are the difference in length.
        lines_above = path.read_text(encoding="utf-8").count("\n") - document.body.count("\n")
        for index, target in _link_targets(document.body):
            if target.startswith(_NOT_A_FILE_LINK):
                continue
            target_file = target.partition("#")[0].partition("?")[0]
            if not (path.parent / target_file).exists():
                findings.append(
                    Finding(
                        rule="link-missing-target",
                        file=document.path.as_posix(),
                        line=lines_above + index + 1,
                        message=f"The link target {target} does not exist.",
                        fix=(
                            "Correct the path, which is read from the directory of this file, "
                            "or remove the link."
                        ),
                    )
                )
    return findings


def _link_targets(body: str) -> Iterator[tuple[int, str]]:
    """Yield the line index and target of each inline link outside fenced code blocks."""
    open_fence: str | None = None
    for index, line in enumerate(body.split("\n")):
        fence = _CODE_FENCE.match(line)
        if open_fence is None:
            if fence:
                open_fence = fence[1]
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
    return findings


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
]
"""Every check, in the order it runs. A new check is one more entry at the end."""
