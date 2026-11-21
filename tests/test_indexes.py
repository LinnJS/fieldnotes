"""The build command writes the committed indexes, llms.txt, and the llms-full files."""

import json
from pathlib import Path
from typing import Any

import pytest
from kb.checks import run_checks

# Ruff sorts this import as first-party when an ignored build/ directory exists and as
# third-party when it does not, so it is kept out of the sorting.
import build  # isort: skip

MIRRORED = "fixture-mirrored-book"
REFERENCE = "fixture-reference-book"
COMMITTED = ("index/catalog.json", "index/topics.json", "index/chapters.jsonl", "llms.txt")
FIX = (
    "Run `uv run python scripts/build.py` and commit the result. Add --root DIRECTORY for a "
    "library that is not the repository root."
)

# A chapter that sits where the license gate forbids one. Its text must reach no output.
PLANTED_CHAPTER = """\
---
id: fixture-reference-book/steeping
resource: fixture-reference-book
title: Steeping
part: "Part One: Leaves"
order: 1
section_label: "§01"
language: zh
edition: v1.0.0
source:
  repository: fixture-author/fixture-reference-book
  revision: aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
  path: Clockwork-Tea-v1.0.0.pdf
  pages:
    first: 1
    last: 2
extraction_status: machine-extracted
---

# Steeping

Wind the kettle key nine turns before the leaves go in.
"""


def run(root: Path, *flags: str) -> int:
    return build.main(["--root", str(root), *flags])


def committed_bytes(root: Path) -> dict[str, bytes]:
    return {name: (root / name).read_bytes() for name in COMMITTED}


def remove_committed(root: Path) -> None:
    for name in COMMITTED:
        (root / name).unlink()


