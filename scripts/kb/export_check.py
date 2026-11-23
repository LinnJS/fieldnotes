"""The read-back check of each EPUB and PDF the export writes.

The export builds a checked Pandoc document, and then Pandoc and the Typst compiler write the
files. This module reads each written file whole and compares it with what the library's
exports hold, so a route that passes the document check still cannot ship. The lists below
were taken from the exports of the real book and of the test fixture library, and anything not
on them is a problem: a member of another kind, an element or an attribute of another kind, a
link that is neither a web address nor a file of the book, or a PDF action other than a web
link or a jump inside the file.

An EPUB is read with the standard library's XML parser. A PDF is read with pypdf. Neither
check runs a program or fetches anything.
"""

import posixpath
import re
import zipfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from urllib.parse import unquote
from xml.parsers import expat

from pypdf import PdfReader
from pypdf.generic import ArrayObject, DictionaryObject, IndirectObject, PdfObject

from kb.export_document import LINK_SCHEMES

__all__ = ["OutputProblem", "ProblemKind", "epub_problems", "pdf_problems"]


class ProblemKind(StrEnum):
    """What a problem of a written file is about. The export groups problems by kind."""

    FILE = "file"
    MEMBER = "member"
    MARKUP = "markup"
    ELEMENT = "element"
    ATTRIBUTE = "attribute"
    ADDRESS = "address"
    MANIFEST = "manifest"
    CATALOG = "catalog"
    PAGE = "page"
    ANNOTATION = "annotation"
    ACTION = "action"
    OUTLINE = "outline"


@dataclass(frozen=True)
class OutputProblem:
    """One thing a written file holds that the library's exports do not write.

    Attributes:
        kind: What the problem is about.
        detail: Where it is and what it is, on one line.
    """

    kind: ProblemKind
    detail: str


_XHTML = "{http://www.w3.org/1999/xhtml}"
_OPS = "{http://www.idpf.org/2007/ops}"
_OPF = "{http://www.idpf.org/2007/opf}"
_DC = "{http://purl.org/dc/elements/1.1/}"
_NCX = "{http://www.daisy.org/z3986/2005/ncx/}"
_CONTAINER = "{urn:oasis:names:tc:opendocument:xmlns:container}"
_XML_LANG = "{http://www.w3.org/XML/1998/namespace}lang"

_MIMETYPE = "mimetype"
_MIMETYPE_TEXT = b"application/epub+zip"
_PACKAGE = "EPUB/content.opf"
_STYLESHEET = "EPUB/styles/stylesheet1.css"
_CHAPTER_PAGE = re.compile(r"EPUB/text/ch\d{3}\.xhtml")

