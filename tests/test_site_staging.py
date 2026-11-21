"""Staging writes the documentation site's source tree from the canonical files of a library."""

import re
import shutil
from pathlib import Path

import pytest
import yaml
from kb.catalog import Library, load_library
from kb.export import bundle_files
from kb.indexes import build_full_text, build_indexes
from kb.site import Downloads, SiteError, publish_canonical_files, stage, write_config

MIRRORED = "fixture-mirrored-book"
REFERENCE = "fixture-reference-book"
EDITION = "v1.0.0"
PINNED_COMMIT = "a" * 40
SOURCE_URL = (
    "https://github.com/fixture-author/fixture-mirrored-book/blob/"
    f"{PINNED_COMMIT}/Paper-Boat-Engineering-v1.0.0.pdf"
)
ERRATUM = "The invented second edition says the pond table lists depth in hands and not in spans."
ERRATUM_URL = "https://example.invalid/fixture-author/fixture-mirrored-book/errata"
MACHINE_EXTRACTED_SENTENCE = "no person has compared it with the source"

CHAPTER_PAGES = [
    f"books/{MIRRORED}/chapters/01-folding-the-hull.md",
    f"books/{MIRRORED}/chapters/02-choosing-a-pond.md",
    f"books/{MIRRORED}/chapters/03-recovering-a-sunk-boat.md",
]

HULL_TOKEN = f"[cite:{MIRRORED}/folding-the-hull@{EDITION}]"

# The tests write their own topics, so the expected links below are named here and do not
# depend on what the committed fixture topics happen to say.
TOPIC = f"""---
id: paper-craft
title: Paper Craft
references:
  - resource: {MIRRORED}
    chapter: {MIRRORED}/folding-the-hull
    note: Covers how a hull is folded from a single sheet.
  - resource: {REFERENCE}
    note: Listed for its subject only.
---

# Paper Craft

**Scope (editorial).** This topic is invented for automated tests.

The hull chapter tells the reader to stop after three folds. {HULL_TOKEN}

Another book shares the subject. [cite:{REFERENCE}]

A token is written as `[cite:{MIRRORED}]` in a document.

## Where to read

- [Folding the Hull](../books/{MIRRORED}/chapters/01-folding-the-hull.md)
- [The license of the book](../books/{MIRRORED}/LICENSE)
- `{REFERENCE}`. Run `python3 scripts/resolve.py {REFERENCE}` for its official URL.
"""

_LINK_TARGET = re.compile(r"\]\(([^)\s]+)")


@pytest.fixture
def library_root(library_copy: Path) -> Path:
    """Return a copy of the fixture library whose only topic is the one written above."""
    topics = library_copy / "topics"
    shutil.rmtree(topics)
    topics.mkdir()
    (topics / "paper-craft.md").write_text(TOPIC, encoding="utf-8")
    return library_copy


@pytest.fixture
def library(library_root: Path) -> Library:
    return load_library(library_root)


@pytest.fixture
def staged(library: Library, tmp_path: Path) -> Path:
    """Stage the library with no downloads and return the staging directory."""
    staging_dir = tmp_path / "site-src"
    stage(library, staging_dir)
    return staging_dir


def read(staging_dir: Path, name: str) -> str:
    return (staging_dir / name).read_text(encoding="utf-8")


def snapshot(directory: Path) -> dict[str, bytes]:
    return {
        path.relative_to(directory).as_posix(): path.read_bytes()
        for path in sorted(directory.rglob("*"))
        if path.is_file()
    }


def catalog_sections(staging_dir: Path) -> dict[str, str]:
    """Split the staged catalog page into the text under each second-level heading."""
    parts = re.split(r"(?m)^## (.+)$", read(staging_dir, "catalog.md"))
    return {parts[n].strip(): parts[n + 1] for n in range(1, len(parts), 2)}


def card(section: str, resource_id: str) -> str:
    """Return the one card of a catalog section that carries the given resource id."""
    cards = [text for text in section.split("</div>") if f"#{resource_id} " in text]
    assert len(cards) == 1
    return cards[0]


def test_each_mirrored_chapter_gets_a_page_and_the_reference_book_gets_none(staged: Path) -> None:
    for page in CHAPTER_PAGES:
        assert (staged / page).is_file()
    assert (staged / f"books/{MIRRORED}/index.md").is_file()
    assert not (staged / f"books/{REFERENCE}").exists()


