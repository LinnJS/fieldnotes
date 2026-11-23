"""The export command writes a PDF, an EPUB, and a bundle that carry attribution and license."""

import dataclasses
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import uuid
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from xml.etree import ElementTree

import export
import pytest
import typst
from conftest import write_root_files
from kb import export as kb_export
from kb.catalog import Library, Resource, load_library
from kb.export import ExportError, checked_document, find_pandoc
from kb.export_document import Json
from pypdf import PdfReader

MIRRORED = "fixture-mirrored-book"
REFERENCE = "fixture-reference-book"
LIBRARY_NAME = "fixture-library"
EDITION = "v1.0.0"
TITLE = "Paper Boat Engineering (Test Fixture)"
AUTHOR_NAME = "Fixture Author"
AUTHOR_NATIVE_NAME = "夹具作者"
CHAPTER_TITLES = ["Folding the Hull", "Choosing a Pond", "Recovering a Sunk Boat"]
PINNED_COMMIT = "a" * 40
SOURCE_PATH = "Paper-Boat-Engineering-v1.0.0.pdf"
SOURCE_URL = (
    f"https://github.com/fixture-author/fixture-mirrored-book/blob/{PINNED_COMMIT}/{SOURCE_PATH}"
)
COPYRIGHT_LINE = "Copyright (c) 2026 Fixture Author (a test fixture, not a real rights holder)"
ERRATUM = "The invented second edition says the pond table lists depth in hands and not in spans."
ERRATUM_URL = "https://example.invalid/fixture-author/fixture-mirrored-book/errata"
CJK_FONT_FAMILIES = [
    "Songti SC",
    "PingFang SC",
    "Hiragino Sans GB",
    "Noto Serif CJK SC",
    "Noto Sans CJK SC",
]


BUNDLE_ENTRIES = [
    "MANIFEST.json",
    "AGENTS.md",
    "LICENSES.md",
    f"books/{MIRRORED}/LICENSE",
    f"books/{MIRRORED}/chapters/01-folding-the-hull.md",
    f"books/{MIRRORED}/chapters/02-choosing-a-pond.md",
    f"books/{MIRRORED}/chapters/03-recovering-a-sunk-boat.md",
    f"books/{MIRRORED}/metadata.yaml",
    f"books/{REFERENCE}/metadata.yaml",
    "catalog.yaml",
    "index/catalog.json",
    "index/chapters.jsonl",
    "index/topics.json",
    "llms.txt",
    "topics/paper-craft.md",
    "topics/tea-service.md",
]

DC = "{http://purl.org/dc/elements/1.1/}"
OPF = "{http://www.idpf.org/2007/opf}"
XHTML = "{http://www.w3.org/1999/xhtml}"
EPUB_TYPE = "{http://www.idpf.org/2007/ops}type"
CONTAINER = "{urn:oasis:names:tc:opendocument:xmlns:container}"


@dataclass(frozen=True)
class Exported:
    """A library whose every export was written by one run of the command."""

    root: Path
    out: Path

    @property
    def pdf(self) -> Path:
        return self.out / f"{MIRRORED}-{EDITION}.pdf"

    @property
    def epub(self) -> Path:
        return self.out / f"{MIRRORED}-{EDITION}.epub"

    @property
    def bundle(self) -> Path:
        return self.out / f"{LIBRARY_NAME}-bundle.zip"


def run_command(
    repo_root: Path, *arguments: str, path: Path | None = None
) -> subprocess.CompletedProcess[str]:
    """Run the export command, with ``path`` as the only directory on the PATH when given."""
    environment = dict(os.environ)
    if path is not None:
        environment["PATH"] = str(path)
    return subprocess.run(
        [sys.executable, str(repo_root / "scripts" / "export.py"), *arguments],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=environment,
        check=False,
    )


def give_the_reference_book_content(root: Path) -> None:
    """Put chapters, a license file, and a source file into the reference-only book.

    One chapter names the reference-only book in its frontmatter. The other still names the
    mirrored book, which must not get it into an export either.
    """
    chapter = (root / "books" / MIRRORED / "chapters" / "01-folding-the-hull.md").read_text(
        encoding="utf-8"
    )
    book = root / "books" / REFERENCE
    (book / "chapters").mkdir()
    (book / "chapters" / "01-folding-the-hull.md").write_text(
        chapter.replace(MIRRORED, REFERENCE), encoding="utf-8"
    )
    (book / "chapters" / "02-misfiled.md").write_text(
        chapter.replace("Folding the Hull", "Misfiled"), encoding="utf-8"
    )
    (book / "LICENSE").write_text("Invented terms.\n", encoding="utf-8")
    (book / "source").mkdir()
    (book / "source" / "book.pdf").write_bytes(b"%PDF-1.7\n")


