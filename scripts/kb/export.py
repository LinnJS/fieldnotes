"""Exports of a library: a PDF and an EPUB of each mirrored book, and one bundle of the library.

Every export is made from the canonical files of a library, so no second source tree exists.

A book's PDF and EPUB come from one Pandoc document that ``checked_document`` builds: the
metadata, a notice section with the attribution and the full license text, and then the
chapters in order. The library's own text is read in one Pandoc run. Each chapter is read alone,
in Pandoc's sandbox, with a dialect that holds only the features the chapters use. The parsed
chapters then go through ``kb.export_document``, which turns what the export must not write into
text and checks the whole document, so a chapter is shown and never run. Pandoc writes the
checked document as Typst markup, which the Typst compiler makes into the PDF, and as the EPUB.
A URL of a record reaches the library's text only through ``kb.prose.link_address``, so a
character of it that Markdown reads as markup is written in its percent-encoded form. Each
written PDF and EPUB is then read back by ``kb.export_check``, and a file that holds anything
the library's exports do not write is removed. The read-back of a PDF also compares its outline
and the block elements of its structure tree with what ``pdf_outline`` and ``pdf_structure``
compute from the checked document.

The bundle is a zip archive of the library's own files, with the chapters and the license file
of mirrored books only.

The license gate is asked before anything about a book is read. A book is exported only when
the gate allows it to be mirrored and its recorded status is ``mirrored``.

Pandoc is a system tool and not a Python dependency. ``find_pandoc`` looks for it on the PATH
and checks its version against ``MINIMUM_PANDOC_VERSION``.
"""

import difflib
import hashlib
import json
import re
import shutil
import subprocess
import tempfile
import uuid
import zipfile
from collections.abc import Iterator, Mapping, Sequence
from pathlib import Path

import typst
import yaml

from kb.catalog import (
    BOOKS_DIR,
    CATALOG_FILE,
    LICENSE_FILE,
    METADATA_FILE,
    TOPICS_DIR,
    ChapterFile,
    Library,
    MirrorStatus,
    Person,
    PinnedSource,
    Resource,
)
from kb.evidence import blob_permalink
from kb.export_check import OutputProblem, ProblemKind, epub_problems, pdf_problems
from kb.export_document import ChapterBlocks, DocumentError, Json, check_document, clean_chapters
from kb.frontmatter import ExtractionStatus
from kb.gate import evaluate
from kb.indexes import newer_editions
from kb.markdown import backtick_fence
from kb.prose import link_address
from kb.readpath import BUILD_COMMAND, CATALOG_INDEX, CHAPTERS_INDEX, LLMS_FILE, TOPICS_INDEX

__all__ = [
    "CHAPTER_FORMAT",
    "CJK_FONT_FAMILIES",
    "EXPORTS_DIR",
    "GENERATED_FILES",
    "HAND_WRITTEN_FILES",
    "MANIFEST_FILE",
    "MINIMUM_PANDOC_VERSION",
    "TEMPLATES_DIR",
    "ExportError",
    "bundle_files",
    "checked_document",
    "find_cjk_font",
    "find_pandoc",
    "pdf_outline",
    "pdf_structure",
    "select_books",
    "write_bundle",
    "write_epub",
    "write_pdf",
]

MINIMUM_PANDOC_VERSION: tuple[int, ...] = (3, 14)
"""Oldest Pandoc the exports are known to work with. It is the version they were tested on."""

EXPORTS_DIR = Path("dist") / "exports"
"""Directory under the library root that exports are written to by default."""

TEMPLATES_DIR = Path(__file__).resolve().parents[2] / "templates"
"""Directory of the tooling that holds ``book.typ`` and ``epub.css``."""

CJK_FONT_FAMILIES = (
    "Songti SC",
    "PingFang SC",
    "Hiragino Sans GB",
    "Noto Serif CJK SC",
    "Noto Sans CJK SC",
)
"""Font families the PDF tries for Chinese, Japanese, and Korean text, in order.

The first three ship with macOS. The Noto families are the ones a Linux machine installs.
"""

MANIFEST_FILE = "MANIFEST.json"
"""Name of the bundle entry that lists every other entry."""

HAND_WRITTEN_FILES = ("AGENTS.md", "LICENSES.md")
"""Files at the library root that a person writes and the bundle must carry."""

GENERATED_FILES = (CATALOG_INDEX, TOPICS_INDEX, CHAPTERS_INDEX, LLMS_FILE)
"""Files at the library root that the build command writes and the bundle must carry."""

_PANDOC = "pandoc"
_PANDOC_RELEASES = "https://github.com/jgm/pandoc/releases"
_PANDOC_VERSION = re.compile(r"pandoc(?:\.exe)? (\d+(?:\.\d+)*)")

