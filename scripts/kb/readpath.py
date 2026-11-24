"""Read the committed indexes: resolve an id, format a citation, and check citations in text.

This module and the two commands built on it, ``scripts/resolve.py`` and
``scripts/check_citations.py``, import only the standard library and run on Python 3.9, so an
agent can call them in a fresh clone before anything is installed. They read
``index/catalog.json``, ``index/chapters.jsonl``, and the chapter Markdown files. They never read
YAML, and they must not import ``kb.catalog`` or anything else that needs a third-party package.

The record types below are the contract between the build, which writes the indexes, and the
read path. ``kb.indexes`` builds exactly these shapes.

Citation tokens follow this grammar::

    resource-id = slug
    chapter-id  = resource-id "/" slug
    edition     = 1*( ALPHA / DIGIT / "." )
    cite-token  = "[cite:" ( chapter-id / resource-id ) [ "@" edition ] "]"

A chapter token is valid only for a mirrored book. A resource token is valid for any cataloged
book. A token with no edition means the edition that is mirrored now.
"""

from __future__ import annotations

import bisect
import difflib
import json
import re
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, TypedDict

__all__ = [
    "BUILD_COMMAND",
    "CATALOG_INDEX",
    "CHAPTERS_INDEX",
    "CODE_FENCE",
    "LLMS_FILE",
    "QUOTE_LINE",
    "RESOLVE_POINTER",
    "TOKEN_PATTERN",
    "TOPICS_INDEX",
    "ChapterRecord",
    "ChapterSourceRecord",
    "CitationProblem",
    "CitationToken",
    "EditionRef",
    "ErratumRecord",
    "HostedEditionRecord",
    "Index",
    "LibraryRecord",
    "OfficialUrlsRecord",
    "PageRangeRecord",
    "PersonRecord",
    "ReadPathError",
    "ResolveError",
    "Resolved",
    "ResourceRecord",
    "ResourceSourceRecord",
    "TitleRecord",
    "TopicRecord",
    "TopicReferenceRecord",
    "check_text",
    "cite_token",
    "cited_ids",
    "edition_note",
    "format_citation",
    "holds_quote",
    "language_name",
    "load_index",
    "mask_code",
    "official_url",
    "opening_fence",
    "page_label",
    "record_json",
    "record_lines",
    "resolve",
    "source_label",
]

CATALOG_INDEX = "index/catalog.json"
TOPICS_INDEX = "index/topics.json"
CHAPTERS_INDEX = "index/chapters.jsonl"
LLMS_FILE = "llms.txt"

BUILD_COMMAND = "uv run python scripts/build.py"
"""The command that rewrites the committed indexes."""

_LANGUAGE_NAMES = {"en": "English", "zh": "Chinese"}

_MINIMUM_QUOTE_WORDS = 4
_MINIMUM_UNSPACED_CHARACTERS = 6
# One character of a script that white space does not divide into words, so a count of
# white-space words cannot tell how long a quote in it is. The ranges, in order, are Hiragana
# and Katakana, the Katakana phonetic extensions, Han extension A, the main Han block, the Han
# compatibility ideographs, the Hangul syllables, and the Han supplementary planes. Korean puts
# spaces between phrases and not between words, so Hangul is measured the same way.
_UNSPACED_CHARACTER = re.compile(
    "["
    "\u3040-\u30ff"
    "\u31f0-\u31ff"
    "\u3400-\u4dbf"
    "\u4e00-\u9fff"
    "\uf900-\ufaff"
    "\uac00-\ud7af"
    "\U00020000-\U000323af"
    "]"
)

