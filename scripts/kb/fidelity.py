"""The fidelity comparison: a chapter must say what its pinned source says.

A chapter is compared with its own section from a fresh extraction of the committed source
file. A chapter shares its first and last page with its neighbors, so the section is the right
thing to compare with and the raw text of the pages is not.

Both texts are reduced to words. Markdown markup is stripped from the chapter. Typographic
variants of quotes, dashes, spaces, and ligatures are made equal, and punctuation at the edges
of a word is dropped, so that markup and spacing never count as a difference. Punctuation inside
a word stays, so ``1,300`` and ``1,800`` are different words. Marks that carry meaning of their
own stay as well: an operator that stands alone, such as ``>=``, a sign or a currency mark in
front of a number, and a percent mark behind one.

Two rules then apply:

1. The chapter and the source hold the same words the same number of times. One changed name,
   one flipped number, or one dropped word fails. A difference passes only when the book's
   extraction profile lists it for that chapter under ``accepted_differences``.
2. The order of the words scores ``SIMILARITY_FLOOR`` or higher on sequence similarity, which
   leaves room for a table or a callout that was repaired into reading order.

A block that a person put back in the order its page prints can move more words than the floor
leaves room for, as when the page prints two boxes side by side and the extraction reads across
them. The extraction profile records such a block under ``accepted_reorders`` with its page and
two readings: the block as the chapter holds it and the block as a fresh extraction reads it.
The record applies when the chapter holds the first reading once, the source holds the second
once, and the two differ by no word beyond what ``accepted_differences`` lists for the chapter.
The second rule then scores the chapter with the extraction's reading in place of the block. The
first rule always compares the chapter as written, and a record that does not apply fails the
chapter. Each reading of one record holds at most ``REORDER_WORD_LIMIT`` words, so no record
can switch the second rule off for a whole chapter.

Errata live in a chapter's frontmatter. They are not chapter text and take no part.
"""

import re
import unicodedata
from collections import Counter
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass, replace
from difflib import SequenceMatcher
from pathlib import Path
from typing import NamedTuple

from kb.blocks import Section, section_links, section_text
from kb.catalog import AcceptedDifference, AcceptedReorder, ChapterFile, Resource
from kb.frontmatter import Chapter
from kb.ingest import IngestError, extract_book
from kb.markdown import link_target
from kb.pdf_spans import Span
from kb.readpath import CODE_FENCE, opening_fence

__all__ = [
    "REORDER_WORD_LIMIT",
    "SIMILARITY_FLOOR",
    "BookFidelity",
    "FidelityResult",
    "check_book",
    "compare",
    "link_destinations",
    "markdown_text",
    "report_lines",
    "words",
]

SIMILARITY_FLOOR = 0.98
"""Lowest sequence similarity between the words of a chapter and of its source that passes."""

REORDER_WORD_LIMIT = 200
"""Most words each reading of one accepted reorder may hold.

A record scores its block as the extraction reads it, so a record with no limit on either
reading could cover a whole chapter. A short passage paired with a long extraction would put
the long reading in place of a few words.
"""

_WORDS_NAMED = 8
_CONTEXT_BEFORE = 2
_CONTEXT_AFTER = 6

_VARIANTS = str.maketrans(
    {
        "\u2018": "'",
        "\u2019": "'",
        "\u201c": '"',
        "\u201d": '"',
        "\u2010": "-",
        "\u2011": "-",
        "\u2012": "-",
        "\u2013": "-",
        "\u2014": "-",
        "\u2212": "-",
    }
)
# The punctuation in front of a word, the word, and the punctuation behind it.
_WORD_PARTS = re.compile(r"([\W_]*)(.*?)([\W_]*)", re.DOTALL)
# A token that holds no letter or digit and is still a word of the text. A bullet, an arrow, or
# a stray bracket is not one, because extraction and Markdown render those differently.
_OPERATOR = re.compile(r"[-<>=!+/%~^&]+")
_SIGNS = "+-"
_NAME_SUFFIX = re.compile(r"[+#]+")