# The elements of a page, each with the attributes Pandoc writes on it. Most come from the
# exports of the real book. The ones marked below come from a fixture export of a chapter that
# uses a node type ``kb.export_document.check_document`` admits and the real book does not.
_PAGE_ELEMENTS: Mapping[str, frozenset[str]] = {
    f"{_XHTML}{tag}": frozenset(attributes)
    for tag, attributes in {
        "a": {"href", f"{_OPS}type"},
        "blockquote": set(),
        "body": {f"{_OPS}type"},
        # A LineBreak node.
        "br": set(),
        "code": set(),
        "div": {"class"},
        "em": set(),
        "h1": {"class", "data-number", "id"},
        "h2": {"class", "data-number"},
        # A Header node of level 3 to 6. Its id goes on the section around it.
        "h3": {"data-number"},
        "h4": {"data-number"},
        "h5": {"data-number"},
        "h6": {"data-number"},
        "head": set(),
        # A HorizontalRule node.
        "hr": set(),
        "html": {_XML_LANG, "lang"},
        "li": {"id"},
        "link": {"href", "rel", "type"},
        "meta": {"charset", "content", "name"},
        "nav": {"hidden", f"{_OPS}type", "id", "role"},
        # The start number and the number style of an OrderedList node. Their values are held
        # to ``_ATTRIBUTE_VALUES``.
        "ol": {"class", "start", "type"},
        "p": {"class"},
        # The language word of a CodeBlock node, held to ``_ATTRIBUTE_VALUES``.
        "pre": {"class"},
        "section": {"class", "data-number", f"{_OPS}type", "id"},
        "span": {"class"},
        "strong": set(),
        "style": set(),
        "table": set(),
        "tbody": set(),
        # The column alignment of a Table node, held to ``_ATTRIBUTE_VALUES``.
        "td": {"style"},
        "th": {"style"},
        "thead": set(),
        "title": set(),
        "tr": set(),
        "ul": set(),
    }.items()
}
# The only values some page attributes may have.
_ATTRIBUTE_VALUES: Mapping[tuple[str, str], re.Pattern[str]] = {
    (f"{_XHTML}ol", "start"): re.compile(r"\d+"),
    # The writer's mark for each list style the document check admits.
    (f"{_XHTML}ol", "type"): re.compile(r"[1aAiI]"),
    (f"{_XHTML}pre", "class"): re.compile(r"[\w+#.-]+"),
    (f"{_XHTML}td", "style"): re.compile(r"text-align: (?:left|right|center);?"),
    (f"{_XHTML}th", "style"): re.compile(r"text-align: (?:left|right|center);?"),
}
_PACKAGE_ELEMENTS: Mapping[str, frozenset[str]] = {
    f"{_OPF}package": frozenset({_XML_LANG, "prefix", "unique-identifier", "version"}),
    f"{_OPF}metadata": frozenset(),
    f"{_DC}identifier": frozenset({"id"}),
    f"{_DC}title": frozenset({"id"}),
    f"{_DC}date": frozenset({"id"}),
    f"{_DC}language": frozenset(),
    f"{_DC}creator": frozenset({"id"}),
    f"{_DC}contributor": frozenset({"id"}),
    f"{_DC}source": frozenset(),
    f"{_DC}rights": frozenset(),
    f"{_OPF}meta": frozenset({"property", "refines", "scheme"}),
    f"{_OPF}manifest": frozenset(),
    f"{_OPF}item": frozenset({"href", "id", "media-type", "properties"}),
    f"{_OPF}spine": frozenset({"toc"}),
    f"{_OPF}itemref": frozenset({"idref", "linear"}),
    f"{_OPF}guide": frozenset(),
    f"{_OPF}reference": frozenset({"href", "title", "type"}),
}
_NAVIGATION_ELEMENTS: Mapping[str, frozenset[str]] = {
    f"{_NCX}ncx": frozenset({"version"}),
    f"{_NCX}head": frozenset(),
    f"{_NCX}meta": frozenset({"content", "name"}),
    f"{_NCX}docTitle": frozenset(),
    f"{_NCX}text": frozenset(),
    f"{_NCX}navMap": frozenset(),
    f"{_NCX}navPoint": frozenset({"id"}),
    f"{_NCX}navLabel": frozenset(),
    f"{_NCX}content": frozenset({"src"}),
}
_CONTAINER_ELEMENTS: Mapping[str, frozenset[str]] = {
    f"{_CONTAINER}container": frozenset({"version"}),
    f"{_CONTAINER}rootfiles": frozenset(),
    f"{_CONTAINER}rootfile": frozenset({"full-path", "media-type"}),
}
# Pandoc's file that tells Apple Books to use the fonts the stylesheet names.
_DISPLAY_OPTIONS_ELEMENTS: Mapping[str, frozenset[str]] = {
    "display_options": frozenset(),
    "platform": frozenset({"name"}),
    "option": frozenset({"name"}),
}
_XML_MEMBERS: Mapping[str, Mapping[str, frozenset[str]]] = {
    "META-INF/container.xml": _CONTAINER_ELEMENTS,
    "META-INF/com.apple.ibooks.display-options.xml": _DISPLAY_OPTIONS_ELEMENTS,
    _PACKAGE: _PACKAGE_ELEMENTS,
    "EPUB/toc.ncx": _NAVIGATION_ELEMENTS,
    "EPUB/nav.xhtml": _PAGE_ELEMENTS,
    "EPUB/text/title_page.xhtml": _PAGE_ELEMENTS,
}

