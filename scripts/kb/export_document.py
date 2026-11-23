"""The pass over a book's parsed chapters, and the check of the whole export document.

Pandoc parses each chapter into a JSON tree, and the export writes the PDF and the EPUB from
that tree. A chapter is the author's text, and the exports must show it and never run it. The
reader still returns raw HTML, links of any scheme, and links made by a reference definition
inside a list item or a block quote, because Pandoc has no switch for them. So
``clean_chapters`` rewrites the parsed chapters into the few things the library writes, and
``check_document`` holds the joined document, metadata included, to that list before any writer
runs. A node type that either function does not know stops the export, so a new Pandoc release
cannot add a node that passes unread.

Both functions work on the JSON alone. They read no file and run no program.
"""

import re
import unicodedata
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass

__all__ = [
    "LINK_SCHEMES",
    "ChapterBlocks",
    "CleanBook",
    "CleanChapter",
    "DocumentError",
    "Json",
    "check_document",
    "clean_chapters",
]

type Json = bool | int | float | str | list[Json] | dict[str, Json] | None
"""A value of Pandoc's JSON document."""

LINK_SCHEMES = frozenset({"http", "https", "mailto"})
"""The schemes a link of an export may have. Any other link target is an id of the document."""

_SCHEME = re.compile(r"([A-Za-z][A-Za-z0-9+.-]*):")
# A code block keeps one class, and only when it is a word such as a language name.
_LANGUAGE_WORD = re.compile(r"[\w+#.-]+")
# The class the library puts on its own headings so that they are not numbered.
_UNNUMBERED = "unnumbered"

_ALIGNMENTS = frozenset({"AlignLeft", "AlignRight", "AlignCenter", "AlignDefault"})
_LIST_STYLES = frozenset(
    {"DefaultStyle", "Example", "Decimal", "LowerRoman", "UpperRoman", "LowerAlpha", "UpperAlpha"}
)
_LIST_DELIMITERS = frozenset({"DefaultDelim", "Period", "OneParen", "TwoParens"})
_DOCUMENT_KEYS = frozenset({"pandoc-api-version", "meta", "blocks"})
# The Unicode categories of a control character, a line separator, and a paragraph separator.
_WORD_BREAKS = frozenset({"Cc", "Zl", "Zp"})


class DocumentError(Exception):
    """A parsed chapter or the export document holds something the export does not write."""


@dataclass(frozen=True)
class ChapterBlocks:
    """One chapter as the reader parsed it.

    Attributes:
        anchor: The id its title takes, ``chapter-<stem>``.
        blocks: The blocks of its body, as Pandoc's JSON holds them. The first one is its
            title.
    """

    anchor: str
    blocks: Json


@dataclass(frozen=True)
class CleanChapter:
    """One chapter after the pass.

    Attributes:
        title: The title heading, with the chapter's anchor as its id.
        body: The blocks after the title.
    """

    title: Json
    body: list[Json]


@dataclass(frozen=True)
class CleanBook:
    """The chapters of a book after the pass.

    Attributes:
        chapters: The chapters, in the order they were given.
        ids: Every id the pass gave: each chapter's anchor and each heading id.
    """

    chapters: tuple[CleanChapter, ...]
    ids: frozenset[str]