# Marks that Markdown puts in front of a line or on a line of their own. The source has none of
# them, and several are spelled like an operator, so they go before the words are counted.
_QUOTE_MARKERS = re.compile(r" {0,3}(?:> ?)+")
_HEADING_MARKER = re.compile(r" {0,3}#{1,6}(?=\s|$)")
_LIST_MARKER = re.compile(r"\s*[-*+](?=\s|$)")
_RULE_LINE = re.compile(r" {0,3}(?:([-*_])(?: *\1){2,}|=+) *")
_TABLE_RULE_CELL = re.compile(r"\s*:?-+:?\s*")

_UNESCAPED_PIPE = re.compile(r"(?<!\\)\|")
# In reading order: a backslash escape, an inline code span, or a link. An escape is matched
# first so that an escaped backtick or bracket opens nothing. A link gives its text, its
# destination as written, and the text of its title. A link written in any other form matches
# nothing here, so its destination and title are counted as words of the chapter.
_INLINE = re.compile(
    r"\\(?P<escaped>[!-/:-@\[-`{-~])"
    r"|(?<!`)(?P<ticks>`+)(?!`)(?P<code>.+?)(?<!`)(?P=ticks)(?!`)"
    r"|\[(?P<text>(?:\\.|[^\]\\])*)\]"
    r"\((?P<target><[^>]*>|[^\s()]*(?:\([^\s()]*\)[^\s()]*)*)"
    r"(?:\s+\"(?P<title>[^\"]*)\")?\)"
)


@dataclass(frozen=True)
class FidelityResult:
    """The outcome of comparing one chapter with its source.

    Attributes:
        chapter: The chapter id.
        passed: Whether the chapter matches its source.
        similarity: Sequence similarity of the two word lists, from 0.0 to 1.0, with the
            extraction's reading in place of each accepted reorder that applies.
        words_removed: Words the source has and the chapter lacks, beyond the accepted
            differences, in reading order.
        words_added: Words the chapter has and the source lacks, beyond the accepted
            differences, in reading order.
        message: What is wrong, on one line, naming the chapter and the first words that
            differ. It is empty when the chapter passed.
        frontmatter: One line for each frontmatter field that is not what the pinned source
            and the extracted section give. The indexes, the citation, and the edition notice
            are all written from the frontmatter, so a wrong field misleads a reader even when
            every word of the body matches.
        similarity_as_written: Sequence similarity of the chapter as written, or ``None`` when
            no accepted reorder applies to it.
    """

    chapter: str
    passed: bool
    similarity: float
    words_removed: tuple[str, ...]
    words_added: tuple[str, ...]
    message: str
    frontmatter: tuple[str, ...] = ()
    similarity_as_written: float | None = None


@dataclass(frozen=True)
class BookFidelity:
    """The outcome of comparing a book's chapters with its committed source file.

    Attributes:
        error: Why the source file could not be extracted, or why its sections cannot be
            matched to chapters, or ``None``. No chapter is compared when this is set.
        source: The source file the chapters were compared with, relative to the library root,
            or ``None`` when it could not be extracted.
        results: One result per chapter, in the order the chapters were given.
        missing: Titles of the sections of the source that none of the chapters holds, in
            the order of the source. A book with one is not mirrored in full.
        unmatched: Spans of the source that fit no role rule of the profile, in reading order.
            They are in no section, so no chapter holds them and no comparison sees them. A
            book with one is not mirrored in full either.
    """

    error: IngestError | None
    source: Path | None
    results: tuple[FidelityResult, ...]
    missing: tuple[str, ...] = ()
    unmatched: tuple[Span, ...] = ()