CHAPTER_FORMAT = (
    "gfm-attributes-yaml_metadata_block-tex_math_dollars-tex_math_gfm-emoji-alerts-task_lists"
    "-footnotes-autolink_bare_uris-strikeout"
)
"""The dialect a chapter is read in: GitHub-flavored Markdown with only the features chapters use.

It keeps tables and the heading ids GitHub gives. The marks of every other extension are shown
as the characters the chapter holds, and a chapter can set no attribute and no metadata.
"""

# The library's own text is GitHub-flavored Markdown too. Attributes let this module give a
# heading an anchor and leave it unnumbered, and the metadata block carries the title data.
# It holds record text, such as a notice, so emoji and bare addresses are off, as they are for
# chapters. The library writes its own links in full.
_LIBRARY_FORMAT = "gfm+attributes+yaml_metadata_block-emoji-autolink_bare_uris"

_NOTICE_ANCHOR = "copy-notice"
_LIBRARY_IDS = frozenset({_NOTICE_ANCHOR, f"{_NOTICE_ANCHOR}-notices", f"{_NOTICE_ANCHOR}-license"})
# The library's notes under each chapter title are read with the notice text, each group after
# a heading with this id and its number. The headings only mark where a group starts.
_NOTES_ANCHOR = "library-notes"
_MARKDOWN_SPECIAL = re.compile(r"[\\`*_\[\]<>&#|~{}]")
# What opens a block at the start of a line and is not escaped above: a number before a full
# stop or a parenthesis, in any script's digits, a list mark, or the mark of a heading rule.
_LINE_START_NUMBER = re.compile(r"(\d+)([.)])")
_LINE_START_MARKS = frozenset("-+=")
_COPYRIGHT_LINE = re.compile(r"^[ \t]*(Copyright\b.*\d{4}.*?)[ \t]*$", re.MULTILINE)

# The zip format cannot hold a date before 1980. A fixed date keeps the bundle reproducible.
_ZIP_DATE = (1980, 1, 1, 0, 0, 0)
_ZIP_UNIX = 3
_ZIP_FILE_MODE = 0o644 << 16


class ExportError(Exception):
    """An export cannot go on.

    Attributes:
        message: What is wrong, on one line.
        fix: What to do about it, on one line.
    """

    def __init__(self, message: str, fix: str) -> None:
        """Build the error.

        Args:
            message: What is wrong, on one line.
            fix: What to do about it, on one line.
        """
        self.message = message
        self.fix = fix
        super().__init__(message)


def find_pandoc() -> Path:
    """Find Pandoc on the PATH and check that it is new enough.

    Returns:
        The path of the ``pandoc`` executable.

    Raises:
        ExportError: No ``pandoc`` is on the PATH, or the one found is older than
            ``MINIMUM_PANDOC_VERSION``.
    """
    required = ".".join(str(number) for number in MINIMUM_PANDOC_VERSION)
    found = shutil.which(_PANDOC)
    if found is None:
        raise ExportError(
            f"The PDF and EPUB exports need Pandoc {required} or newer, and no pandoc is on "
            "the PATH.",
            f"Install it with `brew install pandoc` on macOS. On another system, install the "
            f"package from {_PANDOC_RELEASES}.",
        )
    reported = _pandoc_version(Path(found))
    version = tuple(int(number) for number in reported.split(".")) if reported else ()
    if version < MINIMUM_PANDOC_VERSION:
        reported = reported or "unknown"
        raise ExportError(
            f"The pandoc at {found} is version {reported}, and the exports need version "
            f"{required} or newer.",
            f"Upgrade it with `brew upgrade pandoc` on macOS. On another system, install the "
            f"package from {_PANDOC_RELEASES}.",
        )
    return Path(found)


def find_cjk_font() -> str | None:
    """Find the font the PDF will use for Chinese, Japanese, and Korean text.

    Returns:
        The first family of ``CJK_FONT_FAMILIES`` that the Typst compiler can load on this
        machine, or ``None`` when it can load none of them.
    """
    available = set(typst.Fonts().families())
    return next((family for family in CJK_FONT_FAMILIES if family in available), None)


def select_books(library: Library, book_id: str | None = None) -> tuple[Resource, ...]:
    """Choose the books to export and refuse any that may not be exported.

    Args:
        library: The loaded library.
        book_id: Id of one book, or ``None`` for every book recorded as mirrored.

    Returns:
        The one book asked for, or every book whose recorded status is ``mirrored``, in catalog
        order.

    Raises:
        ExportError: No cataloged book has the id, the license gate refuses a chosen book, or
            the book asked for is not recorded as mirrored.
    """
    if book_id is None:
        books = tuple(
            resource
            for resource in library.resources
            if resource.mirror_status is MirrorStatus.MIRRORED
        )
    else:
        try:
            books = (library.resource(book_id),)
        except KeyError:
            nearest = difflib.get_close_matches(book_id, library.catalog.resources)
            hint = f" The nearest ids are: {', '.join(nearest)}." if nearest else ""
            raise ExportError(
                f"No cataloged book has the id {book_id}.{hint}",
                f"Pass an id listed under resources in {CATALOG_FILE}.",
            ) from None
    for book in books:
        _require_mirrored(library, book)
    return books