def replace_in(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    assert old in text, f"{old!r} is not in {path}"
    path.write_text(text.replace(old, new), encoding="utf-8")


def catalog_resources(root: Path) -> dict[str, dict[str, Any]]:
    catalog = json.loads((root / "index" / "catalog.json").read_text(encoding="utf-8"))
    return {record["id"]: record for record in catalog["resources"]}


def chapter_lines(root: Path) -> list[dict[str, Any]]:
    text = (root / "index" / "chapters.jsonl").read_text(encoding="utf-8")
    return [json.loads(line) for line in text.splitlines()]


def test_building_twice_gives_byte_identical_output(
    library_copy: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    remove_committed(library_copy)

    assert run(library_copy) == 0
    first = committed_bytes(library_copy)
    assert run(library_copy) == 0
    capsys.readouterr()

    assert committed_bytes(library_copy) == first
    for name, content in first.items():
        assert content.endswith(b"\n"), name
        assert str(library_copy).encode() not in content, name


def test_the_full_text_build_gives_byte_identical_output_twice(
    library_copy: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    files = ("dist/llms-full.txt", f"dist/llms-full/{MIRRORED}.txt")

    assert run(library_copy, "--full") == 0
    first = [(library_copy / name).read_bytes() for name in files]
    assert run(library_copy, "--full") == 0
    capsys.readouterr()

    assert [(library_copy / name).read_bytes() for name in files] == first
    for content in first:
        assert str(library_copy).encode() not in content


def test_the_committed_fixture_indexes_are_what_the_build_writes(
    fixture_library_root: Path, library_copy: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    remove_committed(library_copy)

    assert run(library_copy) == 0
    capsys.readouterr()

    assert committed_bytes(library_copy) == committed_bytes(fixture_library_root)


def test_check_passes_on_fresh_output_and_fails_after_a_chapter_title_changes(
    library_copy: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert run(library_copy, "--check") == 0
    capsys.readouterr()
    before = committed_bytes(library_copy)
    replace_in(
        library_copy / "books" / MIRRORED / "chapters" / "01-folding-the-hull.md",
        "title: Folding the Hull",
        "title: Creasing the Hull",
    )

    code = run(library_copy, "--check")

    output = capsys.readouterr()
    assert code == 1
    # The chapter title is recorded in the chapter index and listed in llms.txt, and nowhere else.
    assert output.out.splitlines() == ["stale: index/chapters.jsonl", "stale: llms.txt"]
    assert "uv run python scripts/build.py" in output.err
    assert committed_bytes(library_copy) == before


def test_check_names_a_generated_file_that_is_missing(
    library_copy: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (library_copy / "index" / "topics.json").unlink()

    code = run(library_copy, "--check")

    assert code == 1
    assert capsys.readouterr().out.splitlines() == ["missing: index/topics.json"]


def test_a_reference_only_book_is_cataloged_as_not_quotable_and_has_no_chapter_line(
    library_copy: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    remove_committed(library_copy)

    assert run(library_copy) == 0
    capsys.readouterr()

    resources = catalog_resources(library_copy)
    assert list(resources) == [MIRRORED, REFERENCE]
    reference = resources[REFERENCE]
    assert reference["mirror_status"] == "reference-only"
    assert reference["license_id"] is None
    assert reference["quote_permitted"] is False
    assert reference["chapters"] == []
    assert reference["path"] is None
    assert reference["official_urls"]["site"] == "https://example.invalid/books/clockwork-tea"
    assert reference["topics"] == ["paper-craft", "tea-service"]
    assert {line["resource"] for line in chapter_lines(library_copy)} == {MIRRORED}


def test_a_mirrored_book_is_cataloged_with_its_edition_license_and_chapters(
    library_copy: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    remove_committed(library_copy)

    assert run(library_copy) == 0
    capsys.readouterr()

    mirrored = catalog_resources(library_copy)[MIRRORED]
    assert mirrored["title"] == {
        "original": "纸船工程测试夹具",
        "english": "Paper Boat Engineering (Test Fixture)",
        "english_official": True,
    }
    assert mirrored["author"]["name"] == "Fixture Author"
    assert mirrored["mirror_status"] == "mirrored"
    assert mirrored["license_id"] == "MIT"
    assert mirrored["quote_permitted"] is True
    assert mirrored["edition"] == "v1.0.0"
    assert mirrored["edition_language"] == "en"
    assert mirrored["edition_behind"] is True
    assert mirrored["newer_editions"] == [{"language": "zh", "version": "v1.1.0"}]
    assert mirrored["path"] == "books/fixture-mirrored-book"
    assert mirrored["license_path"] == "books/fixture-mirrored-book/LICENSE"
    assert mirrored["source"] == {
        "repository": "fixture-author/fixture-mirrored-book",
        "revision": "a" * 40,
        "path": "Paper-Boat-Engineering-v1.0.0.pdf",
    }
    assert mirrored["chapters"] == [
        "fixture-mirrored-book/folding-the-hull",
        "fixture-mirrored-book/choosing-a-pond",
        "fixture-mirrored-book/recovering-a-sunk-boat",
    ]
    assert mirrored["topics"] == ["paper-craft"]


def test_a_chapter_line_carries_every_field_an_agent_needs(
    library_copy: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    remove_committed(library_copy)

    assert run(library_copy) == 0
    capsys.readouterr()

    lines = chapter_lines(library_copy)
    assert [line["order"] for line in lines] == [1, 2, 3]
    assert lines[1] == {
        "id": "fixture-mirrored-book/choosing-a-pond",
        "path": "books/fixture-mirrored-book/chapters/02-choosing-a-pond.md",
        "title": "Choosing a Pond",
        "part": "Part One: Paper",
        "order": 2,
        "section_label": "§02",
        "resource": "fixture-mirrored-book",
        "language": "en",
        "edition": "v1.0.0",
        "edition_behind": True,
        "newer_editions": [{"language": "zh", "version": "v1.1.0"}],
        "license_id": "MIT",
        "mirror_status": "mirrored",
        "quote_permitted": True,
        "source": {
            "repository": "fixture-author/fixture-mirrored-book",
            "revision": "a" * 40,
            "path": "Paper-Boat-Engineering-v1.0.0.pdf",
            "pages": {"first": 4, "last": 5},
        },
        "extraction_status": "machine-extracted",
        "errata": [
            {
                "description": (
                    "The invented second edition says the pond table lists depth in hands and "
                    "not in spans."
                ),
                "source_url": "https://example.invalid/fixture-author/fixture-mirrored-book/errata",
            }
        ],
        "topics": [],
    }
    assert lines[0]["topics"] == ["paper-craft"]
    assert lines[2]["extraction_status"] == "human-reviewed"


def test_index_text_is_sorted_by_key_and_keeps_non_ascii_characters_readable(
    fixture_library_root: Path,
) -> None:
    first_line = (
        (fixture_library_root / "index" / "chapters.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()[0]
    )
    catalog = (fixture_library_root / "index" / "catalog.json").read_text(encoding="utf-8")

    assert list(json.loads(first_line)) == sorted(json.loads(first_line))
    assert '"section_label": "§01"' in first_line
    assert "纸船工程测试夹具" in catalog


def test_every_path_in_the_chapter_index_exists(fixture_library_root: Path) -> None:
    lines = chapter_lines(fixture_library_root)

    assert len(lines) == 3
    for line in lines:
        assert (fixture_library_root / line["path"]).is_file(), line["path"]


def test_an_edition_is_behind_when_another_language_has_a_higher_version_number(
    library_copy: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # Version 10 is newer than version 9, although "v10" sorts before "v9" as text.
    book = library_copy / "books" / MIRRORED
    for path in [book / "metadata.yaml", *sorted((book / "chapters").glob("*.md"))]:
        text = path.read_text(encoding="utf-8")
        text = text.replace("v1.1.0", "v10.0.0").replace("v1.0.0", "v9.0.0")
        path.write_text(text, encoding="utf-8")

    assert run(library_copy) == 0
    capsys.readouterr()

    mirrored = catalog_resources(library_copy)[MIRRORED]
    assert mirrored["edition"] == "v9.0.0"
    assert mirrored["edition_behind"] is True
    assert mirrored["newer_editions"] == [{"language": "zh", "version": "v10.0.0"}]


def test_an_edition_is_not_behind_when_no_language_has_a_newer_one(
    library_copy: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    replace_in(library_copy / "books" / MIRRORED / "metadata.yaml", "  zh: v1.1.0", "  zh: v1.0.0")

    assert run(library_copy) == 0
    capsys.readouterr()

    mirrored = catalog_resources(library_copy)[MIRRORED]
    assert mirrored["edition_behind"] is False
    assert mirrored["newer_editions"] == []
    assert [line["edition_behind"] for line in chapter_lines(library_copy)] == [False] * 3


def test_topics_are_indexed_with_the_status_of_each_referenced_book(
    fixture_library_root: Path,
) -> None:
    index = json.loads((fixture_library_root / "index" / "topics.json").read_text(encoding="utf-8"))

    assert [topic["id"] for topic in index["topics"]] == ["paper-craft", "tea-service"]
    paper = index["topics"][0]
    assert paper["title"] == "Paper Craft"
    assert paper["path"] == "topics/paper-craft.md"
    assert paper["references"][0] == {
        "resource": "fixture-mirrored-book",
        "chapter": "fixture-mirrored-book/folding-the-hull",
        "note": "Covers how a hull is folded from a single sheet.",
        "mirror_status": "mirrored",
        "license_id": "MIT",
        "quote_permitted": True,
    }
    assert paper["references"][2] == {
        "resource": "fixture-reference-book",
        "chapter": None,
        "note": "Listed for its subject only. The library holds none of its text.",
        "mirror_status": "reference-only",
        "license_id": None,
        "quote_permitted": False,
    }


def test_llms_txt_links_instructions_books_topics_and_indexes(fixture_library_root: Path) -> None:
    lines = (fixture_library_root / "llms.txt").read_text(encoding="utf-8").splitlines()

    assert lines[0] == "# Fixture Library"
    assert lines[2] == (
        "> A synthetic library used only by automated tests. It holds one mirrored book and one "
        "reference-only book, and all of their text is invented."
    )
    assert [line for line in lines if line.startswith("## ")] == [
        "## Agent instructions",
        "## Mirrored book: Paper Boat Engineering (Test Fixture)",
        "## Books that are not mirrored",
        "## Topics",
        "## Indexes",
    ]
    assert any(line.startswith("- [AGENTS.md](AGENTS.md): ") for line in lines)
    assert any(
        line.startswith("- [License](books/fixture-mirrored-book/LICENSE): ") for line in lines
    )
    assert (
        "- [§03 Recovering a Sunk Boat]"
        "(books/fixture-mirrored-book/chapters/03-recovering-a-sunk-boat.md): "
        "`fixture-mirrored-book/recovering-a-sunk-boat`, source PDF p. 6."
    ) in lines
    [reference] = [line for line in lines if "fixture-reference-book" in line]
    assert reference.startswith(
        "- [Clockwork Tea Manual (Test Fixture)](https://example.invalid/books/clockwork-tea): "
    )
    assert "reference-only, no license terms found." in reference
    assert "Its text is not in this library." in reference
    assert any(line.startswith("- [Paper Craft](topics/paper-craft.md): ") for line in lines)
    for name in ("index/catalog.json", "index/chapters.jsonl", "index/topics.json"):
        assert any(line.startswith(f"- [{name}]({name}): ") for line in lines), name


def test_the_full_text_holds_the_mirrored_book_and_its_license_and_nothing_else(
    library_copy: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    planted = library_copy / "books" / REFERENCE / "chapters" / "01-steeping.md"
    planted.parent.mkdir()
    planted.write_text(PLANTED_CHAPTER, encoding="utf-8")

    assert run(library_copy, "--full") == 0
    capsys.readouterr()

    combined = (library_copy / "dist" / "llms-full.txt").read_text(encoding="utf-8")
    assert (
        "A paper boat begins as a rectangle and ends as a promise that it will float." in combined
    )
    assert "| Mill pond | Nine spans | Gusty |" in combined
    assert (
        "Copyright (c) 2026 Fixture Author (a test fixture, not a real rights holder)" in combined
    )
    assert 'THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND' in combined
    assert "Author: Fixture Author (夹具作者)" in combined
    assert "License: MIT" in combined
    assert f"revision {'a' * 40}" in combined
    assert (
        "[chapter: fixture-mirrored-book/recovering-a-sunk-boat | §03 | source PDF p. 6 | "
        "human-reviewed]"
    ) in combined
    assert "Clockwork Tea" not in combined
    assert REFERENCE not in combined
    assert "Wind the kettle key nine turns" not in combined
    assert sorted(path.name for path in (library_copy / "dist" / "llms-full").iterdir()) == [
        f"{MIRRORED}.txt"
    ]
    one_book = (library_copy / "dist" / "llms-full" / f"{MIRRORED}.txt").read_text(encoding="utf-8")
    assert "Copyright (c) 2026 Fixture Author" in one_book
    assert "Every boat sinks once, and the second launch is the one that teaches." in one_book


def test_the_full_text_prints_an_erratum_with_its_chapter_and_says_the_edition_is_behind(
    library_copy: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert run(library_copy, "--full") == 0
    capsys.readouterr()

    combined = (library_copy / "dist" / "llms-full.txt").read_text(encoding="utf-8")
    pond = combined.index("[chapter: fixture-mirrored-book/choosing-a-pond |")
    sunk = combined.index("[chapter: fixture-mirrored-book/recovering-a-sunk-boat |")
    erratum = combined.index(
        "The invented second edition says the pond table lists depth in hands and not in spans."
    )
    assert pond < erratum < combined.index("# Choosing a Pond") < sunk
    assert "The newest Chinese edition is v1.1.0." in combined


def test_a_chapter_planted_under_a_reference_only_book_reaches_no_index(
    library_copy: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    planted = library_copy / "books" / REFERENCE / "chapters" / "01-steeping.md"
    planted.parent.mkdir()
    planted.write_text(PLANTED_CHAPTER, encoding="utf-8")

    assert run(library_copy) == 0
    capsys.readouterr()

    assert catalog_resources(library_copy)[REFERENCE]["chapters"] == []
    assert all("steeping" not in line["id"] for line in chapter_lines(library_copy))
    assert "steeping" not in (library_copy / "llms.txt").read_text(encoding="utf-8").lower()


def test_a_chapter_under_another_books_directory_reaches_no_output_by_naming_a_mirrored_book(
    library_copy: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    planted = library_copy / "books" / REFERENCE / "chapters" / "04-steeping.md"
    planted.parent.mkdir()
    planted.write_text(
        PLANTED_CHAPTER.replace(f"id: {REFERENCE}/", f"id: {MIRRORED}/").replace(
            f"resource: {REFERENCE}", f"resource: {MIRRORED}"
        ),
        encoding="utf-8",
    )

    assert run(library_copy) == 0
    assert run(library_copy, "--full") == 0
    capsys.readouterr()

    assert f"{MIRRORED}/steeping" not in catalog_resources(library_copy)[MIRRORED]["chapters"]
    assert all("steeping" not in line["id"] for line in chapter_lines(library_copy))
    assert "steeping" not in (library_copy / "llms.txt").read_text(encoding="utf-8").lower()
    for full_text in sorted((library_copy / "dist").glob("llms-full*.txt")):
        assert "kettle key" not in full_text.read_text(encoding="utf-8"), full_text.name


def test_a_stale_generated_file_is_a_finding_with_the_build_command_as_its_fix(
    library_copy: Path,
) -> None:
    replace_in(
        library_copy / "topics" / "tea-service.md", "title: Tea Service", "title: Tea Ceremony"
    )

    findings = run_checks(library_copy)

    # The topic title is recorded in the topic index and listed in llms.txt, and nowhere else.
    assert [(finding.rule, finding.file, finding.line) for finding in findings] == [
        ("index-stale", "index/topics.json", None),
        ("index-stale", "llms.txt", None),
    ]
    assert all(finding.fix == FIX for finding in findings)
    assert "differs from what the build writes" in findings[0].message


def test_a_missing_generated_file_is_a_finding(library_copy: Path) -> None:
    (library_copy / "index" / "chapters.jsonl").unlink()

    findings = run_checks(library_copy)

    assert [(finding.rule, finding.file) for finding in findings] == [
        ("index-stale", "index/chapters.jsonl")
    ]
    assert "does not exist" in findings[0].message
    assert findings[0].fix == FIX


def test_an_invalid_library_is_reported_and_nothing_is_written(
    library_copy: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    before = committed_bytes(library_copy)
    (library_copy / "books" / REFERENCE / "metadata.yaml").write_text(
        "id: [unclosed\n", encoding="utf-8"
    )

    code = run(library_copy)

    output = capsys.readouterr()
    assert code == 1
    assert "books/fixture-reference-book/metadata.yaml" in output.err
    assert "uv run python scripts/validate.py" in output.err
    assert committed_bytes(library_copy) == before