def words(text: str) -> list[str]:
    """Reduce plain text to the words that the comparison counts.

    Returns:
        The words in order. Compatibility characters such as ligatures and non-breaking spaces
        are normalized, curly quotes and dashes become their plain forms, and punctuation at
        the start and end of each word is dropped. A sign or a currency mark in front of a
        number stays, a percent mark behind a number stays, a run of plus or number signs
        behind a letter or a digit stays, and an operator that stands alone is a word. Case
        is kept.
    """
    normalized = unicodedata.normalize("NFKC", text).translate(_VARIANTS)
    return [word for word in map(_word, normalized.split()) if word]


def _word(token: str) -> str:
    """Reduce one white-space token to the word the comparison counts, or to an empty string."""
    parts = _WORD_PARTS.fullmatch(token)
    assert parts is not None
    before, word, after = parts.groups()
    if not word:
        return token if _OPERATOR.fullmatch(token) else ""
    if word[0].isdigit() and before:
        mark = before[-1]
        if mark in _SIGNS or unicodedata.category(mark) == "Sc":
            word = mark + word
    if word[-1].isdigit() and after.startswith("%"):
        word += "%"
    # A run of plus or number signs behind a letter or a digit is part of a name, as in C++,
    # C#, and 18+, so dropping it would make two names one word.
    suffix = _NAME_SUFFIX.match(after)
    if suffix is not None and word[-1].isalnum():
        word += suffix[0]
    return word


def markdown_text(body: str) -> str:
    """Strip the Markdown markup from a chapter body.

    Fence lines of code blocks are dropped and the code is kept. Outside code, a link becomes
    its text followed by the text of its title, an inline code span becomes its content, a
    backslash escape becomes the character it escapes, and the cell separators of a table row
    become spaces. The marks that Markdown puts in front of a line are dropped, which are
    quote, heading, and list markers, and so is a line that is only a rule or the rule row of
    a table.

    Args:
        body: The Markdown below a chapter's frontmatter.

    Returns:
        The text, line for line.
    """
    return "\n".join(
        line if in_code else _strip_structure(line) for line, in_code in _content_lines(body)
    )


def link_destinations(body: str) -> tuple[str, ...]:
    """List the destination of every inline link of a chapter body, as the chapter writes it.

    A link inside a code block or an inline code span is shown and not followed, so it is left
    out.

    Args:
        body: The Markdown below a chapter's frontmatter.

    Returns:
        The destinations in reading order, with the angle brackets a destination is written in.
    """
    return tuple(
        match["target"]
        for line, in_code in _content_lines(body)
        if not in_code
        for match in _INLINE.finditer(line)
        if match["target"] is not None
    )


def _content_lines(body: str) -> Iterator[tuple[str, bool]]:
    """Yield each line of a chapter body that is not a code fence, and whether it is code.

    Words that follow the language on an opening fence line are yielded as a line of prose.
    """
    open_fence: str | None = None
    for line in body.split("\n"):
        fence = CODE_FENCE.match(line)
        if open_fence is not None:
            # A block closes on a bare fence of the same character that is at least as long.
            if fence and fence[1].startswith(open_fence) and not line[fence.end() :].strip():
                open_fence = None
            else:
                yield line, True
        elif (opened := opening_fence(line)) is not None:
            open_fence = opened
            # The one word after the fence names the language of the block. Anything after
            # that word is text on the page of the canonical file, so the source must hold it.
            beyond = line[fence.end() :].split(None, 1)[1:] if fence else []
            if beyond:
                yield beyond[0], False
        else:
            yield line, False


def _strip_structure(line: str) -> str:
    """Strip the markup from one line of Markdown that is outside a code block."""
    quoted = _QUOTE_MARKERS.match(line)
    if quoted:
        line = line[quoted.end() :]
    if _RULE_LINE.fullmatch(line):
        return ""
    if line.lstrip().startswith("|"):
        cells = [
            cell for cell in _UNESCAPED_PIPE.split(line) if not _TABLE_RULE_CELL.fullmatch(cell)
        ]
        return " ".join(_strip_inline(cell.replace("\\|", "|")) for cell in cells)
    for marker in (_HEADING_MARKER, _LIST_MARKER):
        found = marker.match(line)
        if found:
            line = line[found.end() :]
    return _strip_inline(line)


