"""The read-back check of a written EPUB and PDF, and its place after each writer."""

import shutil
import zipfile
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

import pytest
from kb import export as kb_export
from kb.catalog import Library, Resource, load_library
from kb.export import (
    ExportError,
    checked_document,
    find_pandoc,
    pdf_outline,
    write_epub,
    write_pdf,
)
from kb.export_check import OutputProblem, ProblemKind, epub_problems, pdf_problems
from kb.export_document import ChapterBlocks, CleanBook, CleanChapter, Json
from pypdf import PdfReader, PdfWriter
from pypdf.generic import (
    ArrayObject,
    Destination,
    DictionaryObject,
    FloatObject,
    NameObject,
    NumberObject,
    PdfObject,
    TextStringObject,
)

MIRRORED = "fixture-mirrored-book"
XHTML = "{http://www.w3.org/1999/xhtml}"
CHAPTER = "EPUB/text/ch002.xhtml"
NOTICE = "EPUB/text/ch001.xhtml"
PACKAGE = "EPUB/content.opf"

# The three inputs of the chapter route: a script address in an inline link, a brace block after
# a link, and reference definitions inside a list item and a block quote.
SCRIPT_LINKS = (
    "\n## Hostile links\n\n"
    "A [script link](javascript\\:alert(1)) here.\n\n"
    "A [brace link](https://h/\\(c){onmouseover=x}d) here.\n\n"
    "- [x]: javascript:alert(1)\n\n"
    "> [y]: javascript:alert(2)\n\n"
    "Then [x] and [y].\n"
)


# Text that would start a line of the Typst source in the middle of a paragraph: a raw block
# that spans lines, and prose that holds a line separator.
LINE_STARTS = {
    "raw block": "\n<div>\n= Injected heading\n- injected item\n</div>\n",
    "line separator": "\nFirst line\u2028= Injected heading and more.\n",
}


@dataclass(frozen=True)
class Written:
    """The EPUB and the PDF the export wrote for the fixture library."""

    epub: Path
    pdf: Path
    outline: list[str]


def copy_library(source: Path, target: Path, added: str = "") -> tuple[Library, Resource]:
    """Copy the fixture library, add text to its first chapter, and load the copy."""
    shutil.copytree(source, target, ignore=shutil.ignore_patterns("build", "dist"))
    chapter = target / "books" / MIRRORED / "chapters" / "01-folding-the-hull.md"
    chapter.write_text(chapter.read_text(encoding="utf-8") + added, encoding="utf-8")
    library = load_library(target)
    return library, library.resource(MIRRORED)


@pytest.fixture(scope="module")
def written(fixture_library_root: Path, tmp_path_factory: pytest.TempPathFactory) -> Written:
    directory = tmp_path_factory.mktemp("written")
    library, resource = copy_library(fixture_library_root, directory / "library")
    pandoc = find_pandoc()
    return Written(
        epub=write_epub(library, resource, directory / "out", pandoc),
        pdf=write_pdf(library, resource, directory / "out", pandoc),
        outline=library_outline(library, resource),
    )


def outline_titles(pdf: Path) -> list[str]:
    """Return the titles of a PDF's outline, in reading order."""
    titles: list[str] = []
    pending: list[object] = list(reversed(PdfReader(pdf).outline))
    while pending:
        item = pending.pop()
        if isinstance(item, list):
            pending += reversed(item)
        else:
            assert isinstance(item, Destination)
            titles.append(str(item.title))
    return titles


def library_outline(library: Library, resource: Resource) -> list[str]:
    """Return the outline the export computes for a book's PDF."""
    return pdf_outline(checked_document(library, resource, find_pandoc()))


def has(problems: list[OutputProblem], kind: ProblemKind, *parts: str) -> bool:
    """Say whether one problem of the kind names every part."""
    return any(
        problem.kind is kind and all(part in problem.detail for part in parts)
        for problem in problems
    )


def changed_epub(
    epub: Path, target: Path, replace: dict[str, tuple[bytes, bytes]], add: dict[str, bytes]
) -> Path:
    """Copy an EPUB with one replacement in some members and some members added."""
    with zipfile.ZipFile(epub) as source, zipfile.ZipFile(target, "w") as copy:
        for name in source.namelist():
            data = source.read(name)
            if name in replace:
                old, new = replace[name]
                assert old in data
                data = data.replace(old, new, 1)
            copy.writestr(name, data)
        for name, data in add.items():
            copy.writestr(name, data)
    return target


