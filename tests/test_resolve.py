"""The resolve command turns an id into its record and a formatted citation."""

import json
from pathlib import Path

import pytest
import resolve

HULL = "fixture-mirrored-book/folding-the-hull"
SUNK = "fixture-mirrored-book/recovering-a-sunk-boat"
EVERY_ID = {
    "fixture-mirrored-book",
    "fixture-reference-book",
    "fixture-mirrored-book/folding-the-hull",
    "fixture-mirrored-book/choosing-a-pond",
    "fixture-mirrored-book/recovering-a-sunk-boat",
}


def run(root: Path, *arguments: str) -> int:
    return resolve.main(["--root", str(root), *arguments])


def test_a_chapter_id_prints_the_record_and_the_formatted_citation(
    fixture_library_root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = run(fixture_library_root, HULL)

    lines = capsys.readouterr().out.splitlines()
    assert code == 0
    for expected in [
        "id: fixture-mirrored-book/folding-the-hull",
        "title: Folding the Hull",
        "section_label: §01",
        "part: Part One: Paper",
        "order: 1",
        "resource: fixture-mirrored-book",
        "resource_title: Paper Boat Engineering (Test Fixture)",
        "author: Fixture Author (夹具作者)",
        "language: en",
        "edition: v1.0.0",
        "license_id: MIT",
        "mirror_status: mirrored",
        "quote_permitted: true",
        "path: books/fixture-mirrored-book/chapters/01-folding-the-hull.md",
        f"file: {fixture_library_root / 'books/fixture-mirrored-book/chapters'}"
        "/01-folding-the-hull.md",
        "source_repository: fixture-author/fixture-mirrored-book",
        f"source_revision: {'a' * 40}",
        "source_path: Paper-Boat-Engineering-v1.0.0.pdf",
        "source_pages: 3-4",
        "extraction_status: machine-extracted",
        "topics: paper-craft",
        "official_url: https://example.invalid/books/paper-boat",
    ]:
        assert expected in lines
    assert lines[-1] == (
        'citation: Fixture Author, "Paper Boat Engineering (Test Fixture)" (English ed. v1.0.0), '
        '§01 "Folding the Hull", source PDF pp. 3-4. '
        "[cite:fixture-mirrored-book/folding-the-hull@v1.0.0]"
    )


def test_a_chapter_on_one_page_is_cited_with_a_single_page(
    fixture_library_root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert run(fixture_library_root, SUNK) == 0

    lines = capsys.readouterr().out.splitlines()
    assert "source_pages: 6" in lines
    assert lines[-1].endswith(
        '§03 "Recovering a Sunk Boat", source PDF p. 6. '
        "[cite:fixture-mirrored-book/recovering-a-sunk-boat@v1.0.0]"
    )


def test_a_chapter_of_an_edition_that_is_behind_says_so_and_names_the_newer_edition(
    fixture_library_root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert run(fixture_library_root, HULL) == 0

    lines = capsys.readouterr().out.splitlines()
    assert "edition_behind: true" in lines
    assert "newer_editions: zh v1.1.0" in lines
    assert (
        "edition_note: The mirrored English edition v1.0.0 is behind. The newest Chinese edition "
        "is v1.1.0. Say so when you cite it."
    ) in lines


def test_a_chapter_with_an_erratum_prints_it(
    fixture_library_root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert run(fixture_library_root, "fixture-mirrored-book/choosing-a-pond") == 0

    assert (
        "erratum: The invented second edition says the pond table lists depth in hands and not "
        "in spans. Source: https://example.invalid/fixture-author/fixture-mirrored-book/errata"
    ) in capsys.readouterr().out.splitlines()


def test_json_prints_the_chapter_record_as_one_object_with_its_citation(
    fixture_library_root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert run(fixture_library_root, SUNK, "--json") == 0

    [line] = capsys.readouterr().out.splitlines()
    record = json.loads(line)
    assert record["id"] == SUNK
    assert record["path"] == "books/fixture-mirrored-book/chapters/03-recovering-a-sunk-boat.md"
    assert record["source"]["pages"] == {"first": 6, "last": 6}
    assert record["quote_permitted"] is True
    assert record["citation"].endswith("[cite:fixture-mirrored-book/recovering-a-sunk-boat@v1.0.0]")


def test_a_reference_only_resource_prints_its_official_url_and_no_path(
    fixture_library_root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = run(fixture_library_root, "fixture-reference-book")

    lines = capsys.readouterr().out.splitlines()
    assert code == 0
    for expected in [
        "id: fixture-reference-book",
        "title: Clockwork Tea Manual (Test Fixture)",
        "title_original: 发条茶事手册测试夹具",
        "title_english_official: false",
        "license_id: none",
        "mirror_status: reference-only",
        "quote_permitted: false",
        "official_url: https://example.invalid/books/clockwork-tea",
        "topics: paper-craft, tea-service",
    ]:
        assert expected in lines
    keys = [line.partition(":")[0] for line in lines]
    assert "path" not in keys
    assert "file" not in keys
    assert "chapter" not in keys
    assert "citation" not in keys
    assert any(
        line.startswith("text_note: ") and "is not in this library" in line for line in lines
    )


def test_a_mirrored_resource_prints_its_urls_its_flag_and_its_chapter_ids(
    fixture_library_root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert run(fixture_library_root, "fixture-mirrored-book") == 0

    lines = capsys.readouterr().out.splitlines()
    for expected in [
        "id: fixture-mirrored-book",
        "quote_permitted: true",
        "edition: v1.0.0",
        "edition_language: en",
        "edition_behind: true",
        "official_site: https://example.invalid/books/paper-boat",
        "official_repository: https://example.invalid/fixture-author/fixture-mirrored-book",
        "hosted_edition: Fixture Reader https://example.invalid/reader/paper-boat",
        "license_path: books/fixture-mirrored-book/LICENSE",
    ]:
        assert expected in lines
    assert [line for line in lines if line.startswith("chapter: ")] == [
        "chapter: fixture-mirrored-book/folding-the-hull",
        "chapter: fixture-mirrored-book/choosing-a-pond",
        "chapter: fixture-mirrored-book/recovering-a-sunk-boat",
    ]


def test_an_unknown_id_exits_nonzero_and_prints_the_three_nearest_ids(
    fixture_library_root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = run(fixture_library_root, "fixture-mirored-book")

    output = capsys.readouterr()
    assert code == 1
    assert output.out == ""
    start = (
        'resolve: No resource or chapter has the id "fixture-mirored-book". The nearest ids are: '
    )
    assert output.err.startswith(start)
    nearest = output.err.removeprefix(start).removesuffix(".\n").split(", ")
    assert len(nearest) == 3
    assert nearest[0] == "fixture-mirrored-book"
    assert set(nearest) <= EVERY_ID


def test_a_chapter_id_under_a_book_that_is_not_mirrored_exits_nonzero_and_says_why(
    fixture_library_root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = run(fixture_library_root, "fixture-reference-book/steeping")

    output = capsys.readouterr()
    assert code == 1
    assert output.out == ""
    assert "fixture-reference-book has no mirrored chapters" in output.err
    assert "reference-only" in output.err
    assert "https://example.invalid/books/clockwork-tea" in output.err


def test_a_root_without_indexes_exits_nonzero_and_names_the_build_command(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = run(tmp_path, HULL)

    output = capsys.readouterr()
    assert code == 1
    assert "index/catalog.json" in output.err
    assert "uv run python scripts/build.py" in output.err