def compare(
    chapter_id: str,
    source_text: str,
    chapter_body: str,
    accepted: Sequence[AcceptedDifference] = (),
    source_links: Sequence[str] | None = None,
    reorders: Sequence[AcceptedReorder] = (),
) -> FidelityResult:
    """Compare a chapter body with the plain text of its section in the source.

    Args:
        chapter_id: Id of the chapter, used to pick its accepted differences and to name it.
        source_text: Plain text of the section, as ``kb.blocks.section_text`` returns it.
        chapter_body: The chapter's Markdown body.
        accepted: The book's accepted differences. Entries for other chapters are ignored.
        source_links: The link targets the section holds in reading order, as
            ``kb.blocks.section_links`` returns them. ``None`` leaves the destinations of the
            chapter unchecked, which is for a caller that has the plain text alone.
        reorders: The book's accepted reorders. Entries for other chapters are ignored.

    Returns:
        The result. It fails when the words differ beyond the accepted differences, when an
        accepted difference is listed that the chapter does not have, when an accepted reorder
        of the chapter does not apply, when the word order scores below ``SIMILARITY_FLOOR``
        with each reorder that applies in place, or when the destinations of the chapter's links,
        in reading order and counted once per link, are not those of the section. A link
        reads the same whatever it points at, so the words alone cannot show a destination
        that was added, repeated, or swapped with another.
    """
    source = words(source_text)
    chapter = words(markdown_text(chapter_body))

    # A positive count is a word the chapter has too often, a negative one a word it lacks.
    own_accepted = [difference for difference in accepted if difference.chapter == chapter_id]
    balance = Counter(chapter)
    balance.subtract(source)
    balance.update(_listed_words(own_accepted, removed=True))
    balance.subtract(_listed_words(own_accepted, removed=False))

    shared = _first_difference(chapter, source)
    added = _in_reading_order(
        chapter[shared:], {word: count for word, count in balance.items() if count > 0}
    )
    removed = _in_reading_order(
        source[shared:], {word: -count for word, count in balance.items() if count < 0}
    )
    own_reorders = [reorder for reorder in reorders if reorder.chapter == chapter_id]
    scored, applied, problems = _apply_reorders(
        chapter_id, chapter, source, own_reorders, own_accepted
    )
    similarity = SequenceMatcher(None, source, scored, autojunk=False).ratio()
    as_written = SequenceMatcher(None, source, chapter, autojunk=False).ratio() if applied else None

    parts: list[str] = []
    if added or removed:
        parts.append(
            f"The chapter {chapter_id} does not have the words of its source. "
            f"Words only in the chapter: {_named(added)}. "
            f"Words only in the source: {_named(removed)}."
        )
    parts.extend(problems)
    if not (added or removed) and similarity < SIMILARITY_FLOOR:
        # The scored list is the one that failed, so the first difference is named there and
        # never inside a block that a reorder already accounts for.
        first = _first_difference(scored, source)
        parts.append(
            f"The chapter {chapter_id} has the words of its source in a different order. The "
            f"similarity is {similarity:.3f} and must be at least {SIMILARITY_FLOOR}. They "
            f'first differ where the chapter reads "{_context(scored, first)}" and the '
            f'source reads "{_context(source, first)}".'
        )
    message = " ".join(parts)
    if source_links is not None:
        wanted = tuple(link_target(link) for link in source_links)
        found = link_destinations(chapter_body)
        if found != wanted:
            message = " ".join(
                [
                    message or f"The chapter {chapter_id} does not have the links of its source.",
                    _link_difference(found, wanted),
                ]
            )
    return FidelityResult(
        chapter=chapter_id,
        passed=not message,
        similarity=similarity,
        words_removed=removed,
        words_added=added,
        message=message,
        similarity_as_written=as_written,
    )