def test_the_export_of_the_fixture_library_passes_both_checks(written: Written) -> None:
    assert epub_problems(written.epub) == []
    assert pdf_problems(written.pdf, outline=written.outline) == []


def test_an_epub_member_the_export_does_not_write_is_a_problem(
    written: Written, tmp_path: Path
) -> None:
    epub = changed_epub(written.epub, tmp_path / "a.epub", {}, {"EPUB/text/evil.js": b"alert(1)"})

    assert has(epub_problems(epub), ProblemKind.MEMBER, "EPUB/text/evil.js")


def test_a_script_element_in_a_page_is_a_problem(written: Written, tmp_path: Path) -> None:
    epub = changed_epub(
        written.epub,
        tmp_path / "a.epub",
        {CHAPTER: (b"</body>", b"<script>alert(1)</script></body>")},
        {},
    )

    assert has(epub_problems(epub), ProblemKind.ELEMENT, CHAPTER, f"{XHTML}script")


def test_an_event_attribute_is_a_problem(written: Written, tmp_path: Path) -> None:
    epub = changed_epub(
        written.epub, tmp_path / "a.epub", {CHAPTER: (b"<p>", b'<p onclick="alert(1)">')}, {}
    )

    assert has(epub_problems(epub), ProblemKind.ATTRIBUTE, CHAPTER, "onclick", f"{XHTML}p")


@pytest.mark.parametrize(
    ("address", "shown"),
    [(b"javascript:alert(1)", "javascript:alert(1)"), (b"java&#9;script:x", "java\\tscript:x")],
)
def test_a_script_address_is_a_problem(
    written: Written, tmp_path: Path, address: bytes, shown: str
) -> None:
    epub = changed_epub(
        written.epub,
        tmp_path / "a.epub",
        {NOTICE: (b'href="https://example.invalid/books/paper-boat"', b'href="' + address + b'"')},
        {},
    )

    assert has(epub_problems(epub), ProblemKind.ADDRESS, NOTICE, shown)


def test_a_relative_address_outside_the_book_is_a_problem(written: Written, tmp_path: Path) -> None:
    epub = changed_epub(
        written.epub,
        tmp_path / "a.epub",
        {CHAPTER: (b'href="../styles/stylesheet1.css"', b'href="../../secret.css"')},
        {},
    )

    assert has(epub_problems(epub), ProblemKind.ADDRESS, CHAPTER, "../../secret.css")


@pytest.mark.parametrize(
    ("item", "shown"),
    [
        (b'<item id="cover" href="text/ch002.xhtml" media-type="image/png" />', "image/png"),
        (
            b'<item id="run" href="text/ch002.xhtml" media-type="application/javascript" />',
            "application/javascript",
        ),
    ],
)
def test_a_manifest_item_of_another_media_type_is_a_problem(
    written: Written, tmp_path: Path, item: bytes, shown: str
) -> None:
    epub = changed_epub(
        written.epub, tmp_path / "a.epub", {PACKAGE: (b"</manifest>", item + b"</manifest>")}, {}
    )

    assert has(epub_problems(epub), ProblemKind.MANIFEST, PACKAGE, shown)


def test_a_manifest_item_with_another_property_is_a_problem(
    written: Written, tmp_path: Path
) -> None:
    epub = changed_epub(
        written.epub,
        tmp_path / "a.epub",
        {PACKAGE: (b'properties="nav"', b'properties="nav scripted"')},
        {},
    )

    assert has(epub_problems(epub), ProblemKind.MANIFEST, PACKAGE, "scripted")


@pytest.mark.parametrize(
    ("member", "old", "new", "shown"),
    [
        (
            "EPUB/text/ch003.xhtml",
            b"<td>",
            b'<td style="background: url(https://h/x)">',
            "background: url(https://h/x)",
        ),
        ("EPUB/nav.xhtml", b'<ol class="toc">', b'<ol class="toc" type="disc">', "'disc'"),
        (
            "EPUB/text/ch003.xhtml",
            b'<pre class="text">',
            b'<pre class="sourceCode text">',
            "'sourceCode text'",
        ),
    ],
    ids=["cell style other than an alignment", "list type", "code class of two words"],
)
def test_an_attribute_value_the_writer_does_not_write_is_a_problem(
    written: Written, tmp_path: Path, member: str, old: bytes, new: bytes, shown: str
) -> None:
    epub = changed_epub(written.epub, tmp_path / "a.epub", {member: (old, new)}, {})

    assert has(epub_problems(epub), ProblemKind.ATTRIBUTE, member, shown)