def clean_chapters(
    chapters: Sequence[ChapterBlocks],
    chapter_links: Mapping[str, str],
    reserved_ids: Collection[str],
) -> CleanBook:
    """Rewrite a book's parsed chapters into what the export writes.

    A raw node becomes text with the same characters, and a line break or a control character
    inside text becomes a space between words, so no text starts a line of a writer's output.
    An image becomes its text. A link
    outside ``LINK_SCHEMES`` becomes its text, except a link to a chapter file of the same
    book, which points at that chapter's anchor. Every attribute is cleared, except one plain
    language word on a code block. The title takes the chapter's anchor, and every other
    heading keeps the id the reader gave it, with a number added when the id is already taken
    in the book.

    Args:
        chapters: The chapters, in reading order.
        chapter_links: The anchor of each chapter, by the file name a link would use.
        reserved_ids: Ids the library gives to its own headings, which no chapter heading
            may take.

    Returns:
        The cleaned chapters and every id the pass gave.

    Raises:
        DocumentError: A chapter does not open with a level-one heading, or holds a node type
            the pass does not know.
    """
    used = set(reserved_ids) | {chapter.anchor for chapter in chapters}
    ids = {chapter.anchor for chapter in chapters}
    cleaned: list[CleanChapter] = []
    for chapter in chapters:
        blocks = _list(chapter.blocks)
        if not blocks:
            raise DocumentError(f"The chapter {chapter.anchor} is empty.")
        kind, content = _node(blocks[0])
        heading = _items(content, 3) if kind == "Header" else None
        if heading is None or heading[0] != 1:
            raise DocumentError(
                f"The chapter {chapter.anchor} does not open with a level-one heading, so its "
                "title cannot take its anchor."
            )
        cleaner = _Cleaner(chapter_links, used)
        title: Json = {
            "t": "Header",
            "c": [1, [chapter.anchor, [], []], cleaner.inlines(heading[2])],
        }
        cleaned.append(CleanChapter(title=title, body=cleaner.blocks(blocks[1:])))
        ids |= cleaner.ids
    return CleanBook(chapters=tuple(cleaned), ids=frozenset(ids))


def check_document(document: Json, ids: Collection[str], library_ids: Collection[str]) -> None:
    """Hold a whole export document to what the library writes.

    The document, metadata values included, may hold only the node types the library's text
    and the cleaned chapters use. It may hold no raw node and no image. A word may hold no
    control character and no line or paragraph separator, so it cannot start a line of the
    Typst source, where a mark at the start of a line makes a heading or a list. A link may go to an
    address of ``LINK_SCHEMES`` or to an id in ``ids``. An id may sit only on a heading, must
    be in ``ids``, and must be used once. The only classes are ``unnumbered`` on a heading whose
    id is in ``library_ids`` and one plain language word on a code block. No node may carry a
    key and value attribute.

    Args:
        document: The Pandoc JSON document.
        ids: Every id the library computed for the document.
        library_ids: The ids of the library's own headings.

    Raises:
        DocumentError: The document breaks one of these rules. The message names the first
            problem found.
    """
    if not isinstance(document, dict) or set(document) != _DOCUMENT_KEYS:
        raise DocumentError(f"The document must have exactly the keys {sorted(_DOCUMENT_KEYS)}.")
    meta = document["meta"]
    if not isinstance(meta, dict):
        raise DocumentError("The metadata of the document is not a map.")
    checker = _Checker(frozenset(ids), frozenset(library_ids))
    for value in meta.values():
        checker.meta(value)
    checker.blocks(document["blocks"])


def _node(value: Json) -> tuple[str, Json]:
    """Return the type and the content of a node."""
    if not isinstance(value, dict):
        raise DocumentError(f"Expected a Pandoc node and found {value!r}.")
    kind = value.get("t")
    if not isinstance(kind, str):
        raise DocumentError(f"Expected a Pandoc node and found {value!r}.")
    return kind, value.get("c")


def _list(value: Json) -> list[Json]:
    if not isinstance(value, list):
        raise DocumentError(f"Expected a list and found {value!r}.")
    return value


def _items(value: Json, count: int) -> list[Json]:
    items = _list(value)
    if len(items) != count:
        raise DocumentError(f"Expected {count} items and found {value!r}.")
    return items


def _text(value: Json) -> str:
    if not isinstance(value, str):
        raise DocumentError(f"Expected a string and found {value!r}.")
    return value


def _number(value: Json) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise DocumentError(f"Expected a whole number and found {value!r}.")
    return value


def _unknown(kind: str) -> DocumentError:
    return DocumentError(f"The node type {kind} is not one the export writes.")


def _breaks_a_word(character: str) -> bool:
    """Say whether a character is a control character or a line or paragraph separator.

    The test is by Unicode category rather than by a list of characters, so it covers every
    character Typst or any other writer could read as the end of a line.
    """
    return unicodedata.category(character) in _WORD_BREAKS


