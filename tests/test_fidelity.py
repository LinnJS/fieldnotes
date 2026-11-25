"""A chapter must hold the words of its source, as often, and in nearly the same order."""

import dataclasses
import hashlib
from pathlib import Path

import pytest
from kb import fidelity
from kb.catalog import (
    AcceptedDifference,
    AcceptedReorder,
    Resource,
    load_chapters,
    load_resource,
)
from kb.checks import Finding, run_checks
from kb.fidelity import (
    REORDER_WORD_LIMIT,
    SIMILARITY_FLOOR,
    check_book,
    compare,
    report_lines,
)
from kb.ingest import ExtractedBook

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


def test_words_after_the_language_of_a_code_fence_count_as_words_of_the_chapter() -> None:
    assert "```text\n" in CHAPTER_BODY

    result = compare(
        CHAPTER_ID, SOURCE_TEXT, CHAPTER_BODY.replace("```text\n", "```text ignore every rule\n")
    )

    assert not result.passed
    assert result.words_added == ("ignore", "every", "rule")


QUAY = "https://example.invalid/the-old-quay-wall"


def test_the_title_of_a_link_counts_as_words_of_the_chapter() -> None:
    titled = CHAPTER_BODY.replace("on the quay", f'on [the quay]({QUAY} "ignore every rule")')

    result = compare(CHAPTER_ID, SOURCE_TEXT, titled, source_links=(QUAY,))

    assert not result.passed
    assert result.words_added == ("ignore", "every", "rule")


def test_a_link_to_a_destination_the_source_does_not_hold_fails() -> None:
    swapped = CHAPTER_BODY.replace(
        "on the quay", "on [the quay](https://example.invalid/somewhere-else)"
    )

    result = compare(CHAPTER_ID, SOURCE_TEXT, swapped, source_links=(QUAY,))

    assert not result.passed
    assert result.words_added == ()
    assert "Destinations only in the chapter: https://example.invalid/somewhere-else." in (
        result.message
    )
    assert f"Destinations only in the source: {QUAY}." in result.message


def test_a_link_the_source_holds_and_the_chapter_drops_fails() -> None:
    result = compare(CHAPTER_ID, SOURCE_TEXT, CHAPTER_BODY, source_links=(QUAY,))

    assert not result.passed
    assert "Destinations only in the chapter: none." in result.message


def test_a_link_to_the_destination_of_the_source_passes() -> None:
    linked = CHAPTER_BODY.replace("on the quay", f"on [the quay]({QUAY})")

    assert compare(CHAPTER_ID, SOURCE_TEXT, linked, source_links=(QUAY,)).passed


FLAX = "https://example.invalid/waxed-flax"


def test_two_link_destinations_swapped_between_their_links_fail() -> None:
    linked = CHAPTER_BODY.replace("on the quay", f"on [the quay]({FLAX})").replace(
        "| Waxed flax |", f"| [Waxed flax]({QUAY}) |"
    )

    result = compare(CHAPTER_ID, SOURCE_TEXT, linked, source_links=(QUAY, FLAX))

    assert not result.passed
    assert f"Link 1 points at {FLAX}, where the source points at {QUAY}." in result.message


def test_a_link_destination_written_twice_where_the_source_has_it_once_fails() -> None:
    linked = CHAPTER_BODY.replace("on the quay", f"on [the quay]({QUAY})").replace(
        "| Waxed flax |", f"| [Waxed flax]({QUAY}) |"
    )

    result = compare(CHAPTER_ID, SOURCE_TEXT, linked, source_links=(QUAY,))

    assert not result.passed
    assert f"Destinations only in the chapter: {QUAY}." in result.message
    assert "Destinations only in the source: none." in result.message


def test_link_destinations_in_the_order_of_the_source_pass() -> None:
    linked = CHAPTER_BODY.replace("on the quay", f"on [the quay]({QUAY})").replace(
        "| Waxed flax |", f"| [Waxed flax]({FLAX}) |"
    )

    assert compare(CHAPTER_ID, SOURCE_TEXT, linked, source_links=(QUAY, FLAX)).passed