# One chapter with every Markdown feature of a chapter that the document check admits and the
# real book does not use.
ADMITTED_FEATURES = (
    "\nBefore.\n\n---\n\nAfter.\n"
    "\nOne line  \nnext line.\n"
    "\n### A small heading\n\nText.\n"
    "\n3. three\n4. four\n"
    "\n| a | b | c |\n|:--|--:|:-:|\n| 1 | 2 | 3 |\n"
    "\n```python\nprint(1)\n```\n"
)


def test_a_chapter_with_every_admitted_feature_exports_and_passes_both_checks(
    fixture_library_root: Path, tmp_path: Path
) -> None:
    library, resource = copy_library(fixture_library_root, tmp_path / "library", ADMITTED_FEATURES)
    pandoc = find_pandoc()

    epub = write_epub(library, resource, tmp_path / "out", pandoc)
    pdf = write_pdf(library, resource, tmp_path / "out", pandoc)

    assert epub_problems(epub) == []
    assert pdf_problems(pdf, outline=library_outline(library, resource)) == []
    with zipfile.ZipFile(epub) as archive:
        page = archive.read("EPUB/text/ch002.xhtml").decode()
    for markup in (
        "<hr />",
        "<br />",
        '<h3 data-number="1.2.1">',
        '<ol start="3" type="1">',
        '<td style="text-align: right;">',
        '<pre class="python"><code>print(1)</code></pre>',
    ):
        assert markup in page


def test_a_member_that_is_not_well_formed_is_a_problem(written: Written, tmp_path: Path) -> None:
    epub = changed_epub(written.epub, tmp_path / "a.epub", {CHAPTER: (b"</body>", b"</bdy>")}, {})

    assert has(epub_problems(epub), ProblemKind.MARKUP, CHAPTER, "not well-formed")


def test_a_processing_instruction_is_a_problem(written: Written, tmp_path: Path) -> None:
    epub = changed_epub(
        written.epub,
        tmp_path / "a.epub",
        {CHAPTER: (b"<!DOCTYPE html>", b'<?xml-stylesheet href="x.xsl"?><!DOCTYPE html>')},
        {},
    )

    assert has(epub_problems(epub), ProblemKind.MARKUP, CHAPTER, "xml-stylesheet")


def test_text_inside_a_style_element_is_a_problem(written: Written, tmp_path: Path) -> None:
    epub = changed_epub(
        written.epub,
        tmp_path / "a.epub",
        {CHAPTER: (b"<style>", b"<style>@import url(https://h/x.css);")},
        {},
    )

    assert has(epub_problems(epub), ProblemKind.MARKUP, CHAPTER, "style")


def test_a_file_that_is_not_an_archive_is_a_problem(tmp_path: Path) -> None:
    epub = tmp_path / "a.epub"
    epub.write_bytes(b"not an archive")

    assert has(epub_problems(epub), ProblemKind.FILE)


def action(kind: str, **entries: PdfObject) -> DictionaryObject:
    """Return an action of a kind with some entries, the way a PDF holds one."""
    value = DictionaryObject(
        {NameObject("/Type"): NameObject("/Action"), NameObject("/S"): NameObject(kind)}
    )
    for key, entry in entries.items():
        value[NameObject(f"/{key}")] = entry
    return value


def annotation(subtype: str = "/Link", **entries: PdfObject) -> DictionaryObject:
    """Return an annotation with the keys the Typst compiler writes for a link."""
    value = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Annot"),
            NameObject("/Subtype"): NameObject(subtype),
            NameObject("/Rect"): ArrayObject([FloatObject(0)] * 4),
            NameObject("/Border"): ArrayObject([NumberObject(0)] * 3),
        }
    )
    for key, entry in entries.items():
        value[NameObject(f"/{key}")] = entry
    return value