# The attributes that hold an address, and what each may point at. A page link may also be a
# web address. Every other address is a file of the book, read from the member that holds it.
# The stylesheet link of a page and the package path of the container are held to the one file
# they name, apart from this table.
_WEB_OR_BOOK = "web or book"
_BOOK = "book"
_ADDRESSES: Mapping[tuple[str, str], str] = {
    (f"{_XHTML}a", "href"): _WEB_OR_BOOK,
    (f"{_OPF}item", "href"): _BOOK,
    (f"{_OPF}reference", "href"): _BOOK,
    (f"{_NCX}content", "src"): _BOOK,
}
_MEDIA_TYPES = frozenset({"application/x-dtbncx+xml", "application/xhtml+xml", "text/css"})
_ITEM_PROPERTIES = frozenset({"nav"})

_SCHEME = re.compile(r"([A-Za-z][A-Za-z0-9+.-]*):")
# A reader drops a tab or a line break inside a scheme, so ``java<tab>script:`` runs. The
# scheme is read with every such character taken out.
_NOT_SHOWN = re.compile(r"[\x00-\x20\x7f]")

# The entries the Typst compiler writes, taken from the PDF of the real book.
_CATALOG_KEYS = frozenset(
    {
        "/Lang",
        "/MarkInfo",
        "/Metadata",
        "/Names",
        "/Outlines",
        "/PageLabels",
        "/Pages",
        "/StructTreeRoot",
        "/Type",
        "/ViewerPreferences",
    }
)
_NAME_TREES = frozenset({"/Dests"})
_PAGE_KEYS = frozenset(
    {
        "/Annots",
        "/Contents",
        "/MediaBox",
        "/Parent",
        "/Resources",
        "/StructParents",
        "/Tabs",
        "/Type",
    }
)
_LINK_KEYS = frozenset(
    {"/A", "/Border", "/Contents", "/Dest", "/F", "/Rect", "/StructParent", "/Subtype", "/Type"}
)
_URI_ACTION_KEYS = frozenset({"/S", "/Type", "/URI"})
_OUTLINE_ROOT_KEYS = frozenset({"/Count", "/First", "/Last", "/Type"})
_OUTLINE_ITEM_KEYS = frozenset(
    {"/Count", "/Dest", "/First", "/Last", "/Next", "/Parent", "/Prev", "/Title"}
)


def epub_problems(path: Path) -> list[OutputProblem]:
    """List what a written EPUB holds that the library's EPUBs do not.

    Every member must be one the export writes: the type file, the container file, the
    package file, the two navigation files, the title page, a chapter page, the stylesheet,
    or Pandoc's Apple display-options file. Every XML member must be well formed, hold no
    comment, processing instruction, or document type other than ``html``, and hold only the
    elements and attributes listed for its kind. A page link is an address of ``LINK_SCHEMES``
    or a file of the book, and every other address is a file of the book. The manifest lists
    only the three media types the export writes.

    Args:
        path: The EPUB file.

    Returns:
        One problem per finding, in the order found. The list is empty for a file that holds
        only what the export writes.
    """
    try:
        with zipfile.ZipFile(path) as archive:
            members = archive.infolist()
            names = frozenset(member.filename for member in members)
            problems: list[OutputProblem] = []
            for member in members:
                problems.extend(_member_problems(member.filename, archive.read(member), names))
    # A damaged archive raises one of several kinds of error, from the zip reader or from the
    # decompressor. Any of them means the file is not one the export wrote, so the check fails
    # closed.
    except Exception as error:
        return [OutputProblem(ProblemKind.FILE, f"the file cannot be read as an archive: {error}")]
    return list(dict.fromkeys(problems))


