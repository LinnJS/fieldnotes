"""The validation checks report what is wrong with a library as findings."""

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest
from kb import checks
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
        (
            "gate-content",
            "books/fixture-mirrored-book/source/Paper-Boat-Engineering-v1.0.0.pdf",
            None,
        ),
        ("index-stale", "index/catalog.json", None),
        ("index-stale", "index/chapters.jsonl", None),
        ("index-stale", "index/topics.json", None),
        ("index-stale", "llms.txt", None),
        ("topic-reference-not-mirrored", "topics/paper-craft.md", None),
        ("topic-reference-not-mirrored", "topics/paper-craft.md", None),
        ("topic-uncited-paragraph", "topics/paper-craft.md", 19),
        ("topic-uncited-paragraph", "topics/paper-craft.md", 21),
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

    assert located(findings) == [
        ("gate-status", "books/fixture-mirrored-book/metadata.yaml", None),
        ("index-stale", "index/catalog.json", None),
        ("index-stale", "index/chapters.jsonl", None),
        ("index-stale", "index/topics.json", None),
        ("index-stale", "llms.txt", None),
        ("topic-reference-not-mirrored", "topics/paper-craft.md", None),
        ("topic-reference-not-mirrored", "topics/paper-craft.md", None),
        ("topic-uncited-paragraph", "topics/paper-craft.md", 19),
        ("topic-uncited-paragraph", "topics/paper-craft.md", 21),
    ]
    assert (
        "The record says redistribution is unclear and adaptation is allowed. Both must be allowed."
    ) in findings[0].message


def test_a_link_to_a_directory_under_a_reference_only_book_is_a_finding(
    library_copy: Path,
) -> None:
    elsewhere = library_copy / "books" / MIRRORED / "chapters"
    (library_copy / "books" / REFERENCE / "chapters").symlink_to(
        elsewhere, target_is_directory=True
    )

    findings = [finding for finding in run_checks(library_copy) if finding.rule == "gate-content"]

    assert located(findings) == [("gate-content", "books/fixture-reference-book/chapters", None)]


def test_a_file_a_mirrored_book_does_not_account_for_is_a_finding(library_copy: Path) -> None:
    book = library_copy / "books" / MIRRORED
    (book / "notes.txt").write_text("Loose text.\n", encoding="utf-8")
    (book / "source" / "Paper-Boat-Engineering-v0.9.0.pdf").write_bytes(b"%PDF-1.7\n")
    (book / "chapters" / "draft.txt").write_text("Loose text.\n", encoding="utf-8")
    (book / "chapters-zh").mkdir()
    (book / "chapters-zh" / "01-folding-the-hull.md").write_text("Loose text.\n", encoding="utf-8")
    (book / "LICENSE.md").symlink_to(book / "LICENSE")

    assert located(run_checks(library_copy)) == [
        ("book-unexpected-file", "books/fixture-mirrored-book/LICENSE.md", None),
        (
            "book-unexpected-file",
            "books/fixture-mirrored-book/chapters-zh/01-folding-the-hull.md",
            None,
        ),
        ("book-unexpected-file", "books/fixture-mirrored-book/chapters/draft.txt", None),
        ("book-unexpected-file", "books/fixture-mirrored-book/notes.txt", None),
        (
            "book-unexpected-file",
            "books/fixture-mirrored-book/source/Paper-Boat-Engineering-v0.9.0.pdf",
            None,
        ),
    ]


def test_a_mirrored_book_without_a_license_file_is_a_finding(library_copy: Path) -> None:
    (library_copy / "books" / MIRRORED / "LICENSE").unlink()

    assert located(run_checks(library_copy)) == [
        ("gate-license-file", "books/fixture-mirrored-book/LICENSE", None)
    ]


@pytest.mark.parametrize("content", ["", "Permission is hereby granted to no one.\n"])
def test_a_license_file_that_is_not_the_recorded_one_is_a_finding(
    library_copy: Path, content: str
) -> None:
    (library_copy / "books" / MIRRORED / "LICENSE").write_text(content, encoding="utf-8")

    findings = run_checks(library_copy)

    assert located(findings) == [("gate-license-file", "books/fixture-mirrored-book/LICENSE", None)]
    assert "2b83b85f5d96ee4d65a4a46d8f8614161569df54" in findings[0].message


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


@pytest.mark.parametrize("name", ["stolen-copy.pdf", ".hidden-copy.epub"])
def test_a_plain_file_directly_under_the_books_directory_is_a_finding(
    library_copy: Path, name: str
) -> None:
    (library_copy / "books" / name).write_bytes(b"%PDF-1.7 not the library's to hold")

    findings = run_checks(library_copy)

    assert located(findings) == [("catalog-stray-file", f"books/{name}", None)]
    assert findings[0].fix