class _Placement(NamedTuple):
    """Where an accepted reorder that applies stands, and the words that score in its place."""

    span: range
    source_span: range
    page: int
    extraction: list[str]


def _listed_words(differences: Sequence[AcceptedDifference], *, removed: bool) -> list[str]:
    """List every word that accepted differences remove from the source, or that they add."""
    return [
        word
        for difference in differences
        for listed in (difference.words_removed if removed else difference.words_added)
        for word in words(listed)
    ]


def _apply_reorders(
    chapter_id: str,
    chapter: list[str],
    source: list[str],
    reorders: Sequence[AcceptedReorder],
    accepted: Sequence[AcceptedDifference],
) -> tuple[list[str], int, list[str]]:
    """Check the accepted reorders of one chapter and put each one that applies in place.

    Args:
        chapter_id: Id of the chapter, used to name it in a message.
        chapter: The chapter's words as written.
        source: The words of the chapter's section in the source.
        reorders: The accepted reorders of this chapter, in the order the profile lists them.
        accepted: The accepted differences of this chapter.

    Returns:
        The chapter's words with the extraction's reading in place of each passage that
        applies, how many applied, and one message for each reorder that does not apply.
    """
    # A word the two readings differ by must be listed, and two records cannot claim one
    # listed word between them, so each record takes its words from what is left.
    left_added = Counter(_listed_words(accepted, removed=False))
    left_removed = Counter(_listed_words(accepted, removed=True))
    placed: list[_Placement] = []
    problems: list[str] = []
    for reorder in reorders:
        passage = words(markdown_text(reorder.passage))
        extraction = words(markdown_text(reorder.extraction))
        named = f"The accepted reorder of the chapter {chapter_id} on page {reorder.page}"
        if not passage or not extraction:
            problems.append(f"{named} has no words in its passage or in its extraction.")
            continue
        if len(passage) > REORDER_WORD_LIMIT:
            problems.append(
                f"{named} has a passage of {len(passage)} words, and a reorder may hold at "
                f"most {REORDER_WORD_LIMIT}."
            )
            continue
        if len(extraction) > REORDER_WORD_LIMIT:
            problems.append(
                f"{named} has an extraction of {len(extraction)} words, and a reorder may hold "
                f"at most {REORDER_WORD_LIMIT}."
            )
            continue
        in_chapter = _runs(chapter, passage)
        if not in_chapter:
            problems.append(
                f"{named} has a passage that the chapter does not hold. The chapter may have "
                "changed since the reorder was recorded."
            )
            continue
        if len(in_chapter) > 1:
            problems.append(
                f"{named} has a passage that the chapter holds {len(in_chapter)} times. "
                "Lengthen the passage until the chapter holds it once."
            )
            continue
        in_source = _runs(source, extraction)
        if not in_source:
            problems.append(
                f"{named} has an extraction that the source does not hold. Copy the block from "
                "a fresh draft."
            )
            continue
        if len(in_source) > 1:
            problems.append(
                f"{named} has an extraction that the source holds {len(in_source)} times. "
                "Lengthen both readings until the source holds the extraction once."
            )
            continue
        if passage == extraction:
            problems.append(
                f"{named} has a passage that reads as its extraction does, so there is no "
                "reorder to record."
            )
            continue
        needs_added = Counter(passage) - Counter(extraction)
        needs_removed = Counter(extraction) - Counter(passage)
        beyond_added = needs_added - left_added
        beyond_removed = needs_removed - left_removed
        if beyond_added or beyond_removed:
            problems.append(
                f"{named} has a passage that differs from its extraction by words that "
                "accepted_differences does not list for the chapter. Words only in the passage: "
                f"{_named(_in_reading_order(passage, dict(beyond_added)))}. Words only in the "
                f"extraction: {_named(_in_reading_order(extraction, dict(beyond_removed)))}."
            )
            continue
        span = range(in_chapter[0], in_chapter[0] + len(passage))
        source_span = range(in_source[0], in_source[0] + len(extraction))
        overlapped = next(
            (
                taken.page
                for taken in placed
                if _overlap(span, taken.span) or _overlap(source_span, taken.source_span)
            ),
            None,
        )
        if overlapped is not None:
            problems.append(f"{named} overlaps the accepted reorder on page {overlapped}.")
            continue
        left_added -= needs_added
        left_removed -= needs_removed
        placed.append(_Placement(span, source_span, reorder.page, extraction))

    scored = list(chapter)
    # From the end, so that a replacement of another length leaves earlier positions in place.
    for placement in sorted(placed, key=lambda taken: taken.span.start, reverse=True):
        scored[placement.span.start : placement.span.stop] = placement.extraction
    return scored, len(placed), problems