def pdf_problems(path: Path, *, outline: Sequence[str]) -> list[OutputProblem]:
    """List what a written PDF holds that the library's PDFs do not.

    The document catalog and its name dictionary hold only the entries the Typst compiler
    writes, which leaves out an open action, additional actions, a form, a script, and an
    embedded file. Every page holds only the entries the compiler writes. Every annotation is
    a link, which jumps inside the file or opens an address of ``LINK_SCHEMES`` and does
    nothing else. Every outline item jumps inside the file, and the titles of the outline, in
    reading order, are the ones the library computed from the headings of the document it
    checked. Text that the Typst source reads as a heading therefore shows up here.

    Args:
        path: The PDF file.
        outline: The titles the outline must hold, in reading order, as
            ``kb.export.pdf_outline`` computes them.

    Returns:
        One problem per finding, in the order found. The list is empty for a file that holds
        only what the export writes.
    """
    problems: list[OutputProblem] = []
    try:
        reader = PdfReader(path, strict=True)
        catalog = _dictionary(reader.trailer.get("/Root"))
        if catalog is None:
            return [OutputProblem(ProblemKind.FILE, "the file has no document catalog")]
        problems.extend(_catalog_problems(catalog))
        for number, page in enumerate(reader.pages, start=1):
            problems.extend(_page_problems(number, page))
        titles: list[str] = []
        if "/Outlines" in catalog:
            outlines = _dictionary(catalog["/Outlines"])
            if outlines is None:
                problems.append(OutputProblem(ProblemKind.OUTLINE, "the outline is no map"))
            else:
                problems.extend(_outline_problems(outlines, titles))
        problems.extend(_title_problems(titles, outline))
    # pypdf raises many kinds of error on a damaged file. Any of them means the file is not one
    # the export wrote, so the check fails closed.
    except Exception as error:
        problems.append(OutputProblem(ProblemKind.FILE, f"the file cannot be read: {error}"))
    return list(dict.fromkeys(problems))


def _member_problems(name: str, data: bytes, names: frozenset[str]) -> list[OutputProblem]:
    """List the problems of one member of an EPUB."""
    if name == _MIMETYPE:
        if data != _MIMETYPE_TEXT:
            return [OutputProblem(ProblemKind.MEMBER, f"{name} does not hold the EPUB type")]
        return []
    if name == _STYLESHEET:
        return []
    elements = _XML_MEMBERS.get(name)
    if elements is None and _CHAPTER_PAGE.fullmatch(name):
        elements = _PAGE_ELEMENTS
    if elements is None:
        return [OutputProblem(ProblemKind.MEMBER, f"{name} is a member the export does not write")]
    reader = _XmlMember(name, elements, names)
    return reader.read(data)