def checked_document(library: Library, resource: Resource, pandoc: Path) -> dict[str, Json]:
    """Build and check the one Pandoc document that a book's PDF and EPUB are made from.

    The document's metadata names the book. A notice section follows, with the attribution,
    the source, the edition, the extraction status, the notices recorded for the book, and the
    full license text. The chapters come last, in reading order. Under each chapter title the
    library names the chapter's part, says when the chapter is machine-extracted, and shows
    each recorded erratum with its source.

    Each chapter is read alone, with ``CHAPTER_FORMAT`` and in Pandoc's sandbox, and goes
    through ``kb.export_document.clean_chapters``. A link from one chapter to another chapter
    file of the same book then points at that chapter's title, so it works inside the export.
    The whole document is held to ``kb.export_document.check_document`` before it is returned.

    Args:
        library: The loaded library.
        resource: The book.
        pandoc: The Pandoc executable, as ``find_pandoc`` returns it.

    Returns:
        The document as Pandoc's JSON reads it.

    Raises:
        ExportError: The book may not be exported, its license file is missing, Pandoc fails,
            or the document holds something the export does not write.
    """
    pinned = _require_mirrored(library, resource)
    license_text = _read_license(library.root, resource)
    chapters = _chapter_files(library, resource)
    anchors = {file.path.name: f"chapter-{file.path.stem}" for file in chapters}
    separators = [f"{_NOTES_ANCHOR}-{number}" for number in range(len(chapters))]
    library_text = [
        _metadata_block(library, resource, pinned, license_text),
        _notice_section(library, resource, pinned, chapters, license_text),
    ]
    for separator, file in zip(separators, chapters, strict=True):
        library_text += [f"# Notes {{#{separator}}}", _chapter_notes(file)]
    front = _read(pandoc, "\n\n".join(library_text) + "\n", _LIBRARY_FORMAT)
    notice, *notes = _split_at(front["blocks"], separators)
    try:
        book = clean_chapters(
            [
                ChapterBlocks(
                    anchors[file.path.name], _read(pandoc, file.body, CHAPTER_FORMAT)["blocks"]
                )
                for file in chapters
            ],
            anchors,
            _LIBRARY_IDS,
        )
        blocks = list(notice)
        for chapter, chapter_notes in zip(book.chapters, notes, strict=True):
            blocks += [chapter.title, *chapter_notes, *chapter.body]
        document: dict[str, Json] = {
            "pandoc-api-version": front["pandoc-api-version"],
            "meta": front["meta"],
            "blocks": blocks,
        }
        check_document(document, book.ids | _LIBRARY_IDS, _LIBRARY_IDS)
    except DocumentError as error:
        raise ExportError(
            f"Pandoc {_pandoc_version(pandoc) or 'of an unknown version'} parsed {resource.id} "
            f"into a document the export does not write. {error}",
            "Stop and report this message to the owner of the library. Do not change the "
            "chapter or the record to get past it.",
        ) from error
    return document


def pdf_outline(document: Json) -> list[str]:
    """Compute the outline titles of the PDF written from a checked document.

    The Typst template numbers every heading except one of class ``unnumbered``, as ``1``,
    ``1.1``, and so on, and the compiler makes one outline item per heading, in reading order,
    titled with the number and the heading's words. The titles come from the document alone,
    so the read-back of the PDF can tell a heading the document holds from one that the Typst
    source made out of text.

    Args:
        document: The document ``checked_document`` returned.

    Returns:
        The titles, in reading order.
    """
    titles: list[str] = []
    counters: list[int] = []
    blocks = document.get("blocks") if isinstance(document, dict) else None
    for level, numbered, words in _headings(blocks):
        if numbered:
            counters = (counters + [0] * level)[:level]
            counters[-1] += 1
            titles.append(f"{'.'.join(map(str, counters))} {words}")
        else:
            titles.append(words)
    return titles


def _headings(blocks: Json) -> Iterator[tuple[int, bool, str]]:
    """Yield the level, whether it is numbered, and the words of each heading in reading order."""
    if isinstance(blocks, list):
        for block in blocks:
            yield from _headings(block)
    elif isinstance(blocks, dict):
        content = blocks.get("c")
        if blocks.get("t") == "Header" and isinstance(content, list) and len(content) == 3:
            level, attr, inlines = content
            if isinstance(level, int) and isinstance(attr, list) and len(attr) == 3:
                yield level, attr[1] != ["unnumbered"], " ".join(_words(inlines).split())
        else:
            yield from _headings(content)


def _words(inlines: Json) -> str:
    """Return the text of inline nodes, with a space for each space or line break."""
    if isinstance(inlines, list):
        return "".join(_words(inline) for inline in inlines)
    if not isinstance(inlines, dict):
        return ""
    kind, content = inlines.get("t"), inlines.get("c")
    match kind:
        case "Str":
            return str(content)
        case "Space" | "SoftBreak" | "LineBreak":
            return " "
        case "Code":
            return str(content[1]) if isinstance(content, list) else ""
        case "Link":
            return _words(content[1]) if isinstance(content, list) else ""
        case _:
            return _words(content)


