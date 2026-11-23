"""Topic documents are reading paths whose references, citations, and paragraphs are checked."""

import json
from pathlib import Path

import pytest
from kb.catalog import load_topics
from kb.checks import Finding, run_checks

# Ruff sorts this import as first-party when an ignored build/ directory exists and as
# third-party when it does not, so it is kept out of the sorting.
import build  # isort: skip

PAPER = "topics/paper-craft.md"
TEA = "topics/tea-service.md"
HULL = "fixture-mirrored-book/folding-the-hull"
POND = "fixture-mirrored-book/choosing-a-pond"
SUNK = "fixture-mirrored-book/recovering-a-sunk-boat"

REFERENCE_BOOK_ENTRY = "  - resource: fixture-reference-book\n"
POND_ENTRY = (
    "  - resource: fixture-mirrored-book\n"
    f"    chapter: {POND}\n"
    "    note: Covers how to pick the water for a launch.\n"
)
NO_COVERAGE = (
    "No mirrored chapter covers this topic yet, and the books listed below are read at their "
    "official sources."
)

LOOP = "loop-engineering-orange-book"

# The mirrored chapters each topic of the real library references, in the order the topic lists
# them. A chapter belongs here only after it was read and found to cover the topic.
MIRRORED_CHAPTERS = {
    "agent-architecture": [
        "from-prompt-to-context-to-loop",
        "five-moves-of-one-loop",
        "six-parts-of-a-loop",
    ],
    "agent-orchestration": [
        "five-moves-of-one-loop",
        "six-parts-of-a-loop",
        "loops-that-run-while-you-sleep",
    ],
    "agent-reliability": ["loops-that-run-while-you-sleep", "costs"],
    "agent-security": [],
    "coding-agents": [
        "generator-and-evaluator",
        "loops-that-run-while-you-sleep",
        "build-your-first-loop",
    ],
    "context-engineering": ["from-prompt-to-context-to-loop", "loops-that-run-while-you-sleep"],
    "development-workflows": [
        "what-loop-engineering-really-is",
        "five-moves-of-one-loop",
        "stay-the-engineer",
        "build-your-first-loop",
    ],
    "evaluation-and-testing": [
        "five-moves-of-one-loop",
        "generator-and-evaluator",
        "costs",
        "build-your-first-loop",
    ],
    "harness-engineering": ["from-prompt-to-context-to-loop"],
    "memory-and-state-management": [
        "five-moves-of-one-loop",
        "six-parts-of-a-loop",
        "build-your-first-loop",
    ],
    "tool-use-and-integration": ["six-parts-of-a-loop", "generator-and-evaluator"],
}


