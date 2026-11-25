"""Hermes Agent 2.0 is mirrored as 21 chapters that match the pinned English PDF."""

import hashlib
import itertools
from pathlib import Path

import pytest
from kb.catalog import ChapterFile, Library, MirrorStatus, Resource, load_library
from kb.fidelity import check_book
from kb.frontmatter import ExtractionStatus

BOOK_ID = "hermes-agent-orange-book"
BOOK = Path("books") / BOOK_ID
PINNED_COMMIT = "b6e53a8e11e00c8b14b2f72d6b4f1ce71fef6692"
PINNED_PATH = "Hermes-Agent-The-Complete-Guide-v260607.pdf"
PINNED_SHA256 = "250eaee552121313db913893404b9b1574c7f2ea7b06d25e8641054a51642d59"
EDITION = "v260607"
CHAPTER_COUNT = 21
FIRST_SECTION_PAGE = 4
LAST_SECTION_PAGE = 103
ERRATUM_CHAPTER_ID = f"{BOOK_ID}/why-nous-built-this"


@pytest.fixture(scope="module")
def library(repo_root: Path) -> Library:
    return load_library(repo_root)


@pytest.fixture(scope="module")
def book(library: Library) -> Resource:
    return library.resource(BOOK_ID)


@pytest.fixture(scope="module")
def chapters(library: Library) -> tuple[ChapterFile, ...]:
    return library.chapters_of(BOOK_ID)


def test_the_book_is_mirrored_as_21_chapters_in_six_parts(
    book: Resource, chapters: tuple[ChapterFile, ...]
) -> None:
    numbers = range(1, CHAPTER_COUNT + 1)

    assert book.mirror_status is MirrorStatus.MIRRORED
    assert [file.chapter.order for file in chapters] == list(numbers)
    assert [file.chapter.section_label for file in chapters] == [
        f"§{number:02d}" for number in numbers
    ]
    assert len({file.chapter.part for file in chapters}) == 6


def test_the_committed_pdf_has_the_sha256_the_metadata_records(
    library: Library, book: Resource
) -> None:
    pinned = book.pinned_source
    assert pinned is not None
    assert pinned.local_path == f"source/{PINNED_PATH}"
    assert pinned.sha256 == PINNED_SHA256

    digest = hashlib.sha256((library.root / BOOK / pinned.local_path).read_bytes()).hexdigest()

    assert digest == pinned.sha256


def test_the_page_ranges_cover_pages_4_to_103_without_a_gap_or_an_overlap(
    chapters: tuple[ChapterFile, ...],
) -> None:
    ranges = [file.chapter.source.pages for file in chapters]

    assert ranges[0].first == FIRST_SECTION_PAGE
    assert ranges[-1].last == LAST_SECTION_PAGE
    for pages in ranges:
        assert pages.first <= pages.last
    for before, after in itertools.pairwise(ranges):
        # Every section of this book opens on a new page, so no two sections share one.
        assert after.first == before.last + 1


def test_every_chapter_matches_a_fresh_extraction_of_the_pdf(
    library: Library, book: Resource, chapters: tuple[ChapterFile, ...]
) -> None:
    report = check_book(library.root, book, chapters)

    assert report.error is None
    assert len(report.results) == CHAPTER_COUNT
    assert [result.message for result in report.results if not result.passed] == []


def test_every_chapter_names_the_pinned_revision_and_source_path(
    chapters: tuple[ChapterFile, ...],
) -> None:
    assert len(chapters) == CHAPTER_COUNT
    for file in chapters:
        source = file.chapter.source
        assert source.repository == "alchaincyf/hermes-agent-orange-book", file.path
        assert source.revision == PINNED_COMMIT, file.path
        assert source.path == PINNED_PATH, file.path
        assert file.chapter.edition == EDITION, file.path
        assert file.chapter.language == "en", file.path


def test_the_license_evidence_quote_is_in_the_license_file_of_the_book(
    library: Library, book: Resource
) -> None:
    license_text = (library.root / BOOK / "LICENSE").read_text(encoding="utf-8")

    assert book.license.statement is not None
    assert "Copyright (c) 2026 HuaShu" in book.license.statement
    assert book.license.statement in license_text


def test_only_section_03_carries_an_erratum(chapters: tuple[ChapterFile, ...]) -> None:
    with_errata = [file for file in chapters if file.chapter.errata]

    assert [file.chapter.id for file in with_errata] == [ERRATUM_CHAPTER_ID]


def test_every_chapter_is_marked_machine_extracted(chapters: tuple[ChapterFile, ...]) -> None:
    assert len(chapters) == CHAPTER_COUNT
    for file in chapters:
        assert file.chapter.extraction_status is ExtractionStatus.MACHINE_EXTRACTED, file.path
