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
    pdf_structure,
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
    structure: list[str]


def copy_library(
    source: Path, target: Path, added: str = "", record: tuple[str, str] | None = None
) -> tuple[Library, Resource]:
    """Copy the fixture library, change the mirrored book, and load the copy.

    Args:
        source: The fixture library.
        target: Where to copy it.
        added: Text to add to the end of the book's first chapter.
        record: Text of the book's record and the text to put in its place.
    """
    shutil.copytree(source, target, ignore=shutil.ignore_patterns("build", "dist"))
    chapter = target / "books" / MIRRORED / "chapters" / "01-folding-the-hull.md"
    chapter.write_text(chapter.read_text(encoding="utf-8") + added, encoding="utf-8")
    if record is not None:
        old, new = record
        metadata = target / "books" / MIRRORED / "metadata.yaml"
        text = metadata.read_text(encoding="utf-8")
        assert old in text
        metadata.write_text(text.replace(old, new), encoding="utf-8")
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
        structure=library_structure(library, resource),
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


def library_structure(library: Library, resource: Resource) -> list[str]:
    """Return the block elements the export computes for a book's PDF."""
    return pdf_structure(checked_document(library, resource, find_pandoc()))


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
    assert pdf_problems(written.pdf, outline=written.outline, structure=written.structure) == []


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
    assert (
        pdf_problems(
            pdf,
            outline=library_outline(library, resource),
            structure=library_structure(library, resource),
        )
        == []
    )
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

    assert pdf_problems(pdf, outline=(), structure=()) == []


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

    assert has(pdf_problems(pdf, outline=(), structure=()), kind, "page 1", shown)


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

    assert has(pdf_problems(pdf, outline=(), structure=()), ProblemKind.CATALOG, entry)


def test_a_pdf_with_an_embedded_file_is_a_problem(tmp_path: Path) -> None:
    pdf = pdf_file(tmp_path / "a.pdf", attachment=True)

    assert has(pdf_problems(pdf, outline=(), structure=()), ProblemKind.CATALOG, "/EmbeddedFiles")


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

    assert has(pdf_problems(pdf, outline=(), structure=()), ProblemKind.CATALOG, "/JavaScript")


def test_a_pdf_page_with_additional_actions_is_a_problem(tmp_path: Path) -> None:
    pdf = pdf_file(
        tmp_path / "a.pdf",
        page={"/AA": DictionaryObject({NameObject("/O"): action("/JavaScript", JS=SCRIPT)})},
    )

    assert has(pdf_problems(pdf, outline=(), structure=()), ProblemKind.PAGE, "page 1", "/AA")


def test_a_pdf_outline_item_with_an_action_is_a_problem(tmp_path: Path) -> None:
    pdf = pdf_file(tmp_path / "a.pdf", outline_action=action("/JavaScript", JS=SCRIPT))

    assert has(pdf_problems(pdf, outline=["Chapter"], structure=()), ProblemKind.OUTLINE, "/A")


def test_a_file_that_is_not_a_pdf_is_a_problem(tmp_path: Path) -> None:
    pdf = tmp_path / "a.pdf"
    pdf.write_bytes(b"not a pdf")

    assert has(pdf_problems(pdf, outline=(), structure=()), ProblemKind.FILE)


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
    problems = pdf_problems(
        written.pdf, outline=[*written.outline, "Injected heading"], structure=written.structure
    )

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


# Text that starts with a line-start mark where Pandoc's Typst writer does not escape one: a
# table cell, the body of a list item, and the text of a link.
STRUCTURE_ROUTES = {
    "list mark in a cell": "\n| Step | Note |\n|---|---|\n| one | - Keep it dry |\n",
    "term mark in a cell": "\n| Step | Note |\n|---|---|\n| one | / Note: no fourth fold |\n",
    "list number in a cell": "\n| Step | Note |\n|---|---|\n| one | 1. Fold the sheet |\n",
    "plus mark in a cell": "\n| Step | Note |\n|---|---|\n| one | + plus |\n",
    "list number in a list item": "\n- 2\\. Launch\n",
    "list mark in a list item": "\n- \\- a dash\n",
    "term mark in an ordered item": "\n1. / Term: body\n",
    "term mark in a quoted item": "\n> - / Term: body\n",
    "list number in a link": "\nSee [1. Setup](https://example.invalid/a) first.\n",
    "list mark in a link": "\nSee [- dash](https://example.invalid/b) first.\n",
}
NOTICE_LINE = "  - Test fixture. This book and its text are invented for automated tests.\n"


