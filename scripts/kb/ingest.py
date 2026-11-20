"""The ingestion pipeline: from a book's pinned source file to chapter files.

The stages run in this order, and each one can stop the run:

1. ``check_gate`` asks the license gate whether the book may be mirrored at all.
2. ``verify_source`` finds the committed source file and compares its SHA-256 with the metadata.
3. ``extract_book`` reads the file into spans and assembles the spans into sections.
4. ``kb.markdown.draft_chapters`` writes each section as a chapter draft.
5. ``write_drafts`` puts the drafts under ``build/ingest/<book>/``, which Git ignores.
6. ``write_chapters`` copies a draft into the book only where the book has no chapter with that
   id yet. An existing chapter is never overwritten. The run returns a diff for a person to
   apply by hand.

Every function takes the library root, so the same code runs on the real library and on a test
library.
"""

import difflib
import hashlib
import re
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from kb.blocks import Section, build_sections
from kb.catalog import BOOKS_DIR, CHAPTERS_DIR, METADATA_FILE, MirrorStatus, Resource
from kb.gate import evaluate
from kb.markdown import ChapterDraft
from kb.pdf_spans import PdfError, Span, read_pdf

__all__ = [
    "DRAFTS_DIR",
    "ExtractedBook",
    "IngestError",
    "WriteReport",
    "check_gate",
    "extract_book",
    "summary_lines",
    "verify_source",
    "write_chapters",
    "write_drafts",
]

DRAFTS_DIR = Path("build") / "ingest"
"""Directory under the library root that holds one directory of drafts per book."""

_CHAPTER_FILE = re.compile(r"\d+-(?P<slug>.+)\.md")


class IngestError(Exception):
    """A stage of ingestion cannot go on.

    Attributes:
        message: What is wrong, on one line.
        fix: What to do about it, on one line.
        file: The file at fault, relative to the library root, or ``None`` when no single file
            is at fault.
    """

    def __init__(self, message: str, fix: str, file: Path | None = None) -> None:
        """Build the error.

        Args:
            message: What is wrong, on one line.
            fix: What to do about it, on one line.
            file: The file at fault, relative to the library root.
        """
        self.message = message
        self.fix = fix
        self.file = file
        super().__init__(message)


@dataclass(frozen=True)
class ExtractedBook:
    """What one run of extraction read from a book's source file.

    Attributes:
        source: The source file, relative to the library root.
        page_count: Number of pages in the source file.
        sections: The sections in source order.
        unmatched: Spans of text that are in no section, each with its page and text.
    """

    source: Path
    page_count: int
    sections: tuple[Section, ...]
    unmatched: tuple[Span, ...]


@dataclass(frozen=True)
class WriteReport:
    """What ``write_chapters`` did with each draft.

    Attributes:
        created: Chapter files that were written, relative to the library root.
        unchanged: Existing chapter files that equal their draft.
        differing: Existing chapter files that differ from their draft, each with a unified
            diff from the file to the draft. The files were left as they are.
        unassigned: Drafts that were not written because their slug is only proposed.
    """

    created: tuple[Path, ...]
    unchanged: tuple[Path, ...]
    differing: tuple[tuple[Path, str], ...]
    unassigned: tuple[ChapterDraft, ...]


def check_gate(resource: Resource, allowlist: Sequence[str]) -> None:
    """Refuse a book that may not be ingested.

    A book may be ingested when the license gate allows it to be mirrored and its recorded
    status is eligible or mirrored. Nothing but the resource record is read.

    Args:
        resource: The book.
        allowlist: SPDX ids the catalog allows to be mirrored.

    Raises:
        IngestError: The gate refuses the book, or the book is recorded as reference-only.
    """
    decision = evaluate(resource, allowlist)
    metadata = _metadata(resource)
    if not decision.permits(MirrorStatus.MIRRORED):
        raise IngestError(
            f"The license gate does not allow {resource.id} to be mirrored. {decision.reason}",
            "Ingest only a book that passes the gate. Correct the license record if it is wrong.",
            metadata,
        )
    if resource.mirror_status is MirrorStatus.REFERENCE_ONLY:
        raise IngestError(
            f"The mirror_status of {resource.id} is reference-only.",
            "Set mirror_status to eligible once the owner has approved mirroring the book.",
            metadata,
        )