class _XmlMember:
    """The walk of one XML member of an EPUB against its list of elements and attributes."""

    def __init__(
        self, name: str, elements: Mapping[str, frozenset[str]], names: frozenset[str]
    ) -> None:
        self.name = name
        self.elements = elements
        self.names = names
        self.is_page = elements is _PAGE_ELEMENTS
        self.open: list[str] = []
        self.styled = False
        self.problems: list[OutputProblem] = []

    def read(self, data: bytes) -> list[OutputProblem]:
        parser = expat.ParserCreate(namespace_separator=" ")
        parser.StartElementHandler = self.start
        parser.EndElementHandler = self.end
        parser.CharacterDataHandler = self.text
        parser.CommentHandler = self.comment
        parser.ProcessingInstructionHandler = self.instruction
        parser.StartDoctypeDeclHandler = self.doctype
        try:
            parser.Parse(data, True)
        except expat.ExpatError as error:
            self.problem(ProblemKind.MARKUP, f"is not well-formed XML: {error}")
        return self.problems

    def problem(self, kind: ProblemKind, text: str) -> None:
        self.problems.append(OutputProblem(kind, f"{self.name} {text}"))

    def start(self, tag: str, attributes: dict[str, str]) -> None:
        element = _clark(tag)
        self.open.append(element)
        allowed = self.elements.get(element)
        if allowed is None:
            self.problem(ProblemKind.ELEMENT, f"holds the element {element}")
            return
        for raw_name, value in attributes.items():
            attribute = _clark(raw_name)
            pattern = _ATTRIBUTE_VALUES.get((element, attribute))
            if attribute not in allowed or (pattern is not None and not pattern.fullmatch(value)):
                self.problem(
                    ProblemKind.ATTRIBUTE,
                    f"holds the attribute {attribute} on {element}, with the value {value!r}",
                )
            elif (element, attribute) in _ADDRESSES:
                self.address(element, value, web=_ADDRESSES[element, attribute] == _WEB_OR_BOOK)
        if element == f"{_OPF}item":
            self.manifest_item(attributes)
        elif element == f"{_CONTAINER}rootfile" and attributes.get("full-path") != _PACKAGE:
            self.problem(
                ProblemKind.ADDRESS,
                f"names {attributes.get('full-path')!r} as the package, not {_PACKAGE}",
            )
        elif element == f"{_XHTML}link" and self.resolve(attributes.get("href", "")) != (
            _STYLESHEET
        ):
            self.problem(
                ProblemKind.ADDRESS,
                f"links to {attributes.get('href')!r}, which is not the stylesheet",
            )

    def end(self, tag: str) -> None:
        self.open.pop()

    def text(self, data: str) -> None:
        # The parser hands over the text of one element in several pieces, so only the first
        # piece of style rules in a member is reported.
        if self.open and self.open[-1] == f"{_XHTML}style" and data.strip() and not self.styled:
            self.styled = True
            self.problem(ProblemKind.MARKUP, f"holds style rules {data.strip()[:60]!r}")

    def comment(self, data: str) -> None:
        self.problem(ProblemKind.MARKUP, f"holds the comment {data.strip()[:60]!r}")

    def instruction(self, target: str, data: str) -> None:
        self.problem(ProblemKind.MARKUP, f"holds the processing instruction {target}")

    def doctype(
        self, name: str, system_id: str | None, public_id: str | None, internal_subset: bool
    ) -> None:
        plain = name == "html" and system_id is None and public_id is None
        if not (self.is_page and plain and not internal_subset):
            self.problem(ProblemKind.MARKUP, f"holds a document type declaration for {name}")

    def address(self, element: str, value: str, *, web: bool) -> None:
        scheme = _SCHEME.match(_NOT_SHOWN.sub("", value))
        if scheme is not None:
            if web and scheme[1].lower() in LINK_SCHEMES:
                return
        elif self.resolve(value) is not None:
            return
        kind = "a web address or a file of the book" if web else "a file of the book"
        self.problem(ProblemKind.ADDRESS, f"links to {value!r} on {element}, which is not {kind}")

    def resolve(self, value: str) -> str | None:
        """Return the member an address inside the book points at, or ``None``."""
        if _SCHEME.match(_NOT_SHOWN.sub("", value)):
            return None
        target = value.partition("#")[0]
        if not target:
            return self.name
        resolved = posixpath.normpath(posixpath.join(posixpath.dirname(self.name), unquote(target)))
        return resolved if resolved in self.names else None

    def manifest_item(self, attributes: Mapping[str, str]) -> None:
        href = attributes.get("href")
        media_type = attributes.get("media-type")
        if media_type not in _MEDIA_TYPES:
            self.problem(ProblemKind.MANIFEST, f"lists {href!r} with the media type {media_type}")
        properties = set(attributes.get("properties", "").split())
        if properties - _ITEM_PROPERTIES:
            self.problem(
                ProblemKind.MANIFEST,
                f"lists {href!r} with the properties {' '.join(sorted(properties))}",
            )


def _clark(name: str) -> str:
    """Write a name the XML parser reports as ``namespace local`` in the form ``{ns}local``."""
    namespace, separator, local = name.rpartition(" ")
    return f"{{{namespace}}}{local}" if separator else name


def _dictionary(value: PdfObject | None) -> DictionaryObject | None:
    """Return a PDF value as a dictionary, following a reference, or ``None``."""
    resolved = value.get_object() if isinstance(value, IndirectObject) else value
    return resolved if isinstance(resolved, DictionaryObject) else None


def _extra_keys(
    value: DictionaryObject, allowed: frozenset[str], kind: ProblemKind, where: str
) -> list[OutputProblem]:
    return [
        OutputProblem(kind, f"{where} holds the entry {key}")
        for key in value
        if str(key) not in allowed
    ]


def _catalog_problems(catalog: DictionaryObject) -> list[OutputProblem]:
    problems = _extra_keys(catalog, _CATALOG_KEYS, ProblemKind.CATALOG, "the catalog")
    names = catalog.get("/Names")
    if names is not None:
        trees = _dictionary(names)
        if trees is None:
            problems.append(OutputProblem(ProblemKind.CATALOG, "the catalog's /Names is no map"))
        else:
            problems += _extra_keys(trees, _NAME_TREES, ProblemKind.CATALOG, "the catalog's /Names")
    return problems