# The depth of ``#outline(depth: 2)`` in templates/book.typ. The contents page lists a heading
# only down to this level.
_CONTENTS_DEPTH = 2


def pdf_structure(document: Json) -> list[str]:
    """Compute the block elements of the structure tree of the PDF written from a document.

    The Typst compiler writes a tagged PDF. Its structure tree holds one element for each
    heading, list, list item, table, row, cell, and block quote of the Typst source, and for
    each entry of the contents page that ``templates/book.typ`` writes. Pandoc's Typst writer
    escapes a mark such as ``-`` or ``1.`` at the start of a paragraph and not at the start of
    a table cell, a list item, or the text of a link, where the compiler reads it as a list.
    The types come from the document alone, so the read-back of the PDF can tell a list the
    document holds from one that the Typst source made out of text.

    The contents page gives ``H1`` for its title and then ``TOC``. Each heading down to the
    template's depth gives ``TOCI``, and ``Lbl`` after it when the heading is numbered. A step
    from the first level down to the second gives ``TOC`` first. In the body, a heading of
    level n gives ``Hn``. A list gives ``L`` and then ``LI``, ``Lbl``, and ``LBody`` for each
    item. A block quote gives ``BlockQuote``. A table gives ``Table``, then ``THead``, ``TR``,
    and one ``TH`` for each cell when it has head rows, then ``TBody`` and a ``TR`` with one
    ``TD`` for each cell of each row. The blocks inside an item, a quote, or a cell follow
    their element. A paragraph, a code block, a rule, and inline text give nothing, because the
    compiler does not write their elements in a way the document predicts. A table caption,
    foot rows, and head rows inside a table body give nothing either, since no export was
    measured with one, so the read-back refuses a PDF that holds them.

    Args:
        document: The document ``checked_document`` returned.

    Returns:
        The element types, in reading order, without the leading slash of a PDF name.
    """
    blocks = document.get("blocks") if isinstance(document, dict) else None
    tags = ["H1", "TOC"]
    above = 1
    for level, numbered, _ in _headings(blocks):
        if level > _CONTENTS_DEPTH:
            continue
        if level > above:
            tags.append("TOC")
        above = level
        tags.append("TOCI")
        if numbered:
            tags.append("Lbl")
    tags.extend(_block_tags(blocks))
    return tags


def _block_tags(blocks: Json) -> Iterator[str]:
    """Yield the structure element types of some blocks, in reading order."""
    if not isinstance(blocks, list):
        return
    for block in blocks:
        if not isinstance(block, dict):
            continue
        content = block.get("c")
        match block.get("t"):
            case "Header" if isinstance(content, list) and content:
                yield f"H{content[0]}"
            case "BlockQuote":
                yield "BlockQuote"
                yield from _block_tags(content)
            case "BulletList":
                yield from _list_tags(content)
            case "OrderedList" if isinstance(content, list) and len(content) == 2:
                yield from _list_tags(content[1])
            case "Table" if isinstance(content, list) and len(content) == 6:
                yield from _table_tags(content[3], content[4])
            case _:
                pass


def _list_tags(items: Json) -> Iterator[str]:
    """Yield the element types of a list, given its items."""
    yield "L"
    if isinstance(items, list):
        for item in items:
            yield from ("LI", "Lbl", "LBody")
            yield from _block_tags(item)


def _table_tags(head: Json, bodies: Json) -> Iterator[str]:
    """Yield the element types of a table, given its head and its bodies."""
    yield "Table"
    head_rows = head[1] if isinstance(head, list) and len(head) == 2 else None
    if isinstance(head_rows, list) and head_rows:
        yield "THead"
        yield from _row_tags(head_rows, "TH")
    if isinstance(bodies, list):
        for body in bodies:
            yield "TBody"
            if isinstance(body, list) and len(body) == 4:
                yield from _row_tags(body[3], "TD")


def _row_tags(rows: Json, cell_tag: str) -> Iterator[str]:
    """Yield the element types of some table rows, with a cell type for each cell."""
    if not isinstance(rows, list):
        return
    for row in rows:
        yield "TR"
        cells = row[1] if isinstance(row, list) and len(row) == 2 else None
        if not isinstance(cells, list):
            continue
        for cell in cells:
            yield cell_tag
            if isinstance(cell, list) and len(cell) == 5:
                yield from _block_tags(cell[4])