def verify_source(root: Path, resource: Resource) -> Path:
    """Find a book's committed source file and check its SHA-256 against the metadata.

    Args:
        root: The library root.
        resource: The book.

    Returns:
        The source file, relative to the library root.

    Raises:
        IngestError: The book records no pinned source or no local path, the file is missing or
            unreadable, or its SHA-256 differs from ``pinned_source.sha256``. A digest error
            gives both digests.
    """
    pinned = resource.pinned_source
    if pinned is None:
        raise IngestError(
            f"The book {resource.id} records no pinned_source, so it has no source file.",
            "Record the pinned source file under pinned_source in the metadata.",
            _metadata(resource),
        )
    if pinned.local_path is None:
        raise IngestError(
            f"The pinned_source.local_path of {resource.id} is null, so the book has no "
            "committed source file.",
            f"Put the pinned file under {BOOKS_DIR}/{resource.id}/source/ and set "
            "pinned_source.local_path to its path, such as source/<file name>.",
            _metadata(resource),
        )
    source = Path(BOOKS_DIR) / resource.id / pinned.local_path
    try:
        digest = hashlib.sha256((root / source).read_bytes()).hexdigest()
    except FileNotFoundError as error:
        raise IngestError(
            f"The source file {source.as_posix()} does not exist.",
            "Put the pinned file at that path, or correct pinned_source.local_path.",
            source,
        ) from error
    except OSError as error:
        raise IngestError(
            f"The source file {source.as_posix()} could not be read: {error}",
            "Make the file readable and run the command again.",
            source,
        ) from error
    if digest != pinned.sha256:
        raise IngestError(
            f"The source file {source.as_posix()} has the SHA-256 {digest}, and "
            f"pinned_source.sha256 records {pinned.sha256}.",
            "Restore the pinned file. If the pinned edition was replaced on purpose, record the "
            "new digest and compare every chapter with the new file.",
            source,
        )
    return source


def extract_book(root: Path, resource: Resource) -> ExtractedBook:
    """Verify a book's source file and read it into sections.

    Args:
        root: The library root.
        resource: The book.

    Returns:
        The sections, the page count, and the spans that are in no section.

    Raises:
        IngestError: The source file fails ``verify_source``, the book has no extraction
            profile, the profile's section-start pattern is not a valid regular expression, or
            the file cannot be read as a PDF.
    """
    source = verify_source(root, resource)
    profile = resource.extraction_profile
    if profile is None:
        raise IngestError(
            f"The book {resource.id} has no extraction_profile.",
            "Add an extraction_profile to the metadata with the role rules for the source file.",
            _metadata(resource),
        )
    try:
        pdf = read_pdf(root / source)
    except PdfError as error:
        raise IngestError(
            f"The source file {source.as_posix()} could not be read as a PDF: {error.reason}",
            "Replace the file with the pinned upstream PDF.",
            source,
        ) from error
    try:
        extraction = build_sections(pdf.spans, profile)
    except re.error as error:
        raise IngestError(
            f"The section_start pattern of {resource.id} is not a valid regular expression: "
            f"{error}",
            "Correct extraction_profile.section_start in the metadata.",
            _metadata(resource),
        ) from error
    return ExtractedBook(
        source=source,
        page_count=pdf.page_count,
        sections=extraction.sections,
        unmatched=extraction.unmatched,
    )


def write_drafts(root: Path, resource_id: str, drafts: Sequence[ChapterDraft]) -> Path:
    """Write chapter drafts to the book's draft directory, replacing the drafts of an earlier run.

    Args:
        root: The library root.
        resource_id: Id of the book.
        drafts: The drafts to write.

    Returns:
        The draft directory, relative to the library root.

    Raises:
        OSError: The directory or a file cannot be written.
    """
    directory = DRAFTS_DIR / resource_id
    (root / directory).mkdir(parents=True, exist_ok=True)
    # A section that was renumbered or renamed since the last run would leave its old draft.
    for stale in (root / directory).glob("*.md"):
        stale.unlink()
    for draft in drafts:
        _write(root / directory / draft.file_name, draft.text)
    return directory