def normalized(text: str) -> str:
    return " ".join(text.split())


def pdf_pages(path: Path) -> list[str]:
    return [normalized(page.extract_text()) for page in PdfReader(path).pages]


def package_path(archive: zipfile.ZipFile) -> PurePosixPath:
    container = ElementTree.fromstring(archive.read("META-INF/container.xml"))
    rootfile = container.find(f"{CONTAINER}rootfiles/{CONTAINER}rootfile")
    assert rootfile is not None
    return PurePosixPath(rootfile.attrib["full-path"])


def package(archive: zipfile.ZipFile) -> ElementTree.Element:
    return ElementTree.fromstring(archive.read(str(package_path(archive))))


def metadata_values(archive: zipfile.ZipFile, name: str) -> list[str]:
    return [element.text or "" for element in package(archive).iter(f"{DC}{name}")]


def navigation(archive: zipfile.ZipFile) -> list[tuple[str, str]]:
    """Return the label and target file of each top-level entry of the EPUB's contents list."""
    opf = package(archive)
    item = next(
        item for item in opf.iter(f"{OPF}item") if "nav" in item.attrib.get("properties", "")
    )
    directory = package_path(archive).parent
    document = ElementTree.fromstring(archive.read(str(directory / item.attrib["href"])))
    contents = next(
        nav for nav in document.iter(f"{XHTML}nav") if nav.attrib.get(EPUB_TYPE) == "toc"
    )
    entries: list[tuple[str, str]] = []
    for link in contents.findall(f"{XHTML}ol/{XHTML}li/{XHTML}a"):
        target = str(directory / link.attrib["href"].partition("#")[0])
        entries.append((normalized("".join(link.itertext())), target))
    return entries


def content_text(archive: zipfile.ZipFile, name: str) -> str:
    return normalized("".join(ElementTree.fromstring(archive.read(name)).itertext()))


def mirrored_book(root: Path) -> tuple[Library, Resource]:
    library = load_library(root)
    return library, library.resource(MIRRORED)


def words(tree: Json) -> str:
    """Return the text of a Pandoc tree, with one space for each space or line break."""
    if isinstance(tree, list):
        return "".join(words(value) for value in tree)
    if not isinstance(tree, dict):
        return ""
    if tree.get("t") == "Str":
        return str(tree["c"])
    if tree.get("t") in ("Space", "SoftBreak", "LineBreak"):
        return " "
    return "".join(words(value) for key, value in tree.items() if key != "t")


@pytest.fixture(scope="module")
def exported(
    repo_root: Path, fixture_library_root: Path, tmp_path_factory: pytest.TempPathFactory
) -> Exported:
    """Export everything from a library whose reference-only book has content on disk."""
    root = tmp_path_factory.mktemp("export") / "library"
    shutil.copytree(
        fixture_library_root, root, ignore=shutil.ignore_patterns("build", "dist", "index")
    )
    write_root_files(root)
    give_the_reference_book_content(root)

    result = run_command(repo_root, "--root", str(root))

    assert result.returncode == 0, result.stderr
    return Exported(root=root, out=root / "dist" / "exports")


def test_exporting_everything_writes_one_pdf_and_one_epub_per_mirrored_book_and_one_bundle(
    exported: Exported,
) -> None:
    assert sorted(path.name for path in exported.out.iterdir()) == [
        f"{LIBRARY_NAME}-bundle.zip",
        f"{MIRRORED}-{EDITION}.epub",
        f"{MIRRORED}-{EDITION}.pdf",
    ]


def test_pdf_opens_with_a_title_page(exported: Exported) -> None:
    title_page = pdf_pages(exported.pdf)[0]

    assert TITLE in title_page
    assert AUTHOR_NAME in title_page
    assert EDITION in title_page
    assert "unofficial copy" in title_page
    assert CHAPTER_TITLES[0] not in title_page
    assert "Permission is hereby granted" not in title_page


def test_pdf_text_holds_the_author_the_license_and_every_chapter_title_in_order(
    exported: Exported,
) -> None:
    text = " ".join(pdf_pages(exported.pdf))

    assert AUTHOR_NAME in text
    assert "MIT License" in text
    assert COPYRIGHT_LINE in text
    # The license text closes the notice section, and the chapters follow it. The first mention
    # of each title after that point is its chapter heading.
    chapters = text[text.index("OTHER DEALINGS IN THE") :]
    positions = [chapters.index(title) for title in CHAPTER_TITLES]
    assert positions == sorted(positions)