# The line that opens or closes a fenced code block. Group 1 is the fence.
CODE_FENCE = re.compile(r" {0,3}(`{3,}|~{3,})")
# The one definition of a citation token. Group 1 is the reference between the brackets.
TOKEN_PATTERN = re.compile(r"\[cite:([^\]\n]*)\]")
# The text of a reading-list item that points at a book whose text is not in the library.
# Group 1 is the resource id.
RESOLVE_POINTER = re.compile(
    r"`([a-z0-9-]+)`\. Run `python3 scripts/resolve\.py \1` for its official URL\."
)
# A span between straight or curly double quotation marks, between the corner brackets that
# Chinese and Japanese prose quotes with, or inside an HTML quote element, which a Markdown
# reader shows as a quote too. Each alternative holds one group, the text inside the marks, so
# the group that matched is the last one.
_QUOTED_SPAN = re.compile(
    r'"([^"]+)"|“([^”]+)”|「([^」]+)」|『([^』]+)』'
    r"|<blockquote\b[^>]*>(.*?)</blockquote\s*>"
    r"|<q\b[^>]*>(.*?)</q\s*>",
    re.DOTALL | re.IGNORECASE,
)
# The group of _QUOTED_SPAN that holds the text of an HTML block quote, which is checked the
# way a Markdown block quote is.
_HTML_BLOCK_QUOTE_GROUP = 5
_HTML_TAG = re.compile(r"</?[A-Za-z][^>]*>")
# What may stand in front of the mark of a block quote: any indentation, and the markers of the
# list items the quote is nested in. A quote under a list item is indented four spaces or more,
# and one that opens a list item follows its marker, and both are still quotes to a reader. A
# line that only looks like a quote is asked for a citation token, which is the safe direction.
_QUOTE_PREFIX = r"[ \t]*(?:(?:[-*+]|\d{1,9}[.)])[ \t]+)*"
# A line of a Markdown block quote.
QUOTE_LINE = re.compile(_QUOTE_PREFIX + r">")
# A block quote line that opens a list item, which starts a quote of its own.
_ITEM_QUOTE_LINE = re.compile(r"[ \t]*(?:(?:[-*+]|\d{1,9}[.)])[ \t]+)+>")
# A line that opens a block of its own, so it ends a block quote above it instead of continuing
# it: a heading, a code fence, a list item, or a thematic break. A rule comes before a list item,
# because a rule of dashes or asterisks with spaces between also starts like one.
_OPENS_BLOCK = re.compile(
    r" {0,3}#{1,6}(?:[ \t]|$)"
    r"| {0,3}(?:`{3,}|~{3,})"
    r"| {0,3}([-*_])(?:[ \t]*\1){2,}[ \t]*$"
    r"|[ \t]*(?:[-*+]|\d{1,9}[.)])(?:[ \t]|$)"
)
_QUOTE_MARKERS = re.compile(r"(?m)^" + _QUOTE_PREFIX + r"(?:[ \t]{0,3}> ?)+")
_INLINE_CODE = re.compile(r"(`+).+?\1")
# A backslash escape of an ASCII punctuation mark. Group 1 is the mark.
_ESCAPE = re.compile(r"\\([!-/:-@\[-`{-~])")
# An inline code span, which may run over a line break and not over a blank line. Group 2 is
# the code.
_CODE_SPAN = re.compile(
    r"(?<!`)(`+)(?!`)((?:(?!\n[ \t]*\n).)+?)(?<!`)\1(?!`)",
    re.DOTALL,
)
# A blank line, which no emphasis runs over.
_BLANK_LINE = re.compile(r"\n[ \t]*\n")
# A pair of emphasis delimiters around text that starts and ends with something other than
# white space, longest delimiter first. Text in a pair may hold a shorter delimiter of the same
# mark, so the pairs nest. An underscore pair may not touch a letter or a digit outside it,
# because an underscore inside a word, as in file_name, opens no emphasis.
_EMPHASIS_PAIRS = (
    re.compile(r"\*\*\*(?=\S)([^*]+?)(?<=\S)\*\*\*"),
    re.compile(r"\*\*(?=\S)((?:[^*]|\*(?!\*))+?)(?<=\S)\*\*"),
    re.compile(r"\*(?=\S)([^*]+?)(?<=\S)\*"),
    re.compile(r"(?<![^\W_])___(?=\S)([^_]+?)(?<=\S)___(?![^\W_])"),
    re.compile(r"(?<![^\W_])__(?=\S)((?:[^_]|_(?!_))+?)(?<=\S)__(?![^\W_])"),
    re.compile(r"(?<![^\W_])_(?=\S)([^_]+?)(?<=\S)_(?![^\W_])"),
)
# Stands in for the text of a code span while emphasis is removed around it. It is a character
# for private use, which no chapter writes.
_CODE_PLACEHOLDER = "\ue000"
_FRONTMATTER_FENCE = "---"


class EditionRef(TypedDict):
    """One edition of a book, named by its language and version."""

    language: str
    version: str


class PageRangeRecord(TypedDict):
    """First and last page of a section in the source file, counted from 1."""

    first: int
    last: int


class ChapterSourceRecord(TypedDict):
    """Where a chapter's text came from."""

    repository: str
    revision: str
    path: str
    pages: PageRangeRecord


class ErratumRecord(TypedDict):
    """A known upstream erratum, which is recorded beside the text and never applied to it."""

    description: str
    source_url: str


class ChapterRecord(TypedDict):
    """One line of ``index/chapters.jsonl``.

    ``path`` is relative to the library root. ``newer_editions`` lists every language whose newest
    edition has a higher version than ``edition``, and ``edition_behind`` is true when that list
    is not empty. ``topics`` holds the ids of the topics that reference the chapter.
    """

    id: str
    path: str
    title: str
    part: str
    order: int
    section_label: str
    resource: str
    language: str
    edition: str
    edition_behind: bool
    newer_editions: list[EditionRef]
    license_id: str | None
    mirror_status: str
    quote_permitted: bool
    source: ChapterSourceRecord
    extraction_status: str
    errata: list[ErratumRecord]
    topics: list[str]


class TitleRecord(TypedDict):
    """A work's titles. ``english_official`` is false when the library translated the title."""

    original: str
    english: str
    english_official: bool


class PersonRecord(TypedDict):
    """An author or translator."""

    name: str
    native_name: str | None
    url: str | None


class HostedEditionRecord(TypedDict):
    """A reading edition the author hosts outside the site and the repository."""

    name: str
    url: str
    note: str | None


class OfficialUrlsRecord(TypedDict):
    """The author's own locations for a work."""

    site: str | None
    repository: str | None
    hosted_editions: list[HostedEditionRecord]


