"""The citation checker confirms that tokens resolve and that quotes match the cited chapter."""

from pathlib import Path

import check_citations
import pytest
from kb.readpath import CitationProblem, check_text, load_index

HULL = "fixture-mirrored-book/folding-the-hull"
SUNK = "fixture-mirrored-book/recovering-a-sunk-boat"


def check(
    root: Path, tmp_path: Path, text: str, capsys: pytest.CaptureFixture[str]
) -> tuple[int, list[str], str]:
    """Write one document, run the command on it, and return the code, the lines, and stderr."""
    document = tmp_path / "answer.md"
    document.write_text(text, encoding="utf-8")
    code = check_citations.main(["--root", str(root), str(document)])
    output = capsys.readouterr()
    prefix = f"{document}:"
    lines = output.out.splitlines()
    assert all(line.startswith(prefix) for line in lines)
    return code, [line.removeprefix(prefix) for line in lines], output.err


def test_a_quote_that_differs_only_in_line_wrapping_passes(
    fixture_library_root: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    text = (
        "# Notes\n"
        "\n"
        'The book warns that "A damp sheet folds into a soft hull,\n'
        'and a soft hull takes on water before it leaves the bank." '
        f"[cite:{HULL}]\n"
        "\n"
        "> Fold the sheet in half, fold the corners\n"
        "> to the center, and fold the brim up\n"
        "> on both sides.\n"
        "\n"
        f"[cite:{HULL}@v1.0.0]\n"
    )

    code, lines, stderr = check(fixture_library_root, tmp_path, text, capsys)

    assert lines == []
    assert code == 0
    assert stderr.splitlines() == ["check_citations: no problems in 1 file."]


def test_a_quote_with_one_altered_word_fails_and_the_quote_is_printed(
    fixture_library_root: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    text = (
        "# Notes\n"
        "\n"
        'The book warns that "A wet sheet folds into a soft hull, and a soft hull takes on '
        f'water before it leaves the bank." [cite:{HULL}]\n'
    )

    code, lines, stderr = check(fixture_library_root, tmp_path, text, capsys)

    assert code == 1
    assert lines == [
        f"3: The quote is not in {HULL} word for word: "
        '"A wet sheet folds into a soft hull, and a soft hull takes on water before it leaves '
        'the bank."'
    ]
    assert stderr.splitlines() == [
        "check_citations: 1 problem in 1 file. Quote the chapter file word for word, and take "
        "ids from scripts/resolve.py."
    ]


def test_a_block_quote_with_one_altered_word_fails(
    fixture_library_root: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    text = f"> A boat that dries flat will float again.\n\n[cite:{SUNK}]\n"

    code, lines, _ = check(fixture_library_root, tmp_path, text, capsys)

    assert code == 1
    assert lines == [
        f'1: The quote is not in {SUNK} word for word: "A boat that dries flat will float again."'
    ]


def test_a_citation_of_an_id_that_does_not_exist_fails(
    fixture_library_root: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    text = "Hulls are covered early.\n\nSee [cite:fixture-mirrored-book/sewing-a-sail] for sails.\n"

    code, lines, _ = check(fixture_library_root, tmp_path, text, capsys)

    assert code == 1
    [line] = lines
    assert line.startswith(
        "3: The citation [cite:fixture-mirrored-book/sewing-a-sail] does not resolve. "
        'No resource or chapter has the id "fixture-mirrored-book/sewing-a-sail".'
    )


def test_a_quote_that_cites_a_book_that_is_not_mirrored_fails_and_the_quote_is_printed(
    fixture_library_root: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    text = (
        'The manual says "Wind the kettle key nine turns before the leaves go in." '
        "[cite:fixture-reference-book]\n"
    )

    code, lines, _ = check(fixture_library_root, tmp_path, text, capsys)

    assert code == 1
    assert lines == [
        "1: The quote cites fixture-reference-book, whose mirror status is reference-only. "
        "Its text is not in this library, so nothing may be quoted from it: "
        '"Wind the kettle key nine turns before the leaves go in."'
    ]


def test_a_citation_of_a_reference_only_book_with_no_quoted_text_passes(
    fixture_library_root: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    text = (
        "Steeping is covered by another book, which this library links and does not hold "
        "[cite:fixture-reference-book].\n"
    )

    code, lines, _ = check(fixture_library_root, tmp_path, text, capsys)

    assert lines == []
    assert code == 0


def test_an_edition_that_is_not_the_indexed_one_fails(
    fixture_library_root: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    text = f"Folding comes first [cite:{HULL}@v1.1.0].\n"

    code, lines, _ = check(fixture_library_root, tmp_path, text, capsys)

    assert code == 1
    assert lines == [
        f"1: The citation [cite:{HULL}@v1.1.0] names edition v1.1.0, and the index records "
        f"edition v1.0.0 for {HULL}."
    ]


def test_a_block_quote_with_no_citation_fails(
    fixture_library_root: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    text = (
        "The book on drying:\n"
        "\n"
        "> A boat that dries flat will fold again.\n"
        "\n"
        "That is all it says.\n"
        "\n"
        f"Folding comes first [cite:{HULL}].\n"
    )

    code, lines, _ = check(fixture_library_root, tmp_path, text, capsys)

    assert code == 1
    assert lines == [
        "3: The block quote has no citation token in its paragraph or on the next line: "
        '"A boat that dries flat will fold again."'
    ]


def test_a_quote_survives_emphasis_and_inline_code_on_either_side(
    fixture_library_root: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # The chapter prints the second passage inside a block quote of its own.
    text = (
        'The rule is "Lift the boat by its *keel fold* and **never** by the `brim`." '
        f"[cite:{SUNK}]\n"
        "\n"
        "> A boat that dries flat will fold again. A boat that dries crumpled is a paper ball.\n"
        f"> [cite:{SUNK}]\n"
    )

    code, lines, _ = check(fixture_library_root, tmp_path, text, capsys)

    assert lines == []
    assert code == 0


def test_a_quote_matches_text_the_chapter_writes_with_a_backslash_escape(
    library_copy: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    chapter = (
        library_copy / "books" / "fixture-mirrored-book" / "chapters" / "01-folding-the-hull.md"
    )
    body = chapter.read_text(encoding="utf-8")
    assert "Choose a sheet with no creases." in body
    chapter.write_text(
        body.replace("Choose a sheet with no creases.", "Choose a sheet with no \\*creases\\*."),
        encoding="utf-8",
    )
    text = f'A reader sees "Choose a sheet with no *creases*." [cite:{HULL}]\n'

    code, lines, _ = check(library_copy, tmp_path, text, capsys)

    assert lines == []
    assert code == 0


def test_a_quote_that_cites_a_mirrored_book_may_come_from_any_of_its_chapters(
    fixture_library_root: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    text = (
        'The book says "The pond decides more than the boat does." [cite:fixture-mirrored-book]\n'
        "\n"
        'It never says "The pond decides less than the boat does." [cite:fixture-mirrored-book]\n'
    )

    code, lines, _ = check(fixture_library_root, tmp_path, text, capsys)

    assert code == 1
    assert lines == [
        "3: The quote is not in fixture-mirrored-book word for word: "
        '"The pond decides less than the boat does."'
    ]


def test_the_citation_that_resolve_prints_is_not_read_as_a_quote(
    fixture_library_root: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # Both titles have four words or more and sit in double quotes before the token.
    text = (
        "> Every boat sinks once, and the second launch is the one that teaches.\n"
        "\n"
        'Fixture Author, "Paper Boat Engineering (Test Fixture)" (English ed. v1.0.0), '
        '§03 "Recovering a Sunk Boat", source PDF p. 6. '
        f"[cite:{SUNK}@v1.0.0]\n"
    )

    code, lines, _ = check(fixture_library_root, tmp_path, text, capsys)

    assert lines == []
    assert code == 0


def test_a_token_shown_inside_code_is_not_a_citation(
    fixture_library_root: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    text = (
        "Write `[cite:<chapter-id>]` after a quote.\n"
        "\n"
        "```text\n"
        '"An invented passage of several words" [cite:no-such-book/no-such-section]\n'
        "```\n"
    )

    code, lines, _ = check(fixture_library_root, tmp_path, text, capsys)

    assert lines == []
    assert code == 0


def test_every_file_is_checked_and_problems_are_counted_across_files(
    fixture_library_root: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    good = tmp_path / "good.md"
    good.write_text(f"Folding comes first [cite:{HULL}].\n", encoding="utf-8")
    bad = tmp_path / "bad.md"
    bad.write_text("See [cite:no-such-book].\n\nAnd [cite:other-missing-book].\n", encoding="utf-8")

    code = check_citations.main(["--root", str(fixture_library_root), str(good), str(bad)])

    output = capsys.readouterr()
    assert code == 1
    assert [line.partition(": ")[0] for line in output.out.splitlines()] == [
        f"{bad}:1",
        f"{bad}:3",
    ]
    assert output.err.startswith("check_citations: 2 problems in 2 files.")


def test_the_checking_function_takes_text_and_returns_problems_with_line_numbers(
    fixture_library_root: Path,
) -> None:
    index = load_index(fixture_library_root)

    assert check_text(index, f"Folding comes first [cite:{HULL}].\n") == []
    assert check_text(index, f"Intro.\n\nFolding comes first [cite:{HULL}@v2].\n") == [
        CitationProblem(
            line=3,
            message=(
                f"The citation [cite:{HULL}@v2] names edition v2, and the index records edition "
                f"v1.0.0 for {HULL}."
            ),
        )
    ]