def test_pdf_text_holds_the_authors_name_in_its_native_script(exported: Exported) -> None:
    assert AUTHOR_NATIVE_NAME in " ".join(pdf_pages(exported.pdf))


def test_pdf_shows_each_erratum_with_its_source(exported: Exported) -> None:
    text = " ".join(pdf_pages(exported.pdf))

    assert ERRATUM in text
    assert ERRATUM_URL in text


def test_pdf_numbers_every_page_after_the_title_page(exported: Exported) -> None:
    pages = pdf_pages(exported.pdf)

    assert len(pages) > 3
    assert [page.split()[-1] for page in pages[1:]] == [
        str(number) for number in range(2, len(pages) + 1)
    ]


def test_pdf_metadata_names_the_title_and_author_and_carries_no_creation_date(
    exported: Exported,
) -> None:
    metadata = PdfReader(exported.pdf).metadata

    assert metadata is not None
    assert metadata.title == TITLE
    assert metadata.author == f"{AUTHOR_NAME} ({AUTHOR_NATIVE_NAME})"
    assert "/CreationDate" not in metadata


def test_epub_is_a_valid_zip_whose_first_entry_is_an_uncompressed_mimetype(
    exported: Exported,
) -> None:
    with zipfile.ZipFile(exported.epub) as archive:
        first = archive.infolist()[0]

        assert archive.testzip() is None
        assert first.filename == "mimetype"
        assert first.compress_type == zipfile.ZIP_STORED
        assert archive.read(first) == b"application/epub+zip"


def test_epub_package_carries_the_title_author_language_rights_source_and_identifier(
    exported: Exported,
) -> None:
    identifier = uuid.uuid5(uuid.NAMESPACE_URL, f"{LIBRARY_NAME}/{MIRRORED}/{EDITION}")

    with zipfile.ZipFile(exported.epub) as archive:
        assert metadata_values(archive, "title")[0] == TITLE
        assert metadata_values(archive, "creator") == [f"{AUTHOR_NAME} ({AUTHOR_NATIVE_NAME})"]
        assert metadata_values(archive, "language") == ["en"]
        assert metadata_values(archive, "rights") == [f"MIT license. {COPYRIGHT_LINE}"]
        assert metadata_values(archive, "source") == [SOURCE_URL]
        assert metadata_values(archive, "identifier") == [f"urn:uuid:{identifier}"]


def test_epub_navigation_lists_the_notice_and_every_chapter_in_order_one_file_each(
    exported: Exported,
) -> None:
    with zipfile.ZipFile(exported.epub) as archive:
        entries = navigation(archive)

    assert [label for label, _ in entries] == [
        "About this copy",
        "1 Folding the Hull",
        "2 Choosing a Pond",
        "3 Recovering a Sunk Boat",
    ]
    assert len({target for _, target in entries}) == 4


def test_epub_notice_holds_the_attribution_and_the_full_license_text(exported: Exported) -> None:
    license_text = (exported.root / "books" / MIRRORED / "LICENSE").read_text(encoding="utf-8")

    with zipfile.ZipFile(exported.epub) as archive:
        notice_file = navigation(archive)[0][1]
        notice = content_text(archive, notice_file)
        code_blocks = [
            "".join(block.itertext())
            for block in ElementTree.fromstring(archive.read(notice_file)).iter(f"{XHTML}pre")
        ]

    assert "unofficial copy" in notice
    assert "Fixture Library" in notice
    assert "has not endorsed" in notice
    assert f"{AUTHOR_NAME} ({AUTHOR_NATIVE_NAME})" in notice
    assert f"{EDITION}, language en" in notice
    assert PINNED_COMMIT in notice
    assert SOURCE_PATH in notice
    assert "https://example.invalid/books/paper-boat" in notice
    assert "https://example.invalid/fixture-author/fixture-mirrored-book" in notice
    assert "https://example.invalid/reader/paper-boat" in notice
    assert "2 of 3 chapters are machine-extracted" in notice
    assert "Test fixture. This book and its text are invented for automated tests." in notice
    assert [block.strip() for block in code_blocks] == [license_text.strip()]


def test_epub_notice_says_that_another_language_has_a_newer_edition(exported: Exported) -> None:
    with zipfile.ZipFile(exported.epub) as archive:
        notice = content_text(archive, navigation(archive)[0][1])

    assert "The zh edition v1.1.0 is newer than this copy" in notice