class ResourceSourceRecord(TypedDict):
    """The pinned upstream file a mirrored book was extracted from."""

    repository: str
    revision: str
    path: str


class ResourceRecord(TypedDict):
    """One entry of ``resources`` in ``index/catalog.json``.

    ``edition``, ``edition_language``, ``source``, ``path``, and ``license_path`` describe the
    mirrored text and are ``None`` for a book that is not mirrored, whose ``chapters`` list is
    empty. ``newest_editions`` maps a language code to the newest upstream version. ``topics``
    holds the ids of the topics that reference the book.
    """

    id: str
    type: str
    collection: str
    title: TitleRecord
    author: PersonRecord
    translator: PersonRecord | None
    languages: list[str]
    official_urls: OfficialUrlsRecord
    newest_editions: dict[str, str]
    license_id: str | None
    license_evidence: str
    license_permalink: str | None
    mirror_status: str
    quote_permitted: bool
    edition: str | None
    edition_language: str | None
    edition_behind: bool
    newer_editions: list[EditionRef]
    source: ResourceSourceRecord | None
    path: str | None
    license_path: str | None
    chapters: list[str]
    topics: list[str]
    notices: list[str]


class LibraryRecord(TypedDict):
    """The library's own names and URLs, as ``index/catalog.json`` records them."""

    name: str
    title: str
    description: str
    base_url: str
    repository: str


class TopicReferenceRecord(TypedDict):
    """One reference from a topic to a book or to one of its chapters."""

    resource: str
    chapter: str | None
    note: str
    mirror_status: str | None
    license_id: str | None
    quote_permitted: bool


class TopicRecord(TypedDict):
    """One entry of ``topics`` in ``index/topics.json``.

    ``mirrored_chapters`` counts the distinct chapter ids the topic references under books whose
    text may be quoted. It is 0 for a topic that only lists books to read at their official
    sources.
    """

    id: str
    title: str
    path: str
    references: list[TopicReferenceRecord]
    mirrored_chapters: int


class ReadPathError(Exception):
    """The committed indexes, or a chapter file they point at, cannot be read."""


class ResolveError(Exception):
    """An id names no cataloged resource and no mirrored chapter.

    The message says what is wrong in sentences. It names the three nearest valid ids, or the
    book's official URL when the id is a chapter id under a book that has no mirrored chapters.
    """


@dataclass(frozen=True)
class Index:
    """The committed indexes of one library.

    Attributes:
        root: The library root the indexes were read from.
        library: The library's own names and URLs.
        resources: Every cataloged resource by id, in catalog order.
        chapters: Every mirrored chapter by id, in catalog order and then reading order.
    """

    root: Path
    library: LibraryRecord
    resources: dict[str, ResourceRecord]
    chapters: dict[str, ChapterRecord]

    def ids(self) -> list[str]:
        """Return every valid id: the resource ids, then the chapter ids."""
        return [*self.resources, *self.chapters]

    def chapter_body(self, chapter_id: str) -> str:
        """Read the Markdown of one chapter, without its frontmatter.

        Args:
            chapter_id: Id of an indexed chapter.

        Returns:
            The chapter's Markdown body.

        Raises:
            KeyError: No indexed chapter has that id.
            ReadPathError: The chapter file the index points at cannot be read.
        """
        path = self.root / self.chapters[chapter_id]["path"]
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as error:
            raise ReadPathError(
                f"{path} cannot be read, although {CHAPTERS_INDEX} lists it. The index may be "
                f"stale. Run `{BUILD_COMMAND}` in the library, or restore the file."
            ) from error
        return _without_frontmatter(text)


@dataclass(frozen=True)
class Resolved:
    """What an id names.

    Attributes:
        resource: The resource the id names, or the resource of the chapter it names.
        chapter: The chapter, or ``None`` when the id is a resource id.
    """

    resource: ResourceRecord
    chapter: ChapterRecord | None


@dataclass(frozen=True)
class CitationProblem:
    """One thing wrong with the citations of a document.

    Attributes:
        line: Line of the document the problem is on, counted from 1.
        message: What is wrong, on one line.
    """

    line: int
    message: str


def load_index(root: Path) -> Index:
    """Read ``index/catalog.json`` and ``index/chapters.jsonl`` under a library root.

    Args:
        root: The library root, which is the directory that holds ``index/``.

    Returns:
        The indexes.

    Raises:
        ReadPathError: An index file is missing, unreadable, or not what the build writes.
    """
    catalog = _read_json(root, CATALOG_INDEX)
    try:
        library: LibraryRecord = catalog["library"]
        resources: dict[str, ResourceRecord] = {
            record["id"]: record for record in catalog["resources"]
        }
        chapters: dict[str, ChapterRecord] = {}
        for line in _read_text(root, CHAPTERS_INDEX).splitlines():
            if line.strip():
                record: ChapterRecord = json.loads(line)
                chapters[record["id"]] = record
    except (ValueError, KeyError, TypeError) as error:
        raise ReadPathError(_unreadable(root, "the index files")) from error
    return Index(root=root, library=library, resources=resources, chapters=chapters)