def test_chapter_page_shows_author_edition_license_and_official_link(
    staged: Path, library: Library
) -> None:
    page = read(staged, CHAPTER_PAGES[0])

    assert "Fixture Author (夹具作者)" in page
    assert f"{EDITION}, English" in page
    assert "[MIT](../license-text.md)" in page
    assert SOURCE_URL in page
    assert PINNED_COMMIT in page
    assert "pp. 3-4" in page
    assert "machine-extracted" in page
    assert MACHINE_EXTRACTED_SENTENCE in page
    assert f"`{MIRRORED}/folding-the-hull`" in page
    assert f"`{HULL_TOKEN}`" in page
    # The fixture's English edition is behind its Chinese one.
    assert "The newest Chinese edition is v1.1.0." in page


def test_chapter_page_keeps_the_canonical_body_under_its_title(
    staged: Path, library: Library
) -> None:
    page = read(staged, CHAPTER_PAGES[0])
    body = library.chapters_of(MIRRORED)[0].body
    title, _, text = body.partition("\n")

    assert title == "# Folding the Hull"
    assert page.startswith(f"{title}\n")
    assert page.endswith(text)


def test_reviewed_chapter_carries_no_machine_extraction_notice(staged: Path) -> None:
    page = read(staged, CHAPTER_PAGES[2])

    assert "human-reviewed" in page
    assert MACHINE_EXTRACTED_SENTENCE not in page


def test_chapter_page_shows_its_erratum(staged: Path) -> None:
    with_erratum = read(staged, CHAPTER_PAGES[1])

    assert ERRATUM in with_erratum
    assert ERRATUM_URL in with_erratum
    assert "erratum" not in read(staged, CHAPTER_PAGES[0]).lower()


def test_license_page_prints_the_license_file_verbatim(staged: Path, library_root: Path) -> None:
    license_text = (library_root / f"books/{MIRRORED}/LICENSE").read_text(encoding="utf-8")

    assert license_text.strip("\n") in read(staged, f"books/{MIRRORED}/license-text.md")


def test_catalog_page_shows_the_reference_book_with_its_link_and_label(staged: Path) -> None:
    sections = catalog_sections(staged)
    assert list(sections) == ["Mirrored", "Eligible", "Reference-only"]

    mirrored = card(sections["Mirrored"], MIRRORED)
    reference = card(sections["Reference-only"], REFERENCE)
    assert "Clockwork Tea Manual (Test Fixture)" in reference
    assert ">Reference-only</span>" in reference
    assert "https://example.invalid/books/clockwork-tea" in reference
    assert "发条茶事手册测试夹具" in reference
    assert "It is this library's translation, not the author's." in reference
    assert "translation" not in mirrored
    assert "no license terms found" in reference
    assert "Fixture Author (夹具作者)" in reference
    assert "Test fixture. This book is invented for automated tests" in reference

    assert ">Mirrored</span>" in mirrored
    assert f"(books/{MIRRORED}/index.md)" in mirrored
    assert REFERENCE not in sections["Mirrored"]
    assert MIRRORED not in sections["Reference-only"]


def test_eligible_book_gets_a_card_that_says_so_and_no_pages(
    library_root: Path, tmp_path: Path
) -> None:
    metadata = library_root / f"books/{MIRRORED}/metadata.yaml"
    text = metadata.read_text(encoding="utf-8")
    metadata.write_text(
        text.replace("mirror_status: mirrored", "mirror_status: eligible"), encoding="utf-8"
    )
    # The topic cites a chapter, and an eligible book has none to cite.
    shutil.rmtree(library_root / "topics")
    staging_dir = tmp_path / "site-src"

    stage(load_library(library_root), staging_dir)

    eligible = card(catalog_sections(staging_dir)["Eligible"], MIRRORED)
    assert ">Eligible</span>" in eligible
    assert "Its license allows mirroring, and the book has not been mirrored yet." in eligible
    assert not (staging_dir / "books").exists()
    assert not list(staging_dir.glob("llms-full/*.txt"))
    for name, data in snapshot(staging_dir).items():
        assert b"A paper boat begins as a rectangle" not in data, name


def test_citation_token_in_a_topic_becomes_a_link_to_the_chapter_page(staged: Path) -> None:
    page = read(staged, "topics/paper-craft.md")

    assert f"(../books/{MIRRORED}/chapters/01-folding-the-hull.md " in page
    assert f"(../catalog.md#{REFERENCE} " in page
    assert HULL_TOKEN not in page
    assert f"[cite:{REFERENCE}]" not in page
    # A token inside code is an example and not a citation, so it stays as written.
    assert f"`[cite:{MIRRORED}]`" in page