def test_the_notice_names_a_newer_edition_in_the_language_of_this_copy(
    library_copy: Path,
) -> None:
    metadata = library_copy / "books" / MIRRORED / "metadata.yaml"
    text = metadata.read_text(encoding="utf-8")
    assert "newest_editions:\n  en: v1.0.0\n" in text
    metadata.write_text(
        text.replace("newest_editions:\n  en: v1.0.0\n", "newest_editions:\n  en: v1.2.0\n"),
        encoding="utf-8",
    )
    library, resource = mirrored_book(library_copy)

    notice = words(checked_document(library, resource, find_pandoc())["blocks"])

    assert "The en edition v1.2.0 is newer than this copy" in notice
    assert "The zh edition v1.1.0 is newer than this copy" in notice


def test_epub_shows_an_erratum_and_the_extraction_status_under_the_chapter_title(
    exported: Exported,
) -> None:
    with zipfile.ZipFile(exported.epub) as archive:
        _, first, second, third = (
            content_text(archive, target) for _, target in navigation(archive)
        )

    assert f"Erratum. {ERRATUM} Source: {ERRATUM_URL}" in second
    assert second.index("Choosing a Pond") < second.index("Erratum.") < second.index("The pond")
    assert "Erratum." not in first
    assert "Part One: Paper" in first
    assert "Part Two: Water" in third
    assert "Machine-extracted." in first
    assert "Machine-extracted." not in third


def test_epub_link_between_chapters_points_into_the_book(exported: Exported) -> None:
    with zipfile.ZipFile(exported.epub) as archive:
        entries = navigation(archive)
        third = ElementTree.fromstring(archive.read(entries[3][1]))

    links = [
        link.attrib["href"]
        for link in third.iter(f"{XHTML}a")
        if "".join(link.itertext()) == "Folding the Hull"
    ]
    assert len(links) == 1
    assert links[0].partition("#")[0] == PurePosixPath(entries[1][1]).name


def test_bundle_holds_exactly_the_library_files_and_only_metadata_for_other_books(
    exported: Exported,
) -> None:
    with zipfile.ZipFile(exported.bundle) as archive:
        assert archive.namelist() == BUNDLE_ENTRIES


def test_bundle_manifest_lists_every_file_with_its_digest_and_size(exported: Exported) -> None:
    with zipfile.ZipFile(exported.bundle) as archive:
        manifest = json.loads(archive.read("MANIFEST.json"))
        contents = {name: archive.read(name) for name in archive.namelist()[1:]}

    assert list(manifest) == ["files"]
    assert [entry["path"] for entry in manifest["files"]] == BUNDLE_ENTRIES[1:]
    for entry in manifest["files"]:
        data = (exported.root / entry["path"]).read_bytes()
        assert contents[entry["path"]] == data
        assert entry == {
            "path": entry["path"],
            "sha256": hashlib.sha256(data).hexdigest(),
            "size": len(data),
        }


def test_bundle_is_byte_identical_when_built_again(
    repo_root: Path, exported: Exported, tmp_path: Path
) -> None:
    result = run_command(
        repo_root, "--root", str(exported.root), "--format", "bundle", "--out", str(tmp_path)
    )

    assert result.returncode == 0, result.stderr
    again = tmp_path / exported.bundle.name
    assert again.read_bytes() == exported.bundle.read_bytes()
    with zipfile.ZipFile(again) as archive:
        assert {entry.date_time for entry in archive.infolist()} == {(1980, 1, 1, 0, 0, 0)}


def test_bundle_names_a_missing_hand_written_file(repo_root: Path, library_copy: Path) -> None:
    write_root_files(library_copy)
    (library_copy / "AGENTS.md").unlink()

    result = run_command(repo_root, "--root", str(library_copy), "--format", "bundle")

    assert result.returncode == 1
    assert "AGENTS.md" in result.stderr
    assert not (library_copy / "dist").exists()


def test_bundle_names_a_missing_index_file_and_the_command_that_writes_it(
    repo_root: Path, library_copy: Path
) -> None:
    write_root_files(library_copy)
    (library_copy / "index" / "chapters.jsonl").unlink()
    (library_copy / "llms.txt").unlink()

    result = run_command(repo_root, "--root", str(library_copy), "--format", "bundle")

    assert result.returncode == 1
    assert "index/chapters.jsonl" in result.stderr
    assert "llms.txt" in result.stderr
    assert "uv run python scripts/build.py" in result.stderr
    assert not (library_copy / "dist").exists()


