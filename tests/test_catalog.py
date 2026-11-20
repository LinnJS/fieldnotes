"""The loader turns a library directory into validated, typed records."""

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
import yaml
from jsonschema import Draft202012Validator
from kb.catalog import (
    AcceptedDifference,
    Catalog,
    Collection,
    Edition,
    EditionPattern,
    EvidenceKind,
    GitSource,
    HostedEdition,
    LibraryInfo,
    LoadError,
    MirrorStatus,
    NewestEdition,
    Permission,
    Permissions,
    Person,
    PinnedSource,
    ResourceType,
    Role,
    RoleRule,
    SectionAssignment,
    Titles,
    UrlSource,
    load_catalog,
    load_library,
    load_resource,
)

MIRRORED = "fixture-mirrored-book"
REFERENCE = "fixture-reference-book"


def metadata_path(root: Path, resource_id: str) -> Path:
    return root / "books" / resource_id / "metadata.yaml"


def edit_yaml(path: Path, change: Callable[[dict[str, Any]], None]) -> None:
    """Apply a change to the parsed YAML file and write it back."""
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    change(data)
    path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")


def replace_text(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    assert old in text
    path.write_text(text.replace(old, new), encoding="utf-8")


@pytest.mark.parametrize("name", ["resource", "catalog", "chapter", "topic"])
def test_each_schema_file_is_a_valid_json_schema(repo_root: Path, name: str) -> None:
    schema = json.loads((repo_root / "schemas" / f"{name}.schema.json").read_text("utf-8"))

    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    Draft202012Validator.check_schema(schema)


def test_load_library_returns_the_books_in_catalog_order(fixture_library_root: Path) -> None:
    library = load_library(fixture_library_root)

    assert library.root == fixture_library_root
    assert [resource.id for resource in library.resources] == [MIRRORED, REFERENCE]
    assert library.resource(REFERENCE) is library.resources[1]


def test_catalog_order_wins_over_directory_order(library_copy: Path) -> None:
    edit_yaml(
        library_copy / "catalog.yaml",
        lambda data: data.update(resources=[REFERENCE, MIRRORED]),
    )

    library = load_library(library_copy)

    assert [resource.id for resource in library.resources] == [REFERENCE, MIRRORED]


def test_load_catalog_returns_the_library_block_allowlist_and_collections(
    fixture_library_root: Path,
) -> None:
    assert load_catalog(fixture_library_root) == Catalog(
        library=LibraryInfo(
            name="fixture-library",
            title="Fixture Library",
            description=(
                "A synthetic library used only by automated tests. It holds one mirrored "
                "book and one reference-only book, and all of their text is invented."
            ),
            base_url="https://example.invalid/fixture-library/",
            repository="https://example.invalid/fixture-owner/fixture-library",
        ),
        license_allowlist=("MIT",),
        collections=(Collection(id="fixture-books", title="Fixture Books"),),
        resources=(MIRRORED, REFERENCE),
    )


def test_mirrored_book_record_carries_identity_people_and_upstream(
    fixture_library_root: Path,
) -> None:
    book = load_resource(fixture_library_root, MIRRORED)

    assert book.id == MIRRORED
    assert book.type is ResourceType.BOOK
    assert book.collection == "fixture-books"
    assert book.title == Titles(
        original="纸船工程测试夹具",
        english="Paper Boat Engineering (Test Fixture)",
        english_official=True,
    )
    assert book.author == Person(
        name="Fixture Author", native_name="夹具作者", url="https://example.invalid/fixture-author"
    )
    assert book.translator is None
    assert book.languages == ("zh", "en")
    assert book.official_urls.site == "https://example.invalid/books/paper-boat"
    assert book.official_urls.repository == (
        "https://example.invalid/fixture-author/fixture-mirrored-book"
    )
    assert book.official_urls.hosted_editions == (
        HostedEdition(
            name="Fixture Reader",
            url="https://example.invalid/reader/paper-boat",
            note="One page per chapter. Invented for tests.",
        ),
    )
    assert book.site_slug == "paper-boat"
    assert book.upstream == GitSource(
        kind="git",
        repository="fixture-author/fixture-mirrored-book",
        default_branch="main",
        head_commit="b" * 40,
    )
    assert book.notices == (
        "Test fixture. This book and its text are invented for automated tests.",
    )


def test_mirrored_book_record_carries_editions_patterns_and_newest_versions(
    fixture_library_root: Path,
) -> None:
    book = load_resource(fixture_library_root, MIRRORED)

    assert book.editions == (
        Edition(
            language="en",
            version="v1.0.0",
            format="pdf",
            path="Paper-Boat-Engineering-v1.0.0.pdf",
            blob_sha="c" * 40,
        ),
        Edition(
            language="zh",
            version="v1.1.0",
            format="pdf",
            path="纸船工程-v1.1.0.pdf",
            blob_sha="d" * 40,
        ),
    )
    assert book.edition_patterns == (
        EditionPattern(
            language="en", pattern=r"^Paper-Boat-Engineering-(?P<version>v\d+\.\d+\.\d+)\.pdf$"
        ),
        EditionPattern(language="zh", pattern=r"^纸船工程-(?P<version>v\d+\.\d+\.\d+)\.pdf$"),
    )
    assert book.newest_editions == (
        NewestEdition(language="en", version="v1.0.0"),
        NewestEdition(language="zh", version="v1.1.0"),
    )


def test_mirrored_book_record_carries_license_permissions_and_pinned_source(
    fixture_library_root: Path,
) -> None:
    book = load_resource(fixture_library_root, MIRRORED)

    assert book.license.spdx == "MIT"
    assert book.license.evidence is EvidenceKind.LICENSE_FILE
    assert book.license.permalink == (
        f"https://example.invalid/fixture-author/fixture-mirrored-book/blob/{'a' * 40}/LICENSE"
    )
    assert book.license.blob_sha == "2b83b85f5d96ee4d65a4a46d8f8614161569df54"
    assert book.license.commit == "a" * 40
    assert book.license.verified_on == "2026-11-20"
    assert book.license.departs_from_template is False
    assert book.license.locations_checked == ("LICENSE", "README.md")
    assert book.permissions == Permissions(
        redistribution=Permission.ALLOWED,
        adaptation=Permission.ALLOWED,
        commercial_use=Permission.ALLOWED,
        attribution_required=True,
        share_alike=False,
        third_party_rights=False,
    )
    assert book.mirror_status is MirrorStatus.MIRRORED
    assert book.pinned_source == PinnedSource(
        repository="fixture-author/fixture-mirrored-book",
        commit="a" * 40,
        path="Paper-Boat-Engineering-v1.0.0.pdf",
        sha256="e" * 64,
        edition="v1.0.0",
        language="en",
        local_path=None,
    )


def test_license_statement_is_quoted_verbatim_from_the_fixture_license_file(
    fixture_library_root: Path,
) -> None:
    book = load_resource(fixture_library_root, MIRRORED)
    license_text = (fixture_library_root / "books" / MIRRORED / "LICENSE").read_text("utf-8")

    assert book.license.statement is not None
    assert book.license.statement.startswith("Permission is hereby granted")
    assert book.license.statement.endswith("subject to the following conditions:")
    assert book.license.statement in license_text


def test_mirrored_book_record_carries_the_extraction_profile(fixture_library_root: Path) -> None:
    profile = load_resource(fixture_library_root, MIRRORED).extraction_profile

    assert profile is not None
    assert len(profile.roles) == 10
    assert profile.roles[0] == RoleRule(
        role=Role.SECTION_LABEL, font_size=24.0, min_indent=None, max_indent=None
    )
    assert profile.roles[5] == RoleRule(
        role=Role.KICKER, font_size=13.3, min_indent=None, max_indent=80.0
    )
    assert profile.roles[6] == RoleRule(
        role=Role.QUOTE, font_size=13.3, min_indent=80.0, max_indent=None
    )
    assert [rule.role for rule in profile.roles] == [
        Role.SECTION_LABEL,
        Role.SECTION_TITLE,
        Role.LEDE,
        Role.HEADING,
        Role.BODY,
        Role.KICKER,
        Role.QUOTE,
        Role.TABLE_HEADER,
        Role.TABLE_CELL,
        Role.CODE,
    ]
    assert profile.section_start == r"^§\d{2}$"
    assert profile.excluded_pages == (1, 2)
    assert profile.sections == (
        SectionAssignment(
            title="Folding the Hull", slug="folding-the-hull", part="Part One: Paper"
        ),
        SectionAssignment(title="Choosing a Pond", slug="choosing-a-pond", part="Part One: Paper"),
        SectionAssignment(
            title="Recovering a Sunk Boat", slug="recovering-a-sunk-boat", part="Part Two: Water"
        ),
    )
    assert profile.accepted_differences == ()


def test_accepted_word_differences_load_with_their_chapter_and_reason(library_copy: Path) -> None:
    def add_difference(data: dict[str, Any]) -> None:
        data["extraction_profile"]["accepted_differences"] = [
            {
                "chapter": f"{MIRRORED}/choosing-a-pond",
                "words_removed": ["spans"],
                "words_added": ["Spans", "Wind"],
                "reason": "The table header lost a word in extraction.",
            }
        ]

    edit_yaml(metadata_path(library_copy, MIRRORED), add_difference)

    profile = load_resource(library_copy, MIRRORED).extraction_profile

    assert profile is not None
    assert profile.accepted_differences == (
        AcceptedDifference(
            chapter=f"{MIRRORED}/choosing-a-pond",
            words_removed=("spans",),
            words_added=("Spans", "Wind"),
            reason="The table header lost a word in extraction.",
        ),
    )


def test_reference_only_book_record_has_a_url_source_and_no_evidence(
    fixture_library_root: Path,
) -> None:
    book = load_resource(fixture_library_root, REFERENCE)

    assert book.upstream == UrlSource(kind="url", url="https://example.invalid/books/clockwork-tea")
    assert book.official_urls.repository is None
    assert book.official_urls.hosted_editions == ()
    assert book.editions == ()
    assert book.edition_patterns == ()
    assert book.newest_editions == ()
    assert book.license.spdx is None
    assert book.license.evidence is EvidenceKind.NONE
    assert book.license.statement is None
    assert book.license.locations_checked == (
        "https://example.invalid/books/clockwork-tea",
        "https://example.invalid/books",
    )
    assert book.permissions.redistribution is Permission.UNCLEAR
    assert book.mirror_status is MirrorStatus.REFERENCE_ONLY
    assert book.pinned_source is None
    assert book.extraction_profile is None


def test_library_holds_chapters_in_file_order_with_paths_relative_to_the_root(
    fixture_library_root: Path,
) -> None:
    library = load_library(fixture_library_root)
    chapters_dir = Path("books") / MIRRORED / "chapters"

    assert [chapter_file.path for chapter_file in library.chapters] == [
        chapters_dir / "01-folding-the-hull.md",
        chapters_dir / "02-choosing-a-pond.md",
        chapters_dir / "03-recovering-a-sunk-boat.md",
    ]
    assert [chapter_file.chapter.order for chapter_file in library.chapters] == [1, 2, 3]
    assert library.chapters[0].chapter.id == f"{MIRRORED}/folding-the-hull"
    assert library.chapters[0].body.startswith("# Folding the Hull\n")
    assert library.chapters_of(MIRRORED) == library.chapters
    assert library.chapters_of(REFERENCE) == ()


def test_library_holds_topics_in_file_order_and_skips_the_topic_index_page(
    library_copy: Path,
) -> None:
    (library_copy / "topics" / "index.md").write_text("# Topics\n\nA list.\n", encoding="utf-8")

    library = load_library(library_copy)

    assert [topic_file.path for topic_file in library.topics] == [
        Path("topics") / "paper-craft.md",
        Path("topics") / "tea-service.md",
    ]
    assert [topic_file.topic.id for topic_file in library.topics] == ["paper-craft", "tea-service"]
    assert library.topics[1].body.startswith("# Tea Service\n")


def test_no_evidence_with_no_locations_checked_fails_validation(library_copy: Path) -> None:
    path = metadata_path(library_copy, REFERENCE)
    edit_yaml(path, lambda data: data["license"].update(locations_checked=[]))

    with pytest.raises(LoadError) as raised:
        load_resource(library_copy, REFERENCE)

    assert raised.value.path == path
    assert raised.value.json_path == "$.license.locations_checked"
    assert str(path) in str(raised.value)
    assert "$.license.locations_checked" in str(raised.value)


def test_evidence_without_a_permalink_fails_validation(library_copy: Path) -> None:
    edit_yaml(
        metadata_path(library_copy, MIRRORED), lambda data: data["license"].update(permalink=None)
    )

    with pytest.raises(LoadError) as raised:
        load_resource(library_copy, MIRRORED)

    assert raised.value.json_path == "$.license.permalink"


def test_permalink_without_a_full_commit_sha_fails_validation(library_copy: Path) -> None:
    edit_yaml(
        metadata_path(library_copy, MIRRORED),
        lambda data: data["license"].update(
            permalink="https://example.invalid/fixture-author/fixture-mirrored-book/blob/main/LICENSE"
        ),
    )

    with pytest.raises(LoadError) as raised:
        load_resource(library_copy, MIRRORED)

    assert raised.value.json_path == "$.license.permalink"


def test_type_other_than_book_fails_validation(library_copy: Path) -> None:
    edit_yaml(metadata_path(library_copy, MIRRORED), lambda data: data.update(type="article"))

    with pytest.raises(LoadError) as raised:
        load_resource(library_copy, MIRRORED)

    assert raised.value.json_path == "$.type"
    assert "article" in raised.value.message


@pytest.mark.parametrize("bad_id", ["Fixture-Mirrored-Book", "fixture/mirrored-book"])
def test_resource_id_with_an_uppercase_letter_or_a_slash_fails_validation(
    library_copy: Path, bad_id: str
) -> None:
    edit_yaml(metadata_path(library_copy, MIRRORED), lambda data: data.update(id=bad_id))

    with pytest.raises(LoadError) as raised:
        load_resource(library_copy, MIRRORED)

    assert raised.value.json_path == "$.id"
    assert bad_id in raised.value.message


@pytest.mark.parametrize("bad_id", ["Fixture-Mirrored-Book", "fixture/mirrored-book"])
def test_catalog_entry_with_an_uppercase_letter_or_a_slash_fails_validation(
    library_copy: Path, bad_id: str
) -> None:
    path = library_copy / "catalog.yaml"
    edit_yaml(path, lambda data: data.update(resources=[bad_id, REFERENCE]))

    with pytest.raises(LoadError) as raised:
        load_library(library_copy)

    assert raised.value.path == path
    assert raised.value.json_path == "$.resources[0]"


def test_metadata_id_must_equal_its_directory_name(library_copy: Path) -> None:
    edit_yaml(metadata_path(library_copy, MIRRORED), lambda data: data.update(id="another-book"))

    with pytest.raises(LoadError) as raised:
        load_resource(library_copy, MIRRORED)

    assert raised.value.json_path == "$.id"
    assert MIRRORED in raised.value.message


def test_bare_yaml_yes_is_not_a_permission_value(library_copy: Path) -> None:
    replace_text(
        metadata_path(library_copy, MIRRORED), "redistribution: allowed", "redistribution: yes"
    )

    with pytest.raises(LoadError) as raised:
        load_resource(library_copy, MIRRORED)

    assert raised.value.json_path == "$.permissions.redistribution"


def test_misspelled_key_fails_validation(library_copy: Path) -> None:
    def rename(data: dict[str, Any]) -> None:
        data["licence"] = data.pop("license")

    edit_yaml(metadata_path(library_copy, MIRRORED), rename)

    with pytest.raises(LoadError) as raised:
        load_resource(library_copy, MIRRORED)

    assert raised.value.json_path == "$"


def test_git_source_without_a_head_commit_fails_validation(library_copy: Path) -> None:
    edit_yaml(
        metadata_path(library_copy, MIRRORED), lambda data: data["upstream"].pop("head_commit")
    )

    with pytest.raises(LoadError) as raised:
        load_resource(library_copy, MIRRORED)

    assert raised.value.json_path == "$.upstream"
    assert "head_commit" in raised.value.message


def test_edition_pattern_without_a_version_group_fails_validation(library_copy: Path) -> None:
    edit_yaml(
        metadata_path(library_copy, MIRRORED),
        lambda data: data["edition_patterns"].update(en=r"^Paper-Boat-Engineering-(v\d+)\.pdf$"),
    )

    with pytest.raises(LoadError) as raised:
        load_resource(library_copy, MIRRORED)

    assert raised.value.json_path == "$.edition_patterns.en"


def test_unknown_role_in_the_extraction_profile_fails_validation(library_copy: Path) -> None:
    def rename_role(data: dict[str, Any]) -> None:
        data["extraction_profile"]["roles"][4]["role"] = "footnote"

    edit_yaml(metadata_path(library_copy, MIRRORED), rename_role)

    with pytest.raises(LoadError) as raised:
        load_resource(library_copy, MIRRORED)

    assert raised.value.json_path == "$.extraction_profile.roles[4].role"


def test_cataloged_book_without_a_metadata_file_is_a_load_error(library_copy: Path) -> None:
    path = metadata_path(library_copy, REFERENCE)
    path.unlink()

    with pytest.raises(LoadError) as raised:
        load_library(library_copy)

    assert raised.value.path == path
    assert raised.value.json_path is None


def test_malformed_yaml_is_a_load_error_that_names_the_file(library_copy: Path) -> None:
    path = library_copy / "catalog.yaml"
    path.write_text("library: [unclosed\n", encoding="utf-8")

    with pytest.raises(LoadError) as raised:
        load_library(library_copy)

    assert raised.value.path == path
    assert "YAML" in raised.value.message


def test_invalid_chapter_frontmatter_stops_the_library_load(library_copy: Path) -> None:
    path = library_copy / "books" / MIRRORED / "chapters" / "02-choosing-a-pond.md"
    replace_text(path, "order: 2\n", "order: second\n")

    with pytest.raises(LoadError) as raised:
        load_library(library_copy)

    assert raised.value.path == path
    assert raised.value.json_path == "$.order"