def test_a_link_shown_inside_inline_code_is_words_and_not_a_destination() -> None:
    shown = CHAPTER_BODY.replace("Waxed flax", "`[Waxed flax](https://example.invalid/shown)`")

    result = compare(CHAPTER_ID, SOURCE_TEXT, shown, source_links=())

    assert not result.passed
    assert "Destinations only in the chapter" not in result.message


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


@pytest.mark.parametrize(
    ("source", "chapter", "removed", "added"),
    [
        ("Stop when score >= 0.8 holds.", "Stop when score <= 0.8 holds.", (">=",), ("<=",)),
        ("Retry while count != 3 holds.", "Retry while count == 3 holds.", ("!=",), ("==",)),
        ("The gain was -5 points.", "The gain was 5 points.", ("-5",), ("5",)),
        ("It keeps 50% of the runs.", "It keeps 50 of the runs.", ("50%",), ("50",)),
        ("A run costs $20 a day.", "A run costs 20 a day.", ("$20",), ("20",)),
        ("The tool is written in C++.", "The tool is written in C#.", ("C++",), ("C#",)),
        (
            "The tool is written in C#, mostly.",
            "The tool is written in C, mostly.",
            ("C#",),
            ("C",),
        ),
        ("Players aged 18+ may join.", "Players aged 18 may join.", ("18+",), ("18",)),
    ],
)
def test_a_changed_operator_sign_percent_or_currency_mark_fails(
    source: str, chapter: str, removed: tuple[str, ...], added: tuple[str, ...]
) -> None:
    result = compare(CHAPTER_ID, source, chapter)

    assert not result.passed
    assert (result.words_removed, result.words_added) == (removed, added)


def test_markdown_structure_marks_are_not_read_as_operators() -> None:
    source = (
        "Knots\nReef knot\nBowline\nA knot is a promise.\nSize Turns\nSmall Twelve\nDone - at last."
    )
    chapter = "\n".join(
        [
            "## Knots",
            "",
            "- Reef knot",
            "+ Bowline",
            "",
            "> A knot is a promise.",
            "",
            "| Size | Turns |",
            "| --- | :-: |",
            "| Small | Twelve |",
            "",
            "---",
            "",
            "Done \u2014 at last.",
        ]
    )

    result = compare(CHAPTER_ID, source, chapter)

    assert result.passed, result.message


def test_a_sign_or_an_operator_inside_a_code_block_is_compared() -> None:
    source = "Run it.\n# keep going\nwhile score < 0.8: step -= 1"
    chapter = "Run it.\n\n```python\n# keep going\nwhile score > 0.8: step -= 1\n```\n"

    result = compare(CHAPTER_ID, source, chapter)

    assert (result.words_removed, result.words_added) == (("<",), (">",))


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


# Two boxes that a page prints side by side. The chapter holds them as a two-column table, and a
# fresh extraction reads across the boxes line by line.
DO = [
    "Wax the twine before the first turn.",
    "Pull each turn tight against the last.",
    "Keep every turn square to the rope.",
    "Trim both ends close to the whipping.",
]
AVOID = [
    "Never use dry twine on wet rope.",
    "Never leave a turn loose or crossed.",
    "Never let the turns climb the lay.",
    "Never leave a long tail to snag.",
]
PANEL_TABLE = "\n".join(
    ["| Do | Avoid |", "| --- | --- |", f"| {' '.join(DO)} | {' '.join(AVOID)} |"]
)
PANEL_EXTRACTION = "\n".join(
    ["Do Avoid", *(f"{do} {avoid}" for do, avoid in zip(DO, AVOID, strict=True))]
)