def write_pdf(
    library: Library,
    resource: Resource,
    out_dir: Path,
    pandoc: Path,
    document: dict[str, Json] | None = None,
) -> Path:
    """Write a book's PDF.

    Pandoc writes Typst markup through ``templates/book.typ``, and the Typst compiler makes the
    PDF. The compiler draws a character as an empty box when no installed font has it, and it
    does not fail. ``find_cjk_font`` tells a caller beforehand whether that will happen.

    The written file is read back. Its outline must hold the titles of ``pdf_outline``, and
    the block elements of its structure tree must be the ones of ``pdf_structure``, so text
    that the compiler read as a heading, a list, or a table removes the file.

    Args:
        library: The loaded library.
        resource: The book.
        out_dir: Directory to write into. It is created when it does not exist.
        pandoc: The Pandoc executable, as ``find_pandoc`` returns it.
        document: The book's document as ``checked_document`` returns it, for a caller that
            writes both files of a book from one document. It is built here when omitted.

    Returns:
        The file written, ``<out_dir>/<resource-id>-<edition>.pdf``.

    Raises:
        ExportError: The book may not be exported, its license file is missing, Pandoc or the
            Typst compiler fails, or ``kb.export_check.pdf_problems`` finds a problem in the
            written file, which is then removed.
    """
    if document is None:
        document = checked_document(library, resource, pandoc)
    target = _book_file(library, resource, out_dir, "pdf")
    font_variables = [f"--variable=cjk-font={family}" for family in CJK_FONT_FAMILIES]
    with tempfile.TemporaryDirectory() as scratch:
        source = Path(scratch) / "book.typ"
        _write(
            pandoc,
            document,
            "--to=typst",
            "--standalone",
            f"--template={TEMPLATES_DIR / 'book.typ'}",
            "--wrap=none",
            f"--variable=pdf-author={_typst_string(_person_name(resource.author))}",
            *font_variables,
            f"--output={source}",
        )
        try:
            typst.compile(str(source), output=str(target))
        except typst.TypstError as error:
            raise ExportError(
                f"The Typst compiler could not make the PDF of {resource.id}. {error}",
                "Correct templates/book.typ, or the chapter the message points at, and run "
                "the command again.",
            ) from error
    problems = pdf_problems(
        target, outline=pdf_outline(document), structure=pdf_structure(document)
    )
    return _checked_file(target, problems, resource, "PDF")


def write_epub(
    library: Library,
    resource: Resource,
    out_dir: Path,
    pandoc: Path,
    document: dict[str, Json] | None = None,
) -> Path:
    """Write a book's EPUB.

    Pandoc writes an EPUB 3 file with ``templates/epub.css``, one content file per chapter, and
    a navigation document.

    Args:
        library: The loaded library.
        resource: The book.
        out_dir: Directory to write into. It is created when it does not exist.
        pandoc: The Pandoc executable, as ``find_pandoc`` returns it.
        document: The book's document as ``checked_document`` returns it, for a caller that
            writes both files of a book from one document. It is built here when omitted.

    Returns:
        The file written, ``<out_dir>/<resource-id>-<edition>.epub``.

    Raises:
        ExportError: The book may not be exported, its license file is missing, Pandoc fails,
            or ``kb.export_check.epub_problems`` finds a problem in the written file, which is
            then removed.
    """
    if document is None:
        document = checked_document(library, resource, pandoc)
    target = _book_file(library, resource, out_dir, "epub")
    _write(
        pandoc,
        document,
        "--to=epub3",
        f"--css={TEMPLATES_DIR / 'epub.css'}",
        "--split-level=1",
        "--number-sections",
        # Highlighting writes style rules into the page and ids and link anchors into each
        # code line. A code block is shown as plain text instead.
        "--syntax-highlighting=none",
        f"--output={target}",
    )
    return _checked_file(target, epub_problems(target), resource, "EPUB")


def bundle_files(library: Library) -> tuple[Path, ...]:
    """List the files the bundle holds.

    The bundle holds the catalog, ``AGENTS.md``, ``LICENSES.md``, the committed indexes,
    ``llms.txt``, every Markdown file under ``topics/``, and the ``metadata.yaml`` of every
    cataloged book. For a mirrored book it also holds the chapters and the license file. It
    holds nothing else from a book directory, so a source file is never in it.

    Args:
        library: The loaded library.

    Returns:
        The files, relative to the library root and sorted by their POSIX path.

    Raises:
        ExportError: A required file is missing from the library root, the license gate refuses
            a book recorded as mirrored, or a mirrored book has no license file.
    """
    root = library.root
    hand_written = [name for name in HAND_WRITTEN_FILES if not (root / name).is_file()]
    generated = [name for name in GENERATED_FILES if not (root / name).is_file()]
    if hand_written or generated:
        fixes = []
        if generated:
            fixes.append(f"Run `{BUILD_COMMAND}` to write the index files and llms.txt.")
        if hand_written:
            fixes.append(
                f"Add {', '.join(hand_written)} at the library root. A person writes these "
                "files, and no command makes them."
            )
        raise ExportError(
            f"The bundle needs files that are missing from {root}: "
            f"{', '.join([*hand_written, *generated])}.",
            " ".join(fixes),
        )

    files = {Path(name) for name in (CATALOG_FILE, *HAND_WRITTEN_FILES, *GENERATED_FILES)}
    files.update(path.relative_to(root) for path in (root / TOPICS_DIR).glob("*.md"))
    files.update(Path(BOOKS_DIR) / resource.id / METADATA_FILE for resource in library.resources)
    for book in select_books(library):
        _read_license(root, book)
        files.add(_license_path(book))
        files.update(file.path for file in _chapter_files(library, book))
    return tuple(sorted(files, key=lambda path: path.as_posix()))