def resolve(index: Index, identifier: str) -> Resolved:
    """Find the resource or chapter an id names.

    Args:
        index: The indexes to look in.
        identifier: A resource id or a chapter id.

    Returns:
        The record the id names, with its resource.

    Raises:
        ResolveError: Nothing has that id. The error names the nearest valid ids, or says that
            the book has no mirrored chapters when the id is a chapter id under such a book.
    """
    chapter = index.chapters.get(identifier)
    if chapter is not None:
        return Resolved(resource=index.resources[chapter["resource"]], chapter=chapter)
    resource = index.resources.get(identifier)
    if resource is not None:
        return Resolved(resource=resource, chapter=None)

    parent_id, slash, _ = identifier.partition("/")
    parent = index.resources.get(parent_id) if slash else None
    if parent is not None and not parent["quote_permitted"]:
        url = official_url(parent)
        where = f" Read it at {url}." if url else ""
        raise ResolveError(
            f'{parent_id} has no mirrored chapters, so "{identifier}" names nothing. Its mirror '
            f"status is {parent['mirror_status']} and its text is not in this library.{where}"
        )
    nearest = difflib.get_close_matches(identifier, index.ids(), n=3, cutoff=0.0)
    raise ResolveError(
        f'No resource or chapter has the id "{identifier}". The nearest ids are: '
        f"{', '.join(nearest)}."
    )


def language_name(code: str) -> str:
    """Return the English name of a language code, or the code itself when it is not known."""
    return _LANGUAGE_NAMES.get(code, code)


def page_label(pages: PageRangeRecord) -> str:
    """Word a page range for a citation, such as ``pp. 9-12``, or ``p. 6`` for one page."""
    if pages["first"] == pages["last"]:
        return f"p. {pages['first']}"
    return f"pp. {pages['first']}-{pages['last']}"


def source_label(source_path: str) -> str:
    """Name a source file by its format, such as ``source PDF`` for a path that ends in .pdf."""
    suffix = PurePosixPath(source_path).suffix.lstrip(".")
    return f"source {suffix.upper()}" if suffix else "source"


def cite_token(identifier: str, edition: str | None = None) -> str:
    """Build a citation token.

    Args:
        identifier: A resource id or a chapter id.
        edition: The edition to pin the citation to, or ``None`` for a token without one.

    Returns:
        The token, such as ``[cite:book/section@v260615]``.
    """
    suffix = f"@{edition}" if edition else ""
    return f"[cite:{identifier}{suffix}]"


def format_citation(resource: ResourceRecord, chapter: ChapterRecord) -> str:
    """Format the citation of a chapter for a person to read.

    The form is ``Author, "Title" (English ed. v260615), §03 "Section title", source PDF
    pp. 9-12. [cite:<chapter-id>@v260615]``. Every tool prints citations through this function,
    so they all read the same.

    Args:
        resource: The chapter's book.
        chapter: The chapter to cite.

    Returns:
        The citation on one line, ending with the citation token.
    """
    source = chapter["source"]
    return (
        f'{resource["author"]["name"]}, "{resource["title"]["english"]}" '
        f"({language_name(chapter['language'])} ed. {chapter['edition']}), "
        f'{chapter["section_label"]} "{chapter["title"]}", '
        f"{source_label(source['path'])} {page_label(source['pages'])}. "
        f"{cite_token(chapter['id'], chapter['edition'])}"
    )


def official_url(resource: ResourceRecord) -> str | None:
    """Return the first official location of a work: its site, its repository, or a hosted edition.

    Args:
        resource: The resource record.

    Returns:
        The URL, or ``None`` when the record holds none.
    """
    urls = resource["official_urls"]
    hosted = [edition["url"] for edition in urls["hosted_editions"]]
    candidates = [urls["site"], urls["repository"], *hosted]
    return next((url for url in candidates if url), None)


def edition_note(language: str | None, edition: str | None, newer: list[EditionRef]) -> str | None:
    """Say that a mirrored edition is behind, and name each newer edition.

    Args:
        language: Language code of the mirrored edition.
        edition: Version of the mirrored edition.
        newer: The newest edition of each language that is ahead of the mirrored one.

    Returns:
        The sentences to show with a record, or ``None`` when no edition is newer or nothing is
        mirrored.
    """
    if not newer or language is None or edition is None:
        return None
    newest = " ".join(
        f"The newest {language_name(ref['language'])} edition is {ref['version']}." for ref in newer
    )
    return (
        f"The mirrored {language_name(language)} edition {edition} is behind. {newest} "
        "Say so when you cite it."
    )


def record_json(resolved: Resolved) -> dict[str, Any]:
    """Return the record an id names as one JSON-ready object.

    Args:
        resolved: What the id names.

    Returns:
        The chapter record with a ``citation`` key added, or the resource record.
    """
    if resolved.chapter is None:
        return dict(resolved.resource)
    record: dict[str, Any] = dict(resolved.chapter)
    record["citation"] = format_citation(resolved.resource, resolved.chapter)
    return record


