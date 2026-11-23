"""The citation checker confirms that tokens resolve and that quotes match the cited chapter."""

from pathlib import Path

import check_citations
import pytest
from kb.readpath import CitationProblem, check_text, load_index, opening_fence

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


QUOTATION_MARKS = [
    pytest.param('"', '"', id="straight"),
    pytest.param("“", "”", id="curly"),
    pytest.param("「", "」", id="corner"),
    pytest.param("『", "』", id="white-corner"),
]
# Eleven characters with no space between them, which no fixture chapter holds.
INVENTED_CHINESE = "折纸船之前要先把纸浸湿"


@pytest.mark.parametrize(("opening", "closing"), QUOTATION_MARKS)
def test_a_fabricated_chinese_quote_of_a_mirrored_chapter_fails(
    fixture_library_root: Path,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    opening: str,
    closing: str,
) -> None:
    text = f"作者写道{opening}{INVENTED_CHINESE}{closing} [cite:{HULL}]\n"

    code, lines, _ = check(fixture_library_root, tmp_path, text, capsys)

    assert code == 1
    assert lines == [f'1: The quote is not in {HULL} word for word: "{INVENTED_CHINESE}"']


@pytest.mark.parametrize(("opening", "closing"), QUOTATION_MARKS)
def test_a_chinese_quote_that_cites_a_book_that_is_not_mirrored_fails(
    fixture_library_root: Path,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    opening: str,
    closing: str,
) -> None:
    text = f"手册写道{opening}{INVENTED_CHINESE}{closing} [cite:fixture-reference-book]\n"

    code, lines, _ = check(fixture_library_root, tmp_path, text, capsys)

    assert code == 1
    assert lines == [
        "1: The quote cites fixture-reference-book, whose mirror status is reference-only. "
        f'Its text is not in this library, so nothing may be quoted from it: "{INVENTED_CHINESE}"'
    ]


@pytest.mark.parametrize(("opening", "closing"), QUOTATION_MARKS)
def test_a_chinese_span_of_five_characters_is_not_read_as_a_quote(
    fixture_library_root: Path,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    opening: str,
    closing: str,
) -> None:
    text = f"这一章讲的是{opening}纸船会沉没{closing}这件事。 [cite:{HULL}]\n"

    code, lines, _ = check(fixture_library_root, tmp_path, text, capsys)

    assert lines == []
    assert code == 0