def write_bundle(library: Library, out_dir: Path) -> Path:
    """Write the bundle: one zip archive of the files ``bundle_files`` lists.

    The first entry is ``MANIFEST.json``, an object whose ``files`` key lists every other entry
    with its ``path``, its ``sha256`` in lowercase hex, and its ``size`` in bytes. The other
    entries follow in the order of ``bundle_files``. Every entry carries the same fixed date,
    so the same library gives the same bytes.

    Args:
        library: The loaded library.
        out_dir: Directory to write into. It is created when it does not exist.

    Returns:
        The file written, ``<out_dir>/<library-name>-bundle.zip``.

    Raises:
        ExportError: ``bundle_files`` refuses the library.
    """
    entries = [
        (path.as_posix(), (library.root / path).read_bytes()) for path in bundle_files(library)
    ]
    manifest = {
        "files": [
            {"path": name, "sha256": hashlib.sha256(data).hexdigest(), "size": len(data)}
            for name, data in entries
        ]
    }
    manifest_bytes = (json.dumps(manifest, indent=2) + "\n").encode()

    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / f"{library.catalog.library.name}-bundle.zip"
    with zipfile.ZipFile(target, "w") as archive:
        for name, data in [(MANIFEST_FILE, manifest_bytes), *entries]:
            entry = zipfile.ZipInfo(name, date_time=_ZIP_DATE)
            entry.compress_type = zipfile.ZIP_DEFLATED
            # The host system and the file mode are fixed too. Left alone, they would differ
            # between the machines that build the bundle.
            entry.create_system = _ZIP_UNIX
            entry.external_attr = _ZIP_FILE_MODE
            archive.writestr(entry, data)
    return target


def _require_mirrored(library: Library, resource: Resource) -> PinnedSource:
    """Return the pinned source of a book that may be exported, and refuse any other book."""
    decision = evaluate(resource, library.catalog.license_allowlist)
    pinned = resource.pinned_source
    # The gate refuses a book with no pinned source, so the first test only narrows the type.
    if pinned is None or not decision.permits(MirrorStatus.MIRRORED):
        raise ExportError(
            f"The license gate does not allow {resource.id} to be exported. {decision.reason}",
            "Export only a mirrored book. If the license record in "
            f"{BOOKS_DIR}/{resource.id}/{METADATA_FILE} is wrong, correct it.",
        )
    if resource.mirror_status is not MirrorStatus.MIRRORED:
        raise ExportError(
            f"The book {resource.id} passes the license gate and its mirror_status is "
            f"{resource.mirror_status.value}, so it is not yet mirrored and has nothing to "
            "export.",
            "Ingest the book and have the owner set mirror_status to mirrored, then export it.",
        )
    return pinned


def _chapter_files(library: Library, resource: Resource) -> list[ChapterFile]:
    """Return the chapter files in a book's own directory, in reading order."""
    return sorted(library.chapters_of(resource.id), key=lambda file: file.chapter.order)


def _license_path(resource: Resource) -> Path:
    return Path(BOOKS_DIR) / resource.id / LICENSE_FILE


def _read_license(root: Path, resource: Resource) -> str:
    path = _license_path(resource)
    try:
        return (root / path).read_text(encoding="utf-8")
    except FileNotFoundError:
        raise ExportError(
            f"The mirrored book {resource.id} has no license file at {path.as_posix()}.",
            "Copy the upstream license text into that file. Every export must carry it.",
        ) from None


def _checked_file(
    target: Path, problems: Sequence[OutputProblem], resource: Resource, label: str
) -> Path:
    """Return a written file that passed its read-back check, and remove one that did not."""
    if not problems:
        return target
    target.unlink(missing_ok=True)
    groups: dict[ProblemKind, list[str]] = {}
    for problem in problems:
        groups.setdefault(problem.kind, []).append(problem.detail)
    found = " ".join(
        f"{kind.value.capitalize()}: {' | '.join(details)}." for kind, details in groups.items()
    )
    raise ExportError(
        f"The {label} of {resource.id} holds what the export does not write, so it was removed. "
        f"{found}",
        "Stop and report this message to the owner of the library. Do not change the chapter, "
        "the record, or the lists of the check to get past it.",
    )


def _book_file(library: Library, resource: Resource, out_dir: Path, suffix: str) -> Path:
    pinned = _require_mirrored(library, resource)
    out_dir.mkdir(parents=True, exist_ok=True)
    return out_dir / f"{resource.id}-{pinned.edition}.{suffix}"