def _words(text: str) -> list[Json]:
    """Return text as words joined by spaces, splitting it where a character breaks a word."""
    words = "".join(" " if _breaks_a_word(character) else character for character in text)
    nodes: list[Json] = []
    for word in words.split(" "):
        if word:
            if nodes:
                nodes.append({"t": "Space"})
            nodes.append({"t": "Str", "c": word})
    return nodes


def _empty_attr() -> Json:
    return ["", [], []]


def _is_web_address(url: str) -> bool:
    scheme = _SCHEME.match(url)
    return scheme is not None and scheme[1].lower() in LINK_SCHEMES


class _Cleaner:
    """The pass over the blocks of one chapter."""

    def __init__(self, chapter_links: Mapping[str, str], used: set[str]) -> None:
        self.chapter_links = chapter_links
        # Shared by every chapter of the book, so a heading id is unique across the book.
        self.used = used
        self.ids: set[str] = set()

    def blocks(self, value: Json) -> list[Json]:
        cleaned: list[Json] = []
        for block in _list(value):
            cleaned.extend(self.block(block))
        return cleaned

    def block(self, value: Json) -> list[Json]:
        kind, content = _node(value)
        match kind:
            case "Para" | "Plain":
                return [{"t": kind, "c": self.inlines(content)}]
            case "Header":
                level, attr, inlines = _items(content, 3)
                identifier = self.heading_id(_text(_items(attr, 3)[0]))
                return [
                    {
                        "t": "Header",
                        "c": [_number(level), [identifier, [], []], self.inlines(inlines)],
                    }
                ]
            case "CodeBlock":
                attr, code = _items(content, 2)
                classes = _list(_items(attr, 3)[1])
                first = classes[0] if classes else None
                kept: list[Json] = (
                    [first] if isinstance(first, str) and _LANGUAGE_WORD.fullmatch(first) else []
                )
                return [{"t": "CodeBlock", "c": [["", kept, []], _text(code)]}]
            case "RawBlock":
                return [{"t": "Para", "c": _words(_text(_items(content, 2)[1]))}]
            case "BlockQuote":
                return [{"t": "BlockQuote", "c": self.blocks(content)}]
            case "BulletList":
                return [{"t": "BulletList", "c": [self.blocks(item) for item in _list(content)]}]
            case "OrderedList":
                attributes, items = _items(content, 2)
                return [
                    {
                        "t": "OrderedList",
                        "c": [attributes, [self.blocks(item) for item in _list(items)]],
                    }
                ]
            case "HorizontalRule":
                return [{"t": "HorizontalRule"}]
            case "Table":
                return [{"t": "Table", "c": self.table(content)}]
            case _:
                raise _unknown(kind)

    def table(self, content: Json) -> list[Json]:
        _, caption, columns, head, bodies, foot = _items(content, 6)
        short, long = _items(caption, 2)
        return [
            _empty_attr(),
            [None if short is None else self.inlines(short), self.blocks(long)],
            columns,
            [_empty_attr(), self.rows(_items(head, 2)[1])],
            [
                [_empty_attr(), _number(header_columns), self.rows(heads), self.rows(rows)]
                for _, header_columns, heads, rows in (_items(body, 4) for body in _list(bodies))
            ],
            [_empty_attr(), self.rows(_items(foot, 2)[1])],
        ]

    def rows(self, value: Json) -> list[Json]:
        rows: list[Json] = []
        for row in _list(value):
            cells: list[Json] = []
            for cell in _list(_items(row, 2)[1]):
                _, alignment, row_span, column_span, blocks = _items(cell, 5)
                cells.append(
                    [
                        _empty_attr(),
                        alignment,
                        _number(row_span),
                        _number(column_span),
                        self.blocks(blocks),
                    ]
                )
            rows.append([_empty_attr(), cells])
        return rows

    def inlines(self, value: Json) -> list[Json]:
        cleaned: list[Json] = []
        for inline in _list(value):
            cleaned.extend(self.inline(inline))
        return cleaned

    def inline(self, value: Json) -> list[Json]:
        kind, content = _node(value)
        match kind:
            case "Str":
                return _words(_text(content))
            case "Space" | "SoftBreak" | "LineBreak":
                return [{"t": kind}]
            case "Emph" | "Strong":
                return [{"t": kind, "c": self.inlines(content)}]
            case "Code":
                return [{"t": "Code", "c": [_empty_attr(), _text(_items(content, 2)[1])]}]
            case "RawInline":
                return _words(_text(_items(content, 2)[1]))
            case "Image":
                return self.inlines(_items(content, 3)[1])
            case "Link":
                _, inlines, target = _items(content, 3)
                url, title = (_text(part) for part in _items(target, 2))
                shown = self.inlines(inlines)
                if _is_web_address(url):
                    return [{"t": "Link", "c": [_empty_attr(), shown, [url, title]]}]
                anchor = self.chapter_links.get(url.partition("#")[0])
                if anchor is not None:
                    return [{"t": "Link", "c": [_empty_attr(), shown, [f"#{anchor}", title]]}]
                return shown
            case _:
                raise _unknown(kind)

    def heading_id(self, identifier: str) -> str:
        """Return the id a heading keeps, numbered the way Pandoc numbers a repeated id."""
        if not identifier:
            return ""
        unique = identifier
        number = 0
        while unique in self.used:
            number += 1
            unique = f"{identifier}-{number}"
        self.used.add(unique)
        self.ids.add(unique)
        return unique