def _page_problems(number: int, page: DictionaryObject) -> list[OutputProblem]:
    where = f"page {number}"
    problems = _extra_keys(page, _PAGE_KEYS, ProblemKind.PAGE, where)
    listed = page.get("/Annots")
    if listed is None:
        return problems
    annotations = listed.get_object()
    if not isinstance(annotations, ArrayObject):
        return [*problems, OutputProblem(ProblemKind.ANNOTATION, f"{where} has no annotation list")]
    for entry in annotations:
        annotation = _dictionary(entry)
        if annotation is None:
            problems.append(
                OutputProblem(ProblemKind.ANNOTATION, f"{where} has a broken annotation")
            )
            continue
        subtype = annotation.get("/Subtype")
        if subtype != "/Link":
            problems.append(
                OutputProblem(
                    ProblemKind.ANNOTATION, f"{where} holds an annotation of the type {subtype}"
                )
            )
            continue
        problems += _extra_keys(annotation, _LINK_KEYS, ProblemKind.ANNOTATION, f"{where}, a link,")
        if "/A" in annotation:
            problems += _action_problems(where, annotation["/A"])
    return problems


def _action_problems(where: str, value: PdfObject) -> list[OutputProblem]:
    action = _dictionary(value)
    if action is None:
        return [OutputProblem(ProblemKind.ACTION, f"{where} holds a link whose action is no map")]
    kind = action.get("/S")
    if kind != "/URI":
        return [OutputProblem(ProblemKind.ACTION, f"{where} holds a link whose action is {kind}")]
    problems = _extra_keys(action, _URI_ACTION_KEYS, ProblemKind.ACTION, f"{where}, a link action,")
    address = action.get("/URI")
    scheme = _SCHEME.match(_NOT_SHOWN.sub("", str(address)))
    if scheme is None or scheme[1].lower() not in LINK_SCHEMES:
        schemes = ", ".join(sorted(LINK_SCHEMES))
        problems.append(
            OutputProblem(
                ProblemKind.ADDRESS,
                f"{where} links to {str(address)!r}, which is not an address of {schemes}",
            )
        )
    return problems


def _outline_problems(outlines: DictionaryObject, titles: list[str]) -> list[OutputProblem]:
    """List the problems of the outline's items, and add their titles to ``titles``."""
    problems = _extra_keys(outlines, _OUTLINE_ROOT_KEYS, ProblemKind.OUTLINE, "the outline")
    seen: set[tuple[int, int]] = set()
    pending: list[PdfObject] = [outlines.raw_get("/First")] if "/First" in outlines else []
    while pending:
        reference = pending.pop()
        if isinstance(reference, IndirectObject):
            if (reference.idnum, reference.generation) in seen:
                problems.append(OutputProblem(ProblemKind.OUTLINE, "the outline has a loop"))
                continue
            seen.add((reference.idnum, reference.generation))
        item = _dictionary(reference)
        if item is None:
            problems.append(OutputProblem(ProblemKind.OUTLINE, "an outline item is no map"))
            continue
        problems += _extra_keys(item, _OUTLINE_ITEM_KEYS, ProblemKind.OUTLINE, "an outline item")
        titles.append(str(item.get("/Title", "")))
        # The next sibling goes on the stack first, so the children come out before it and
        # the titles are read in reading order.
        pending += [item.raw_get(key) for key in ("/Next", "/First") if key in item]
    return problems


def _title_problems(titles: Sequence[str], outline: Sequence[str]) -> list[OutputProblem]:
    """Compare the outline's titles with the ones the library computed, word by word."""
    found = [" ".join(title.split()) for title in titles]
    wanted = [" ".join(title.split()) for title in outline]
    if found == wanted:
        return []
    for index, (title, expected) in enumerate(zip(found, wanted, strict=False)):
        if title != expected:
            return [
                OutputProblem(
                    ProblemKind.OUTLINE,
                    f"outline item {index + 1} is {title!r} where the library wrote {expected!r}",
                )
            ]
    extra = found[len(wanted) :]
    if extra:
        return [
            OutputProblem(
                ProblemKind.OUTLINE,
                f"the outline holds {extra!r} after the titles the library wrote",
            )
        ]
    return [
        OutputProblem(
            ProblemKind.OUTLINE,
            f"the outline lacks {wanted[len(found) :]!r}, which the library wrote",
        )
    ]