def test_reading_list_item_for_a_book_that_is_not_mirrored_links_its_catalog_card(
    staged: Path,
) -> None:
    page = read(staged, "topics/paper-craft.md")
    items = [line for line in page.splitlines() if line.startswith("- ")]

    assert items[-1].startswith(
        f"- [Clockwork Tea Manual (Test Fixture)](../catalog.md#{REFERENCE} "
    )
    assert items[-1].endswith("is not mirrored. Its catalog card lists the official links.")
    assert "scripts/resolve.py" not in page


def test_links_between_canonical_files_point_at_staged_pages(staged: Path) -> None:
    page = read(staged, "topics/paper-craft.md")

    assert f"(../books/{MIRRORED}/license-text.md)" in page
    targets = [target.partition("#")[0] for target in _LINK_TARGET.findall(page)]
    assert len(targets) == 5
    for target in targets:
        assert (staged / "topics" / target).resolve().is_file(), target
    # A chapter's link to a sibling chapter also lands on a staged page.
    for target in _LINK_TARGET.findall(read(staged, CHAPTER_PAGES[2]).partition("</div>")[2]):
        if "://" not in target:
            assert (staged / CHAPTER_PAGES[2]).parent.joinpath(target).resolve().is_file(), target


def test_token_that_does_not_resolve_fails_staging_and_names_the_file(
    library_root: Path, tmp_path: Path
) -> None:
    topic = library_root / "topics" / "paper-craft.md"
    topic.write_text(
        TOPIC.replace(HULL_TOKEN, f"[cite:{MIRRORED}/no-such-chapter]"), encoding="utf-8"
    )

    with pytest.raises(SiteError) as raised:
        stage(load_library(library_root), tmp_path / "site-src")

    assert "topics/paper-craft.md" in str(raised.value)
    assert f"[cite:{MIRRORED}/no-such-chapter]" in str(raised.value)


def test_staging_twice_gives_identical_files(library: Library, tmp_path: Path) -> None:
    staging_dir = tmp_path / "site-src"
    stage(library, staging_dir)
    first = snapshot(staging_dir)
    # A file left over from an earlier run must not survive, because staging starts empty.
    (staging_dir / "left-over.md").write_text("stale\n", encoding="utf-8")

    stage(library, staging_dir)

    assert snapshot(staging_dir) == first
    stage(library, tmp_path / "elsewhere")
    assert snapshot(tmp_path / "elsewhere") == first


def test_machine_files_are_staged_and_linked_from_the_agents_page(
    staged: Path, library: Library
) -> None:
    for name, text in build_indexes(library).items():
        assert read(staged, name) == text
    full_text = build_full_text(library)
    assert read(staged, "llms-full.txt") == full_text["dist/llms-full.txt"]
    assert read(staged, f"llms-full/{MIRRORED}.txt") == full_text[f"dist/llms-full/{MIRRORED}.txt"]

    agents = read(staged, "agents.md")
    for name in (
        "llms.txt",
        "llms-full.txt",
        f"llms-full/{MIRRORED}.txt",
        "index/catalog.json",
        "index/topics.json",
        "index/chapters.jsonl",
    ):
        assert f"]({name})" in agents
    assert "python3 scripts/resolve.py" in agents
    assert "python3 scripts/check_citations.py" in agents


def test_downloads_are_staged_and_only_the_mirrored_book_links_them(
    library: Library, tmp_path: Path
) -> None:
    exports = tmp_path / "exports"
    exports.mkdir()
    pdf = exports / f"{MIRRORED}-{EDITION}.pdf"
    epub = exports / f"{MIRRORED}-{EDITION}.epub"
    bundle = exports / "fixture-library-bundle.zip"
    for number, path in enumerate((pdf, epub, bundle)):
        path.write_bytes(b"download %d" % number)
    staging_dir = tmp_path / "site-src"

    stage(library, staging_dir, Downloads(books={MIRRORED: (pdf, epub)}, bundle=bundle))

    assert sorted(path.name for path in (staging_dir / "downloads").iterdir()) == sorted(
        [pdf.name, epub.name, bundle.name]
    )
    assert (staging_dir / "downloads" / pdf.name).read_bytes() == b"download 0"
    overview = read(staging_dir, f"books/{MIRRORED}/index.md")
    assert f"(../../downloads/{pdf.name})" in overview
    assert f"(../../downloads/{epub.name})" in overview
    assert f"(downloads/{bundle.name})" in read(staging_dir, "agents.md")

    reference = card(catalog_sections(staging_dir)["Reference-only"], REFERENCE)
    assert "downloads/" not in reference
    assert "chapters/" not in reference
    assert not [name for name in snapshot(staging_dir) if REFERENCE in name]