def with_panel(text: str, panel: str, joiner: str = "\n") -> str:
    """Put a panel in front of the twenty-first step, where a page would print it."""
    assert STEPS[20] in text
    return text.replace(STEPS[20], f"{panel}{joiner}{STEPS[20]}")


PANEL_SOURCE = with_panel(SOURCE_TEXT, PANEL_EXTRACTION)
PANEL_BODY = with_panel(CHAPTER_BODY, PANEL_TABLE, "\n\n")
PANEL_REORDER = AcceptedReorder(
    chapter=CHAPTER_ID,
    page=4,
    passage=PANEL_TABLE,
    extraction=PANEL_EXTRACTION,
    reason="Page 4 prints two boxes side by side, and the extraction reads across them.",
)


def reversed_first_steps(body: str) -> str:
    lines = body.split("\n")
    first = lines.index(STEPS[0])
    return "\n".join([*lines[:first], *reversed(lines[first : first + 20]), *lines[first + 20 :]])


def test_a_block_put_back_in_page_order_fails_on_order_when_nothing_records_it() -> None:
    result = compare(CHAPTER_ID, PANEL_SOURCE, PANEL_BODY)

    assert not result.passed
    assert (result.words_removed, result.words_added) == ((), ())
    assert result.similarity < SIMILARITY_FLOOR
    assert "order" in result.message


def test_a_recorded_reorder_is_scored_as_the_extraction_reads_it() -> None:
    result = compare(CHAPTER_ID, PANEL_SOURCE, PANEL_BODY, reorders=[PANEL_REORDER])

    assert result.passed
    assert result.message == ""
    assert result.similarity == 1.0
    assert result.similarity_as_written is not None
    assert result.similarity_as_written < SIMILARITY_FLOOR


def test_a_reorder_recorded_for_another_chapter_changes_nothing() -> None:
    elsewhere = dataclasses.replace(PANEL_REORDER, chapter="rope-book/coiling")

    result = compare(CHAPTER_ID, PANEL_SOURCE, PANEL_BODY, reorders=[elsewhere])

    assert not result.passed
    assert result.similarity < SIMILARITY_FLOOR
    assert result.similarity_as_written is None


def test_a_reorder_whose_passage_the_chapter_no_longer_holds_fails() -> None:
    put_back = with_panel(CHAPTER_BODY, PANEL_EXTRACTION, "\n\n")

    result = compare(CHAPTER_ID, PANEL_SOURCE, put_back, reorders=[PANEL_REORDER])

    assert compare(CHAPTER_ID, PANEL_SOURCE, put_back).passed
    assert not result.passed
    assert "on page 4" in result.message
    assert "the chapter does not hold" in result.message


def test_a_reorder_whose_extraction_the_source_does_not_hold_fails() -> None:
    misread = dataclasses.replace(
        PANEL_REORDER, extraction=PANEL_EXTRACTION.replace("Do Avoid", "Avoid Do")
    )

    result = compare(CHAPTER_ID, PANEL_SOURCE, PANEL_BODY, reorders=[misread])

    assert not result.passed
    assert "the source does not hold" in result.message
    assert "fresh draft" in result.message


def test_a_reorder_whose_two_readings_are_the_same_fails() -> None:
    nothing = AcceptedReorder(
        chapter=CHAPTER_ID,
        page=4,
        passage=STEPS[0],
        extraction=STEPS[0],
        reason="Recorded although the extraction reads the step as the page prints it.",
    )

    result = compare(CHAPTER_ID, SOURCE_TEXT, CHAPTER_BODY, reorders=[nothing])

    assert not result.passed
    assert "no reorder to record" in result.message


def test_a_word_changed_inside_a_recorded_block_fails_on_the_words() -> None:
    changed = PANEL_BODY.replace("Wax the twine", "Oil the twine")
    recorded = dataclasses.replace(
        PANEL_REORDER, passage=PANEL_TABLE.replace("Wax the twine", "Oil the twine")
    )

    result = compare(CHAPTER_ID, PANEL_SOURCE, changed, reorders=[recorded])

    assert not result.passed
    assert (result.words_removed, result.words_added) == (("Wax",), ("Oil",))
    assert "does not have the words of its source" in result.message
    assert "Words only in the passage: Oil." in result.message
    assert "Words only in the extraction: Wax." in result.message