def pdf_file(
    target: Path,
    *,
    annotations: Sequence[DictionaryObject] = (),
    jump: bool = False,
    catalog: Mapping[str, PdfObject] | None = None,
    page: Mapping[str, PdfObject] | None = None,
    attachment: bool = False,
    outline_action: DictionaryObject | None = None,
) -> Path:
    """Write a two-page PDF with pypdf and return its path.

    Args:
        target: Where to write it.
        annotations: Annotations of the first page.
        jump: Add a link on the first page to the second page.
        catalog: Entries added to the document catalog.
        page: Entries added to the first page.
        attachment: Embed a file.
        outline_action: Add an outline item that carries this action.
    """
    writer = PdfWriter()
    first = writer.add_blank_page(200, 200)
    second = writer.add_blank_page(200, 200)
    annots = ArrayObject(annotations)
    if jump:
        destination = ArrayObject([second.indirect_reference, NameObject("/Fit")])
        annots.append(annotation(Dest=destination))
    if annots:
        first[NameObject("/Annots")] = annots
    for key, entry in (page or {}).items():
        first[NameObject(key)] = entry
    for key, entry in (catalog or {}).items():
        writer.root_object[NameObject(key)] = entry
    if attachment:
        writer.add_attachment("notes.txt", b"invented")
    if outline_action is not None:
        item = writer.add_outline_item(title="Chapter", page_number=1).get_object()
        assert isinstance(item, DictionaryObject)
        item[NameObject("/A")] = outline_action
    writer.write(target)
    return target


SCRIPT = TextStringObject("app.alert(1)")


def test_a_pdf_with_a_web_link_and_an_internal_jump_passes(tmp_path: Path) -> None:
    pdf = pdf_file(
        tmp_path / "a.pdf",
        annotations=[annotation(A=action("/URI", URI=TextStringObject("https://h/a")))],
        jump=True,
    )

    assert pdf_problems(pdf, outline=()) == []


@pytest.mark.parametrize(
    ("annotations", "kind", "shown"),
    [
        (
            [annotation(A=action("/URI", URI=TextStringObject("javascript:alert(1)")))],
            ProblemKind.ADDRESS,
            "javascript:alert(1)",
        ),
        ([annotation(A=action("/JavaScript", JS=SCRIPT))], ProblemKind.ACTION, "/JavaScript"),
        (
            [annotation(A=action("/Launch", F=TextStringObject("calc.exe")))],
            ProblemKind.ACTION,
            "/Launch",
        ),
        (
            [annotation(A=action("/SubmitForm", F=TextStringObject("https://h/")))],
            ProblemKind.ACTION,
            "/SubmitForm",
        ),
        (
            [
                annotation(
                    A=action(
                        "/URI",
                        URI=TextStringObject("https://h/a"),
                        Next=action("/JavaScript", JS=SCRIPT),
                    )
                )
            ],
            ProblemKind.ACTION,
            "/Next",
        ),
        (
            [annotation(AA=DictionaryObject({NameObject("/E"): action("/JavaScript", JS=SCRIPT)}))],
            ProblemKind.ANNOTATION,
            "/AA",
        ),
        ([annotation("/FileAttachment")], ProblemKind.ANNOTATION, "/FileAttachment"),
    ],
    ids=[
        "script address",
        "script action",
        "launch action",
        "form action",
        "chained action",
        "link with additional actions",
        "file attachment annotation",
    ],
)
def test_a_pdf_link_other_than_a_web_link_or_a_jump_is_a_problem(
    tmp_path: Path, annotations: list[DictionaryObject], kind: ProblemKind, shown: str
) -> None:
    pdf = pdf_file(tmp_path / "a.pdf", annotations=annotations)

    assert has(pdf_problems(pdf, outline=()), kind, "page 1", shown)


@pytest.mark.parametrize(
    ("entry", "value"),
    [
        ("/OpenAction", action("/JavaScript", JS=SCRIPT)),
        ("/AcroForm", DictionaryObject({NameObject("/Fields"): ArrayObject()})),
        ("/AA", DictionaryObject({NameObject("/WC"): action("/JavaScript", JS=SCRIPT)})),
    ],
    ids=["open action", "form", "document additional actions"],
)
def test_a_pdf_catalog_entry_the_export_does_not_write_is_a_problem(
    tmp_path: Path, entry: str, value: PdfObject
) -> None:
    pdf = pdf_file(tmp_path / "a.pdf", catalog={entry: value})

    assert has(pdf_problems(pdf, outline=()), ProblemKind.CATALOG, entry)


def test_a_pdf_with_an_embedded_file_is_a_problem(tmp_path: Path) -> None:
    pdf = pdf_file(tmp_path / "a.pdf", attachment=True)

    assert has(pdf_problems(pdf, outline=()), ProblemKind.CATALOG, "/EmbeddedFiles")