def test_home_page_says_what_the_library_is_and_that_it_is_independent(staged: Path) -> None:
    home = read(staged, "index.md")

    assert home.startswith("# Fixture Library\n")
    assert "A synthetic library used only by automated tests." in home
    assert "independent" in home
    assert "(catalog.md)" in home
    assert "(agents.md)" in home


def test_generated_config_takes_its_names_from_the_catalog_and_lists_every_page(
    library: Library, tmp_path: Path, repo_root: Path
) -> None:
    staging_dir = tmp_path / "build" / "site-src"
    config_file = tmp_path / "build" / "mkdocs.yml"

    navigation = stage(library, staging_dir)
    write_config(
        library, navigation, config_file, docs_dir=staging_dir, site_dir=tmp_path / "dist" / "site"
    )

    config = yaml.safe_load(config_file.read_text(encoding="utf-8"))
    assert (config_file.parent / config["INHERIT"]).resolve() == repo_root / "mkdocs.yml"
    assert config["site_name"] == "Fixture Library"
    assert config["site_description"].startswith("A synthetic library used only by automated")
    assert config["site_url"] == "https://example.invalid/fixture-library/"
    assert config["repo_url"] == "https://example.invalid/fixture-owner/fixture-library"
    assert config["docs_dir"] == "site-src"
    assert config["site_dir"] == "../dist/site"
    assert [next(iter(entry)) for entry in config["nav"]] == [
        "Home",
        "Books",
        "Topics",
        "Catalog",
        "Agents",
    ]

    def leaves(entry: object) -> list[str]:
        if isinstance(entry, str):
            return [entry]
        if isinstance(entry, dict):
            return [leaf for value in entry.values() for leaf in leaves(value)]
        assert isinstance(entry, list)
        return [leaf for item in entry for leaf in leaves(item)]

    listed = leaves(config["nav"])
    pages = [name for name in snapshot(staging_dir) if name.endswith(".md")]
    assert sorted(listed) == sorted(pages)
    # The chapters of a book are listed in reading order, between its overview and its license.
    book = listed.index(f"books/{MIRRORED}/index.md")
    assert listed[book + 1 : book + 5] == [*CHAPTER_PAGES, f"books/{MIRRORED}/license-text.md"]


def test_canonical_files_are_served_at_their_repository_paths(
    library_root: Path, tmp_path: Path
) -> None:
    (library_root / "AGENTS.md").write_text("Instructions for agents.\n", encoding="utf-8")
    (library_root / "LICENSES.md").write_text("Licenses.\n", encoding="utf-8")
    site_dir = tmp_path / "site"
    site_dir.mkdir()
    (site_dir / "llms.txt").write_text("as built\n", encoding="utf-8")

    copied = publish_canonical_files(load_library(library_root), site_dir)

    served = set(snapshot(site_dir))
    assert f"books/{MIRRORED}/chapters/01-folding-the-hull.md" in served
    assert f"books/{MIRRORED}/LICENSE" in served
    assert f"books/{REFERENCE}/metadata.yaml" in served
    assert {"AGENTS.md", "catalog.yaml", "topics/paper-craft.md"} <= served
    assert (site_dir / CHAPTER_PAGES[0]).read_bytes() == (
        library_root / CHAPTER_PAGES[0]
    ).read_bytes()
    # A file the build already wrote is left as built.
    assert read(site_dir, "llms.txt") == "as built\n"
    assert Path("llms.txt") not in copied
    # The source file of a mirrored book and anything else in a book directory stay out.
    assert not any("/source/" in name for name in served)
    assert {name for name in served if name.startswith(f"books/{REFERENCE}/")} == {
        f"books/{REFERENCE}/metadata.yaml"
    }


def test_no_built_page_takes_the_place_of_a_served_file_when_case_is_ignored(
    library_root: Path, staged: Path
) -> None:
    (library_root / "AGENTS.md").write_text("Instructions for agents.\n", encoding="utf-8")
    (library_root / "LICENSES.md").write_text("Licenses.\n", encoding="utf-8")
    # MkDocs builds the page ``a/b.md`` into the directory ``a/b``.
    page_directories = {
        name.removesuffix(".md").lower() for name in snapshot(staged) if name.endswith(".md")
    }
    served = {path.as_posix().lower() for path in bundle_files(load_library(library_root))}

    assert page_directories & served == set()