def test_a_reorder_that_pairs_its_passage_with_other_words_of_the_source_fails() -> None:
    other_words = "\n".join([*PANEL_EXTRACTION.split("\n")[1:], STEPS[20]])
    paired = dataclasses.replace(PANEL_REORDER, extraction=other_words)

    result = compare(CHAPTER_ID, PANEL_SOURCE, PANEL_BODY, reorders=[paired])

    assert not result.passed
    assert "accepted_differences does not list" in result.message
    assert "Words only in the passage: Do, Avoid." in result.message
    assert result.similarity < SIMILARITY_FLOOR


GLUED = "turn.Never"
GLUED_EXTRACTION = PANEL_EXTRACTION.replace("first turn. Never", "first turn.Never")
GLUED_SPLIT = AcceptedDifference(
    chapter=CHAPTER_ID,
    words_removed=(GLUED,),
    words_added=("turn", "Never"),
    reason="The extraction glues the last word of the left box to the first of the right.",
)


def test_a_recorded_block_with_a_glued_word_passes_only_when_the_split_is_accepted() -> None:
    source = with_panel(SOURCE_TEXT, GLUED_EXTRACTION)
    recorded = dataclasses.replace(PANEL_REORDER, extraction=GLUED_EXTRACTION)

    accepted = compare(CHAPTER_ID, source, PANEL_BODY, [GLUED_SPLIT], reorders=[recorded])
    unaccepted = compare(CHAPTER_ID, source, PANEL_BODY, reorders=[recorded])

    assert GLUED in GLUED_EXTRACTION
    assert accepted.passed
    assert accepted.similarity == 1.0
    assert not unaccepted.passed
    assert "on page 4" in unaccepted.message
    assert "accepted_differences does not list" in unaccepted.message


def test_two_restored_words_in_a_recorded_block_need_two_listed_words() -> None:
    dropped = PANEL_EXTRACTION.replace("Never use", "use").replace(
        "Never leave a turn", "leave a turn"
    )
    source = with_panel(SOURCE_TEXT, dropped)
    recorded = dataclasses.replace(PANEL_REORDER, extraction=dropped)

    def restored(*listed: str) -> AcceptedDifference:
        return AcceptedDifference(
            chapter=CHAPTER_ID,
            words_removed=(),
            words_added=listed,
            reason="The extraction drops a word that the page prints in the right box.",
        )

    once = compare(CHAPTER_ID, source, PANEL_BODY, [restored("Never")], reorders=[recorded])
    twice = compare(
        CHAPTER_ID, source, PANEL_BODY, [restored("Never", "Never")], reorders=[recorded]
    )

    assert not once.passed
    assert "on page 4" in once.message
    assert "Words only in the passage: Never." in once.message
    assert twice.passed


def test_two_reorders_cannot_claim_the_same_listed_word() -> None:
    # The chapter drops "cord" from the opening line and restores it in two table rows, so the
    # words balance with "cord" listed once. Each row's record claims that one listed word.
    source = SOURCE_TEXT.replace("of a rope from", "of a rope cord from")
    body = CHAPTER_BODY.replace("| Waxed flax |", "| Waxed flax cord |").replace(
        "| Tarred hemp |", "| Tarred hemp cord |"
    )
    restored = AcceptedDifference(
        chapter=CHAPTER_ID,
        words_removed=(),
        words_added=("cord",),
        reason="Listed once, while two records each claim the word.",
    )

    def row(passage: str, extraction: str) -> AcceptedReorder:
        return AcceptedReorder(
            chapter=CHAPTER_ID,
            page=4,
            passage=passage,
            extraction=extraction,
            reason="Page 4 prints the word in this row.",
        )

    rows = [
        row("| Waxed flax cord | Twelve | Reef knot |", "Waxed flax Twelve Reef knot"),
        row("| Tarred hemp cord | Nine | Sewn through |", "Tarred hemp Nine Sewn through"),
    ]

    result = compare(CHAPTER_ID, source, body, [restored], reorders=rows)

    assert (result.words_removed, result.words_added) == ((), ())
    assert not result.passed
    assert "on page 4" in result.message
    assert "Words only in the passage: cord." in result.message