def write_chapters(root: Path, resource_id: str, drafts: Sequence[ChapterDraft]) -> WriteReport:
    """Copy each draft into the book unless the book already has a chapter with its id.

    A chapter is found by the slug its file name ends with, whatever number the name starts
    with, because a chapter keeps its id when its order changes. An existing chapter file is
    never written to. A draft whose slug is only proposed is not written, because writing it
    would fix a chapter id that nobody has confirmed.

    Args:
        root: The library root.
        resource_id: Id of the book.
        drafts: The drafts, as ``write_drafts`` wrote them.

    Returns:
        What was created, what was left alone, and a diff for each existing chapter that
        differs from its draft.

    Raises:
        OSError: A chapter file cannot be read or written.
    """
    chapters = Path(BOOKS_DIR) / resource_id / CHAPTERS_DIR
    existing: dict[str, Path] = {}
    for path in sorted((root / chapters).glob("*.md")):
        named = _CHAPTER_FILE.fullmatch(path.name)
        if named:
            existing.setdefault(named["slug"], chapters / path.name)

    created: list[Path] = []
    unchanged: list[Path] = []
    differing: list[tuple[Path, str]] = []
    unassigned: list[ChapterDraft] = []
    for draft in drafts:
        current = existing.get(draft.slug)
        if current is not None:
            text = (root / current).read_bytes().decode("utf-8")
            if text == draft.text:
                unchanged.append(current)
            else:
                differing.append((current, _diff(text, draft, current, resource_id)))
        elif draft.slug_is_proposed:
            unassigned.append(draft)
        else:
            (root / chapters).mkdir(parents=True, exist_ok=True)
            _write(root / chapters / draft.file_name, draft.text)
            created.append(chapters / draft.file_name)
    return WriteReport(
        created=tuple(created),
        unchanged=tuple(unchanged),
        differing=tuple(differing),
        unassigned=tuple(unassigned),
    )


def summary_lines(
    resource: Resource, book: ExtractedBook, drafts: Sequence[ChapterDraft]
) -> list[str]:
    """Describe one extraction for a person: sections, pages, unmatched spans, proposed slugs.

    Args:
        resource: The book.
        book: What was extracted.
        drafts: The chapter drafts of the extracted sections.

    Returns:
        The lines to print.
    """
    excluded = resource.extraction_profile.excluded_pages if resource.extraction_profile else ()
    left_out = ", ".join(str(page) for page in sorted(excluded)) or "none"
    lines = [
        f"Source: {book.source.as_posix()}",
        f"Pages: {book.page_count}. Left out: {left_out}.",
        f"Sections found: {len(drafts)}",
    ]
    for draft in drafts:
        section = draft.section
        proposed = " (proposed slug)" if draft.slug_is_proposed else ""
        lines.append(
            f"  {draft.order:02d}  {section.label}  {section.title}  "
            f"pages {section.first_page}-{section.last_page}  {draft.slug}{proposed}"
        )
    lines.append(f"Unmatched spans: {len(book.unmatched)}")
    lines.extend(
        f"  page {span.page}, size {span.size:.1f}, indent {span.x:.1f}: {span.text.strip()!r}"
        for span in book.unmatched
    )
    if book.unmatched:
        lines.append(
            "  Unmatched text is in no chapter. Add a role rule for its font size to "
            "extraction_profile.roles, or list its page under excluded_pages."
        )
    proposals = [draft for draft in drafts if draft.slug_is_proposed]
    if proposals:
        lines.append(f"Proposed slugs: {len(proposals)}")
        lines.extend(f"  {draft.slug}  for  {draft.section.title}" for draft in proposals)
        lines.append(
            "  A proposed slug is not recorded. Add each section to extraction_profile.sections "
            f"in {_metadata(resource).as_posix()} with its title, slug, and part."
        )
    return lines


def _metadata(resource: Resource) -> Path:
    return Path(BOOKS_DIR) / resource.id / METADATA_FILE


def _write(path: Path, text: str) -> None:
    # Bytes are written so that a line ending is never translated and the drafts are the same
    # on every platform.
    path.write_bytes(text.encode("utf-8"))


def _diff(current_text: str, draft: ChapterDraft, current: Path, resource_id: str) -> str:
    return "".join(
        difflib.unified_diff(
            current_text.splitlines(keepends=True),
            draft.text.splitlines(keepends=True),
            fromfile=current.as_posix(),
            tofile=(DRAFTS_DIR / resource_id / draft.file_name).as_posix(),
        )
    )
