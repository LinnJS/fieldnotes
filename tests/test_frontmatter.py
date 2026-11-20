"""Chapter and topic files split into validated frontmatter records and a Markdown body."""

from pathlib import Path

import pytest
from kb.frontmatter import (
    Chapter,
    ChapterSource,
    Erratum,
    ExtractionStatus,
    PageRange,
    Topic,
    TopicReference,
    load_chapter,
    load_topic,
    split_frontmatter,
)
from kb.schema import LoadError

CHAPTERS = Path("books") / "fixture-mirrored-book" / "chapters"

VALID_CHAPTER = """\
---
id: some-book/first-section
resource: some-book
title: First Section
part: Part One
order: 1
section_label: "§01"
language: en
edition: v1.0.0
source:
  repository: some-author/some-book
  revision: aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
  path: Some-Book-v1.0.0.pdf
  pages:
    first: 3
    last: 4
extraction_status: machine-extracted
---

# First Section

Body text.
"""


def write(path: Path, text: str) -> Path:
    path.write_text(text, encoding="utf-8")
    return path


def test_split_frontmatter_returns_the_yaml_and_the_body() -> None:
    frontmatter, body = split_frontmatter("---\nid: a\ntitle: B\n---\n\n# Heading\n\nText.\n")

    assert frontmatter == "id: a\ntitle: B"
    assert body == "# Heading\n\nText.\n"


def test_split_frontmatter_keeps_a_horizontal_rule_in_the_body() -> None:
    _, body = split_frontmatter("---\nid: a\n---\nAbove.\n\n---\n\nBelow.\n")

    assert body == "Above.\n\n---\n\nBelow.\n"


def test_split_frontmatter_rejects_text_that_does_not_open_with_a_fence() -> None:
    with pytest.raises(ValueError, match="must start with"):
        split_frontmatter("# Heading\n\nText.\n")


def test_split_frontmatter_rejects_an_unclosed_fence() -> None:
    with pytest.raises(ValueError, match="never closed"):
        split_frontmatter("---\nid: a\n\n# Heading\n")


def test_load_chapter_returns_the_typed_record_and_the_body(fixture_library_root: Path) -> None:
    chapter, body = load_chapter(fixture_library_root / CHAPTERS / "02-choosing-a-pond.md")

    assert chapter == Chapter(
        id="fixture-mirrored-book/choosing-a-pond",
        resource="fixture-mirrored-book",
        title="Choosing a Pond",
        part="Part One: Paper",
        order=2,
        section_label="§02",
        language="en",
        edition="v1.0.0",
        source=ChapterSource(
            repository="fixture-author/fixture-mirrored-book",
            revision="a" * 40,
            path="Paper-Boat-Engineering-v1.0.0.pdf",
            pages=PageRange(first=4, last=5),
        ),
        extraction_status=ExtractionStatus.MACHINE_EXTRACTED,
        errata=(
            Erratum(
                description=(
                    "The invented second edition says the pond table lists depth in hands "
                    "and not in spans."
                ),
                source_url="https://example.invalid/fixture-author/fixture-mirrored-book/errata",
            ),
        ),
    )
    assert chapter.slug == "choosing-a-pond"
    assert body.startswith("# Choosing a Pond\n")
    assert body.endswith("launch from the lee bank\n```\n")
    assert "extraction_status" not in body


def test_load_chapter_without_errata_gives_an_empty_tuple(fixture_library_root: Path) -> None:
    chapter, _ = load_chapter(fixture_library_root / CHAPTERS / "03-recovering-a-sunk-boat.md")

    assert chapter.errata == ()
    assert chapter.extraction_status is ExtractionStatus.HUMAN_REVIEWED


def test_load_topic_returns_the_typed_record_and_the_body(fixture_library_root: Path) -> None:
    topic, body = load_topic(fixture_library_root / "topics" / "paper-craft.md")

    assert topic == Topic(
        id="paper-craft",
        title="Paper Craft",
        references=(
            TopicReference(
                resource="fixture-mirrored-book",
                chapter="fixture-mirrored-book/folding-the-hull",
                note="Covers how a hull is folded from a single sheet.",
            ),
            TopicReference(
                resource="fixture-mirrored-book",
                chapter="fixture-mirrored-book/recovering-a-sunk-boat",
                note="Covers drying and refolding a boat after it sinks.",
            ),
            TopicReference(
                resource="fixture-reference-book",
                chapter=None,
                note="Listed for its subject only. The library holds none of its text.",
            ),
        ),
    )
    assert body.startswith("# Paper Craft\n")


def test_missing_required_field_reports_the_file_and_the_field_name(tmp_path: Path) -> None:
    without_title = VALID_CHAPTER.replace("title: First Section\n", "")
    path = write(tmp_path / "01-first-section.md", without_title)

    with pytest.raises(LoadError) as raised:
        load_chapter(path)

    assert raised.value.path == path
    assert raised.value.json_path == "$"
    assert str(path) in str(raised.value)
    assert "'title'" in str(raised.value)


def test_invalid_nested_value_reports_its_json_path(tmp_path: Path) -> None:
    path = write(tmp_path / "01-first-section.md", VALID_CHAPTER.replace("first: 3", "first: 0"))

    with pytest.raises(LoadError) as raised:
        load_chapter(path)

    assert raised.value.json_path == "$.source.pages.first"


def test_extraction_status_accepts_only_the_two_review_states(tmp_path: Path) -> None:
    path = write(
        tmp_path / "01-first-section.md",
        VALID_CHAPTER.replace("machine-extracted", "proofread"),
    )

    with pytest.raises(LoadError) as raised:
        load_chapter(path)

    assert raised.value.json_path == "$.extraction_status"


def test_chapter_id_must_begin_with_its_resource_id(tmp_path: Path) -> None:
    path = write(
        tmp_path / "01-first-section.md",
        VALID_CHAPTER.replace("id: some-book/first-section", "id: other-book/first-section"),
    )

    with pytest.raises(LoadError) as raised:
        load_chapter(path)

    assert raised.value.json_path == "$.id"
    assert "some-book/" in raised.value.message


@pytest.mark.parametrize("bad_id", ["Some-Book/first-section", "some-book", "some-book/a/b"])
def test_chapter_id_must_be_a_resource_slug_a_slash_and_a_slug(tmp_path: Path, bad_id: str) -> None:
    path = write(
        tmp_path / "01-first-section.md",
        VALID_CHAPTER.replace("id: some-book/first-section", f"id: {bad_id}"),
    )

    with pytest.raises(LoadError) as raised:
        load_chapter(path)

    assert raised.value.json_path == "$.id"


def test_file_without_frontmatter_is_a_load_error_that_names_the_file(tmp_path: Path) -> None:
    path = write(tmp_path / "01-first-section.md", "# First Section\n\nBody text.\n")

    with pytest.raises(LoadError) as raised:
        load_chapter(path)

    assert raised.value.path == path
    assert "frontmatter" in raised.value.message


def test_malformed_frontmatter_yaml_is_a_load_error(tmp_path: Path) -> None:
    path = write(tmp_path / "paper-craft.md", "---\nid: [unclosed\n---\n\nBody.\n")

    with pytest.raises(LoadError) as raised:
        load_topic(path)

    assert raised.value.path == path
    assert "YAML" in raised.value.message


def test_missing_file_is_a_load_error(tmp_path: Path) -> None:
    path = tmp_path / "absent.md"

    with pytest.raises(LoadError) as raised:
        load_topic(path)

    assert raised.value.path == path