def _runs(sequence: Sequence[str], run: Sequence[str]) -> list[int]:
    """List every position where the words of a run stand unbroken in a sequence."""
    width = len(run)
    wanted = list(run)
    return [
        start
        for start in range(len(sequence) - width + 1)
        if sequence[start] == wanted[0] and list(sequence[start : start + width]) == wanted
    ]


def _overlap(first: range, second: range) -> bool:
    return first.start < second.stop and second.start < first.stop


def _first_difference(ours: Sequence[str], theirs: Sequence[str]) -> int:
    return next(
        (
            index
            for index, (mine, other) in enumerate(zip(ours, theirs, strict=False))
            if mine != other
        ),
        min(len(ours), len(theirs)),
    )


def check_book(root: Path, resource: Resource, chapters: Sequence[ChapterFile]) -> BookFidelity:
    """Compare chapters of a book with a fresh extraction of its committed source file.

    A chapter is matched to a section through the book's extraction profile: the profile gives
    the title that belongs to the chapter's slug, and the extraction gives the section with that
    title.

    Returns:
        One result per chapter, the sections of the source that no chapter holds, and the
        spans of the source that are in no section. When the source file cannot be extracted,
        or two of its sections have one title, the report holds the error and no results.
    """
    profile = resource.extraction_profile
    try:
        book = extract_book(root, resource)
    except IngestError as error:
        return BookFidelity(error=error, source=None, results=())
    # A chapter is found by its section's title, so of two sections with one title only the
    # last could be compared, and the other would be reported nowhere.
    counted = Counter(section.title for section in book.sections)
    repeated = [title for title, count in counted.items() if count > 1]
    if repeated:
        named = ", ".join(f'"{title}"' for title in repeated)
        return BookFidelity(
            error=IngestError(
                f"The source file {book.source.as_posix()} has more than one section titled "
                f"{named}, and the extraction profile finds a section by its title, so no "
                "chapter of the book can be matched to its section.",
                "Stop, leave the book and its record as they are, and report the book to the "
                "owner. The profile cannot tell these sections apart.",
            ),
            source=book.source,
            results=(),
        )
    # extract_book refuses a book that has no profile, so these are never empty by default.
    assignments = () if profile is None else profile.sections
    accepted = () if profile is None else profile.accepted_differences
    reorders = () if profile is None else profile.accepted_reorders
    titles = {assignment.slug: assignment.title for assignment in assignments}
    parts = {assignment.slug: assignment.part for assignment in assignments}
    sections = {section.title: section for section in book.sections}
    orders = {section.title: order for order, section in enumerate(book.sections, start=1)}

    results: list[FidelityResult] = []
    for chapter_file in chapters:
        chapter = chapter_file.chapter
        title = titles.get(chapter.slug)
        section = None if title is None else sections.get(title)
        if section is not None:
            result = compare(
                chapter.id,
                section_text(section),
                chapter_file.body,
                accepted,
                section_links(section),
                reorders,
            )
            differing = _frontmatter_differences(
                chapter, resource, section, orders[section.title], parts[chapter.slug]
            )
            pages = chapter.source.pages
            # The check cannot tell which page a block of the source stands on, so the page a
            # reorder names is held to the chapter's pages and the reviewer reads the rest.
            outside = [
                f"The accepted reorder of the chapter {chapter.id} names page {reorder.page}, "
                f"and the chapter holds pages {pages.first} to {pages.last}."
                for reorder in reorders
                if reorder.chapter == chapter.id and not pages.first <= reorder.page <= pages.last
            ]
            if outside:
                result = replace(
                    result, passed=False, message=" ".join([result.message, *outside]).strip()
                )
            results.append(replace(result, frontmatter=differing))
            continue
        reason = (
            f"The book's extraction_profile assigns the slug {chapter.slug} to no section."
            if title is None
            else f'The source file has no section titled "{title}".'
        )
        results.append(
            FidelityResult(
                chapter=chapter.id,
                passed=False,
                similarity=0.0,
                words_removed=(),
                words_added=(),
                message=f"The chapter {chapter.id} has no section in the source. {reason}",
            )
        )
    held = {titles.get(chapter_file.chapter.slug) for chapter_file in chapters}
    missing = tuple(section.title for section in book.sections if section.title not in held)
    return BookFidelity(
        error=None,
        source=book.source,
        results=tuple(results),
        missing=missing,
        unmatched=book.unmatched,
    )