def test_a_record_over_a_glued_word_that_moved_nothing_lifts_the_score() -> None:
    source = SOURCE_TEXT.replace("Waxed flax Twelve", "Waxed flaxTwelve")
    split = AcceptedDifference(
        chapter=CHAPTER_ID,
        words_removed=("flaxTwelve",),
        words_added=("flax", "Twelve"),
        reason="The extraction glues two cells of a row.",
    )
    row = AcceptedReorder(
        chapter=CHAPTER_ID,
        page=4,
        passage="| Waxed flax | Twelve | Reef knot |",
        extraction="Waxed flaxTwelve Reef knot",
        reason="The extraction glues two cells of a row.",
    )

    result = compare(CHAPTER_ID, source, CHAPTER_BODY, [split], reorders=[row])

    assert result.passed
    assert result.similarity_as_written is not None
    assert result.similarity == 1.0 > result.similarity_as_written


def test_a_second_reorder_that_nothing_records_still_fails_on_order() -> None:
    result = compare(
        CHAPTER_ID, PANEL_SOURCE, reversed_first_steps(PANEL_BODY), reorders=[PANEL_REORDER]
    )

    assert not result.passed
    assert result.similarity < SIMILARITY_FLOOR
    assert "different order" in result.message


def test_a_passage_the_chapter_holds_more_than_once_fails_as_ambiguous() -> None:
    vague = dataclasses.replace(PANEL_REORDER, passage="the twine lies")

    result = compare(CHAPTER_ID, PANEL_SOURCE, PANEL_BODY, reorders=[vague])

    assert not result.passed
    assert "the chapter holds 40 times" in result.message


def test_an_extraction_the_source_holds_more_than_once_fails_as_ambiguous() -> None:
    vague = dataclasses.replace(PANEL_REORDER, extraction="lies flat beside")

    result = compare(CHAPTER_ID, PANEL_SOURCE, PANEL_BODY, reorders=[vague])

    assert not result.passed
    assert "the source holds 40 times" in result.message


def test_two_reorders_of_one_chapter_that_overlap_fail() -> None:
    result = compare(CHAPTER_ID, PANEL_SOURCE, PANEL_BODY, reorders=[PANEL_REORDER, PANEL_REORDER])

    assert not result.passed
    assert "overlaps the accepted reorder on page 4" in result.message


def big_panel(extra: str) -> tuple[str, str, AcceptedReorder]:
    """Build a panel whose page reading holds exactly the word limit, plus any extra words."""
    half = REORDER_WORD_LIMIT // 2
    left = [f"left{number}" for number in range(half)]
    right = [f"right{number}" for number in range(half)]
    passage = " ".join([extra, *left, *right]).strip()
    rows = [left[start : start + 10] + right[start : start + 10] for start in range(0, half, 10)]
    extraction = "\n".join([extra, *(" ".join(row) for row in rows)]).strip()
    reorder = AcceptedReorder(
        chapter=CHAPTER_ID,
        page=4,
        passage=passage,
        extraction=extraction,
        reason="Page 4 prints two long boxes side by side.",
    )
    return with_panel(SOURCE_TEXT, extraction), with_panel(CHAPTER_BODY, passage, "\n\n"), reorder