def test_one_book_in_one_format_goes_to_the_chosen_directory(
    repo_root: Path, library_copy: Path, tmp_path: Path
) -> None:
    out = tmp_path / "chosen"

    result = run_command(
        repo_root,
        "--root",
        str(library_copy),
        "--book",
        MIRRORED,
        "--format",
        "epub",
        "--out",
        str(out),
    )

    assert result.returncode == 0, result.stderr
    assert [path.name for path in out.iterdir()] == [f"{MIRRORED}-{EDITION}.epub"]
    assert not (library_copy / "dist").exists()


def test_translator_is_credited_in_the_package_and_the_notice(
    repo_root: Path, library_copy: Path, tmp_path: Path
) -> None:
    metadata = library_copy / "books" / MIRRORED / "metadata.yaml"
    metadata.write_text(
        metadata.read_text(encoding="utf-8").replace(
            "translator: null",
            "translator:\n  name: Fixture Translator\n  native_name: null\n  url: null",
        ),
        encoding="utf-8",
    )

    result = run_command(
        repo_root, "--root", str(library_copy), "--format", "epub", "--out", str(tmp_path)
    )

    assert result.returncode == 0, result.stderr
    with zipfile.ZipFile(tmp_path / f"{MIRRORED}-{EDITION}.epub") as archive:
        assert metadata_values(archive, "contributor") == ["Fixture Translator"]
        assert "Translator: Fixture Translator" in content_text(archive, navigation(archive)[0][1])


def test_reference_only_book_is_refused_with_the_gate_reason(
    repo_root: Path, fixture_library_root: Path, tmp_path: Path
) -> None:
    result = run_command(
        repo_root,
        "--root",
        str(fixture_library_root),
        "--book",
        REFERENCE,
        "--out",
        str(tmp_path / "out"),
    )

    assert result.returncode == 1
    assert REFERENCE in result.stderr
    assert "No license terms were found at any location checked." in result.stderr
    assert not (tmp_path / "out").exists()


def test_book_recorded_as_mirrored_is_refused_when_the_gate_rejects_its_record(
    repo_root: Path, library_copy: Path
) -> None:
    metadata = library_copy / "books" / MIRRORED / "metadata.yaml"
    metadata.write_text(
        metadata.read_text(encoding="utf-8").replace(
            "redistribution: allowed", "redistribution: unclear"
        ),
        encoding="utf-8",
    )

    result = run_command(repo_root, "--root", str(library_copy), "--book", MIRRORED)

    assert result.returncode == 1
    assert "The license gate does not allow" in result.stderr
    assert "redistribution is unclear" in result.stderr
    assert not (library_copy / "dist").exists()


def test_eligible_book_is_refused_as_not_yet_mirrored(repo_root: Path, library_copy: Path) -> None:
    metadata = library_copy / "books" / MIRRORED / "metadata.yaml"
    metadata.write_text(
        metadata.read_text(encoding="utf-8").replace(
            "mirror_status: mirrored", "mirror_status: eligible"
        ),
        encoding="utf-8",
    )

    result = run_command(repo_root, "--root", str(library_copy), "--book", MIRRORED)

    assert result.returncode == 1
    assert "eligible" in result.stderr
    assert "not yet mirrored" in result.stderr
    assert not (library_copy / "dist").exists()


def test_unknown_book_id_is_refused_with_the_nearest_ids(
    repo_root: Path, fixture_library_root: Path, tmp_path: Path
) -> None:
    result = run_command(
        repo_root,
        "--root",
        str(fixture_library_root),
        "--book",
        "fixture-mirored-book",
        "--out",
        str(tmp_path / "out"),
    )

    assert result.returncode == 1
    assert "fixture-mirored-book" in result.stderr
    assert MIRRORED in result.stderr
    assert not (tmp_path / "out").exists()


def test_unknown_format_is_refused_with_the_valid_values(
    repo_root: Path, fixture_library_root: Path
) -> None:
    result = run_command(repo_root, "--root", str(fixture_library_root), "--format", "docx")

    assert result.returncode != 0
    assert "docx" in result.stderr
    for value in ("pdf", "epub", "bundle", "all"):
        assert value in result.stderr


def test_missing_pandoc_is_reported_with_the_install_command(
    repo_root: Path, library_copy: Path, tmp_path: Path
) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()

    result = run_command(
        repo_root, "--root", str(library_copy), "--book", MIRRORED, "--format", "pdf", path=empty
    )

    assert result.returncode == 1
    assert "brew install pandoc" in result.stderr
    assert "https://github.com/jgm/pandoc/releases" in result.stderr
    assert "Traceback" not in result.stderr
    assert not (library_copy / "dist").exists()