def test_a_pdf_with_a_script_in_its_name_tree_is_a_problem(tmp_path: Path) -> None:
    scripts = DictionaryObject(
        {
            NameObject("/Names"): ArrayObject(
                [TextStringObject("run"), action("/JavaScript", JS=SCRIPT)]
            )
        }
    )
    pdf = pdf_file(
        tmp_path / "a.pdf",
        catalog={"/Names": DictionaryObject({NameObject("/JavaScript"): scripts})},
    )

    assert has(pdf_problems(pdf, outline=()), ProblemKind.CATALOG, "/JavaScript")


def test_a_pdf_page_with_additional_actions_is_a_problem(tmp_path: Path) -> None:
    pdf = pdf_file(
        tmp_path / "a.pdf",
        page={"/AA": DictionaryObject({NameObject("/O"): action("/JavaScript", JS=SCRIPT)})},
    )

    assert has(pdf_problems(pdf, outline=()), ProblemKind.PAGE, "page 1", "/AA")


def test_a_pdf_outline_item_with_an_action_is_a_problem(tmp_path: Path) -> None:
    pdf = pdf_file(tmp_path / "a.pdf", outline_action=action("/JavaScript", JS=SCRIPT))

    assert has(pdf_problems(pdf, outline=["Chapter"]), ProblemKind.OUTLINE, "/A")


def test_a_file_that_is_not_a_pdf_is_a_problem(tmp_path: Path) -> None:
    pdf = tmp_path / "a.pdf"
    pdf.write_bytes(b"not a pdf")

    assert has(pdf_problems(pdf, outline=()), ProblemKind.FILE)


def unchanged_chapters(
    chapters: Sequence[ChapterBlocks], chapter_links: Mapping[str, str], reserved_ids: object
) -> CleanBook:
    """Stand in for the pass over the parsed chapters with one that changes nothing."""
    cleaned = []
    for chapter in chapters:
        assert isinstance(chapter.blocks, list)
        title, *body = chapter.blocks
        cleaned.append(CleanChapter(title=title, body=body))
    return CleanBook(chapters=tuple(cleaned), ids=frozenset())


def no_check(document: Json, ids: object, library_ids: object) -> None:
    """Stand in for the check of the document with one that lets everything through."""


@pytest.mark.parametrize("writer", [write_epub, write_pdf], ids=["epub", "pdf"])
def test_with_the_document_pass_switched_off_the_output_check_stops_the_chapter_route(
    fixture_library_root: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    writer: Callable[[Library, Resource, Path, Path], Path],
) -> None:
    monkeypatch.setattr(kb_export, "clean_chapters", unchanged_chapters)
    monkeypatch.setattr(kb_export, "check_document", no_check)
    library, resource = copy_library(fixture_library_root, tmp_path / "library", SCRIPT_LINKS)
    out = tmp_path / "out"

    with pytest.raises(ExportError) as raised:
        writer(library, resource, out, find_pandoc())

    assert "holds what the export does not write" in raised.value.message
    assert "javascript:alert(1)" in raised.value.message
    assert "report" in raised.value.fix
    assert list(out.iterdir()) == []


@pytest.mark.parametrize("added", list(LINE_STARTS.values()), ids=list(LINE_STARTS))
def test_a_chapter_cannot_add_a_heading_to_the_pdf(
    fixture_library_root: Path, tmp_path: Path, written: Written, added: str
) -> None:
    library, resource = copy_library(fixture_library_root, tmp_path / "library", added)

    pdf = write_pdf(library, resource, tmp_path / "out", find_pandoc())

    assert outline_titles(pdf) == outline_titles(written.pdf)


def test_the_outline_of_the_fixture_pdf_is_the_one_the_library_computes(written: Written) -> None:
    assert outline_titles(written.pdf) == written.outline
    assert "1 Folding the Hull" in written.outline


def test_an_outline_title_the_library_did_not_compute_is_a_problem(written: Written) -> None:
    problems = pdf_problems(written.pdf, outline=[*written.outline, "Injected heading"])

    assert has(problems, ProblemKind.OUTLINE, "Injected heading")


def test_with_the_document_pass_switched_off_the_outline_check_stops_a_line_start(
    fixture_library_root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(kb_export, "clean_chapters", unchanged_chapters)
    monkeypatch.setattr(kb_export, "check_document", no_check)
    library, resource = copy_library(
        fixture_library_root, tmp_path / "library", LINE_STARTS["line separator"]
    )
    out = tmp_path / "out"

    with pytest.raises(ExportError) as raised:
        write_pdf(library, resource, out, find_pandoc())

    assert "holds what the export does not write" in raised.value.message
    assert "Injected heading" in raised.value.message
    assert list(out.iterdir()) == []