def record_lines(index: Index, resolved: Resolved) -> list[str]:
    """Describe the record an id names as ``key: value`` lines.

    A key whose value is missing is left out, so a book that is not mirrored prints no path. A
    key that holds several values is printed once per value.

    Args:
        index: The indexes the record came from.
        resolved: What the id names.

    Returns:
        The lines. For a chapter the last one is the formatted citation.
    """
    if resolved.chapter is None:
        pairs = _resource_pairs(resolved.resource)
    else:
        pairs = _chapter_pairs(index, resolved.resource, resolved.chapter)
    return [f"{key}: {_shown(value)}" for key, value in pairs if value is not None]


def check_text(index: Index, text: str) -> list[CitationProblem]:
    """Check every citation token and every quote in a Markdown document.

    A token must resolve, and an edition after ``@`` must be the indexed edition. A quote is a
    Markdown block quote, at any indentation and inside a list item as well, an HTML
    ``<blockquote>``, or a long enough span in quotation marks in a paragraph that holds a
    token. The marks are straight double quotes, curly double quotes, the corner brackets 「」
    and 『』, and the HTML element ``<q>``. A span is long enough
    when it holds four words or more, or six characters or more of a script written without
    spaces, which are Han, Hiragana, Katakana, and Hangul. A span is checked against the first
    token after it in its paragraph, and against the nearest token in front of it when none
    follows.

    A quote must appear word for word in the chapter it cites, or in any chapter of the book
    when it cites a book. White space, emphasis markers that pair, the backticks around inline
    code, and the backslash of an escape are ignored on both sides. Any other asterisk,
    underscore, backtick, or backslash is compared. A quote that starts or ends inside a word
    of the chapter does not match, where a word is a run of ASCII letters and digits. A quote
    that cites a book whose text may not be quoted is a problem, and so is a block quote with
    no token in its paragraph or on the next line that has text.

    Tokens inside fenced code blocks and inline code are not citations. A quoted span that is
    exactly the title of the cited book or chapter is a title and not a quote, so the citation
    that ``format_citation`` writes passes.

    Args:
        index: The indexes to check against.
        text: The Markdown document.

    Returns:
        The problems in line order. The list is empty when nothing is wrong.

    Raises:
        ReadPathError: A chapter file the index points at cannot be read.
    """
    masked = mask_code(text)
    line_starts = _line_starts(text)
    tokens = _tokens(masked)

    problems: list[CitationProblem] = []
    targets: dict[int, Resolved] = {}
    for token in tokens:
        line = _line_of(line_starts, token.offset)
        try:
            target = resolve(index, token.identifier)
        except ResolveError as error:
            problems.append(
                CitationProblem(line, f"The citation {token.text} does not resolve. {error}")
            )
            continue
        targets[token.offset] = target
        indexed = (
            target.resource["edition"] if target.chapter is None else target.chapter["edition"]
        )
        if token.edition is not None and token.edition != indexed:
            recorded = f"edition {indexed}" if indexed else "no mirrored edition"
            problems.append(
                CitationProblem(
                    line,
                    f"The citation {token.text} names edition {token.edition}, and the index "
                    f"records {recorded} for {token.identifier}.",
                )
            )

    bodies: dict[str, str] = {}
    for quote in _quotes(text, masked, tokens):
        line = _line_of(line_starts, quote.offset)
        shown = " ".join(_QUOTE_MARKERS.sub("", quote.text).split())
        if quote.token is None:
            problems.append(
                CitationProblem(
                    line,
                    "The block quote has no citation token in its paragraph or on the next "
                    f'line: "{shown}"',
                )
            )
            continue
        # A token that does not resolve is already a problem, and its quote cannot be checked.
        cited = targets.get(quote.token.offset)
        if cited is None:
            continue
        if not quote.block and _comparable(quote.text) in _titles(cited):
            continue
        message = _quote_problem(index, cited, quote.token.identifier, quote.text, shown, bodies)
        if message is not None:
            problems.append(CitationProblem(line, message))
    return sorted(problems, key=lambda problem: problem.line)


def cited_ids(text: str) -> dict[int, list[str]]:
    """Find the ids that the citation tokens of a Markdown document name, line by line.

    A token counts here exactly when ``check_text`` reads it as a citation, so one inside a
    fenced code block or inline code does not.

    Args:
        text: The Markdown document.

    Returns:
        The lines that hold a token, counted from 1. Each one maps to the chapter ids and
        resource ids its tokens name, in the order of the tokens and without any edition.
    """
    line_starts = _line_starts(text)
    ids: dict[int, list[str]] = {}
    for token in _tokens(mask_code(text)):
        ids.setdefault(_line_of(line_starts, token.offset), []).append(token.identifier)
    return ids


@dataclass(frozen=True)
class CitationToken:
    """One citation token found in a text.

    Attributes:
        offset: Where the token starts in the text.
        text: The whole token, brackets included.
        reference: What is between the brackets after ``cite:``, an id with an optional
            ``@<edition>``.
    """

    offset: int
    text: str
    reference: str

    @property
    def identifier(self) -> str:
        """The chapter id or resource id the token names."""
        return self.reference.partition("@")[0]

    @property
    def edition(self) -> str | None:
        """The edition after the ``@``, or ``None`` when the token names none."""
        _, at, edition = self.reference.partition("@")
        return edition if at else None