def test_a_chinese_span_of_six_characters_is_read_as_a_quote(
    fixture_library_root: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    text = f"这一章讲的是“纸船都会沉没”这件事。 [cite:{HULL}]\n"

    code, lines, _ = check(fixture_library_root, tmp_path, text, capsys)

    assert code == 1
    assert lines == [f'1: The quote is not in {HULL} word for word: "纸船都会沉没"']


def test_a_span_of_three_words_is_not_read_as_a_quote(
    fixture_library_root: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    text = f'The chapter never calls a hull "strong and heavy" in any section. [cite:{HULL}]\n'

    code, lines, _ = check(fixture_library_root, tmp_path, text, capsys)

    assert lines == []
    assert code == 0


def test_a_span_of_four_words_is_read_as_a_quote(
    fixture_library_root: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    text = f'The chapter never calls a hull "strong and very heavy" in any section. [cite:{HULL}]\n'

    code, lines, _ = check(fixture_library_root, tmp_path, text, capsys)

    assert code == 1
    assert lines == [f'1: The quote is not in {HULL} word for word: "strong and very heavy"']


def test_a_quote_that_starts_inside_a_word_of_the_chapter_fails(
    fixture_library_root: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # The chapter says "never by the brim", so the cut span says the opposite.
    text = f'The chapter says to lift it "ever by the brim. Let it drain bow down" [cite:{SUNK}]\n'

    code, lines, _ = check(fixture_library_root, tmp_path, text, capsys)

    assert code == 1
    assert lines == [
        f'1: The quote is not in {SUNK} word for word: "ever by the brim. Let it drain bow down"'
    ]


def test_a_quote_that_ends_inside_a_word_of_the_chapter_fails(
    fixture_library_root: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    text = f"> A fourth fold adds weight and no stren\n\n[cite:{HULL}]\n"

    code, lines, _ = check(fixture_library_root, tmp_path, text, capsys)

    assert code == 1
    assert lines == [
        f'1: The quote is not in {HULL} word for word: "A fourth fold adds weight and no stren"'
    ]


def test_a_quote_of_whole_words_from_the_middle_of_a_sentence_passes(
    fixture_library_root: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    text = (
        f'The chapter says "never by the brim. Let it drain bow down" [cite:{SUNK}]\n'
        "\n"
        f'It also says "and a soft hull takes on water before it leaves the bank" [cite:{HULL}]\n'
    )

    code, lines, _ = check(fixture_library_root, tmp_path, text, capsys)

    assert lines == []
    assert code == 0


def test_a_quote_passes_when_a_later_place_in_the_chapter_holds_it_as_whole_words(
    library_copy: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    chapter = (
        library_copy / "books" / "fixture-mirrored-book" / "chapters" / "01-folding-the-hull.md"
    )
    with chapter.open("a", encoding="utf-8") as file:
        file.write(
            "\nA boat left unattended for many launches will sink. "
            "A boat attended for many launches will not.\n"
        )
    text = f'The chapter says a boat "attended for many launches" stays afloat. [cite:{HULL}]\n'

    code, lines, _ = check(library_copy, tmp_path, text, capsys)

    assert lines == []
    assert code == 0


def test_a_chinese_quote_from_the_middle_of_a_sentence_passes(
    library_copy: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    chapter = (
        library_copy / "books" / "fixture-mirrored-book" / "chapters" / "01-folding-the-hull.md"
    )
    with chapter.open("a", encoding="utf-8") as file:
        file.write("\n纸船下水之前要先检查船底有没有裂缝。船身要用A4纸折出三道折痕。\n")
    # The first quote sits between two Chinese characters, and the second follows a digit.
    text = f"这一章说“要先检查船底有没有裂缝”还说「纸折出三道折痕」。 [cite:{HULL}]\n"

    code, lines, _ = check(library_copy, tmp_path, text, capsys)

    assert lines == []
    assert code == 0


def test_a_fabricated_quote_whose_only_token_stands_in_front_of_it_fails(
    fixture_library_root: Path,
) -> None:
    index = load_index(fixture_library_root)
    text = f'[cite:{HULL}] says "A wet sheet folds into a hard hull every time."\n'

    assert check_text(index, text) == [
        CitationProblem(
            line=1,
            message=(
                f"The quote is not in {HULL} word for word: "
                '"A wet sheet folds into a hard hull every time."'
            ),
        )
    ]


def test_a_quote_of_a_book_that_is_not_mirrored_fails_with_its_token_in_front(
    fixture_library_root: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    text = (
        "The manual [cite:fixture-reference-book] says "
        '"Wind the kettle key nine turns before the leaves go in."\n'
    )

    code, lines, _ = check(fixture_library_root, tmp_path, text, capsys)

    assert code == 1
    assert lines == [
        "1: The quote cites fixture-reference-book, whose mirror status is reference-only. "
        "Its text is not in this library, so nothing may be quoted from it: "
        '"Wind the kettle key nine turns before the leaves go in."'
    ]


def test_a_quote_is_checked_against_the_token_after_it_before_any_token_in_front(
    fixture_library_root: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # The first quote is in the chapter the token after it names. The second has no token after
    # it, so the nearest one in front, which names the same chapter, is the one it is held to.
    text = (
        f'After folding [cite:{HULL}], the book says "Lift the boat by its keel fold and never '
        f'by the brim." [cite:{SUNK}] and then "Let it drain bow down, then dry it flat under a '
        'book."\n'
    )

    code, lines, _ = check(fixture_library_root, tmp_path, text, capsys)

    assert lines == []
    assert code == 0


def test_a_line_that_opens_with_inline_code_in_three_backticks_hides_nothing_below_it(
    fixture_library_root: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    text = (
        "```--root``` is the option that names the library.\n"
        "\n"
        "See [cite:fixture-mirrored-book/sewing-a-sail] for sails.\n"
    )

    code, lines, _ = check(fixture_library_root, tmp_path, text, capsys)

    assert code == 1
    [line] = lines
    assert line.startswith(
        "3: The citation [cite:fixture-mirrored-book/sewing-a-sail] does not resolve."
    )


@pytest.mark.parametrize(
    ("line", "fence"),
    [
        ("```", "```"),
        ("```text", "```"),
        ("   ````markdown", "````"),
        ("~~~", "~~~"),
        ("~~~ a `quoted` word", "~~~"),
        ("```--root``` is the option.", None),
        ("```js `x`", None),
        ("    ```", None),
        ("Plain text with ``` inside.", None),
    ],
)
def test_a_backtick_fence_opens_a_block_only_when_no_backtick_follows_it(
    line: str, fence: str | None
) -> None:
    assert opening_fence(line) == fence


NESTED_BLOCK_QUOTES = [
    "- The book on drying:\n\n    > {quote}\n\n    {token}\n",
    "- The book on drying:\n    > {quote}\n    {token}\n",
    "- > {quote}\n\n  {token}\n",
    "1. > {quote}\n\n   {token}\n",
    "\t> {quote}\n\n{token}\n",
]


@pytest.mark.parametrize("layout", NESTED_BLOCK_QUOTES)
def test_a_fabricated_block_quote_inside_a_list_item_fails(
    layout: str, fixture_library_root: Path
) -> None:
    index = load_index(fixture_library_root)
    text = layout.format(quote="A boat that dries flat will float again.", token=f"[cite:{SUNK}]")

    problems = check_text(index, text)

    assert [problem.message for problem in problems] == [
        f'The quote is not in {SUNK} word for word: "A boat that dries flat will float again."'
    ]


@pytest.mark.parametrize("layout", NESTED_BLOCK_QUOTES)
def test_a_block_quote_inside_a_list_item_with_no_citation_fails(
    layout: str, fixture_library_root: Path
) -> None:
    index = load_index(fixture_library_root)
    text = layout.format(quote="A boat that dries flat will fold again.", token="No source.")

    problems = check_text(index, text)

    assert [problem.message for problem in problems] == [
        "The block quote has no citation token in its paragraph or on the next line: "
        '"A boat that dries flat will fold again."'
    ]


@pytest.mark.parametrize("layout", NESTED_BLOCK_QUOTES)
def test_an_exact_block_quote_inside_a_list_item_passes(
    layout: str, fixture_library_root: Path
) -> None:
    index = load_index(fixture_library_root)
    text = layout.format(quote="A boat that dries flat will fold again.", token=f"[cite:{SUNK}]")

    assert check_text(index, text) == []


def test_the_quotes_of_two_list_items_next_to_each_other_are_two_quotes(
    fixture_library_root: Path,
) -> None:
    index = load_index(fixture_library_root)
    first = "A boat that dries flat will fold again."
    second = "A boat that dries crumpled is a paper ball."
    token = f"[cite:{SUNK}]"

    assert check_text(index, f"- > {first} {token}\n- > {second} {token}\n") == []

    problems = check_text(index, f"- > {first} {token}\n- > A boat is a paper ball. {token}\n")

    assert [problem.message for problem in problems] == [
        f'The quote is not in {SUNK} word for word: "A boat is a paper ball."'
    ]


def test_the_lines_of_one_quote_in_a_list_item_are_still_one_quote(
    fixture_library_root: Path,
) -> None:
    index = load_index(fixture_library_root)
    text = (
        "- > A boat that dries flat will fold again.\n"
        f"  > A boat that dries crumpled is a paper ball. [cite:{SUNK}]\n"
    )

    assert check_text(index, text) == []