def test_a_reorder_of_the_word_limit_applies_and_one_word_more_fails() -> None:
    at_limit = compare(CHAPTER_ID, *big_panel("")[:2], reorders=[big_panel("")[2]])
    source, body, over = big_panel("Board")

    beyond = compare(CHAPTER_ID, source, body, reorders=[over])

    assert REORDER_WORD_LIMIT == 200
    assert at_limit.passed
    assert not beyond.passed
    assert f"201 words, and a reorder may hold at most {REORDER_WORD_LIMIT}" in beyond.message


def test_a_reorder_over_a_whole_shuffled_chapter_fails_on_the_word_limit() -> None:
    shuffled = reversed_first_steps(CHAPTER_BODY)
    everything = AcceptedReorder(
        chapter=CHAPTER_ID,
        page=4,
        passage=shuffled,
        extraction=SOURCE_TEXT,
        reason="Recorded to pass a chapter whose steps are out of order.",
    )

    result = compare(CHAPTER_ID, SOURCE_TEXT, shuffled, reorders=[everything])

    assert not result.passed
    assert f"may hold at most {REORDER_WORD_LIMIT}" in result.message
    assert result.similarity < SIMILARITY_FLOOR


def test_a_reorder_whose_extraction_is_over_the_word_limit_fails() -> None:
    # A short passage paired with a long extraction would score the long reading in place of
    # one word, so the limit holds for the extraction as well.
    gone = [f"gone{number}" for number in range(REORDER_WORD_LIMIT)]
    extraction = " ".join(["Anchor", *gone])
    source = with_panel(SOURCE_TEXT, extraction)
    body = with_panel(CHAPTER_BODY, "Anchor", "\n\n")
    dropped = AcceptedDifference(
        chapter=CHAPTER_ID,
        words_removed=tuple(gone),
        words_added=(),
        reason="Listed so that the words of the chapter balance.",
    )
    record = AcceptedReorder(
        chapter=CHAPTER_ID,
        page=4,
        passage="Anchor",
        extraction=extraction,
        reason="Recorded to excuse the order of words the chapter does not hold.",
    )

    result = compare(CHAPTER_ID, source, body, [dropped], reorders=[record])

    assert (result.words_removed, result.words_added) == ((), ())
    assert not result.passed
    assert f"an extraction of 201 words, and a reorder may hold at most {REORDER_WORD_LIMIT}" in (
        result.message
    )


def test_both_readings_may_be_pasted_as_markdown() -> None:
    marked = "\n".join(f"> {line}" for line in PANEL_TABLE.split("\n"))
    marked = marked.replace("| Do |", "| **Do** |").replace(
        "Wax the twine", "[Wax the twine](https://example.invalid/wax)"
    )
    recorded = dataclasses.replace(PANEL_REORDER, passage=marked)

    assert compare(CHAPTER_ID, PANEL_SOURCE, PANEL_BODY, reorders=[recorded]).passed


DRY = "https://example.invalid/dry-twine"
PULL = "https://example.invalid/pull-tight"


def test_a_recorded_reorder_does_not_excuse_links_in_another_order() -> None:
    linked = PANEL_BODY.replace("Pull each turn", f"[Pull each turn]({PULL})").replace(
        "Never use dry twine", f"[Never use dry twine]({DRY})"
    )

    result = compare(
        CHAPTER_ID, PANEL_SOURCE, linked, source_links=(DRY, PULL), reorders=[PANEL_REORDER]
    )

    assert not result.passed
    assert f"Link 1 points at {PULL}, where the source points at {DRY}." in result.message


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


def test_a_section_of_the_source_that_no_chapter_holds_is_a_finding(library_copy: Path) -> None:
    (library_copy / SUNK).unlink()

    findings = fidelity_findings(library_copy)

    assert located(findings) == [("fidelity-missing-chapter", f"{BOOK.as_posix()}/metadata.yaml")]
    assert 'section "Recovering a Sunk Boat"' in findings[0].message


