"""The validation checks report what is wrong with a library as findings."""

from pathlib import Path

import pytest
from kb.catalog import Library
from kb.checks import CHECKS, Finding, run_checks

MIRRORED = "fixture-mirrored-book"
REFERENCE = "fixture-reference-book"

CHAPTER_TEMPLATE = """\
---
id: {resource}/{slug}
resource: {resource}
title: Invented Section
part: "Part One: Paper"
order: {order}
section_label: "§0{order}"
language: en
edition: v1.0.0
source:
  repository: fixture-author/fixture-mirrored-book
  revision: aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
  path: Paper-Boat-Engineering-v1.0.0.pdf
  pages:
    first: 3
    last: 4
extraction_status: machine-extracted
---

# Invented Section

Test fixture. This text is invented for automated tests.
"""

# The link sits on line 11 of the file, counted from the opening frontmatter fence.
TOPIC_WITH_BROKEN_LINK = """\
---
id: tea-service
title: Tea Service
references:
  - resource: fixture-reference-book
    note: Listed for its subject only.
---

# Tea Service

See [the kettle guide](kettle-guide.md) for more.
"""


def write_chapter(
    root: Path, directory: str, file_name: str, *, resource: str, slug: str, order: int
) -> Path:
    path = root / "books" / directory / "chapters" / file_name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        CHAPTER_TEMPLATE.format(resource=resource, slug=slug, order=order), encoding="utf-8"
    )
    return path