@pytest.mark.parametrize("added", list(STRUCTURE_ROUTES.values()), ids=list(STRUCTURE_ROUTES))
def test_a_chapter_cannot_add_a_list_to_the_pdf(
    fixture_library_root: Path, tmp_path: Path, added: str
) -> None:
    library, resource = copy_library(fixture_library_root, tmp_path / "library", added)
    out = tmp_path / "out"

    with pytest.raises(ExportError) as raised:
        write_pdf(library, resource, out, find_pandoc())

    assert "holds what the export does not write" in raised.value.message
    assert "Structure:" in raised.value.message
    assert "report" in raised.value.fix
    assert list(out.iterdir()) == []


def test_a_notice_that_validation_did_not_see_cannot_add_a_term_list_to_the_pdf(
    fixture_library_root: Path, tmp_path: Path
) -> None:
    notice = '  - "/ Reprint: the second printing moves the pond table."\n'
    library, resource = copy_library(
        fixture_library_root, tmp_path / "library", record=(NOTICE_LINE, notice)
    )
    out = tmp_path / "out"

    with pytest.raises(ExportError) as raised:
        write_pdf(library, resource, out, find_pandoc())

    assert "Structure:" in raised.value.message
    assert list(out.iterdir()) == []


@pytest.mark.parametrize("added", list(STRUCTURE_ROUTES.values()), ids=list(STRUCTURE_ROUTES))
def test_a_line_start_mark_in_a_cell_an_item_or_a_link_is_text_in_the_epub(
    fixture_library_root: Path, tmp_path: Path, added: str
) -> None:
    library, resource = copy_library(fixture_library_root, tmp_path / "library", added)

    epub = write_epub(library, resource, tmp_path / "out", find_pandoc())

    assert epub_problems(epub) == []


def test_a_title_that_validation_did_not_see_cannot_add_a_term_list_to_the_title_page(
    fixture_library_root: Path, tmp_path: Path
) -> None:
    title = "english: Paper Boat Engineering (Test Fixture)"
    library, resource = copy_library(
        fixture_library_root,
        tmp_path / "library",
        record=(title, 'english: "/ Paper: Boat Engineering (Test Fixture)"'),
    )
    out = tmp_path / "out"

    with pytest.raises(ExportError) as raised:
        write_pdf(library, resource, out, find_pandoc())

    assert "Structure: block element 1 " in raised.value.message
    assert list(out.iterdir()) == []


def test_a_cell_that_starts_like_a_typst_heading_writes_no_pdf(
    fixture_library_root: Path, tmp_path: Path
) -> None:
    added = "\n| Step | Note |\n|---|---|\n| one | = Heading try |\n"
    library, resource = copy_library(fixture_library_root, tmp_path / "library", added)
    out = tmp_path / "out"

    # The template breaks the page before a heading of the first level, which the compiler
    # refuses inside a cell, so the compiler stops this one before the read-back does.
    with pytest.raises(ExportError):
        write_pdf(library, resource, out, find_pandoc())

    assert list(out.iterdir()) == []


# Every nesting of the block features a chapter may hold, written the way a faithful chapter
# writes them.
FAITHFUL_NESTINGS = (
    "\n- one\n  - two\n    - three\n- back\n"
    "\n- bullet\n  1. ordered inside\n  2. second\n"
    "\n1. ordered\n   - bullet inside\n2. next\n"
    "\n- first paragraph\n\n  second paragraph\n"
    "\n- item\n\n  > a quote inside an item\n"
    "\n- item\n\n  ```text\n  code inside an item\n  ```\n"
    "\n> - a list\n> - inside a quote\n"
    "\n> outer\n>\n> > inner\n"
    "\n### Level three\n\n#### Level four\n\n##### Level five\n\n###### Level six\n\nText.\n"
    "\n| a | | c |\n|:--|--:|:-:|\n| `code` | | 3 |\n|  | 2 |  |\n"
)
# Marks that stand where Pandoc escapes them or where the compiler reads no line start.
HARMLESS_MARKS = (
    "\nfirst line\\\n1\\. after a hard break\n"
    "\nsecond line  \n\\- after a two-space break\n"
    "\nthird line\n\\+ after a soft break\n"
    "\n> 1\\. a quoted paragraph that starts with a number\n"
    "\n*\\- emphasis* and **1\\. strong** and `- code`.\n"
    "\n### 1\\. A heading that starts with a number\n\n### \\- A heading that starts with a dash\n"
)
PAGE_CROSSING = (
    "\n| n | note |\n|---|---|\n"
    + "".join(f"| {row} | a row of the long table |\n" for row in range(90))
    + "\n"
    + "".join(f"- item {item} of the long list\n" for item in range(70))
)