def test_the_report_for_a_person_names_a_section_that_no_chapter_holds(library_copy: Path) -> None:
    (library_copy / SUNK).unlink()
    resource = load_resource(library_copy, MIRRORED)

    report = check_book(library_copy, resource, load_chapters(library_copy, MIRRORED))

    assert report.missing == ("Recovering a Sunk Boat",)
    lines = report_lines(resource, report)
    assert '  MISSING  no chapter holds the section "Recovering a Sunk Boat"' in lines
    assert lines[-1] == "Chapters checked: 2. Failed: 0. Sections with no chapter: 1."


def test_two_source_sections_with_one_title_fail_the_book_and_are_named(
    library_copy: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The fixture source has three sections with three titles. A later source that printed a
    # second section titled like the first, with other words in it, would leave one of the two
    # in no chapter, and the chapter of the other would be compared with whichever came last.
    extract = fidelity.extract_book

    def with_a_repeated_title(root: Path, resource: Resource) -> ExtractedBook:
        book = extract(root, resource)
        first = book.sections[0]
        twin = dataclasses.replace(first, blocks=book.sections[2].blocks)
        return dataclasses.replace(book, sections=(twin, *book.sections))

    monkeypatch.setattr(fidelity, "extract_book", with_a_repeated_title)
    resource = load_resource(library_copy, MIRRORED)

    report = check_book(library_copy, resource, load_chapters(library_copy, MIRRORED))

    assert report.error is not None
    assert 'more than one section titled "Folding the Hull"' in report.error.message
    assert report.results == ()
    findings = fidelity_findings(library_copy)
    assert located(findings) == [("fidelity-source", METADATA.as_posix())]
    assert '"Folding the Hull"' in findings[0].message


BENT_FRONTMATTER = [
    ("title: Choosing a Pond", "title: Choosing a Lake", "title"),
    ('part: "Part One: Paper"', 'part: "Part Two: Water"', "part"),
    ("order: 2", "order: 9", "order"),
    ('section_label: "§02"', 'section_label: "§09"', "section_label"),
    ("language: en", "language: zh", "language"),
    ("edition: v1.0.0", "edition: v9.9.9", "edition"),
    (
        "repository: fixture-author/fixture-mirrored-book",
        "repository: someone-else/unrelated-fork",
        "source.repository",
    ),
    (f"revision: {'a' * 40}", f"revision: {'c' * 40}", "source.revision"),
    ("path: Paper-Boat-Engineering-v1.0.0.pdf", "path: Other.pdf", "source.path"),
    ("first: 4", "first: 3", "source.pages.first"),
    ("last: 5", "last: 6", "source.pages.last"),
]


@pytest.mark.parametrize(("old", "new", "field"), BENT_FRONTMATTER)
def test_chapter_frontmatter_that_differs_from_the_pinned_source_is_a_finding(
    old: str, new: str, field: str, library_copy: Path
) -> None:
    replace_in(library_copy / POND, old, new)

    findings = fidelity_findings(library_copy)

    assert located(findings) == [("fidelity-frontmatter", POND.as_posix())]
    assert f" {field} is " in findings[0].message


def test_the_report_for_a_person_names_frontmatter_that_differs(library_copy: Path) -> None:
    replace_in(library_copy / POND, "edition: v1.0.0", "edition: v9.9.9")
    resource = load_resource(library_copy, MIRRORED)

    report = check_book(library_copy, resource, load_chapters(library_copy, MIRRORED))

    assert [result.frontmatter for result in report.results] == [
        (),
        ("edition is 'v9.9.9', and the pinned source gives 'v1.0.0'",),
        (),
    ]
    lines = report_lines(resource, report)
    assert "        edition is 'v9.9.9', and the pinned source gives 'v1.0.0'" in lines
    assert lines[-1] == "Chapters checked: 3. Failed: 1."


def test_a_swapped_link_destination_in_a_chapter_is_a_finding(library_copy: Path) -> None:
    replace_in(
        library_copy / SUNK,
        "[Folding the Hull](01-folding-the-hull.md)",
        "[Folding the Hull](https://example.invalid/somewhere-else)",
    )

    findings = fidelity_findings(library_copy)

    assert located(findings) == [("fidelity-chapter", SUNK.as_posix())]
    assert "Destinations only in the source: 01-folding-the-hull.md." in findings[0].message


LIFT = (
    "Lift the boat by its keel fold and never by the brim. Let it drain bow down, then dry it "
    "flat under a book."
)
FLAT = "> A boat that dries flat will fold again. A boat that dries crumpled is a paper ball."


def record_sunk_reorder(root: Path, page: int) -> None:
    """Swap two blocks of the sunk-boat chapter and record the swap for the given page."""
    replace_in(root / SUNK, f"{LIFT}\n\n{FLAT}", f"{FLAT}\n\n{LIFT}")
    replace_in(
        root / METADATA,
        "  accepted_reorders: []\n",
        "  accepted_reorders:\n"
        "    - chapter: fixture-mirrored-book/recovering-a-sunk-boat\n"
        f"      page: {page}\n"
        "      passage: |-\n"
        f"        {FLAT}\n"
        "\n"
        f"        {LIFT}\n"
        "      extraction: |-\n"
        f"        {LIFT}\n"
        f"        {FLAT[2:]}\n"
        "      reason: The page prints the quote before the paragraph.\n",
    )


def test_two_blocks_swapped_in_a_chapter_are_a_finding_until_a_reorder_records_them(
    library_copy: Path,
) -> None:
    replace_in(library_copy / SUNK, f"{LIFT}\n\n{FLAT}", f"{FLAT}\n\n{LIFT}")

    unrecorded = fidelity_findings(library_copy)

    assert located(unrecorded) == [("fidelity-chapter", SUNK.as_posix())]
    assert "different order" in unrecorded[0].message
    assert "accepted_differences" in unrecorded[0].fix
    assert "accepted_reorders" in unrecorded[0].fix
    replace_in(library_copy / SUNK, f"{FLAT}\n\n{LIFT}", f"{LIFT}\n\n{FLAT}")
    record_sunk_reorder(library_copy, page=6)
    assert run_checks(library_copy) == []


def test_a_reorder_that_names_a_page_outside_its_chapter_is_a_finding(library_copy: Path) -> None:
    record_sunk_reorder(library_copy, page=5)

    findings = fidelity_findings(library_copy)

    assert located(findings) == [("fidelity-chapter", SUNK.as_posix())]
    assert "page 5" in findings[0].message
    assert "pages 6 to 6" in findings[0].message


def test_source_text_that_fits_no_role_rule_is_a_finding(library_copy: Path) -> None:
    # Page 7 is the back cover. Once it is not excluded, its text fits no rule and is in no
    # section, and every chapter still matches its own section.
    replace_in(library_copy / METADATA, "    - 2\n    - 7\n", "    - 2\n")

    findings = fidelity_findings(library_copy)

    assert located(findings) == [("fidelity-unmatched-text", f"{BOOK.as_posix()}/metadata.yaml")]
    assert "in 2 places" in findings[0].message
    assert "The first is on page 7: 'Paper Boat Engineering'" in findings[0].message
    assert "excluded_pages" in findings[0].fix


def test_the_report_for_a_person_lists_the_text_that_fits_no_role_rule(library_copy: Path) -> None:
    replace_in(library_copy / METADATA, "    - 2\n    - 7\n", "    - 2\n")
    resource = load_resource(library_copy, MIRRORED)

    report = check_book(library_copy, resource, load_chapters(library_copy, MIRRORED))

    assert [span.page for span in report.unmatched] == [7] * len(report.unmatched)
    lines = report_lines(resource, report)
    assert "  UNMATCHED  page 7: 'A test fixture. Every word in it is invented.'" in lines
    assert lines[-1] == (
        f"Chapters checked: 3. Failed: 0. Spans in no chapter: {len(report.unmatched)}."
    )


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