def _frontmatter_differences(
    chapter: Chapter, resource: Resource, section: Section, order: int, part: str
) -> tuple[str, ...]:
    """Name each frontmatter field of a chapter that is not what its source gives.

    The expected values are the ones ``kb.markdown.draft_chapters`` writes for the section. The
    extraction status and the errata are set by a person and are not compared.

    Args:
        chapter: The frontmatter of the chapter.
        resource: The book, whose pinned source names the edition and the file.
        section: The extracted section the chapter holds.
        order: Position of the section in the source, counted from 1.
        part: The part the extraction profile assigns to the section.
    """
    expected: list[tuple[str, object, object]] = [
        ("title", chapter.title, section.title),
        ("part", chapter.part, part),
        ("order", chapter.order, order),
        ("section_label", chapter.section_label, section.label),
        ("source.pages.first", chapter.source.pages.first, section.first_page),
        ("source.pages.last", chapter.source.pages.last, section.last_page),
    ]
    pinned = resource.pinned_source
    if pinned is not None:
        expected += [
            ("language", chapter.language, pinned.language),
            ("edition", chapter.edition, pinned.edition),
            ("source.repository", chapter.source.repository, pinned.repository),
            ("source.revision", chapter.source.revision, pinned.commit),
            ("source.path", chapter.source.path, pinned.path),
        ]
    return tuple(
        f"{field} is {found!r}, and the pinned source gives {wanted!r}"
        for field, found, wanted in expected
        if found != wanted
    )