def replace_in(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    assert old in text, f"{old!r} is not in {path}"
    path.write_text(text.replace(old, new), encoding="utf-8")


def append_to(path: Path, text: str) -> None:
    with path.open("a", encoding="utf-8") as file:
        file.write(text)


def topic_findings(root: Path) -> list[Finding]:
    """Return the findings of a library, without the stale indexes every edited copy has."""
    return [finding for finding in run_checks(root) if finding.rule != "index-stale"]


def located(findings: list[Finding]) -> list[tuple[str, str, int | None]]:
    return [(finding.rule, finding.file, finding.line) for finding in findings]


def rebuild(root: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert build.main(["--root", str(root)]) == 0
    capsys.readouterr()


def test_a_topic_that_references_an_existing_chapter_has_no_finding(library_copy: Path) -> None:
    replace_in(library_copy / PAPER, REFERENCE_BOOK_ENTRY, POND_ENTRY + REFERENCE_BOOK_ENTRY)

    assert topic_findings(library_copy) == []


def test_a_chapter_id_that_does_not_exist_is_a_finding_that_names_the_topic_and_the_id(
    library_copy: Path,
) -> None:
    replace_in(
        library_copy / PAPER, f"chapter: {HULL}", "chapter: fixture-mirrored-book/folding-the-sail"
    )

    findings = topic_findings(library_copy)

    assert located(findings) == [("topic-reference-chapter", PAPER, None)]
    assert "paper-craft" in findings[0].message
    assert "fixture-mirrored-book/folding-the-sail" in findings[0].message


def test_a_chapter_id_under_a_reference_only_book_is_a_finding(library_copy: Path) -> None:
    replace_in(
        library_copy / TEA,
        REFERENCE_BOOK_ENTRY,
        REFERENCE_BOOK_ENTRY + "    chapter: fixture-reference-book/steeping\n",
    )

    findings = topic_findings(library_copy)

    assert located(findings) == [("topic-reference-not-mirrored", TEA, None)]
    assert "fixture-reference-book/steeping" in findings[0].message
    assert "reference-only" in findings[0].message


def test_an_unknown_resource_id_is_a_finding(library_copy: Path) -> None:
    replace_in(
        library_copy / TEA,
        "  - resource: fixture-reference-book",
        "  - resource: fixture-lost-book",
    )

    findings = topic_findings(library_copy)

    assert located(findings) == [("topic-reference-resource", TEA, None)]
    assert "fixture-lost-book" in findings[0].message


def test_a_quote_that_cites_a_reference_only_book_is_a_finding(library_copy: Path) -> None:
    # The fixture topic has 17 lines, so the blank line is line 18 and the quote is on line 19.
    append_to(
        library_copy / TEA,
        '\nThe manual says "Wind the kettle key nine turns" before the leaves go in. '
        "[cite:fixture-reference-book]\n",
    )

    findings = topic_findings(library_copy)

    # The paragraph also names no mirrored chapter, which is a finding of its own.
    assert located(findings) == [("topic-citation", TEA, 19), ("topic-uncited-paragraph", TEA, 19)]
    assert "reference-only" in findings[0].message
    assert "Wind the kettle key nine turns" in findings[0].message


def test_a_paragraph_after_the_scope_statement_with_no_token_is_a_finding(
    library_copy: Path,
) -> None:
    # The fixture topic has 27 lines, so the blank line is line 28 and the paragraph is line 29.
    append_to(library_copy / PAPER, "\nA brim folded twice sheds water.\n")

    findings = topic_findings(library_copy)

    assert located(findings) == [("topic-uncited-paragraph", PAPER, 29)]
    assert "paper-craft" in findings[0].message


def test_a_paragraph_that_cites_only_a_book_that_is_not_mirrored_is_a_finding(
    library_copy: Path,
) -> None:
    # The fixture topic has 27 lines, so the blank line is line 28 and the paragraph is line 29.
    append_to(
        library_copy / PAPER,
        "\nThe kettle manual tells the reader to wind the key before the leaves go in. "
        "[cite:fixture-reference-book]\n",
    )

    findings = topic_findings(library_copy)

    assert located(findings) == [("topic-uncited-paragraph", PAPER, 29)]
    assert "paper-craft" in findings[0].message
    assert "mirrored chapter" in findings[0].message


def test_a_paragraph_that_cites_a_mirrored_book_and_none_of_its_chapters_is_a_finding(
    library_copy: Path,
) -> None:
    append_to(
        library_copy / PAPER,
        "\nThe book covers folding, launching, and recovery. [cite:fixture-mirrored-book]\n",
    )

    assert located(topic_findings(library_copy)) == [("topic-uncited-paragraph", PAPER, 29)]


def test_a_paragraph_that_cites_a_mirrored_chapter_and_a_book_that_is_not_mirrored_passes(
    library_copy: Path,
) -> None:
    append_to(
        library_copy / PAPER,
        "\nThe hull chapter stops at three folds, and the kettle manual is about another craft. "
        f"[cite:{HULL}] [cite:fixture-reference-book]\n",
    )

    assert topic_findings(library_copy) == []


def test_a_block_quote_may_carry_its_token_on_the_next_line_with_text(library_copy: Path) -> None:
    append_to(
        library_copy / PAPER,
        "\n"
        "> A boat that dries flat will fold again. A boat that dries crumpled is a paper ball.\n"
        "\n"
        f"[cite:{SUNK}@v1.0.0]\n",
    )

    assert topic_findings(library_copy) == []


def test_a_fenced_block_with_no_token_is_a_finding(library_copy: Path) -> None:
    # The fixture topic has 27 lines, so the blank line is line 28 and the fence opens on 29.
    append_to(
        library_copy / PAPER,
        "\n```text\nWind the kettle key nine turns before the leaves go in.\n```\n",
    )

    findings = topic_findings(library_copy)

    assert located(findings) == [("topic-uncited-paragraph", PAPER, 29)]
    assert "Wind the kettle key" in findings[0].message


def test_a_fenced_block_that_never_closes_is_a_finding(library_copy: Path) -> None:
    append_to(
        library_copy / PAPER,
        "\n~~~\nWind the kettle key nine turns before the leaves go in.\n\nThen pour.\n",
    )

    assert located(topic_findings(library_copy)) == [("topic-uncited-paragraph", PAPER, 29)]


def test_a_fenced_block_may_carry_its_token_on_the_next_line_with_text(
    library_copy: Path,
) -> None:
    append_to(
        library_copy / PAPER,
        "\n```text\nfold, fold, fold, stop\n```\n\n"
        f"The hull chapter gives the count. [cite:{HULL}@v1.0.0]\n",
    )

    assert topic_findings(library_copy) == []


def test_a_heading_that_holds_a_sentence_needs_a_token_and_a_title_does_not(
    library_copy: Path,
) -> None:
    sentence = (
        "## Wind the kettle key nine turns before the leaves go in, and never wind it once "
        "the water has boiled"
    )
    append_to(library_copy / PAPER, f"\n{sentence}\n\n## Further reading\n")

    findings = topic_findings(library_copy)

    assert located(findings) == [("topic-uncited-paragraph", PAPER, 29)]
    assert "Wind the kettle key" in findings[0].message


def test_a_paragraph_of_the_landing_page_after_its_first_needs_a_token(
    library_copy: Path,
) -> None:
    (library_copy / "topics" / "index.md").write_text(
        "# Topics\n"
        "\n"
        "Each topic is a reading path through the library.\n"
        "\n"
        "| Topic | Mirrored chapters |\n"
        "| --- | --- |\n"
        "| [Paper Craft](paper-craft.md) | 2 |\n"
        "\n"
        "- [Paper Craft](paper-craft.md)\n"
        "\n"
        "Wind the kettle key nine turns before the leaves go in.\n"
        "\n"
        f"Stop after three folds. [cite:{HULL}]\n",
        encoding="utf-8",
    )

    findings = topic_findings(library_copy)

    assert located(findings) == [("topic-uncited-paragraph", "topics/index.md", 11)]
    assert "landing page" in findings[0].message


def test_a_quote_on_the_landing_page_that_cites_a_reference_only_book_is_a_finding(
    library_copy: Path,
) -> None:
    (library_copy / "topics" / "index.md").write_text(
        "# Topics\n"
        "\n"
        'The manual says "Wind the kettle key nine turns" first. '
        "[cite:fixture-reference-book]\n",
        encoding="utf-8",
    )

    findings = topic_findings(library_copy)

    assert located(findings) == [("topic-citation", "topics/index.md", 3)]
    assert "reference-only" in findings[0].message


def test_a_list_item_that_makes_a_claim_needs_a_token_and_a_pointer_does_not(
    library_copy: Path,
) -> None:
    # Lines 25 to 27 hold the two chapter links and the resolve instruction, which pass.
    append_to(library_copy / PAPER, "- `fixture-reference-book` explains how to wind a kettle.\n")

    assert located(topic_findings(library_copy)) == [("topic-uncited-paragraph", PAPER, 28)]


def test_the_no_coverage_sentence_is_allowed_only_word_for_word(library_copy: Path) -> None:
    replace_in(library_copy / TEA, NO_COVERAGE, "No mirrored chapter covers this topic yet.")

    assert located(topic_findings(library_copy)) == [("topic-uncited-paragraph", TEA, 13)]


def test_the_no_coverage_sentence_is_a_finding_in_a_topic_with_mirrored_chapters(
    library_copy: Path,
) -> None:
    append_to(library_copy / PAPER, f"\n{NO_COVERAGE}\n")

    assert located(topic_findings(library_copy)) == [("topic-uncited-paragraph", PAPER, 29)]


def test_a_body_that_does_not_open_with_the_labeled_scope_statement_is_a_finding(
    library_copy: Path,
) -> None:
    replace_in(library_copy / TEA, "**Scope (editorial).** This topic", "This topic")

    assert located(topic_findings(library_copy)) == [("topic-scope", TEA, 11)]


def test_a_file_name_that_differs_from_the_topic_id_is_a_finding(library_copy: Path) -> None:
    (library_copy / TEA).rename(library_copy / "topics" / "tea-time.md")

    findings = topic_findings(library_copy)

    assert located(findings) == [("topic-filename", "topics/tea-time.md", None)]
    assert "tea-service.md" in findings[0].message


def test_a_broken_link_on_the_topic_landing_page_is_a_finding(library_copy: Path) -> None:
    (library_copy / "topics" / "index.md").write_text(
        "# Topics\n"
        "\n"
        "| Topic | Mirrored chapters |\n"
        "| --- | --- |\n"
        "| [Paper Craft](paper-craft.md) | 2 |\n"
        "| [Kettle Care](kettle-care.md) | 0 |\n",
        encoding="utf-8",
    )

    findings = run_checks(library_copy)

    assert located(findings) == [("link-missing-target", "topics/index.md", 6)]
    assert "kettle-care.md" in findings[0].message


def test_the_topic_index_counts_the_mirrored_chapters_each_topic_references(
    library_copy: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    def counts() -> dict[str, int]:
        text = (library_copy / "index" / "topics.json").read_text(encoding="utf-8")
        return {topic["id"]: topic["mirrored_chapters"] for topic in json.loads(text)["topics"]}

    assert counts() == {"paper-craft": 2, "tea-service": 0}

    replace_in(library_copy / PAPER, REFERENCE_BOOK_ENTRY, POND_ENTRY + REFERENCE_BOOK_ENTRY)
    # A chapter id under a book that is not mirrored names no mirrored chapter.
    replace_in(
        library_copy / TEA,
        REFERENCE_BOOK_ENTRY,
        REFERENCE_BOOK_ENTRY + "    chapter: fixture-reference-book/steeping\n",
    )
    rebuild(library_copy, capsys)

    assert counts() == {"paper-craft": 3, "tea-service": 0}


def test_a_chapter_line_lists_the_topics_that_reference_it(
    library_copy: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    def topics_by_chapter() -> dict[str, list[str]]:
        text = (library_copy / "index" / "chapters.jsonl").read_text(encoding="utf-8")
        lines = [json.loads(line) for line in text.splitlines()]
        return {line["id"]: line["topics"] for line in lines}

    assert topics_by_chapter() == {HULL: ["paper-craft"], POND: [], SUNK: ["paper-craft"]}

    replace_in(library_copy / TEA, REFERENCE_BOOK_ENTRY, POND_ENTRY + REFERENCE_BOOK_ENTRY)
    rebuild(library_copy, capsys)

    assert topics_by_chapter() == {
        HULL: ["paper-craft"],
        POND: ["tea-service"],
        SUNK: ["paper-craft"],
    }


def test_the_library_has_the_eleven_topics_and_every_one_passes_the_checks(
    repo_root: Path,
) -> None:
    assert [topic_file.topic.id for topic_file in load_topics(repo_root)] == [
        "agent-architecture",
        "agent-orchestration",
        "agent-reliability",
        "agent-security",
        "coding-agents",
        "context-engineering",
        "development-workflows",
        "evaluation-and-testing",
        "harness-engineering",
        "memory-and-state-management",
        "tool-use-and-integration",
    ]
    in_topics = [finding for finding in run_checks(repo_root) if finding.file.startswith("topics/")]
    assert in_topics == []


def test_the_committed_topic_index_lists_each_topic_with_its_references_and_chapter_count(
    repo_root: Path,
) -> None:
    text = (repo_root / "index" / "topics.json").read_text(encoding="utf-8")
    topics = json.loads(text)["topics"]

    assert [topic["id"] for topic in topics] == list(MIRRORED_CHAPTERS)
    for topic in topics:
        expected = [f"{LOOP}/{slug}" for slug in MIRRORED_CHAPTERS[topic["id"]]]
        chapters = [ref["chapter"] for ref in topic["references"] if ref["chapter"]]
        assert chapters == expected, topic["id"]
        assert topic["mirrored_chapters"] == len(expected), topic["id"]
        assert topic["references"], topic["id"]


def test_the_landing_page_links_every_topic_and_gives_its_mirrored_chapter_count(
    repo_root: Path,
) -> None:
    rows = (repo_root / "topics" / "index.md").read_text(encoding="utf-8").splitlines()

    for topic_id, slugs in MIRRORED_CHAPTERS.items():
        [row] = [line for line in rows if f"]({topic_id}.md)" in line]
        assert row.endswith(f"| {len(slugs)} |"), topic_id