@pytest.mark.parametrize(
    "added",
    [FAITHFUL_NESTINGS, HARMLESS_MARKS, PAGE_CROSSING],
    ids=["every nesting", "marks that open no block", "a table and a list that cross pages"],
)
def test_a_faithful_chapter_exports_with_the_structure_the_library_computes(
    fixture_library_root: Path, tmp_path: Path, added: str
) -> None:
    library, resource = copy_library(fixture_library_root, tmp_path / "library", added)
    pandoc = find_pandoc()

    epub = write_epub(library, resource, tmp_path / "out", pandoc)
    pdf = write_pdf(library, resource, tmp_path / "out", pandoc)

    assert epub_problems(epub) == []
    assert pdf.is_file()


def test_the_structure_of_the_fixture_pdf_is_the_one_the_library_computes(
    written: Written,
) -> None:
    assert written.structure[:3] == ["H1", "TOC", "TOCI"]
    for tag in ("Lbl", "H1", "H2", "L", "LI", "LBody", "Table", "THead", "TH", "TBody", "TR", "TD"):
        assert tag in written.structure
    assert pdf_problems(written.pdf, outline=written.outline, structure=written.structure) == []


@pytest.mark.parametrize("change", ["added", "removed", "swapped"])
def test_a_structure_the_library_did_not_compute_is_one_problem_that_names_the_place(
    written: Written, change: str
) -> None:
    at = written.structure.index("Table")
    wanted = list(written.structure)
    if change == "added":
        wanted.insert(at, "L")
    elif change == "removed":
        del wanted[at]
    else:
        wanted[at], wanted[at + 1] = wanted[at + 1], wanted[at]

    problems = pdf_problems(written.pdf, outline=written.outline, structure=wanted)

    assert [problem.kind for problem in problems] == [ProblemKind.STRUCTURE]
    assert f"block element {at + 1} of {len(written.structure)}" in problems[0].detail
    assert "Table" in problems[0].detail


def test_a_structure_that_ends_early_or_late_is_a_problem(written: Written) -> None:
    short, long = written.structure[:-1], [*written.structure, "L"]

    for wanted in (short, long):
        problems = pdf_problems(written.pdf, outline=written.outline, structure=wanted)

        assert [problem.kind for problem in problems] == [ProblemKind.STRUCTURE]
        assert f"block element {len(written.structure) + (wanted is long)}" in problems[0].detail


def changed_structure(
    pdf: Path, target: Path, change: Callable[[DictionaryObject, DictionaryObject], None]
) -> Path:
    """Copy a PDF after a change to its catalog or to the first table of its structure tree."""
    writer = PdfWriter(clone_from=pdf)
    catalog = writer.root_object
    tree = catalog["/StructTreeRoot"]
    assert isinstance(tree, DictionaryObject)
    pending: list[PdfObject] = [tree["/K"]]
    table = None
    while pending and table is None:
        kid = pending.pop().get_object()
        if isinstance(kid, ArrayObject):
            pending += reversed(list(kid))
        elif isinstance(kid, DictionaryObject) and "/S" in kid:
            if kid["/S"] == "/Table":
                table = kid
            elif "/K" in kid:
                pending.append(kid["/K"])
    assert table is not None
    change(catalog, table)
    writer.write(target)
    return target


def test_a_copy_of_the_fixture_pdf_still_passes(written: Written, tmp_path: Path) -> None:
    pdf = changed_structure(written.pdf, tmp_path / "a.pdf", lambda catalog, table: None)

    assert pdf_problems(pdf, outline=written.outline, structure=written.structure) == []


def test_a_pdf_with_no_structure_tree_is_a_problem(written: Written, tmp_path: Path) -> None:
    def remove(catalog: DictionaryObject, table: DictionaryObject) -> None:
        del catalog["/StructTreeRoot"]

    pdf = changed_structure(written.pdf, tmp_path / "a.pdf", remove)

    problems = pdf_problems(pdf, outline=written.outline, structure=written.structure)

    assert has(problems, ProblemKind.STRUCTURE, "block element 1 of 0", "the file holds nothing")