class _Checker:
    """The walk of a whole export document that ``check_document`` makes."""

    def __init__(self, ids: frozenset[str], library_ids: frozenset[str]) -> None:
        self.ids = ids
        self.library_ids = library_ids
        self.seen: set[str] = set()

    def meta(self, value: Json) -> None:
        kind, content = _node(value)
        match kind:
            case "MetaMap":
                if not isinstance(content, dict):
                    raise DocumentError(f"Expected a map and found {content!r}.")
                for item in content.values():
                    self.meta(item)
            case "MetaList":
                for item in _list(content):
                    self.meta(item)
            case "MetaBool":
                if not isinstance(content, bool):
                    raise DocumentError(f"Expected true or false and found {content!r}.")
            case "MetaString":
                _text(content)
            case "MetaInlines":
                self.inlines(content)
            case "MetaBlocks":
                self.blocks(content)
            case _:
                raise _unknown(kind)

    def blocks(self, value: Json) -> None:
        for block in _list(value):
            self.block(block)

    def block(self, value: Json) -> None:
        kind, content = _node(value)
        match kind:
            case "Para" | "Plain":
                self.inlines(content)
            case "Header":
                level, attr, inlines = _items(content, 3)
                _number(level)
                identifier = self.attr(attr, kind, may_have_id=True)
                classes = _list(_items(attr, 3)[1])
                if classes and not (classes == [_UNNUMBERED] and identifier in self.library_ids):
                    raise DocumentError(
                        f"The heading {identifier!r} has the classes {classes}. Only a heading "
                        f"of the library may have the class {_UNNUMBERED}."
                    )
                self.inlines(inlines)
            case "CodeBlock":
                attr, code = _items(content, 2)
                self.attr(attr, kind, may_have_id=False)
                classes = _list(_items(attr, 3)[1])
                if len(classes) > 1 or any(
                    not isinstance(name, str) or not _LANGUAGE_WORD.fullmatch(name)
                    for name in classes
                ):
                    raise DocumentError(
                        f"A code block has the classes {classes}. It may have one plain "
                        "language word."
                    )
                _text(code)
            case "BlockQuote":
                self.blocks(content)
            case "BulletList":
                for item in _list(content):
                    self.blocks(item)
            case "OrderedList":
                attributes, items = _items(content, 2)
                start, style, delimiter = _items(attributes, 3)
                _number(start)
                if _node(style)[0] not in _LIST_STYLES:
                    raise _unknown(_node(style)[0])
                if _node(delimiter)[0] not in _LIST_DELIMITERS:
                    raise _unknown(_node(delimiter)[0])
                for item in _list(items):
                    self.blocks(item)
            case "HorizontalRule":
                pass
            case "Table":
                self.table(content)
            case _:
                raise _unknown(kind)

    def table(self, content: Json) -> None:
        attr, caption, columns, head, bodies, foot = _items(content, 6)
        self.plain_attr(attr, "Table")
        short, long = _items(caption, 2)
        if short is not None:
            self.inlines(short)
        self.blocks(long)
        for column in _list(columns):
            alignment, width = _items(column, 2)
            self.alignment(alignment)
            width_kind, width_value = _node(width)
            if width_kind == "ColWidth":
                if not isinstance(width_value, int | float) or isinstance(width_value, bool):
                    raise DocumentError(f"Expected a column width and found {width_value!r}.")
            elif width_kind != "ColWidthDefault":
                raise _unknown(width_kind)
        head_attr, head_rows = _items(head, 2)
        self.plain_attr(head_attr, "TableHead")
        self.rows(head_rows)
        for body in _list(bodies):
            body_attr, header_columns, heads, rows = _items(body, 4)
            self.plain_attr(body_attr, "TableBody")
            _number(header_columns)
            self.rows(heads)
            self.rows(rows)
        foot_attr, foot_rows = _items(foot, 2)
        self.plain_attr(foot_attr, "TableFoot")
        self.rows(foot_rows)

    def rows(self, value: Json) -> None:
        for row in _list(value):
            attr, cells = _items(row, 2)
            self.plain_attr(attr, "Row")
            for cell in _list(cells):
                cell_attr, alignment, row_span, column_span, blocks = _items(cell, 5)
                self.plain_attr(cell_attr, "Cell")
                self.alignment(alignment)
                _number(row_span)
                _number(column_span)
                self.blocks(blocks)

    def alignment(self, value: Json) -> None:
        kind = _node(value)[0]
        if kind not in _ALIGNMENTS:
            raise _unknown(kind)

    def inlines(self, value: Json) -> None:
        for inline in _list(value):
            self.inline(inline)

    def inline(self, value: Json) -> None:
        kind, content = _node(value)
        match kind:
            case "Str":
                word = _text(content)
                if any(_breaks_a_word(character) for character in word):
                    raise DocumentError(
                        f"The word {word!r} holds a control character or a line or paragraph "
                        "separator, which could start a line of the Typst source."
                    )
            case "Space" | "SoftBreak" | "LineBreak":
                pass
            case "Emph" | "Strong":
                self.inlines(content)
            case "Code":
                attr, code = _items(content, 2)
                self.plain_attr(attr, kind)
                _text(code)
            case "Link":
                attr, inlines, target = _items(content, 3)
                self.plain_attr(attr, kind)
                self.inlines(inlines)
                url, title = _items(target, 2)
                _text(title)
                self.link(_text(url))
            case _:
                raise _unknown(kind)

    def link(self, url: str) -> None:
        if url.startswith("#"):
            if url[1:] not in self.ids:
                raise DocumentError(f"A link goes to {url!r}, an id the library did not compute.")
        elif not _is_web_address(url):
            raise DocumentError(
                f"A link goes to {url!r}, which is not an address of "
                f"{', '.join(sorted(LINK_SCHEMES))} or an id of the document."
            )

    def plain_attr(self, value: Json, kind: str) -> None:
        """Check the attributes of a node that may carry no id and no class."""
        self.attr(value, kind, may_have_id=False)
        classes = _list(_items(value, 3)[1])
        if classes:
            raise DocumentError(f"A {kind} node has the classes {classes}. It may have none.")

    def attr(self, value: Json, kind: str, *, may_have_id: bool) -> str:
        """Check the id and the key and value attributes of a node, and return the id."""
        identifier, _, pairs = _items(value, 3)
        identifier = _text(identifier)
        if _list(pairs):
            raise DocumentError(f"A {kind} node has the key and value attributes {pairs}.")
        if not identifier:
            return identifier
        if not may_have_id:
            raise DocumentError(f"A {kind} node has the id {identifier!r}. Only a heading may.")
        if identifier not in self.ids:
            raise DocumentError(f"The id {identifier!r} is not one the library computed.")
        if identifier in self.seen:
            raise DocumentError(f"The id {identifier!r} is used twice.")
        self.seen.add(identifier)
        return identifier
