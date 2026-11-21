"""A chapter must hold the words of its source, as often, and in nearly the same order."""

import hashlib
from pathlib import Path

from kb.catalog import AcceptedDifference, load_chapters, load_resource
from kb.checks import Finding, run_checks
from kb.fidelity import SIMILARITY_FLOOR, check_book, compare

MIRRORED = "fixture-mirrored-book"
REFERENCE = "fixture-reference-book"
CHAPTER_ID = "rope-book/whipping-a-rope-end"

BOOK = Path("books") / MIRRORED
METADATA = BOOK / "metadata.yaml"
SOURCE = BOOK / "source" / "Paper-Boat-Engineering-v1.0.0.pdf"
HULL = BOOK / "chapters" / "01-folding-the-hull.md"
POND = BOOK / "chapters" / "02-choosing-a-pond.md"
SUNK = BOOK / "chapters" / "03-recovering-a-sunk-boat.md"

# Forty sentences of eleven words each. A section this long is needed for the order rule to have
# room: at 0.98, a few words in several hundred may move.
STEPS = [
    f"Turn {number} of the twine lies flat beside turn {number + 1}." for number in range(1, 41)
]

SOURCE_TEXT = "\n".join(
    [
        "Whipping a Rope End",
        "A whipping keeps the strands of a rope from coming apart.",
        "Marta Oduya taught this method on the quay in 1,300 lessons.",
        *STEPS[:20],
        "Twine Turns Finish",
        "Waxed flax Twelve Reef knot",
        "Tarred hemp Nine Sewn through",
        "Dyed nylon Fifteen Melted flat",
        *STEPS[20:],
        "Pull the end through - it's what holds the whipping - and trim it.",
        "trim --close twine",
    ]
)

CHAPTER_BODY = "\n".join(
    [
        "# Whipping a Rope End",
        "",
        "*A whipping keeps the strands of a rope from coming apart.*",
        "",
        "Marta Oduya taught this method on the quay",
        "in 1,300 lessons.",
        "",
        *STEPS[:20],
        "",
        "| Twine | Turns | Finish |",
        "| --- | --- | --- |",
        "| Waxed flax | Twelve | Reef knot |",
        "| Tarred hemp | Nine | Sewn through |",
        "| Dyed nylon | Fifteen | Melted flat |",
        "",
        *STEPS[20:],
        "",
        "> Pull the end through \u2014 it\u2019s what holds the whipping \u2014 and trim it.",
        "",
        "```text",
        "trim --close twine",
        "```",
        "",
    ]
)