def replace_in(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    assert old in text, f"{old!r} is not in {path}"
    path.write_text(text.replace(old, new), encoding="utf-8")


def located(findings: list[Finding]) -> list[tuple[str, str, int | None]]:
    return [(finding.rule, finding.file, finding.line) for finding in findings]


def test_the_fixture_library_has_no_findings(fixture_library_root: Path) -> None:
    assert run_checks(fixture_library_root) == []


def test_every_finding_carries_a_fix_hint(library_copy: Path) -> None:
    (library_copy / "books" / REFERENCE / "source").mkdir()
    (library_copy / "books" / REFERENCE / "source" / "book.pdf").write_bytes(b"%PDF-1.7\n")

    [finding] = run_checks(library_copy)

    assert finding.message
    assert finding.fix


def test_a_chapter_under_a_reference_only_book_is_a_finding_that_names_the_file(
    library_copy: Path,
) -> None:
    write_chapter(
        library_copy, REFERENCE, "01-steeping.md", resource=REFERENCE, slug="steeping", order=1
    )

    findings = run_checks(library_copy)

    assert located(findings) == [
        ("gate-content", "books/fixture-reference-book/chapters/01-steeping.md", None)
    ]
    assert "reference-only" in findings[0].message


def test_a_source_file_under_a_reference_only_book_is_a_finding(library_copy: Path) -> None:
    (library_copy / "books" / REFERENCE / "source").mkdir()
    (library_copy / "books" / REFERENCE / "source" / "book.pdf").write_bytes(b"%PDF-1.7\n")

    assert located(run_checks(library_copy)) == [
        ("gate-content", "books/fixture-reference-book/source/book.pdf", None)
    ]


def test_an_eligible_book_may_hold_only_its_metadata(library_copy: Path) -> None:
    replace_in(
        library_copy / "books" / MIRRORED / "metadata.yaml",
        "mirror_status: mirrored",
        "mirror_status: eligible",
    )

    assert located(run_checks(library_copy)) == [
        ("gate-content", "books/fixture-mirrored-book/LICENSE", None),
        ("gate-content", "books/fixture-mirrored-book/chapters/01-folding-the-hull.md", None),
        ("gate-content", "books/fixture-mirrored-book/chapters/02-choosing-a-pond.md", None),
        (
            "gate-content",
            "books/fixture-mirrored-book/chapters/03-recovering-a-sunk-boat.md",
            None,
        ),
    ]


def test_a_mirrored_book_the_gate_refuses_is_a_finding_that_quotes_the_reason(
    library_copy: Path,
) -> None:
    replace_in(
        library_copy / "books" / MIRRORED / "metadata.yaml",
        "redistribution: allowed",
        "redistribution: unclear",
    )

    findings = run_checks(library_copy)

    assert located(findings) == [("gate-status", "books/fixture-mirrored-book/metadata.yaml", None)]
    assert (
        "The record says redistribution is unclear and adaptation is allowed. Both must be allowed."
    ) in findings[0].message


def test_a_mirrored_book_without_a_license_file_is_a_finding(library_copy: Path) -> None:
    (library_copy / "books" / MIRRORED / "LICENSE").unlink()

    assert located(run_checks(library_copy)) == [
        ("gate-license-file", "books/fixture-mirrored-book/LICENSE", None)
    ]


def test_a_cataloged_id_without_metadata_is_a_finding(library_copy: Path) -> None:
    replace_in(
        library_copy / "catalog.yaml",
        "  - fixture-reference-book\n",
        "  - fixture-reference-book\n  - ghost-book\n",
    )

    findings = run_checks(library_copy)

    assert located(findings) == [("catalog-missing-book", "catalog.yaml", None)]
    assert "ghost-book" in findings[0].message


def test_a_book_directory_the_catalog_does_not_list_is_a_finding(library_copy: Path) -> None:
    (library_copy / "books" / "stray-book").mkdir()

    assert located(run_checks(library_copy)) == [
        ("catalog-unlisted-book", "books/stray-book", None)
    ]


def test_a_collection_the_catalog_does_not_declare_is_a_finding(library_copy: Path) -> None:
    replace_in(
        library_copy / "books" / REFERENCE / "metadata.yaml",
        "collection: fixture-books",
        "collection: other-books",
    )

    findings = run_checks(library_copy)

    assert located(findings) == [
        ("catalog-unknown-collection", "books/fixture-reference-book/metadata.yaml", None)
    ]
    assert "other-books" in findings[0].message


def test_two_chapters_with_one_id_are_a_finding_that_names_both_files(library_copy: Path) -> None:
    write_chapter(
        library_copy,
        MIRRORED,
        "04-folding-the-hull.md",
        resource=MIRRORED,
        slug="folding-the-hull",
        order=4,
    )

    findings = run_checks(library_copy)

    assert located(findings) == [
        (
            "chapter-duplicate-id",
            "books/fixture-mirrored-book/chapters/01-folding-the-hull.md",
            None,
        )
    ]
    assert "fixture-mirrored-book/folding-the-hull" in findings[0].message
    assert "books/fixture-mirrored-book/chapters/04-folding-the-hull.md" in findings[0].message


def test_order_values_with_a_gap_are_a_finding(library_copy: Path) -> None:
    chapters = library_copy / "books" / MIRRORED / "chapters"
    replace_in(chapters / "03-recovering-a-sunk-boat.md", "order: 3", "order: 4")
    (chapters / "03-recovering-a-sunk-boat.md").rename(chapters / "04-recovering-a-sunk-boat.md")

    findings = run_checks(library_copy)

    assert located(findings) == [("chapter-order", "books/fixture-mirrored-book/chapters", None)]
    assert "1, 2, 4" in findings[0].message


def test_a_file_name_number_that_disagrees_with_the_order_is_a_finding(library_copy: Path) -> None:
    chapters = library_copy / "books" / MIRRORED / "chapters"
    (chapters / "02-choosing-a-pond.md").rename(chapters / "05-choosing-a-pond.md")

    findings = run_checks(library_copy)

    assert located(findings) == [
        ("chapter-filename", "books/fixture-mirrored-book/chapters/05-choosing-a-pond.md", None)
    ]
    assert "02-choosing-a-pond.md" in findings[0].message


def test_a_file_name_slug_that_disagrees_with_the_id_is_a_finding(library_copy: Path) -> None:
    chapters = library_copy / "books" / MIRRORED / "chapters"
    (chapters / "02-choosing-a-pond.md").rename(chapters / "02-choosing-a-lake.md")

    assert located(run_checks(library_copy)) == [
        ("chapter-filename", "books/fixture-mirrored-book/chapters/02-choosing-a-lake.md", None)
    ]


def test_a_chapter_filed_under_another_book_is_a_finding(library_copy: Path) -> None:
    write_chapter(
        library_copy, MIRRORED, "04-steeping.md", resource=REFERENCE, slug="steeping", order=4
    )

    findings = run_checks(library_copy)

    assert located(findings) == [
        ("chapter-resource", "books/fixture-mirrored-book/chapters/04-steeping.md", None)
    ]
    assert "fixture-reference-book" in findings[0].message


def test_a_link_to_a_missing_file_is_a_finding_with_its_line_number(library_copy: Path) -> None:
    (library_copy / "topics" / "tea-service.md").write_text(
        TOPIC_WITH_BROKEN_LINK, encoding="utf-8"
    )

    findings = run_checks(library_copy)

    assert located(findings) == [("link-missing-target", "topics/tea-service.md", 11)]
    assert "kettle-guide.md" in findings[0].message


def test_a_broken_link_in_a_chapter_is_a_finding(library_copy: Path) -> None:
    chapter = library_copy / "books" / MIRRORED / "chapters" / "01-folding-the-hull.md"
    replace_in(
        chapter,
        "# Folding the Hull\n",
        "# Folding the Hull\n\nSee [the next section](02-choosing-a-lake.md).\n",
    )

    # The frontmatter and its two fences take 18 lines. A blank line, the heading, and another
    # blank line come before the link.
    assert located(run_checks(library_copy)) == [
        (
            "link-missing-target",
            "books/fixture-mirrored-book/chapters/01-folding-the-hull.md",
            22,
        )
    ]


def test_links_that_resolve_or_leave_the_library_are_not_findings(library_copy: Path) -> None:
    with (library_copy / "topics" / "tea-service.md").open("a", encoding="utf-8") as topic:
        topic.write(
            "\n"
            "See [paper craft](paper-craft.md) and [its scope](paper-craft.md#paper-craft).\n"
            "Read [the hull section](../books/fixture-mirrored-book/chapters/"
            "01-folding-the-hull.md).\n"
            "Visit [the site](https://example.invalid/tea) or [the mirror](http://example.invalid).\n"
            "Write to [the editor](mailto:editor@example.invalid).\n"
            "Jump to [the top](#tea-service).\n"
        )

    assert run_checks(library_copy) == []


def test_links_inside_a_fenced_code_block_are_ignored(library_copy: Path) -> None:
    with (library_copy / "topics" / "tea-service.md").open("a", encoding="utf-8") as topic:
        topic.write(
            "\n"
            "```markdown\n"
            "A sample [link](not-a-real-file.md) that is only shown.\n"
            "```\n"
            "\n"
            "~~~\n"
            "Another [sample](also-missing.md).\n"
            "~~~\n"
        )

    assert run_checks(library_copy) == []


def test_malformed_yaml_is_a_finding(library_copy: Path) -> None:
    (library_copy / "books" / REFERENCE / "metadata.yaml").write_text(
        "id: [unclosed\n", encoding="utf-8"
    )

    findings = run_checks(library_copy)

    assert located(findings) == [
        ("invalid-file", "books/fixture-reference-book/metadata.yaml", None)
    ]
    assert "malformed" in findings[0].message


def test_a_schema_violation_is_a_finding_that_gives_the_json_path(library_copy: Path) -> None:
    replace_in(
        library_copy / "books" / REFERENCE / "metadata.yaml",
        "mirror_status: reference-only",
        "mirror_status: borrowed",
    )

    findings = run_checks(library_copy)

    assert located(findings) == [
        ("invalid-file", "books/fixture-reference-book/metadata.yaml", None)
    ]
    assert "$.mirror_status" in findings[0].message


def test_a_chapter_with_broken_frontmatter_is_a_finding(library_copy: Path) -> None:
    replace_in(
        library_copy / "books" / MIRRORED / "chapters" / "02-choosing-a-pond.md",
        "order: 2",
        "order: second",
    )

    findings = run_checks(library_copy)

    assert located(findings) == [
        ("invalid-file", "books/fixture-mirrored-book/chapters/02-choosing-a-pond.md", None)
    ]
    assert "$.order" in findings[0].message


def test_a_topic_with_broken_frontmatter_is_a_finding(library_copy: Path) -> None:
    replace_in(library_copy / "topics" / "paper-craft.md", "title: Paper Craft\n", "")

    assert located(run_checks(library_copy)) == [("invalid-file", "topics/paper-craft.md", None)]


def test_a_catalog_that_cannot_load_is_the_only_finding(library_copy: Path) -> None:
    (library_copy / "catalog.yaml").write_text("library: [\n", encoding="utf-8")
    (library_copy / "books" / REFERENCE / "notes.md").write_text("Stray text.\n", encoding="utf-8")

    assert located(run_checks(library_copy)) == [("invalid-file", "catalog.yaml", None)]


def test_one_broken_file_does_not_hide_findings_in_other_files(library_copy: Path) -> None:
    (library_copy / "books" / REFERENCE / "metadata.yaml").write_text(
        "id: [unclosed\n", encoding="utf-8"
    )
    (library_copy / "topics" / "tea-service.md").write_text(
        TOPIC_WITH_BROKEN_LINK, encoding="utf-8"
    )
    (library_copy / "books" / MIRRORED / "LICENSE").unlink()

    assert located(run_checks(library_copy)) == [
        ("gate-license-file", "books/fixture-mirrored-book/LICENSE", None),
        ("invalid-file", "books/fixture-reference-book/metadata.yaml", None),
        ("link-missing-target", "topics/tea-service.md", 11),
    ]


def test_findings_are_sorted_by_file_then_line_then_rule(library_copy: Path) -> None:
    (library_copy / "topics" / "tea-service.md").write_text(
        TOPIC_WITH_BROKEN_LINK + "\nSee also [the cup guide](cup-guide.md).\n", encoding="utf-8"
    )
    (library_copy / "topics" / "paper-craft.md").write_text(
        TOPIC_WITH_BROKEN_LINK.replace("tea-service", "paper-craft"), encoding="utf-8"
    )
    replace_in(
        library_copy / "books" / REFERENCE / "metadata.yaml",
        "collection: fixture-books",
        "collection: other-books",
    )
    replace_in(
        library_copy / "books" / REFERENCE / "metadata.yaml",
        "mirror_status: reference-only",
        "mirror_status: mirrored",
    )

    assert located(run_checks(library_copy)) == [
        ("gate-license-file", "books/fixture-reference-book/LICENSE", None),
        ("catalog-unknown-collection", "books/fixture-reference-book/metadata.yaml", None),
        ("gate-status", "books/fixture-reference-book/metadata.yaml", None),
        ("link-missing-target", "topics/paper-craft.md", 11),
        ("link-missing-target", "topics/tea-service.md", 11),
        ("link-missing-target", "topics/tea-service.md", 13),
    ]


def test_a_check_appended_to_the_registry_runs_with_the_built_in_checks(
    library_copy: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def always_reports(library: Library) -> list[Finding]:
        return [Finding(rule="added-rule", file="catalog.yaml", message="Added.", fix="None.")]

    monkeypatch.setattr("kb.checks.CHECKS", [*CHECKS, always_reports])

    assert located(run_checks(library_copy)) == [("added-rule", "catalog.yaml", None)]