def report_lines(resource: Resource, report: BookFidelity) -> list[str]:
    """Describe a comparison for a person.

    Args:
        resource: The book that was compared.
        report: The outcome of ``check_book`` for that book.

    Returns:
        The lines to print: the source file, one line per chapter with the message of each
        failure and each differing frontmatter field below it, one line per section that no
        chapter holds, one line per span that is in no section, every accepted difference and
        every accepted reorder of the book with its reason, and a count. The line of a chapter
        that an accepted reorder applies to gives its similarity as written as well.
    """
    lines = [] if report.source is None else [f"Source: {report.source.as_posix()}"]
    for result in report.results:
        verdict = "pass" if result.passed and not result.frontmatter else "FAIL"
        line = f"  {verdict}  {result.chapter}  similarity {result.similarity:.3f}"
        if result.similarity_as_written is not None:
            line += f" ({result.similarity_as_written:.3f} as written)"
        lines.append(line)
        if not result.passed:
            lines.append(f"        {result.message}")
        lines.extend(f"        {difference}" for difference in result.frontmatter)
    lines.extend(f'  MISSING  no chapter holds the section "{title}"' for title in report.missing)
    lines.extend(
        f"  UNMATCHED  page {span.page}: {span.text.strip()!r}" for span in report.unmatched
    )
    profile = resource.extraction_profile
    accepted = () if profile is None else profile.accepted_differences
    lines.append(f"Accepted differences: {len(accepted)}")
    lines.extend(
        f"  {difference.chapter}  removed: {', '.join(difference.words_removed) or 'none'}  "
        f"added: {', '.join(difference.words_added) or 'none'}  reason: {difference.reason}"
        for difference in accepted
    )
    reorders = () if profile is None else profile.accepted_reorders
    lines.append(f"Accepted reorders: {len(reorders)}")
    lines.extend(
        f"  {reorder.chapter}  page {reorder.page}  "
        f"{len(words(markdown_text(reorder.passage)))} words  reason: {reorder.reason}"
        for reorder in reorders
    )
    failed = sum(not result.passed or bool(result.frontmatter) for result in report.results)
    count = f"Chapters checked: {len(report.results)}. Failed: {failed}."
    if report.missing:
        count += f" Sections with no chapter: {len(report.missing)}."
    if report.unmatched:
        count += f" Spans in no chapter: {len(report.unmatched)}."
    lines.append(count)
    return lines


def _listed(destinations: Iterable[str]) -> str:
    return ", ".join(sorted(destinations)) or "none"


def _link_difference(found: Sequence[str], wanted: Sequence[str]) -> str:
    """Say how the destinations of a chapter differ from those of its section, in reading order.

    A destination counts once for each link that points at it, so one written twice where the
    section has it once is a destination only in the chapter.
    """
    extra = Counter(found)
    extra.subtract(wanted)
    if any(extra.values()):
        return (
            f"Destinations only in the chapter: {_listed((+extra).elements())}. "
            f"Destinations only in the source: {_listed((-extra).elements())}."
        )
    number, ours, theirs = next(
        (number, ours, theirs)
        for number, (ours, theirs) in enumerate(zip(found, wanted, strict=True), start=1)
        if ours != theirs
    )
    return (
        "The chapter links to the destinations of its source in another order. "
        f"Link {number} points at {ours}, where the source points at {theirs}."
    )


def _strip_inline(text: str) -> str:
    def plain(match: re.Match[str]) -> str:
        if match["escaped"] is not None:
            return match["escaped"]
        if match["code"] is not None:
            return match["code"]
        # The source has no place for a title, so its words are words of the chapter alone.
        title = f" {match['title']}" if match["title"] else ""
        return _strip_inline(match["text"]) + title

    return _INLINE.sub(plain, text)


def _in_reading_order(sequence: Sequence[str], surplus: dict[str, int]) -> tuple[str, ...]:
    """List each surplus word as often as it is surplus, in the order the sequence reads."""
    remaining = dict(surplus)
    found: list[str] = []
    for word in sequence:
        if remaining.get(word, 0) > 0:
            remaining[word] -= 1
            found.append(word)
    # A word that an accepted difference lists and neither text holds is in no sequence.
    for word in sorted(remaining):
        found.extend([word] * remaining[word])
    return tuple(found)


def _named(listed: Sequence[str]) -> str:
    if not listed:
        return "none"
    more = len(listed) - _WORDS_NAMED
    return ", ".join(listed[:_WORDS_NAMED]) + (f" (and {more} more)" if more > 0 else "")


def _context(sequence: Sequence[str], index: int) -> str:
    return " ".join(sequence[max(0, index - _CONTEXT_BEFORE) : index + _CONTEXT_AFTER])