def test_old_pandoc_is_reported_with_the_found_and_the_required_version(
    repo_root: Path, library_copy: Path, tmp_path: Path
) -> None:
    old = tmp_path / "old"
    old.mkdir()
    (old / "pandoc").write_text("#!/bin/sh\necho 'pandoc 2.19.2'\n", encoding="utf-8")
    (old / "pandoc").chmod(0o755)

    result = run_command(
        repo_root, "--root", str(library_copy), "--book", MIRRORED, "--format", "epub", path=old
    )

    assert result.returncode == 1
    assert "2.19.2" in result.stderr
    assert "3.14" in result.stderr
    assert not (library_copy / "dist").exists()


class OnlyBundledFonts:
    """Stands in for the font search on a machine that has no CJK font installed."""

    def families(self) -> list[str]:
        return ["DejaVu Sans Mono", "Libertinus Serif", "New Computer Modern"]


def test_pdf_build_succeeds_with_a_warning_when_no_cjk_font_is_installed(
    library_copy: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(typst, "Fonts", OnlyBundledFonts)

    code = export.main(["--root", str(library_copy), "--book", MIRRORED, "--format", "pdf"])

    assert code == 0
    assert (library_copy / "dist" / "exports" / f"{MIRRORED}-{EDITION}.pdf").is_file()
    warning = capsys.readouterr().err
    assert "warning" in warning
    for family in CJK_FONT_FAMILIES:
        assert family in warning


# A link to a script address, written in three ways a renderer reads as a live link.
SCRIPT_LINKS = (
    "\n## Hostile links\n\n"
    "A [script link](javascript\\:alert(1)) here.\n\n"
    "A [brace link](https://h/\\(c){onmouseover=x}d) here.\n\n"
    "- [x]: javascript:alert(1)\n\n"
    "> [y]: javascript:alert(2)\n\n"
    "Then [x] and [y].\n"
)


def append_to_chapter(root: Path, text: str, name: str = "01-folding-the-hull.md") -> None:
    with (root / "books" / MIRRORED / "chapters" / name).open("a", encoding="utf-8") as file:
        file.write(text)


def epub_markup(epub: Path) -> list[tuple[str, str, str]]:
    """Return the tag, attribute name, and value of every attribute in the EPUB's XHTML files."""
    found: list[tuple[str, str, str]] = []
    with zipfile.ZipFile(epub) as archive:
        for name in archive.namelist():
            if name.endswith(".xhtml"):
                for element in ElementTree.fromstring(archive.read(name)).iter():
                    found.extend((element.tag, key, value) for key, value in element.attrib.items())
    return found


def epub_text(epub: Path) -> str:
    with zipfile.ZipFile(epub) as archive:
        return " ".join(
            content_text(archive, name) for name in archive.namelist() if name.endswith(".xhtml")
        )


def export_epub(repo_root: Path, root: Path, out: Path) -> Path:
    result = run_command(repo_root, "--root", str(root), "--format", "epub", "--out", str(out))
    assert result.returncode == 0, result.stderr
    return out / f"{MIRRORED}-{EDITION}.epub"


def test_a_chapter_cannot_put_a_script_address_or_an_event_attribute_in_the_epub(
    repo_root: Path, library_copy: Path, tmp_path: Path
) -> None:
    append_to_chapter(library_copy, SCRIPT_LINKS)

    epub = export_epub(repo_root, library_copy, tmp_path)

    markup = epub_markup(epub)
    events = [found for found in markup if found[1].lower().startswith("on")]
    addresses = [
        found
        for found in markup
        if found[1] in ("href", "src") and "javascript" in found[2].lower()
    ]
    assert events == []
    assert addresses == []
    assert "{onmouseover=x}d) here." in epub_text(epub)


def test_a_chapter_cannot_set_attributes_or_markup_in_an_export(library_copy: Path) -> None:
    append_to_chapter(
        library_copy,
        '\n## Config { onclick="alert(1)" }\n\n'
        'A [link](https://example.invalid/a){ onclick="x" } and `code`{ onclick="y" }.\n\n'
        "<script>alert(1)</script>\n\n"
        # A fence that never closes is a code block to the end of its chapter.
        "~~~ {.c onmouseover=x}\n",
    )
    library, resource = mirrored_book(library_copy)

    document = checked_document(library, resource, find_pandoc())
    built = subprocess.run(
        [str(find_pandoc()), "--from=json", "--to=html"],
        input=json.dumps(document),
        capture_output=True,
        text=True,
        check=True,
    ).stdout

    assert re.search(r"<[^<>]*\son(?:click|mouseover)=", built) is None
    assert "<script" not in built
    assert 'Config { onclick="alert(1)" }</h2>' in built
    assert '</a>{ onclick="x" } and <code>code</code>{ onclick="y" }.' in normalized(built)
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in built
    assert '<pre><code></code></pre>\n<h1 id="chapter-02-choosing-a-pond">' in built


def test_a_yaml_block_in_a_chapter_changes_no_metadata(
    repo_root: Path, library_copy: Path, tmp_path: Path
) -> None:
    chapter = library_copy / "books" / MIRRORED / "chapters" / "01-folding-the-hull.md"
    title = "# Folding the Hull\n"
    chapter.write_text(
        chapter.read_text(encoding="utf-8").replace(
            title, f"{title}\n---\ntitle: Hijacked\ndescription: Hijacked\n---\n"
        ),
        encoding="utf-8",
    )
    library, resource = mirrored_book(library_copy)

    document = checked_document(library, resource, find_pandoc())
    epub = export_epub(repo_root, library_copy, tmp_path)

    assert "Hijacked" not in words(document["meta"])
    with zipfile.ZipFile(epub) as archive:
        assert b"Hijacked" not in archive.read(str(package_path(archive)))
        assert metadata_values(archive, "title")[0] == TITLE


def test_an_image_in_a_chapter_becomes_its_text_and_its_file_is_never_read(
    repo_root: Path, library_copy: Path, tmp_path: Path
) -> None:
    secret = tmp_path / "secret.png"
    secret.write_bytes(b"\x89PNG secret bytes")
    append_to_chapter(library_copy, f"\nSee ![the secret picture]({secret}) here.\n")

    epub = export_epub(repo_root, library_copy, tmp_path / "out")

    assert "See the secret picture here." in epub_text(epub)
    with zipfile.ZipFile(epub) as archive:
        media = [
            item.attrib["media-type"]
            for item in package(archive).iter(f"{OPF}item")
            if not item.attrib["media-type"].startswith(("application/", "text/"))
        ]
        assert media == []
        assert all(b"secret bytes" not in archive.read(name) for name in archive.namelist())


def test_two_chapters_with_the_same_heading_get_different_ids_and_both_stay_in_the_navigation(
    repo_root: Path, library_copy: Path, tmp_path: Path
) -> None:
    append_to_chapter(library_copy, "\n## Shared heading\n\nFirst.\n")
    append_to_chapter(
        library_copy, "\n## Shared heading\n\nThird.\n", "03-recovering-a-sunk-boat.md"
    )
    library, resource = mirrored_book(library_copy)

    headings = [
        block["c"][1][0]
        for block in checked_document(library, resource, find_pandoc())["blocks"]
        if block["t"] == "Header" and words(block["c"][2]) == "Shared heading"
    ]
    epub = export_epub(repo_root, library_copy, tmp_path)

    assert headings == ["shared-heading", "shared-heading-1"]
    with zipfile.ZipFile(epub) as archive:
        opf = package(archive)
        item = next(
            item for item in opf.iter(f"{OPF}item") if "nav" in item.attrib.get("properties", "")
        )
        nav = ElementTree.fromstring(
            archive.read(str(package_path(archive).parent / item.attrib["href"]))
        )
    targets = [
        link.attrib["href"]
        for link in nav.iter(f"{XHTML}a")
        if "Shared heading" in "".join(link.itertext())
    ]
    assert [target.partition("#")[2] for target in targets] == headings


# A record URL that closes the link the library writes around it and opens a script element.
# The schema accepts it, because it starts with https:// and holds no white space.
HOSTILE_URL = "https://example.invalid/x><script>alert(1)</script>"
HOSTILE_URL_PERCENT = "https://example.invalid/x%3E%3Cscript%3Ealert%281%29%3C/script%3E"

# Where each record URL of the notice sits in the fixture record.
RECORD_URL_LINES = {
    "person": "  url: https://example.invalid/fixture-author\n",
    "official site": "  site: https://example.invalid/books/paper-boat\n",
    "official repository": "  repository: https://example.invalid/fixture-author/fixture-mirrored-book\n",
    "hosted edition": "      url: https://example.invalid/reader/paper-boat\n",
}


def epub_elements(epub: Path) -> list[str]:
    """Return the tag of every element in the EPUB's XHTML files."""
    with zipfile.ZipFile(epub) as archive:
        return [
            element.tag
            for name in archive.namelist()
            if name.endswith(".xhtml")
            for element in ElementTree.fromstring(archive.read(name)).iter()
        ]


def notice_addresses(epub: Path) -> list[str]:
    """Return the address of every link in the notice section, in order."""
    with zipfile.ZipFile(epub) as archive:
        notice = ElementTree.fromstring(archive.read(navigation(archive)[0][1]))
    return [link.attrib["href"] for link in notice.iter(f"{XHTML}a")]


@pytest.mark.parametrize("field", list(RECORD_URL_LINES))
def test_a_record_url_with_markup_reaches_the_epub_as_its_percent_form(
    repo_root: Path, library_copy: Path, tmp_path: Path, field: str
) -> None:
    metadata = library_copy / "books" / MIRRORED / "metadata.yaml"
    text = metadata.read_text(encoding="utf-8")
    line = RECORD_URL_LINES[field]
    assert text.count(line) == 1
    key = line.split(":")[0]
    metadata.write_text(text.replace(line, f"{key}: '{HOSTILE_URL}'\n"), encoding="utf-8")

    epub = export_epub(repo_root, library_copy, tmp_path)

    assert not [tag for tag in epub_elements(epub) if tag.endswith("script")]
    assert HOSTILE_URL_PERCENT in notice_addresses(epub)
    with zipfile.ZipFile(epub) as archive:
        assert all(b"<script" not in archive.read(name) for name in archive.namelist())


def test_an_ordinary_record_url_is_written_unchanged(exported: Exported) -> None:
    assert notice_addresses(exported.epub) == [
        "https://example.invalid/fixture-author",
        SOURCE_URL,
        "https://example.invalid/books/paper-boat",
        "https://example.invalid/fixture-author/fixture-mirrored-book",
        "https://example.invalid/reader/paper-boat",
    ]


def test_a_record_url_with_a_script_scheme_stops_the_export(library_copy: Path) -> None:
    library, resource = mirrored_book(library_copy)
    # The schema refuses this URL when the record is loaded, so the test puts it in afterwards.
    author = dataclasses.replace(resource.author, url="javascript:alert(1)")

    with pytest.raises(ExportError) as raised:
        checked_document(library, dataclasses.replace(resource, author=author), find_pandoc())

    assert "A link goes to 'javascript:alert" in raised.value.message
    assert "which is not an address of http, https, mailto" in raised.value.message
    assert "report" in raised.value.fix


def test_a_notice_with_an_attribute_block_after_a_link_stops_the_export(
    library_copy: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The escape of record text is switched off, so only the check of the document stands
    # between the attribute block and the writers.
    monkeypatch.setattr(kb_export, "_plain", lambda text: text)
    metadata = library_copy / "books" / MIRRORED / "metadata.yaml"
    metadata.write_text(
        metadata.read_text(encoding="utf-8").replace(
            "  - Test fixture. This book and its text are invented for automated tests.\n",
            "  - 'See [the site](https://example.invalid/a){onclick=\"alert(1)\"} now.'\n",
        ),
        encoding="utf-8",
    )
    library, resource = mirrored_book(library_copy)

    with pytest.raises(ExportError) as raised:
        checked_document(library, resource, find_pandoc())

    assert "key and value attributes" in raised.value.message
    assert "onclick" in raised.value.message


def test_a_node_type_the_check_does_not_know_stops_the_export(
    library_copy: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Footnotes are off in the chapter reader. With them on, a chapter parses to a note, which
    # the pass does not know.
    monkeypatch.setattr(kb_export, "CHAPTER_FORMAT", "gfm")
    append_to_chapter(library_copy, "\nA mark[^1].\n\n[^1]: The note.\n")
    library, resource = mirrored_book(library_copy)

    with pytest.raises(ExportError) as raised:
        checked_document(library, resource, find_pandoc())

    assert "Note" in raised.value.message
    assert "Pandoc 3." in raised.value.message
    assert "report" in raised.value.fix


def test_a_notice_with_colons_and_a_bare_address_exports_as_its_text(library_copy: Path) -> None:
    metadata = library_copy / "books" / MIRRORED / "metadata.yaml"
    metadata.write_text(
        metadata.read_text(encoding="utf-8").replace(
            "  - Test fixture. This book and its text are invented for automated tests.\n",
            "  - 'Options a:b:c and ok:ok: values, see ftp://example.invalid/x now.'\n",
        ),
        encoding="utf-8",
    )
    library, resource = mirrored_book(library_copy)

    document = checked_document(library, resource, find_pandoc())

    assert "Options a:b:c and ok:ok: values, see ftp://example.invalid/x now." in words(document)