def test_a_structure_element_of_another_type_is_a_problem(written: Written, tmp_path: Path) -> None:
    def retype(catalog: DictionaryObject, table: DictionaryObject) -> None:
        table[NameObject("/S")] = NameObject("/Form")

    pdf = changed_structure(written.pdf, tmp_path / "a.pdf", retype)

    problems = pdf_problems(pdf, outline=written.outline, structure=written.structure)

    assert has(problems, ProblemKind.STRUCTURE, "an element of type /Form")


def test_a_structure_tree_with_a_loop_is_a_problem(written: Written, tmp_path: Path) -> None:
    def loop(catalog: DictionaryObject, table: DictionaryObject) -> None:
        kids = table["/K"]
        assert isinstance(kids, ArrayObject)
        kids.append(table.indirect_reference)

    pdf = changed_structure(written.pdf, tmp_path / "a.pdf", loop)

    problems = pdf_problems(pdf, outline=written.outline, structure=written.structure)

    assert has(problems, ProblemKind.STRUCTURE, "a loop")


def node(kind: str, content: Json = None) -> Json:
    """Return one node of Pandoc's JSON document."""
    return {"t": kind, "c": content} if content is not None else {"t": kind}


def heading(level: int, word: str, *classes: str) -> Json:
    return node("Header", [level, [word.lower(), list(classes), []], [node("Str", word)]])


def cell(*blocks: Json) -> Json:
    return [["", [], []], node("AlignDefault"), 1, 1, list(blocks)]


def table(head: list[list[Json]], body: list[list[Json]]) -> Json:
    empty: Json = ["", [], []]
    return node(
        "Table",
        [
            empty,
            [None, []],
            [],
            [empty, [[empty, row] for row in head]],
            [[empty, 0, [], [[empty, row] for row in body]]],
            [empty, []],
        ],
    )


WORD = node("Plain", [node("Str", "word")])


@pytest.mark.parametrize(
    ("blocks", "structure"),
    [
        ([node("Para", [node("Str", "word")])], ["H1", "TOC"]),
        (
            [heading(1, "Notice", "unnumbered"), heading(1, "One"), heading(2, "Two")],
            ["H1", "TOC", "TOCI", "TOCI", "Lbl", "TOC", "TOCI", "Lbl", "H1", "H1", "H2"],
        ),
        (
            [heading(1, "One"), heading(2, "Two"), heading(3, "Three"), heading(1, "Four")],
            [
                "H1",
                "TOC",
                "TOCI",
                "Lbl",
                "TOC",
                "TOCI",
                "Lbl",
                "TOCI",
                "Lbl",
                "H1",
                "H2",
                "H3",
                "H1",
            ],
        ),
        (
            [node("BlockQuote", [node("BulletList", [[WORD], [WORD]])])],
            ["H1", "TOC", "BlockQuote", "L", "LI", "Lbl", "LBody", "LI", "Lbl", "LBody"],
        ),
        (
            [node("OrderedList", [[1, node("Decimal"), node("Period")], [[WORD]]])],
            ["H1", "TOC", "L", "LI", "Lbl", "LBody"],
        ),
        (
            [table([[cell(WORD), cell()]], [[cell(node("BulletList", [[WORD]])), cell(WORD)]])],
            [
                "H1",
                "TOC",
                "Table",
                "THead",
                "TR",
                "TH",
                "TH",
                "TBody",
                "TR",
                "TD",
                "L",
                "LI",
                "Lbl",
                "LBody",
                "TD",
            ],
        ),
        ([table([], [[cell(WORD)]])], ["H1", "TOC", "Table", "TBody", "TR", "TD"]),
    ],
    ids=[
        "no block element",
        "a numbered and an unnumbered heading in the contents",
        "a heading below the depth of the contents",
        "a list inside a quote",
        "an ordered list",
        "a list inside a cell",
        "a table with no head row",
    ],
)
def test_the_structure_the_library_computes_from_a_document(
    blocks: list[Json], structure: list[str]
) -> None:
    assert pdf_structure({"blocks": blocks}) == structure


def test_a_chapter_link_with_a_title_exports_and_passes_both_checks(
    fixture_library_root: Path, tmp_path: Path
) -> None:
    added = '\nA [titled link](https://example.invalid/a "A title") here.\n'
    library, resource = copy_library(fixture_library_root, tmp_path / "library", added)

    epub = write_epub(library, resource, tmp_path / "out", find_pandoc())

    assert epub_problems(epub) == []