def _pandoc_version(pandoc: Path) -> str:
    """Return the version a Pandoc executable reports, or an empty string when it reports none."""
    output = subprocess.run(
        [str(pandoc), "--version"], capture_output=True, text=True, encoding="utf-8", check=False
    ).stdout
    match = _PANDOC_VERSION.match(output)
    return match[1] if match else ""


def _run_pandoc(pandoc: Path, text: str, *options: str) -> str:
    result = subprocess.run(
        [str(pandoc), *options],
        input=text,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    if result.returncode != 0:
        raise ExportError(
            f"Pandoc stopped with exit code {result.returncode}. {result.stderr.strip()}",
            "Correct what the Pandoc message points at and run the command again.",
        )
    return result.stdout


def _read(pandoc: Path, markdown: str, dialect: str) -> dict[str, Json]:
    """Parse Markdown in Pandoc's sandbox, which reads no file and fetches nothing."""
    parsed: Json = json.loads(
        _run_pandoc(pandoc, markdown, f"--from={dialect}", "--to=json", "--sandbox")
    )
    if not isinstance(parsed, dict):
        raise ExportError(
            "Pandoc returned something other than a document.",
            "Stop and report this message to the owner of the library.",
        )
    return parsed


def _write(pandoc: Path, document: Mapping[str, Json], *options: str) -> None:
    # The real books export with no warning, so a warning means the document holds something
    # new, and the run stops before anyone reads the file.
    _run_pandoc(pandoc, json.dumps(document), "--from=json", "--fail-if-warnings", *options)


def _split_at(blocks: Json, separators: Sequence[str]) -> list[list[Json]]:
    """Split blocks at the headings whose ids are ``separators``, and drop those headings.

    Returns:
        The blocks before the first separator, then the blocks after each separator.
    """
    groups: list[list[Json]] = [[]]
    wanted = set(separators)
    if not isinstance(blocks, list):
        raise ExportError(
            "Pandoc returned a document with no list of blocks.",
            "Stop and report this message to the owner of the library.",
        )
    for block in blocks:
        identifier = _header_id(block)
        if identifier in wanted:
            groups.append([])
        else:
            groups[-1].append(block)
    if len(groups) != len(separators) + 1:
        raise ExportError(
            "The library's notes for the chapters did not come back from Pandoc in one group "
            "for each chapter.",
            "Stop and report this message to the owner of the library.",
        )
    return groups


def _header_id(block: Json) -> str | None:
    if not isinstance(block, dict) or block.get("t") != "Header":
        return None
    content = block.get("c")
    if not isinstance(content, list) or len(content) != 3 or not isinstance(content[1], list):
        return None
    identifier = content[1][0] if content[1] else None
    return identifier if isinstance(identifier, str) else None


def _metadata_block(
    library: Library, resource: Resource, pinned: PinnedSource, license_text: str
) -> str:
    """Write the Pandoc metadata block. Pandoc reads each text value as Markdown."""
    title, other_title = _titles(resource, pinned)
    spdx = resource.license.spdx
    rights = [f"{spdx} license."] if spdx else []
    rights.extend(_COPYRIGHT_LINE.findall(license_text))
    info = library.catalog.library
    metadata: dict[str, object] = {"title": _plain(title)}
    if other_title is not None:
        metadata["subtitle"] = _plain(other_title)
    metadata["author"] = [_plain(_person_name(resource.author))]
    if resource.translator is not None:
        translator = _plain(_person_name(resource.translator))
        metadata["translator"] = translator
        metadata["contributor"] = [{"role": "trl", "text": translator}]
    metadata["lang"] = pinned.language
    metadata["rights"] = _plain(" ".join(rights))
    metadata["source"] = link_address(blob_permalink(pinned.repository, pinned.commit, pinned.path))
    # The same book and edition always get the same identifier, so a reader treats a rebuilt
    # file as the same publication.
    identifier = uuid.uuid5(uuid.NAMESPACE_URL, f"{info.name}/{resource.id}/{pinned.edition}")
    metadata["identifier"] = f"urn:uuid:{identifier}"
    metadata["edition"] = _plain(f"Edition {pinned.edition}, language {pinned.language}")
    metadata["unofficial"] = _plain(_unofficial_statement(library))
    block = yaml.safe_dump(metadata, allow_unicode=True, sort_keys=False, width=1000)
    return f"---\n{block}---"


def _unofficial_statement(library: Library) -> str:
    return (
        f"This is an unofficial copy made by {library.catalog.library.title}, an independent "
        "community library. The author has not endorsed this copy or the library."
    )


def _titles(resource: Resource, pinned: PinnedSource) -> tuple[str, str | None]:
    """Return the title in the language of the pinned edition, and the other title if any."""
    english = resource.title.english
    if not resource.title.english_official:
        english = f"{english} (title translated by the library)"
    title, other = (
        (english, resource.title.original)
        if pinned.language == "en"
        else (resource.title.original, english)
    )
    return title, (None if other == title else other)


def _person_name(person: Person) -> str:
    if person.native_name is None:
        return person.name
    return f"{person.name} ({person.native_name})"


def _person_line(label: str, person: Person) -> str:
    link = "" if person.url is None else f", <{link_address(person.url)}>"
    return f"- **{label}:** {_plain(_person_name(person))}{link}"


def _notice_section(
    library: Library,
    resource: Resource,
    pinned: PinnedSource,
    chapters: Sequence[ChapterFile],
    license_text: str,
) -> str:
    urls = resource.official_urls
    permalink = link_address(blob_permalink(pinned.repository, pinned.commit, pinned.path))
    machine_extracted = sum(
        file.chapter.extraction_status is ExtractionStatus.MACHINE_EXTRACTED for file in chapters
    )

    facts = [_person_line("Author", resource.author)]
    if resource.translator is not None:
        facts.append(_person_line("Translator", resource.translator))
    facts.append(f"- **Edition:** {_plain(pinned.edition)}, language {_plain(pinned.language)}")
    facts.extend(
        f"- **Newer edition:** The {_plain(newest['language'])} edition "
        f"{_plain(newest['version'])} is newer than this copy. This copy does not hold its "
        "changes."
        for newest in newer_editions(resource, pinned.edition)
    )
    facts.append(
        f"- **Source:** the file [{_plain(pinned.path)}]({permalink}) in the repository "
        f"{_plain(pinned.repository)}, at commit {pinned.commit}"
    )
    if urls.site is not None:
        facts.append(f"- **Official site:** <{link_address(urls.site)}>")
    if urls.repository is not None:
        facts.append(f"- **Official repository:** <{link_address(urls.repository)}>")
    for hosted in urls.hosted_editions:
        note = "" if hosted.note is None else f". {_plain(hosted.note)}"
        facts.append(
            f"- **Official hosted edition:** {_plain(hosted.name)}, "
            f"<{link_address(hosted.url)}>{note}"
        )
    facts.append(
        f"- **Extraction:** {machine_extracted} of {len(chapters)} chapters are "
        "machine-extracted. A program converted a machine-extracted chapter from the source "
        "file, and no person has compared it with the source yet, so it can hold conversion "
        "errors. Each machine-extracted chapter says so under its title."
    )
    if resource.license.spdx is not None:
        facts.append(f"- **License:** {_plain(resource.license.spdx)}, printed in full below")

    blocks = [
        f"# About this copy {{#{_NOTICE_ANCHOR} .unnumbered}}",
        _plain(_unofficial_statement(library)),
        "\n".join(facts),
    ]
    if resource.notices:
        blocks.append(f"## Notices {{#{_NOTICE_ANCHOR}-notices .unnumbered}}")
        blocks.append("\n".join(f"- {_plain(notice)}" for notice in resource.notices))
    blocks.append(f"## License {{#{_NOTICE_ANCHOR}-license .unnumbered}}")
    blocks.append(
        "The work keeps the license its author gave it, which follows in full. The license of "
        f"{_plain(library.catalog.library.title)} does not apply to the work."
    )
    blocks.append(_code_block(license_text))
    return "\n\n".join(blocks)


def _chapter_notes(chapter_file: ChapterFile) -> str:
    """Write the library's notes under a chapter title: its part, its extraction, its errata."""
    chapter = chapter_file.chapter
    blocks = [f"**{_plain(chapter.part)}**"]
    if chapter.extraction_status is ExtractionStatus.MACHINE_EXTRACTED:
        blocks.append(
            "> **Machine-extracted.** No person has compared this chapter with the source file yet."
        )
    blocks.extend(
        f"> **Erratum.** {_plain(erratum.description)} Source: "
        f"[{_plain(erratum.source_url)}]({link_address(erratum.source_url)})"
        for erratum in chapter.errata
    )
    return "\n\n".join(blocks)


def _plain(text: str) -> str:
    """Escape text from a record so that Markdown shows it as written, on one line.

    The start of the text is escaped as well, because the text may start a line or a list item,
    where a mark such as ``1.``, ``-``, or ``--`` would open a list or draw a rule.
    """
    escaped = _MARKDOWN_SPECIAL.sub(r"\\\g<0>", " ".join(text.split()))
    number = _LINE_START_NUMBER.match(escaped)
    if number is not None:
        return f"{number[1]}\\{number[2]}{escaped[number.end() :]}"
    if escaped[:1] in _LINE_START_MARKS:
        return f"\\{escaped}"
    return escaped


def _code_block(text: str) -> str:
    """Fence text verbatim, with a fence longer than any run of backticks inside it."""
    fence = backtick_fence(text)
    lines = text.strip("\n")
    return f"{fence}\n{lines}\n{fence}"


def _typst_string(text: str) -> str:
    """Write text as a Typst string literal."""
    escaped = text.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'