def replace_in(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    assert old in text, f"{old!r} is not in {path}"
    path.write_text(text.replace(old, new), encoding="utf-8")


def fidelity_findings(root: Path) -> list[Finding]:
    return [finding for finding in run_checks(root) if finding.rule.startswith("fidelity-")]


def located(findings: list[Finding]) -> list[tuple[str, str]]:
    return [(finding.rule, finding.file) for finding in findings]


def test_a_chapter_that_differs_only_in_markup_whitespace_and_punctuation_style_passes() -> None:
    result = compare(CHAPTER_ID, SOURCE_TEXT, CHAPTER_BODY)

    assert result.passed
    assert result.chapter == CHAPTER_ID
    assert result.similarity == 1.0
    assert (result.words_removed, result.words_added) == ((), ())
    assert result.message == ""


def test_markup_added_by_hand_does_not_count_as_words() -> None:
    marked_up = (
        CHAPTER_BODY.replace("Marta Oduya", "**Marta Oduya**")
        .replace("on the quay", "on [the quay](https://example.invalid/the-old-quay-wall)")
        .replace("Waxed flax", "`Waxed flax`")
        .replace("| Twelve |", "|   Twelve   |")
        .replace("and trim it.", "and trim\n> it.")
    )

    assert compare(CHAPTER_ID, SOURCE_TEXT, marked_up).passed


def test_a_chapter_in_which_one_name_is_changed_fails_and_names_the_words() -> None:
    result = compare(CHAPTER_ID, SOURCE_TEXT, CHAPTER_BODY.replace("Marta Oduya", "Maria Oduya"))

    assert not result.passed
    assert result.words_removed == ("Marta",)
    assert result.words_added == ("Maria",)
    assert CHAPTER_ID in result.message
    assert "Maria" in result.message
    assert "Marta" in result.message


def test_a_flipped_number_and_a_dropped_word_each_fail() -> None:
    flipped = compare(CHAPTER_ID, SOURCE_TEXT, CHAPTER_BODY.replace("1,300", "1,800"))
    dropped = compare(CHAPTER_ID, SOURCE_TEXT, CHAPTER_BODY.replace("Sewn through", "Sewn"))
    doubled = compare(CHAPTER_ID, SOURCE_TEXT, CHAPTER_BODY.replace("Reef knot", "Reef Reef knot"))

    assert (flipped.words_removed, flipped.words_added) == (("1,300",), ("1,800",))
    assert (dropped.words_removed, dropped.words_added) == (("through",), ())
    assert (doubled.words_removed, doubled.words_added) == ((), ("Reef",))
    assert not (flipped.passed or dropped.passed or doubled.passed)


def test_the_first_words_that_differ_are_named_in_reading_order() -> None:
    reworded = CHAPTER_BODY.replace(
        "A whipping keeps the strands of a rope from coming apart.",
        "A whipping stops the strands of a rope from fraying loose.",
    )

    result = compare(CHAPTER_ID, SOURCE_TEXT, reworded)

    assert not result.passed
    assert result.words_removed == ("keeps", "coming", "apart")
    assert result.words_added == ("stops", "fraying", "loose")
    assert "stops, fraying, loose" in result.message
    assert "keeps, coming, apart" in result.message


def test_table_rows_repaired_into_a_different_order_pass() -> None:
    repaired = CHAPTER_BODY.replace(
        "| Waxed flax | Twelve | Reef knot |\n| Tarred hemp | Nine | Sewn through |\n",
        "| Tarred hemp | Nine | Sewn through |\n| Waxed flax | Twelve | Reef knot |\n",
    )

    result = compare(CHAPTER_ID, SOURCE_TEXT, repaired)

    assert repaired != CHAPTER_BODY
    assert result.passed
    assert SIMILARITY_FLOOR <= result.similarity < 1.0


def test_the_same_words_in_a_very_different_order_fail_on_order() -> None:
    lines = CHAPTER_BODY.split("\n")
    first_steps = lines.index(STEPS[0])
    shuffled = "\n".join(
        [
            *lines[:first_steps],
            *reversed(lines[first_steps : first_steps + 20]),
            *lines[first_steps + 20 :],
        ]
    )

    result = compare(CHAPTER_ID, SOURCE_TEXT, shuffled)

    assert not result.passed
    assert (result.words_removed, result.words_added) == ((), ())
    assert result.similarity < SIMILARITY_FLOOR
    assert CHAPTER_ID in result.message
    assert "order" in result.message
    # The steps are reversed, so the chapter reads step 20 where the source reads step 1.
    assert "Turn 20 of the twine" in result.message
    assert "Turn 1 of the twine" in result.message


def test_a_restored_word_passes_only_when_the_profile_lists_it_for_that_chapter() -> None:
    restored = CHAPTER_BODY.replace("Sewn through", "Sewn right through")
    accepted = AcceptedDifference(
        chapter=CHAPTER_ID,
        words_removed=(),
        words_added=("right",),
        reason="The extraction drops a word that the source page prints in the table.",
    )
    for_another_chapter = AcceptedDifference(
        chapter="rope-book/coiling",
        words_removed=(),
        words_added=("right",),
        reason="Listed for another chapter.",
    )

    unlisted = compare(CHAPTER_ID, SOURCE_TEXT, restored)

    assert not unlisted.passed
    assert unlisted.words_added == ("right",)
    assert compare(CHAPTER_ID, SOURCE_TEXT, restored, [accepted]).passed
    assert not compare(CHAPTER_ID, SOURCE_TEXT, restored, [for_another_chapter]).passed


def test_an_accepted_difference_the_chapter_does_not_have_fails() -> None:
    stale = AcceptedDifference(
        chapter=CHAPTER_ID,
        words_removed=("Marta",),
        words_added=("Maria",),
        reason="The chapter was changed back and the entry was left behind.",
    )

    result = compare(CHAPTER_ID, SOURCE_TEXT, CHAPTER_BODY, [stale])

    assert not result.passed
    assert (result.words_removed, result.words_added) == (("Maria",), ("Marta",))


def test_every_fixture_chapter_matches_the_committed_source(fixture_library_root: Path) -> None:
    book = load_resource(fixture_library_root, MIRRORED)
    chapters = load_chapters(fixture_library_root, MIRRORED)

    report = check_book(fixture_library_root, book, chapters)

    assert report.error is None
    assert [(result.chapter, result.passed, result.similarity) for result in report.results] == [
        ("fixture-mirrored-book/folding-the-hull", True, 1.0),
        ("fixture-mirrored-book/choosing-a-pond", True, 1.0),
        ("fixture-mirrored-book/recovering-a-sunk-boat", True, 1.0),
    ]


def test_two_reworded_paragraphs_are_a_finding_that_names_the_chapter_and_the_words(
    library_copy: Path,
) -> None:
    replace_in(
        library_copy / HULL,
        "Choose a sheet with no creases. A damp sheet folds into a soft hull, and a soft hull "
        "takes on water before it leaves the bank.",
        "Pick paper that is smooth. Wet paper makes a weak hull, and a weak hull sinks at once.",
    )
    replace_in(
        library_copy / HULL,
        "A fourth fold adds weight and no strength.",
        "More folds only make the boat heavier.",
    )

    findings = fidelity_findings(library_copy)

    assert located(findings) == [("fidelity-chapter", HULL.as_posix())]
    assert "fixture-mirrored-book/folding-the-hull" in findings[0].message
    assert "Pick, paper, that, is, smooth" in findings[0].message
    assert "Choose, a, sheet, with, no" in findings[0].message
    assert findings[0].fix


def test_a_chapter_edited_only_in_its_markup_is_not_a_finding(library_copy: Path) -> None:
    replace_in(library_copy / SUNK, "never by the brim", "**never** by the brim")
    replace_in(library_copy / SUNK, "Let it drain bow down,", "Let it drain\nbow down,")
    replace_in(
        library_copy / POND,
        "| Garden basin | Two spans | Still |",
        "| Garden basin|Two spans|Still |",
    )

    assert run_checks(library_copy) == []


def test_errata_in_the_frontmatter_take_no_part_in_the_comparison(library_copy: Path) -> None:
    replace_in(
        library_copy / HULL,
        "extraction_status: machine-extracted\n",
        "extraction_status: machine-extracted\n"
        "errata:\n"
        "  - description: An invented later edition calls the brim a gunwale.\n"
        "    source_url: https://example.invalid/fixture-author/fixture-mirrored-book/errata\n",
    )

    assert fidelity_findings(library_copy) == []


def test_a_chapter_with_no_section_in_the_source_is_a_finding(library_copy: Path) -> None:
    text = (library_copy / SUNK).read_text(encoding="utf-8")
    extra = library_copy / BOOK / "chapters" / "04-naming-the-boat.md"
    extra.write_text(
        text.replace("recovering-a-sunk-boat", "naming-the-boat").replace("order: 3", "order: 4"),
        encoding="utf-8",
    )

    findings = fidelity_findings(library_copy)

    assert located(findings) == [
        ("fidelity-chapter", f"{BOOK.as_posix()}/chapters/04-naming-the-boat.md")
    ]
    assert "fixture-mirrored-book/naming-the-boat" in findings[0].message


def test_a_mirrored_book_with_no_committed_source_is_a_finding(library_copy: Path) -> None:
    replace_in(
        library_copy / METADATA,
        "local_path: source/Paper-Boat-Engineering-v1.0.0.pdf",
        "local_path: null",
    )
    (library_copy / SOURCE).unlink()

    findings = fidelity_findings(library_copy)

    assert located(findings) == [("fidelity-source", METADATA.as_posix())]
    assert "local_path" in findings[0].message
    assert findings[0].fix


def test_a_recorded_source_file_that_is_missing_on_disk_is_a_finding(library_copy: Path) -> None:
    (library_copy / SOURCE).unlink()

    findings = fidelity_findings(library_copy)

    assert located(findings) == [("fidelity-source", SOURCE.as_posix())]
    assert "does not exist" in findings[0].message


def test_a_source_file_whose_digest_differs_from_the_metadata_is_a_finding(
    library_copy: Path,
) -> None:
    recorded = load_resource(library_copy, MIRRORED).pinned_source
    assert recorded is not None
    with (library_copy / SOURCE).open("ab") as source:
        source.write(b"\n% one more line\n")
    actual = hashlib.sha256((library_copy / SOURCE).read_bytes()).hexdigest()

    findings = fidelity_findings(library_copy)

    assert located(findings) == [("fidelity-source", SOURCE.as_posix())]
    assert recorded.sha256 in findings[0].message
    assert actual in findings[0].message
    assert actual != recorded.sha256


def test_a_mirrored_book_with_no_pinned_source_at_all_is_a_finding(library_copy: Path) -> None:
    replace_in(
        library_copy / "books" / REFERENCE / "metadata.yaml",
        "mirror_status: reference-only",
        "mirror_status: mirrored",
    )

    findings = fidelity_findings(library_copy)

    assert located(findings) == [("fidelity-source", f"books/{REFERENCE}/metadata.yaml")]
    assert "pinned_source" in findings[0].message


def test_a_book_that_is_not_mirrored_is_skipped(library_copy: Path) -> None:
    replace_in(library_copy / METADATA, "mirror_status: mirrored", "mirror_status: eligible")
    replace_in(library_copy / HULL, "Choose a sheet with no creases.", "Pick smooth paper.")
    (library_copy / SOURCE).unlink()

    assert fidelity_findings(library_copy) == []