@dataclass(frozen=True)
class _Quote:
    """One quote: where it starts, its text, the token that cites it, and its kind."""

    offset: int
    text: str
    token: CitationToken | None
    block: bool


def _read_text(root: Path, name: str) -> str:
    try:
        return (root / name).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as error:
        raise ReadPathError(_unreadable(root, name)) from error


def _read_json(root: Path, name: str) -> Any:
    try:
        return json.loads(_read_text(root, name))
    except ValueError as error:
        raise ReadPathError(_unreadable(root, name)) from error


def _unreadable(root: Path, name: str) -> str:
    return (
        f"{name} under {root} cannot be read. Pass --root with the directory of a library that "
        f"holds {CATALOG_INDEX}, or rebuild the indexes there with `{BUILD_COMMAND}`."
    )


def _without_frontmatter(text: str) -> str:
    lines = text.split("\n")
    if lines[0].rstrip() != _FRONTMATTER_FENCE:
        return text
    for number in range(1, len(lines)):
        if lines[number].rstrip() == _FRONTMATTER_FENCE:
            return "\n".join(lines[number + 1 :])
    return text


def _shown(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _person(person: PersonRecord) -> str:
    native = person["native_name"]
    return f"{person['name']} ({native})" if native else person["name"]


def _editions(editions: list[EditionRef]) -> str | None:
    return ", ".join(f"{ref['language']} {ref['version']}" for ref in editions) or None


def _chapter_pairs(
    index: Index, resource: ResourceRecord, chapter: ChapterRecord
) -> list[tuple[str, object]]:
    source = chapter["source"]
    pages = source["pages"]
    page_range = (
        str(pages["first"])
        if pages["first"] == pages["last"]
        else f"{pages['first']}-{pages['last']}"
    )
    return [
        ("id", chapter["id"]),
        ("title", chapter["title"]),
        ("section_label", chapter["section_label"]),
        ("part", chapter["part"]),
        ("order", chapter["order"]),
        ("resource", chapter["resource"]),
        ("resource_title", resource["title"]["english"]),
        ("author", _person(resource["author"])),
        ("language", chapter["language"]),
        ("edition", chapter["edition"]),
        ("edition_behind", chapter["edition_behind"]),
        ("newer_editions", _editions(chapter["newer_editions"])),
        (
            "edition_note",
            edition_note(chapter["language"], chapter["edition"], chapter["newer_editions"]),
        ),
        ("license_id", chapter["license_id"] or "none"),
        ("mirror_status", chapter["mirror_status"]),
        ("quote_permitted", chapter["quote_permitted"]),
        ("path", chapter["path"]),
        ("file", (index.root / chapter["path"]).resolve()),
        ("source_repository", source["repository"]),
        ("source_revision", source["revision"]),
        ("source_path", source["path"]),
        ("source_pages", page_range),
        ("extraction_status", chapter["extraction_status"]),
        *(
            ("erratum", f"{erratum['description']} Source: {erratum['source_url']}")
            for erratum in chapter["errata"]
        ),
        ("topics", ", ".join(chapter["topics"]) or None),
        ("official_url", official_url(resource)),
        ("citation", format_citation(resource, chapter)),
    ]


def _resource_pairs(resource: ResourceRecord) -> list[tuple[str, object]]:
    title = resource["title"]
    urls = resource["official_urls"]
    source = resource["source"]
    translator = resource["translator"]
    newest = [
        EditionRef(language=language, version=version)
        for language, version in resource["newest_editions"].items()
    ]
    text_note = None
    if not resource["quote_permitted"]:
        text_note = (
            "The text of this book is not in this library. Read it at an official URL above, "
            "and do not quote it."
        )
    return [
        ("id", resource["id"]),
        ("type", resource["type"]),
        ("collection", resource["collection"]),
        ("title", title["english"]),
        ("title_original", title["original"]),
        ("title_english_official", title["english_official"]),
        ("author", _person(resource["author"])),
        ("translator", _person(translator) if translator else None),
        ("languages", ", ".join(resource["languages"]) or None),
        ("license_id", resource["license_id"] or "none"),
        ("license_evidence", resource["license_evidence"]),
        ("license_permalink", resource["license_permalink"]),
        ("mirror_status", resource["mirror_status"]),
        ("quote_permitted", resource["quote_permitted"]),
        ("edition", resource["edition"]),
        ("edition_language", resource["edition_language"]),
        ("edition_behind", resource["edition_behind"] if resource["edition"] else None),
        ("newer_editions", _editions(resource["newer_editions"])),
        (
            "edition_note",
            edition_note(
                resource["edition_language"], resource["edition"], resource["newer_editions"]
            ),
        ),
        ("newest_editions", _editions(newest)),
        ("path", resource["path"]),
        ("license_path", resource["license_path"]),
        ("source_repository", source["repository"] if source else None),
        ("source_revision", source["revision"] if source else None),
        ("source_path", source["path"] if source else None),
        ("official_url", official_url(resource)),
        ("official_site", urls["site"]),
        ("official_repository", urls["repository"]),
        *(
            ("hosted_edition", f"{hosted['name']} {hosted['url']}")
            for hosted in urls["hosted_editions"]
        ),
        ("topics", ", ".join(resource["topics"]) or None),
        *(("notice", notice) for notice in resource["notices"]),
        *(("chapter", chapter_id) for chapter_id in resource["chapters"]),
        ("text_note", text_note),
    ]


def _line_starts(text: str) -> list[int]:
    starts = [0]
    for match in re.finditer("\n", text):
        starts.append(match.end())
    return starts


def _line_of(line_starts: list[int], offset: int) -> int:
    return bisect.bisect_right(line_starts, offset)


def opening_fence(line: str) -> str | None:
    """Return the fence of a line that opens a fenced code block.

    A run of backticks opens a block only when no backtick follows it on the line, which is the
    CommonMark rule for the info string. A line such as three backticks, a word, three
    backticks, and then text is inline code followed by text, and it opens nothing.

    Args:
        line: One line of Markdown that is outside a fenced code block.

    Returns:
        The run of backticks or tildes, or ``None`` when the line opens no block.
    """
    fence = CODE_FENCE.match(line)
    if fence is None:
        return None
    if fence.group(1).startswith("`") and "`" in line[fence.end() :]:
        return None
    return fence.group(1)


def mask_code(text: str) -> str:
    """Blank out fenced code blocks and inline code, keeping every offset and line break.

    A citation token or a link inside code is an example and not a reference, so callers
    search the masked text and read matches from the original at the same offsets.

    Args:
        text: The Markdown.

    Returns:
        The text with every character of code replaced by a space.
    """
    masked: list[str] = []
    open_fence: str | None = None
    for line in text.split("\n"):
        fence = CODE_FENCE.match(line)
        if open_fence is None:
            open_fence = opening_fence(line)
            if open_fence is not None:
                masked.append(" " * len(line))
            else:
                masked.append(_INLINE_CODE.sub(lambda match: " " * len(match.group(0)), line))
            continue
        # A block closes on a bare fence of the same character that is at least as long.
        if fence and fence.group(1).startswith(open_fence) and not line[fence.end() :].strip():
            open_fence = None
        masked.append(" " * len(line))
    return "\n".join(masked)


def _comparable(text: str) -> str:
    r"""Reduce Markdown to the words a quote is compared on.

    Only markup goes: the marks of a block quote, the backticks around a code span, the
    backslash of an escape, and emphasis delimiters that pair. A code span keeps its text as
    written. A lone asterisk, an underscore inside a word, and a backslash in front of a letter
    are text, and stay. White space is joined.

    Escapes are undone before code spans and emphasis are looked for, so an escaped mark reads
    as the markup it spells. A chapter that writes ``\*word\*`` and a quote that writes
    ``*word*`` both reduce to ``word``, which is what a reader who copies the page writes.
    """
    codes: list[str] = []

    def unwrap(match: re.Match[str]) -> str:
        codes.append(match[2])
        return _CODE_PLACEHOLDER

    unescaped = _ESCAPE.sub(r"\1", _QUOTE_MARKERS.sub("", text))
    prose = _CODE_SPAN.sub(unwrap, unescaped)
    paragraphs = [_without_emphasis(paragraph) for paragraph in _BLANK_LINE.split(prose)]
    restored = iter(codes)
    joined = re.sub(_CODE_PLACEHOLDER, lambda _: next(restored), "\n\n".join(paragraphs))
    return " ".join(joined.split())


def _without_emphasis(text: str) -> str:
    """Remove each pair of emphasis delimiters, inner pairs as well, from one paragraph."""
    while True:
        reduced = text
        for pair in _EMPHASIS_PAIRS:
            reduced = pair.sub(r"\1", reduced)
        if reduced == text:
            return text
        text = reduced


def _titles(cited: Resolved) -> set[str]:
    title = cited.resource["title"]
    titles = {_comparable(title["english"]), _comparable(title["original"])}
    if cited.chapter is not None:
        titles.add(_comparable(cited.chapter["title"]))
    return titles


def _inside_word(left: str, right: str) -> bool:
    """Say whether two neighboring characters are both ASCII letters or digits."""
    pair = left + right
    return pair.isascii() and pair.isalnum()


def _holds_whole(body: str, wanted: str) -> bool:
    """Say whether a body holds a text at a place where neither end of it cuts a word.

    An end cuts a word when the characters on both sides of it are ASCII letters or digits.
    Text in a script written without spaces has no such end, so it may start or stop anywhere.
    """
    if not wanted:
        return True
    start = body.find(wanted)
    while start != -1:
        end = start + len(wanted)
        cut_before = start > 0 and _inside_word(body[start - 1], wanted[0])
        cut_after = end < len(body) and _inside_word(wanted[-1], body[end])
        if not cut_before and not cut_after:
            return True
        start = body.find(wanted, start + 1)
    return False


def _quote_problem(
    index: Index, cited: Resolved, identifier: str, quote: str, shown: str, bodies: dict[str, str]
) -> str | None:
    resource = cited.resource
    if not resource["quote_permitted"]:
        return (
            f"The quote cites {identifier}, whose mirror status is {resource['mirror_status']}. "
            f'Its text is not in this library, so nothing may be quoted from it: "{shown}"'
        )
    chapter_ids = resource["chapters"] if cited.chapter is None else [cited.chapter["id"]]
    wanted = _comparable(quote)
    for chapter_id in chapter_ids:
        if chapter_id not in bodies:
            bodies[chapter_id] = _comparable(index.chapter_body(chapter_id))
        if _holds_whole(bodies[chapter_id], wanted):
            return None
    return f'The quote is not in {identifier} word for word: "{shown}"'


def _paragraphs(masked: str) -> Iterator[list[tuple[int, int]]]:
    """Yield each run of lines that hold text, as the start and end offset of every line."""
    paragraph: list[tuple[int, int]] = []
    offset = 0
    for line in masked.split("\n"):
        end = offset + len(line)
        if line.strip():
            paragraph.append((offset, end))
        elif paragraph:
            yield paragraph
            paragraph = []
        offset = end + 1
    if paragraph:
        yield paragraph


def _tokens(masked: str) -> list[CitationToken]:
    return [
        CitationToken(match.start(), match.group(0), match.group(1))
        for match in TOKEN_PATTERN.finditer(masked)
    ]


def _first_token(tokens: list[CitationToken], start: int, end: int) -> CitationToken | None:
    return next((token for token in tokens if start <= token.offset < end), None)


def _last_token(tokens: list[CitationToken], start: int, end: int) -> CitationToken | None:
    return next((token for token in reversed(tokens) if start <= token.offset < end), None)


def _long_enough(span: str) -> bool:
    """Say whether a quoted span is long enough to be a quote and not a term or a title."""
    if len(span.split()) >= _MINIMUM_QUOTE_WORDS:
        return True
    return len(_UNSPACED_CHARACTER.findall(span)) >= _MINIMUM_UNSPACED_CHARACTERS


def holds_quote(text: str) -> bool:
    """Say whether a text holds a quoted span that the citation checker reads as a quote.

    Args:
        text: One paragraph or one line of Markdown.

    Returns:
        True when a span between quotation marks is long enough to be a quote and not a term
        or a title.
    """
    return any(_long_enough(_quoted_text(span)) for span in _QUOTED_SPAN.finditer(text))


def _quoted_text(span: re.Match[str]) -> str:
    """Return the text inside a match of ``_QUOTED_SPAN``, without the tags of any element."""
    return _HTML_TAG.sub("", span[span.lastindex or 0])


def _quotes(text: str, masked: str, tokens: list[CitationToken]) -> Iterator[_Quote]:
    """Yield every block quote, and every quoted span in a paragraph that holds a token.

    The token of a quoted span is the first one after it in its paragraph. A span that no token
    follows takes the nearest token in front of it, so a token put on the wrong side of a quote
    does not keep the quote from being checked.
    """
    paragraphs = list(_paragraphs(masked))
    for number, paragraph in enumerate(paragraphs):
        paragraph_end = paragraph[-1][1]
        # The line after a block quote may sit below a blank line, where Markdown starts a new
        # paragraph, so the token is also looked for on the first line of the next paragraph.
        following = paragraphs[number + 1][0] if number + 1 < len(paragraphs) else None
        prose = list(masked[paragraph[0][0] : paragraph_end])
        run: list[tuple[int, int]] = []
        for line in [*paragraph, None]:
            quoted = line is not None and QUOTE_LINE.match(masked, line[0], line[1])
            # Markdown reads a line with no mark under a quote line as more of the same quote,
            # unless the line opens a block of its own.
            lazy = (
                bool(run)
                and line is not None
                and not quoted
                and _OPENS_BLOCK.match(masked, line[0], line[1]) is None
            )
            # The quotes of two list items are two quotes, each with its own token.
            opens_item = line is not None and _ITEM_QUOTE_LINE.match(masked, line[0], line[1])
            if run and ((not quoted and not lazy) or opens_item):
                start, end = run[0][0], run[-1][1]
                token = _first_token(tokens, start, paragraph_end)
                if token is None and following is not None:
                    token = _first_token(tokens, following[0], following[1])
                quote = TOKEN_PATTERN.sub("", text[start:end])
                if _comparable(quote):
                    yield _Quote(offset=start, text=quote, token=token, block=True)
                base = paragraph[0][0]
                prose[start - base : end - base] = " " * (end - start)
                run = []
            if (quoted or lazy) and line is not None:
                run.append(line)
        base = paragraph[0][0]
        for span in _QUOTED_SPAN.finditer("".join(prose)):
            start, end = base + span.start(), base + span.end()
            group = span.lastindex or 0
            # The text is read from the original at the same offsets, because inline code in
            # the masked text is blanked.
            quote = _HTML_TAG.sub("", text[base + span.start(group) : base + span.end(group)])
            block = group == _HTML_BLOCK_QUOTE_GROUP
            if not (_comparable(quote) if block else _long_enough(quote)):
                continue
            token = _first_token(tokens, end, paragraph_end) or _last_token(tokens, base, start)
            if token is None and block and following is not None:
                token = _first_token(tokens, following[0], following[1])
            if token is not None or block:
                yield _Quote(offset=start, text=quote, token=token, block=block)