def test_a_collection_the_catalog_does_not_declare_is_a_finding(library_copy: Path) -> None:
    replace_in(
        library_copy / "books" / REFERENCE / "metadata.yaml",
        "collection: fixture-books",
        "collection: other-books",
    )

    findings = run_checks(library_copy)

    assert located(findings) == [
        ("catalog-unknown-collection", "books/fixture-reference-book/metadata.yaml", None),
        ("index-stale", "index/catalog.json", None),
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

    # The second file holds invented text and invented frontmatter under the id of a real
    # section, so it also fails both comparisons with the source.
    assert located(findings) == [
        (
            "chapter-duplicate-id",
            "books/fixture-mirrored-book/chapters/01-folding-the-hull.md",
            None,
        ),
        ("fidelity-chapter", "books/fixture-mirrored-book/chapters/04-folding-the-hull.md", None),
        (
            "fidelity-frontmatter",
            "books/fixture-mirrored-book/chapters/04-folding-the-hull.md",
            None,
        ),
        ("index-stale", "index/catalog.json", None),
        ("index-stale", "index/chapters.jsonl", None),
        ("index-stale", "llms.txt", None),
    ]
    assert "fixture-mirrored-book/folding-the-hull" in findings[0].message
    assert "books/fixture-mirrored-book/chapters/04-folding-the-hull.md" in findings[0].message


def test_order_values_with_a_gap_are_a_finding(library_copy: Path) -> None:
    chapters = library_copy / "books" / MIRRORED / "chapters"
    replace_in(chapters / "03-recovering-a-sunk-boat.md", "order: 3", "order: 4")
    (chapters / "03-recovering-a-sunk-boat.md").rename(chapters / "04-recovering-a-sunk-boat.md")

    findings = run_checks(library_copy)

    # The fixture topic links the renamed chapter file under its old name, and the section is
    # still the third of the source.
    assert located(findings) == [
        ("chapter-order", "books/fixture-mirrored-book/chapters", None),
        (
            "fidelity-frontmatter",
            "books/fixture-mirrored-book/chapters/04-recovering-a-sunk-boat.md",
            None,
        ),
        ("index-stale", "index/chapters.jsonl", None),
        ("index-stale", "llms.txt", None),
        ("link-missing-target", "topics/paper-craft.md", 26),
    ]
    assert "1, 2, 4" in findings[0].message


def test_a_file_name_number_that_disagrees_with_the_order_is_a_finding(library_copy: Path) -> None:
    chapters = library_copy / "books" / MIRRORED / "chapters"
    (chapters / "02-choosing-a-pond.md").rename(chapters / "05-choosing-a-pond.md")

    findings = run_checks(library_copy)

    assert located(findings) == [
        ("chapter-filename", "books/fixture-mirrored-book/chapters/05-choosing-a-pond.md", None),
        ("index-stale", "index/chapters.jsonl", None),
        ("index-stale", "llms.txt", None),
    ]
    assert "02-choosing-a-pond.md" in findings[0].message


def test_a_file_name_slug_that_disagrees_with_the_id_is_a_finding(library_copy: Path) -> None:
    chapters = library_copy / "books" / MIRRORED / "chapters"
    (chapters / "02-choosing-a-pond.md").rename(chapters / "02-choosing-a-lake.md")

    assert located(run_checks(library_copy)) == [
        ("chapter-filename", "books/fixture-mirrored-book/chapters/02-choosing-a-lake.md", None),
        ("index-stale", "index/chapters.jsonl", None),
        ("index-stale", "llms.txt", None),
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

    # The topic written here also lacks the labeled scope statement.
    assert located(findings) == [
        ("index-stale", "index/topics.json", None),
        ("link-missing-target", "topics/tea-service.md", 11),
        ("topic-scope", "topics/tea-service.md", 11),
    ]
    assert "kettle-guide.md" in findings[1].message


def test_a_broken_link_in_a_chapter_is_a_finding(library_copy: Path) -> None:
    chapter = library_copy / "books" / MIRRORED / "chapters" / "01-folding-the-hull.md"
    replace_in(
        chapter,
        "# Folding the Hull\n",
        "# Folding the Hull\n\nSee [the next section](02-choosing-a-lake.md).\n",
    )

    # The frontmatter and its two fences take 18 lines. A blank line, the heading, and another
    # blank line come before the link. The added sentence is not in the source, so the chapter
    # also fails the comparison with it.
    assert located(run_checks(library_copy)) == [
        ("fidelity-chapter", "books/fixture-mirrored-book/chapters/01-folding-the-hull.md", None),
        (
            "link-missing-target",
            "books/fixture-mirrored-book/chapters/01-folding-the-hull.md",
            22,
        ),
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

    # No link is a finding. The added paragraph cites nothing, which is a finding of its own.
    assert located(run_checks(library_copy)) == [
        ("topic-uncited-paragraph", "topics/tea-service.md", 19)
    ]


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

    # No link is a finding. Each fenced block cites nothing, which is a finding of its own.
    assert located(run_checks(library_copy)) == [
        ("topic-uncited-paragraph", "topics/tea-service.md", 19),
        ("topic-uncited-paragraph", "topics/tea-service.md", 23),
    ]


def test_malformed_yaml_is_a_finding(library_copy: Path) -> None:
    (library_copy / "books" / REFERENCE / "metadata.yaml").write_text(
        "id: [unclosed\n", encoding="utf-8"
    )

    findings = run_checks(library_copy)

    assert located(findings) == [
        ("invalid-file", "books/fixture-reference-book/metadata.yaml", None),
        ("index-stale", "index/catalog.json", None),
        ("index-stale", "index/topics.json", None),
        ("index-stale", "llms.txt", None),
    ]
    assert "malformed" in findings[0].message


LICENSE_LINK = f"https://github.com/fixture-author/fixture-mirrored-book/blob/{'a' * 40}/LICENSE"


def evidence_findings(root: Path) -> list[Finding]:
    return [finding for finding in run_checks(root) if finding.rule == "gate-evidence"]


@pytest.mark.parametrize(
    "permalink",
    [
        f"https://github.com/someone-else/unrelated-fork/blob/{'a' * 40}/LICENSE",
        f"https://github.com/fixture-author/fixture-mirrored-book/blob/{'c' * 40}/LICENSE",
        f"https://example.invalid/fixture-author/fixture-mirrored-book/blob/{'a' * 40}/LICENSE",
        f"https://github.com/fixture-author/fixture-mirrored-book-2/blob/{'a' * 40}/LICENSE",
    ],
)
def test_a_license_permalink_that_is_not_the_recorded_repository_and_commit_is_a_finding(
    permalink: str, library_copy: Path
) -> None:
    replace_in(library_copy / "books" / MIRRORED / "metadata.yaml", LICENSE_LINK, permalink)

    findings = evidence_findings(library_copy)

    assert located(findings) == [
        ("gate-evidence", "books/fixture-mirrored-book/metadata.yaml", None)
    ]
    assert permalink in findings[0].message


def test_a_license_file_whose_permalink_names_a_readme_is_a_finding(library_copy: Path) -> None:
    replace_in(
        library_copy / "books" / MIRRORED / "metadata.yaml",
        LICENSE_LINK,
        LICENSE_LINK.removesuffix("LICENSE") + "README.md?plain=1#L29",
    )

    findings = evidence_findings(library_copy)

    assert located(findings) == [
        ("gate-evidence", "books/fixture-mirrored-book/metadata.yaml", None)
    ]
    assert "README" in findings[0].message


@pytest.mark.parametrize(
    "suffix",
    [
        f"../../../../someone-else/unrelated-fork/blob/{'a' * 40}/LICENSE",
        f"%2e%2e/%2e%2e/%2e%2e/%2e%2e/someone-else/unrelated-fork/blob/{'a' * 40}/LICENSE",
        "docs/./LICENSE",
        "docs//LICENSE",
        "docs%2FLICENSE",
        "LICENSE)<svg/onload=alert(1)>",
        'LICENSE"onmouseover="alert(1)',
        "LICENSE?raw=1",
        "LICENSE#L1)<script>alert(1)</script>",
        "",
    ],
)
def test_a_license_permalink_that_leaves_the_recorded_file_is_a_finding(
    suffix: str, library_copy: Path
) -> None:
    permalink = LICENSE_LINK.removesuffix("LICENSE") + suffix
    replace_in(library_copy / "books" / MIRRORED / "metadata.yaml", LICENSE_LINK, permalink)

    findings = evidence_findings(library_copy)

    assert located(findings) == [
        ("gate-evidence", "books/fixture-mirrored-book/metadata.yaml", None)
    ]
    assert permalink in findings[0].message


@pytest.mark.parametrize("file_name", ["LICENSE", "LICENSE.md", "LICENSE.txt", "COPYING"])
def test_a_license_permalink_to_a_root_license_file_of_the_recorded_repository_and_commit_passes(
    file_name: str, library_copy: Path
) -> None:
    permalink = LICENSE_LINK.removesuffix("LICENSE") + file_name
    replace_in(library_copy / "books" / MIRRORED / "metadata.yaml", LICENSE_LINK, permalink)

    assert evidence_findings(library_copy) == []


@pytest.mark.parametrize("path", ["docs/LICENSE.txt", "NOTICE", "docs/README.md"])
def test_license_file_evidence_that_is_not_a_root_license_file_is_a_finding_to_report(
    path: str, library_copy: Path
) -> None:
    permalink = LICENSE_LINK.removesuffix("LICENSE") + path
    replace_in(library_copy / "books" / MIRRORED / "metadata.yaml", LICENSE_LINK, permalink)

    findings = evidence_findings(library_copy)

    assert located(findings) == [
        ("gate-evidence", "books/fixture-mirrored-book/metadata.yaml", None)
    ]
    assert path in findings[0].message
    assert "stop" in findings[0].fix.lower()
    assert "owner" in findings[0].fix


def test_a_license_file_whose_permalink_names_an_encoded_readme_is_a_finding(
    library_copy: Path,
) -> None:
    replace_in(
        library_copy / "books" / MIRRORED / "metadata.yaml",
        LICENSE_LINK,
        LICENSE_LINK.removesuffix("LICENSE") + "%52EADME.md?plain=1#L29",
    )

    findings = evidence_findings(library_copy)

    assert located(findings) == [
        ("gate-evidence", "books/fixture-mirrored-book/metadata.yaml", None)
    ]
    assert "README" in findings[0].message


README_EVIDENCE = (
    "  evidence: readme-statement\n  statement: All rights reserved.\n"
    f"  permalink: https://github.com/someone/somewhere/blob/{'d' * 40}/README.md?plain=1#L3\n"
    f"  blob_sha: {'e' * 40}\n  commit: {'d' * 40}\n"
)
NO_EVIDENCE = (
    "  evidence: none\n  statement: null\n  permalink: null\n  blob_sha: null\n  commit: null\n"
)


def test_readme_statement_evidence_at_the_root_readme_passes(library_copy: Path) -> None:
    replace_in(library_copy / "books" / REFERENCE / "metadata.yaml", NO_EVIDENCE, README_EVIDENCE)

    assert evidence_findings(library_copy) == []


@pytest.mark.parametrize("path", ["docs/README.md", "LICENSE"])
def test_readme_statement_evidence_that_is_not_the_root_readme_is_a_finding(
    path: str, library_copy: Path
) -> None:
    metadata = library_copy / "books" / REFERENCE / "metadata.yaml"
    replace_in(metadata, NO_EVIDENCE, README_EVIDENCE.replace("README.md?plain=1#L3", path))

    findings = evidence_findings(library_copy)

    assert located(findings) == [
        ("gate-evidence", "books/fixture-reference-book/metadata.yaml", None)
    ]
    assert "stop" in findings[0].fix.lower()


GIT_UPSTREAM = (
    "upstream:\n  kind: git\n  repository: fixture-author/fixture-mirrored-book\n"
    "  default_branch: main\n  head_commit: bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb\n"
)
URL_UPSTREAM = "upstream:\n  kind: url\n  url: https://example.invalid/books/paper-boat\n"


def test_license_evidence_of_a_record_with_a_web_page_upstream_is_tied_to_the_pinned_source(
    library_copy: Path,
) -> None:
    metadata = library_copy / "books" / MIRRORED / "metadata.yaml"
    replace_in(metadata, GIT_UPSTREAM, URL_UPSTREAM)

    assert evidence_findings(library_copy) == []

    elsewhere = f"https://github.com/third-party/another-repo/blob/{'a' * 40}/LICENSE"
    replace_in(metadata, LICENSE_LINK, elsewhere)

    findings = evidence_findings(library_copy)

    assert located(findings) == [
        ("gate-evidence", "books/fixture-mirrored-book/metadata.yaml", None)
    ]
    assert elsewhere in findings[0].message
    assert "pinned_source.repository" in findings[0].message


def test_license_evidence_with_no_repository_on_record_is_still_read_as_a_link(
    library_copy: Path,
) -> None:
    metadata = library_copy / "books" / REFERENCE / "metadata.yaml"
    replace_in(
        metadata,
        "  evidence: none\n  statement: null\n  permalink: null\n  blob_sha: null\n"
        "  commit: null\n",
        "  evidence: readme-statement\n  statement: All rights reserved.\n"
        f"  permalink: https://github.com/someone/somewhere/blob/{'d' * 40}/README.md?plain=1#L3\n"
        f"  blob_sha: {'e' * 40}\n  commit: {'d' * 40}\n",
    )

    assert evidence_findings(library_copy) == []

    replace_in(metadata, f"blob/{'d' * 40}/", f"blob/{'f' * 40}/")

    findings = evidence_findings(library_copy)

    assert located(findings) == [
        ("gate-evidence", "books/fixture-reference-book/metadata.yaml", None)
    ]
    assert "license.commit" in findings[0].message


def test_a_pinned_source_in_another_repository_than_upstream_is_a_finding(
    library_copy: Path,
) -> None:
    replace_in(
        library_copy / "books" / MIRRORED / "metadata.yaml",
        "pinned_source:\n  repository: fixture-author/fixture-mirrored-book\n",
        "pinned_source:\n  repository: someone-else/unrelated-fork\n",
    )

    findings = evidence_findings(library_copy)

    assert located(findings) == [
        ("gate-evidence", "books/fixture-mirrored-book/metadata.yaml", None)
    ]
    assert "someone-else/unrelated-fork" in findings[0].message


def test_a_repeated_key_in_a_record_is_a_finding_and_does_not_pass_the_gate(
    library_copy: Path,
) -> None:
    # PyYAML keeps the last of two equal keys, so the second line would hide the first.
    replace_in(
        library_copy / "books" / MIRRORED / "metadata.yaml",
        "  third_party_rights: false\n",
        "  third_party_rights: true\n  third_party_rights: false\n",
    )

    findings = [finding for finding in run_checks(library_copy) if finding.rule == "invalid-file"]

    assert located(findings) == [
        ("invalid-file", "books/fixture-mirrored-book/metadata.yaml", None)
    ]
    assert "third_party_rights" in findings[0].message
    assert "a second time" in findings[0].message


def test_a_merge_key_in_a_record_is_a_finding_and_does_not_pass_the_gate(
    library_copy: Path,
) -> None:
    # A merge key gives a key a second value that the explicit line below it overrides.
    replace_in(
        library_copy / "books" / MIRRORED / "metadata.yaml",
        "  third_party_rights: false\n",
        "  <<: {third_party_rights: true}\n  third_party_rights: false\n",
    )

    findings = [finding for finding in run_checks(library_copy) if finding.rule == "invalid-file"]

    assert located(findings) == [
        ("invalid-file", "books/fixture-mirrored-book/metadata.yaml", None)
    ]
    assert "merge key" in findings[0].message


def test_a_repeated_key_in_chapter_frontmatter_is_a_finding(library_copy: Path) -> None:
    replace_in(
        library_copy / "books" / MIRRORED / "chapters" / "02-choosing-a-pond.md",
        "extraction_status: machine-extracted\n",
        "extraction_status: machine-extracted\nextraction_status: human-reviewed\n",
    )

    findings = [finding for finding in run_checks(library_copy) if finding.rule == "invalid-file"]

    assert located(findings) == [
        ("invalid-file", "books/fixture-mirrored-book/chapters/02-choosing-a-pond.md", None)
    ]
    assert "extraction_status" in findings[0].message


def test_a_repeated_key_in_the_catalog_is_a_finding(library_copy: Path) -> None:
    replace_in(
        library_copy / "catalog.yaml",
        "license_allowlist:",
        "license_allowlist: [CC-BY-NC-SA-4.0]\nlicense_allowlist:",
    )

    findings = run_checks(library_copy)

    assert located(findings) == [("invalid-file", "catalog.yaml", None)]
    assert "license_allowlist" in findings[0].message


def test_a_schema_violation_is_a_finding_that_gives_the_json_path(library_copy: Path) -> None:
    replace_in(
        library_copy / "books" / REFERENCE / "metadata.yaml",
        "mirror_status: reference-only",
        "mirror_status: borrowed",
    )

    findings = run_checks(library_copy)

    assert located(findings) == [
        ("invalid-file", "books/fixture-reference-book/metadata.yaml", None),
        ("index-stale", "index/catalog.json", None),
        ("index-stale", "index/topics.json", None),
        ("index-stale", "llms.txt", None),
    ]
    assert "$.mirror_status" in findings[0].message


REORDER = (
    "    - chapter: fixture-mirrored-book/choosing-a-pond\n"
    "      page: 4\n"
    "      passage: A basin. A tub.\n"
    "      extraction: A tub. A basin.\n"
    "      reason: Page 4 prints the two lines in this order.\n"
)


@pytest.mark.parametrize(
    ("reorders", "path"),
    [
        ("", "$.extraction_profile: 'accepted_reorders' is a required property"),
        (REORDER.replace("      page: 4\n", ""), "$.extraction_profile.accepted_reorders[0]"),
        (REORDER.replace("page: 4", "page: 0"), "$.extraction_profile.accepted_reorders[0].page"),
        (
            REORDER.replace("passage: A basin. A tub.", "passage: ''"),
            "$.extraction_profile.accepted_reorders[0].passage",
        ),
        (REORDER + "      note: extra\n", "$.extraction_profile.accepted_reorders[0]"),
    ],
    ids=["no-key", "no-page", "page-zero", "empty-passage", "unknown-key"],
)
def test_an_accepted_reorder_that_breaks_the_schema_is_a_finding_that_gives_the_json_path(
    library_copy: Path, reorders: str, path: str
) -> None:
    replace_in(
        library_copy / "books" / MIRRORED / "metadata.yaml",
        "  accepted_reorders: []\n",
        f"  accepted_reorders:\n{reorders}" if reorders else "",
    )

    findings = [finding for finding in run_checks(library_copy) if finding.rule == "invalid-file"]

    assert located(findings) == [("invalid-file", f"books/{MIRRORED}/metadata.yaml", None)]
    assert path in findings[0].message


def test_angle_brackets_and_backticks_in_an_accepted_reorder_are_not_findings(
    library_copy: Path,
) -> None:
    replace_in(
        library_copy / "books" / MIRRORED / "metadata.yaml",
        "  accepted_reorders: []\n",
        "  accepted_reorders:\n"
        + REORDER.replace("A basin. A tub.", "'<A basin.> `A tub.`'").replace(
            "A tub. A basin.", "'`A tub.` <A basin.>'"
        ),
    )

    assert markup_findings(library_copy) == []


def test_a_chapter_with_broken_frontmatter_is_a_finding(library_copy: Path) -> None:
    replace_in(
        library_copy / "books" / MIRRORED / "chapters" / "02-choosing-a-pond.md",
        "order: 2",
        "order: second",
    )

    findings = run_checks(library_copy)

    assert located(findings) == [
        ("invalid-file", "books/fixture-mirrored-book/chapters/02-choosing-a-pond.md", None),
        ("index-stale", "index/catalog.json", None),
        ("index-stale", "index/chapters.jsonl", None),
        ("index-stale", "llms.txt", None),
    ]
    assert "$.order" in findings[0].message


def test_a_topic_with_broken_frontmatter_is_a_finding(library_copy: Path) -> None:
    replace_in(library_copy / "topics" / "paper-craft.md", "title: Paper Craft\n", "")

    assert located(run_checks(library_copy)) == [
        ("index-stale", "index/catalog.json", None),
        ("index-stale", "index/chapters.jsonl", None),
        ("index-stale", "index/topics.json", None),
        ("index-stale", "llms.txt", None),
        ("invalid-file", "topics/paper-craft.md", None),
    ]


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
        ("index-stale", "index/catalog.json", None),
        ("index-stale", "index/topics.json", None),
        ("index-stale", "llms.txt", None),
        ("link-missing-target", "topics/tea-service.md", 11),
        ("topic-scope", "topics/tea-service.md", 11),
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
        ("fidelity-source", "books/fixture-reference-book/metadata.yaml", None),
        ("gate-status", "books/fixture-reference-book/metadata.yaml", None),
        ("index-stale", "index/catalog.json", None),
        ("index-stale", "index/chapters.jsonl", None),
        ("index-stale", "index/topics.json", None),
        ("index-stale", "llms.txt", None),
        ("link-missing-target", "topics/paper-craft.md", 11),
        ("topic-scope", "topics/paper-craft.md", 11),
        ("link-missing-target", "topics/tea-service.md", 11),
        ("topic-scope", "topics/tea-service.md", 11),
        ("link-missing-target", "topics/tea-service.md", 13),
        ("topic-uncited-paragraph", "topics/tea-service.md", 13),
    ]


def test_a_check_appended_to_the_registry_runs_with_the_built_in_checks(
    library_copy: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def always_reports(library: Library) -> list[Finding]:
        return [Finding(rule="added-rule", file="catalog.yaml", message="Added.", fix="None.")]

    monkeypatch.setattr("kb.checks.CHECKS", [*CHECKS, always_reports])

    assert located(run_checks(library_copy)) == [("added-rule", "catalog.yaml", None)]


def test_a_line_that_opens_with_inline_code_in_three_backticks_hides_no_topic_text(
    library_copy: Path,
) -> None:
    # The fixture topic has 17 lines. The added lines are 19 and 21, and line 19 is inline
    # code followed by text, which is a paragraph and opens no fenced block.
    with (library_copy / "topics" / "tea-service.md").open("a", encoding="utf-8") as topic:
        topic.write(
            "\n"
            "```steep``` is the word the kettle guide uses.\n"
            "\n"
            "See [the kettle guide](kettle-guide.md) for more.\n"
        )

    assert located(run_checks(library_copy)) == [
        ("topic-uncited-paragraph", "topics/tea-service.md", 19),
        ("link-missing-target", "topics/tea-service.md", 21),
        ("topic-uncited-paragraph", "topics/tea-service.md", 21),
    ]


SCRIPT_TITLE = "x</title><script>alert(1)</script>"
CHAPTER_ONE = f"books/{MIRRORED}/chapters/01-folding-the-hull.md"


def markup_findings(root: Path) -> list[Finding]:
    return [finding for finding in run_checks(root) if finding.rule == "record-markup"]


def says_stop_and_report(fix: str) -> bool:
    return "stop" in fix and "report" in fix and "owner" in fix


@pytest.mark.parametrize(
    "title",
    [
        SCRIPT_TITLE,
        "&lt;script&gt;alert(1)&lt;/script&gt;",
        "x&lt/title&gt&ltscript&gtalert(1)&lt/script&gt",
    ],
)
def test_a_chapter_title_that_holds_markup_is_a_finding_that_says_to_stop_and_report(
    title: str, library_copy: Path
) -> None:
    replace_in(
        library_copy / CHAPTER_ONE, "title: Folding the Hull\n", f"title: {json.dumps(title)}\n"
    )

    findings = markup_findings(library_copy)

    assert located(findings) == [("record-markup", CHAPTER_ONE, None)]
    assert "title" in findings[0].message
    assert says_stop_and_report(findings[0].fix)


@pytest.mark.parametrize(
    ("file", "old"),
    [
        (f"books/{MIRRORED}/metadata.yaml", "english: Paper Boat Engineering (Test Fixture)"),
        ("topics/tea-service.md", "title: Tea Service"),
    ],
)
def test_a_book_title_or_a_topic_title_that_holds_markup_is_a_finding(
    file: str, old: str, library_copy: Path
) -> None:
    key = old.partition(":")[0]
    replace_in(library_copy / file, old, f"{key}: {json.dumps(SCRIPT_TITLE)}")

    findings = markup_findings(library_copy)

    assert located(findings) == [("record-markup", file, None)]
    assert "title" in findings[0].message


def test_a_quotation_mark_is_refused_in_the_library_description_and_allowed_in_a_title(
    library_copy: Path,
) -> None:
    replace_in(library_copy / "catalog.yaml", "A synthetic library", 'A "synthetic" library')
    replace_in(
        library_copy / CHAPTER_ONE, "title: Folding the Hull\n", "title: 'Folding the \"Hull\"'\n"
    )

    findings = markup_findings(library_copy)

    assert located(findings) == [("record-markup", "catalog.yaml", None)]
    assert "library.description" in findings[0].message
    assert "quotation mark" in findings[0].message


def test_a_chapter_source_path_that_holds_an_element_is_a_finding(library_copy: Path) -> None:
    replace_in(
        library_copy / CHAPTER_ONE,
        "  path: Paper-Boat-Engineering-v1.0.0.pdf\n",
        '  path: "a/b.<img src=x onerror=alert(1)>"\n',
    )

    findings = markup_findings(library_copy)

    assert located(findings) == [("record-markup", CHAPTER_ONE, None)]
    assert "source.path" in findings[0].message


@pytest.mark.parametrize("ending", [">", '"', "\\"])
def test_a_person_url_that_holds_markup_characters_is_a_finding(
    ending: str, library_copy: Path
) -> None:
    replace_in(
        library_copy / "books" / MIRRORED / "metadata.yaml",
        "  url: https://example.invalid/fixture-author\n",
        f"  url: 'https://example.invalid/fixture-author{ending}'\n",
    )

    findings = markup_findings(library_copy)

    assert located(findings) == [("record-markup", f"books/{MIRRORED}/metadata.yaml", None)]
    assert "author.url" in findings[0].message


def test_a_control_character_in_a_notice_is_a_finding(library_copy: Path) -> None:
    replace_in(
        library_copy / "books" / MIRRORED / "metadata.yaml",
        "  - Test fixture. This book and its text are invented for automated tests.\n",
        '  - "Test fixture.\\x1b[2J This book is invented."\n',
    )

    findings = markup_findings(library_copy)

    assert located(findings) == [("record-markup", f"books/{MIRRORED}/metadata.yaml", None)]
    assert "notices[0]" in findings[0].message


def test_plain_punctuation_a_markdown_link_and_chinese_text_in_a_notice_are_not_findings(
    library_copy: Path,
) -> None:
    replace_in(
        library_copy / "books" / MIRRORED / "metadata.yaml",
        "  - Test fixture. This book and its text are invented for automated tests.\n",
        "  - The author's note says paper & glue hold.\n"
        "  - See [the reader](https://example.invalid/reader) for more.\n"
        "  - 本作品采用纸船许可证。\n",
    )

    assert markup_findings(library_copy) == []


def test_markup_in_the_quoted_license_statement_is_not_a_finding(library_copy: Path) -> None:
    replace_in(
        library_copy / "books" / MIRRORED / "metadata.yaml",
        "    Permission is hereby granted",
        "    <Permission> is hereby granted",
    )

    assert markup_findings(library_copy) == []


def test_a_string_under_a_key_no_schema_knows_is_held_to_the_text_rule(
    library_copy: Path,
) -> None:
    replace_in(
        library_copy / "books" / MIRRORED / "metadata.yaml",
        "site_slug: paper-boat\n",
        "site_slug: paper-boat\nsubtitle: '<b>Bold</b>'\n",
    )

    findings = markup_findings(library_copy)

    assert located(findings) == [("record-markup", f"books/{MIRRORED}/metadata.yaml", None)]
    assert "subtitle" in findings[0].message


MIRRORED_RECORD = f"books/{MIRRORED}/metadata.yaml"
FIXTURE_NOTICE = "  - Test fixture. This book and its text are invented for automated tests.\n"


def set_notice(root: Path, notice: str) -> None:
    """Replace the one notice of the mirrored fixture book with a notice."""
    replace_in(root / MIRRORED_RECORD, FIXTURE_NOTICE, f"  - {json.dumps(notice)}\n")


@pytest.mark.parametrize(
    ("notice", "mark"),
    [
        ("1. Launch from the lee bank.", "a list number"),
        ("/ Reprint: the second printing moves the pond table.", "a term mark"),
    ],
    ids=["a nested list on the site and in the EPUB", "a term list in the PDF"],
)
def test_a_notice_that_starts_with_a_line_start_mark_is_a_finding_that_says_to_stop_and_report(
    notice: str, mark: str, library_copy: Path
) -> None:
    set_notice(library_copy, notice)

    findings = markup_findings(library_copy)

    assert located(findings) == [("record-markup", MIRRORED_RECORD, None)]
    assert "notices[0]" in findings[0].message
    assert f"starts with {mark}" in findings[0].message
    assert says_stop_and_report(findings[0].fix)


@pytest.mark.parametrize(
    ("notice", "mark"),
    [
        ("- Keep it dry.", "a list mark"),
        ("+ Keep it dry.", "a list mark"),
        ("* Keep it dry.", "a list mark"),
        ("-", "a list mark"),
        ("2) Fold the sheet.", "a list number"),
        ("# Folding", "a heading mark"),
        ("= Folding", "a heading mark"),
        ("===", "a heading mark"),
        ("---", "a rule mark"),
        ("* * *", "a rule mark"),
        ("___", "a rule mark"),
        ("~~~ text", "a fence mark"),
        ("| a | b |", "a table mark"),
        ("  - Keep it dry.", "a list mark"),
        ("\n\n1. Launch.", "a list number"),
    ],
)
def test_each_line_start_mark_at_the_start_of_a_notice_is_a_finding(
    notice: str, mark: str, library_copy: Path
) -> None:
    set_notice(library_copy, notice)

    findings = markup_findings(library_copy)

    assert located(findings) == [("record-markup", MIRRORED_RECORD, None)]
    assert f"starts with {mark}" in findings[0].message


@pytest.mark.parametrize(
    "notice",
    [
        "-5 degrees is too cold for the glue.",
        "1.5 times the size of the sheet.",
        "/usr/bin is the path.",
        "#12 in the series.",
        "2024 edition.",
        "The hull - not the sail - takes the water.",
        "The steps are 1. fold and 2. launch.",
        "__init__ is not a rule.",
    ],
)
def test_a_notice_that_only_looks_like_a_line_start_mark_is_not_a_finding(
    notice: str, library_copy: Path
) -> None:
    set_notice(library_copy, notice)

    assert markup_findings(library_copy) == []


def test_a_mark_on_a_later_line_of_a_notice_is_not_a_finding(library_copy: Path) -> None:
    replace_in(
        library_copy / MIRRORED_RECORD,
        FIXTURE_NOTICE,
        "  - |-\n    The pond table moved.\n    - It now follows the hull table.\n",
    )

    assert markup_findings(library_copy) == []


def test_a_chapter_title_that_starts_with_a_list_number_is_a_finding(library_copy: Path) -> None:
    replace_in(
        library_copy / CHAPTER_ONE, "title: Folding the Hull\n", "title: 1. Folding the Hull\n"
    )

    findings = markup_findings(library_copy)

    assert located(findings) == [("record-markup", CHAPTER_ONE, None)]
    assert "title" in findings[0].message


def test_a_book_title_that_starts_with_a_list_mark_is_a_finding(library_copy: Path) -> None:
    replace_in(
        library_copy / MIRRORED_RECORD,
        "english: Paper Boat Engineering (Test Fixture)",
        'english: "- Paper Boat Engineering (Test Fixture)"',
    )

    findings = markup_findings(library_copy)

    assert located(findings) == [("record-markup", MIRRORED_RECORD, None)]
    assert "title.english starts with a list mark" in findings[0].message


def test_a_library_description_that_starts_with_a_list_mark_is_a_finding(
    library_copy: Path,
) -> None:
    replace_in(library_copy / "catalog.yaml", "A synthetic library", "- A synthetic library")

    findings = markup_findings(library_copy)

    assert located(findings) == [("record-markup", "catalog.yaml", None)]
    assert "library.description" in findings[0].message
    assert "starts with a list mark" in findings[0].message


def test_a_line_start_mark_in_a_field_that_no_page_shows_is_not_a_finding(
    library_copy: Path,
) -> None:
    replace_in(library_copy / MIRRORED_RECORD, "    - README.md\n", '    - "- README.md"\n')

    assert markup_findings(library_copy) == []


def schema_nodes(schema: dict[str, Any], node: dict[str, Any]) -> list[dict[str, Any]]:
    """Return a schema node with every node it refers to or applies conditionally."""
    nodes = [node]
    reference = node.get("$ref")
    if isinstance(reference, str):
        nodes += schema_nodes(schema, schema["$defs"][reference.rpartition("/")[2]])
    for branch in node.get("allOf", []):
        nodes += schema_nodes(schema, branch.get("then", {}))
    return nodes


def schema_defines(schema: dict[str, Any], field: str) -> bool:
    nodes = [schema]
    for part in field.split("."):
        name = part.replace("[]", "")
        nodes = [
            expanded["properties"][name]
            for node in nodes
            for expanded in schema_nodes(schema, node)
            if name in expanded.get("properties", {})
        ]
        for _ in range(part.count("[]")):
            nodes = [
                expanded["items"]
                for node in nodes
                for expanded in schema_nodes(schema, node)
                if "items" in expanded
            ]
    return bool(nodes)


@pytest.mark.parametrize(
    "table", ["RECORD_URL_FIELDS", "RECORD_ATTRIBUTE_FIELDS", "RECORD_UNRENDERED_FIELDS"]
)
def test_every_field_with_its_own_markup_rule_is_one_a_schema_defines(
    table: str, repo_root: Path
) -> None:
    fields_by_schema: Mapping[str, frozenset[str]] = getattr(checks, table)
    for schema_name, fields in fields_by_schema.items():
        schema = json.loads(
            (repo_root / "schemas" / f"{schema_name}.schema.json").read_text(encoding="utf-8")
        )
        undefined = [field for field in sorted(fields) if not schema_defines(schema, field)]
        assert undefined == [], f"{schema_name}: {undefined}"
