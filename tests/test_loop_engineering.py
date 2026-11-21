"""Loop Engineering is mirrored as nine chapters that match the pinned English PDF."""

import hashlib
import itertools
import re
from pathlib import Path

import pytest
from kb.catalog import ChapterFile, Library, MirrorStatus, Resource, load_library
from kb.fidelity import check_book
from kb.frontmatter import ExtractionStatus

BOOK_ID = "loop-engineering-orange-book"
BOOK = Path("books") / BOOK_ID
PINNED_COMMIT = "829aa6084cd68680e7f389bbde9dcaebda7a43e6"
PINNED_PATH = "Loop-Engineering-The-Complete-Guide-v260615.pdf"
FIRST_SECTION_PAGE = 3
LAST_SECTION_PAGE = 35

_FENCED_BLOCK = re.compile(r"^```[^\n]*\n(?P<code>.*?)^```[ \t]*$", re.MULTILINE | re.DOTALL)
_TABLE_SEPARATOR = re.compile(r"\|(?:\s*:?-+:?\s*\|)+")


@pytest.fixture(scope="module")
def library(repo_root: Path) -> Library:
    return load_library(repo_root)


@pytest.fixture(scope="module")
def book(library: Library) -> Resource:
    return library.resource(BOOK_ID)


@pytest.fixture(scope="module")
def chapters(library: Library) -> tuple[ChapterFile, ...]:
    return library.chapters_of(BOOK_ID)


def _chapter_labeled(chapters: tuple[ChapterFile, ...], label: str) -> ChapterFile:
    (found,) = [file for file in chapters if file.chapter.section_label == label]
    return found


def _tables(body: str) -> list[list[list[str]]]:
    """Return each pipe table of a Markdown body as its body rows, each row a list of cells."""
    tables: list[list[list[str]]] = []
    rows: list[str] = []
    for line in [*body.splitlines(), ""]:
        if line.startswith("|"):
            rows.append(line)
            continue
        if len(rows) > 2 and _TABLE_SEPARATOR.fullmatch(rows[1].strip()):
            tables.append(
                [[cell.strip() for cell in row.strip().strip("|").split("|")] for row in rows[2:]]
            )
        rows = []
    return tables


def test_the_book_is_mirrored_as_nine_chapters_in_four_parts(
    book: Resource, chapters: tuple[ChapterFile, ...]
) -> None:
    assert book.mirror_status is MirrorStatus.MIRRORED
    assert [file.chapter.order for file in chapters] == [1, 2, 3, 4, 5, 6, 7, 8, 9]
    assert [file.chapter.section_label for file in chapters] == [
        "§01",
        "§02",
        "§03",
        "§04",
        "§05",
        "§06",
        "§07",
        "§08",
        "§09",
    ]
    assert len({file.chapter.part for file in chapters}) == 4


def test_the_committed_pdf_has_the_sha256_the_metadata_records(
    library: Library, book: Resource
) -> None:
    pinned = book.pinned_source
    assert pinned is not None
    assert pinned.local_path == f"source/{PINNED_PATH}"

    digest = hashlib.sha256((library.root / BOOK / pinned.local_path).read_bytes()).hexdigest()

    assert digest == pinned.sha256


def test_the_page_ranges_cover_pages_3_to_35_without_a_gap_or_an_overlap(
    chapters: tuple[ChapterFile, ...],
) -> None:
    ranges = [file.chapter.source.pages for file in chapters]

    assert ranges[0].first == FIRST_SECTION_PAGE
    assert ranges[-1].last == LAST_SECTION_PAGE
    for pages in ranges:
        assert pages.first <= pages.last
    for before, after in itertools.pairwise(ranges):
        # A section may begin on the page where the one before it ends.
        assert after.first in (before.last, before.last + 1)


def test_every_chapter_matches_a_fresh_extraction_of_the_pdf(
    library: Library, book: Resource, chapters: tuple[ChapterFile, ...]
) -> None:
    report = check_book(library.root, book, chapters)

    assert report.error is None
    assert len(report.results) == 9
    assert [result.message for result in report.results if not result.passed] == []


def test_every_chapter_names_the_pinned_revision_and_source_path(
    chapters: tuple[ChapterFile, ...],
) -> None:
    assert len(chapters) == 9
    for file in chapters:
        source = file.chapter.source
        assert source.repository == "alchaincyf/loop-engineering-orange-book", file.path
        assert source.revision == PINNED_COMMIT, file.path
        assert source.path == PINNED_PATH, file.path
        assert file.chapter.edition == "v260615", file.path
        assert file.chapter.language == "en", file.path


def test_the_license_evidence_quote_is_in_the_license_file_of_the_book(
    library: Library, book: Resource
) -> None:
    license_text = (library.root / BOOK / "LICENSE").read_text(encoding="utf-8")

    assert book.license.statement is not None
    assert "Copyright (c) 2026 HuaShu" in book.license.statement
    assert book.license.statement in license_text


def test_section_03_holds_the_table_of_the_five_moves(chapters: tuple[ChapterFile, ...]) -> None:
    tables = _tables(_chapter_labeled(chapters, "§03").body)

    first_columns = [[row[0] for row in table] for table in tables]

    assert ["Discovery", "Handoff", "Verification", "Persistence", "Scheduling"] in first_columns


def test_section_09_holds_the_goal_command_in_a_fenced_code_block(
    chapters: tuple[ChapterFile, ...],
) -> None:
    body = _chapter_labeled(chapters, "§09").body

    blocks = [match["code"] for match in _FENCED_BLOCK.finditer(body)]

    assert any("/goal all tests in test/auth pass" in block for block in blocks)


def test_every_chapter_is_marked_machine_extracted(chapters: tuple[ChapterFile, ...]) -> None:
    assert len(chapters) == 9
    for file in chapters:
        assert file.chapter.extraction_status is ExtractionStatus.MACHINE_EXTRACTED, file.path
