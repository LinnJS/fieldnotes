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

Errata live in a chapter's frontmatter. They are not chapter text and take no part.
"""

import re
import unicodedata
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path

from kb.blocks import section_text
from kb.catalog import AcceptedDifference, ChapterFile, Resource
from kb.ingest import IngestError, extract_book
from kb.readpath import CODE_FENCE, opening_fence

__all__ = [
    "SIMILARITY_FLOOR",
    "BookFidelity",
    "FidelityResult",
    "check_book",
    "compare",
    "markdown_text",
    "report_lines",
    "words",
]

SIMILARITY_FLOOR = 0.98
"""Lowest sequence similarity between the words of a chapter and of its source that passes."""

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

# Marks that Markdown puts in front of a line or on a line of their own. The source has none of
# them, and several are spelled like an operator, so they go before the words are counted.
_QUOTE_MARKERS = re.compile(r" {0,3}(?:> ?)+")
_HEADING_MARKER = re.compile(r" {0,3}#{1,6}(?=\s|$)")
_LIST_MARKER = re.compile(r"\s*[-*+](?=\s|$)")
_RULE_LINE = re.compile(r" {0,3}(?:([-*_])(?: *\1){2,}|=+) *")
_TABLE_RULE_CELL = re.compile(r"\s*:?-+:?\s*")

_UNESCAPED_PIPE = re.compile(r"(?<!\\)\|")
# In reading order: a backslash escape, an inline code span, or a link. An escape is matched
# first so that an escaped backtick or bracket opens nothing.
_INLINE = re.compile(
    r"\\(?P<escaped>[!-/:-@\[-`{-~])"
    r"|(?<!`)(?P<ticks>`+)(?!`)(?P<code>.+?)(?<!`)(?P=ticks)(?!`)"
    r"|\[(?P<text>(?:\\.|[^\]\\])*)\]\((?:<[^>]*>|[^\s()]*(?:\([^\s()]*\)[^\s()]*)*)"
    r"(?:\s+\"[^\"]*\")?\)"
)


@dataclass(frozen=True)
class FidelityResult:
    """The outcome of comparing one chapter with its source.

    Attributes:
        chapter: The chapter id.
        passed: Whether the chapter matches its source.
        similarity: Sequence similarity of the two word lists, from 0.0 to 1.0.
        words_removed: Words the source has and the chapter lacks, beyond the accepted
            differences, in reading order.
        words_added: Words the chapter has and the source lacks, beyond the accepted
            differences, in reading order.
        message: What is wrong, on one line, naming the chapter and the first words that
            differ. It is empty when the chapter passed.
    """

    chapter: str
    passed: bool
    similarity: float
    words_removed: tuple[str, ...]
    words_added: tuple[str, ...]
    message: str


@dataclass(frozen=True)
class BookFidelity:
    """The outcome of comparing a book's chapters with its committed source file.

    Attributes:
        error: Why the source file could not be extracted, or ``None``. No chapter is compared
            when this is set.
        source: The source file the chapters were compared with, relative to the library root,
            or ``None`` when it could not be extracted.
        results: One result per chapter, in the order the chapters were given.
        missing: Titles of the sections of the source that none of the chapters holds, in
            the order of the source. A book with one is not mirrored in full.
    """

    error: IngestError | None
    source: Path | None
    results: tuple[FidelityResult, ...]
    missing: tuple[str, ...] = ()


def words(text: str) -> list[str]:
    """Reduce plain text to the words that the comparison counts.

    Args:
        text: Plain text.

    Returns:
        The words in order. Compatibility characters such as ligatures and non-breaking spaces
        are normalized, curly quotes and dashes become their plain forms, and punctuation at
        the start and end of each word is dropped. A sign or a currency mark in front of a
        number stays, a percent mark behind a number stays, and an operator that stands alone
        is a word. Case is kept.
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
    return word


def markdown_text(body: str) -> str:
    """Strip the Markdown markup from a chapter body.

    Fence lines of code blocks are dropped and the code is kept. Outside code, a link becomes
    its text, an inline code span becomes its content, a backslash escape becomes the character
    it escapes, and the cell separators of a table row become spaces. The marks that Markdown
    puts in front of a line are dropped, which are quote, heading, and list markers, and so is
    a line that is only a rule or the rule row of a table.

    Args:
        body: The Markdown below a chapter's frontmatter.

    Returns:
        The text, line for line.
    """
    lines: list[str] = []
    open_fence: str | None = None
    for line in body.split("\n"):
        fence = CODE_FENCE.match(line)
        if open_fence is not None:
            # A block closes on a bare fence of the same character that is at least as long.
            if fence and fence[1].startswith(open_fence) and not line[fence.end() :].strip():
                open_fence = None
            else:
                lines.append(line)
        elif (opened := opening_fence(line)) is not None:
            open_fence = opened
        else:
            lines.append(_strip_structure(line))
    return "\n".join(lines)


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
) -> FidelityResult:
    """Compare a chapter body with the plain text of its section in the source.

    Args:
        chapter_id: Id of the chapter, used to pick its accepted differences and to name it.
        source_text: Plain text of the section, as ``kb.blocks.section_text`` returns it.
        chapter_body: The chapter's Markdown body.
        accepted: The book's accepted differences. Entries for other chapters are ignored.

    Returns:
        The result. It fails when the words differ beyond the accepted differences, when an
        accepted difference is listed that the chapter does not have, or when the word order
        scores below ``SIMILARITY_FLOOR``.
    """
    source = words(source_text)
    chapter = words(markdown_text(chapter_body))

    # A positive count is a word the chapter has too often, a negative one a word it lacks.
    balance = Counter(chapter)
    balance.subtract(source)
    for difference in accepted:
        if difference.chapter == chapter_id:
            balance.update(word for listed in difference.words_removed for word in words(listed))
            balance.subtract(word for listed in difference.words_added for word in words(listed))

    shared = next(
        (
            index
            for index, (ours, theirs) in enumerate(zip(chapter, source, strict=False))
            if ours != theirs
        ),
        min(len(chapter), len(source)),
    )
    added = _in_reading_order(
        chapter[shared:], {word: count for word, count in balance.items() if count > 0}
    )
    removed = _in_reading_order(
        source[shared:], {word: -count for word, count in balance.items() if count < 0}
    )
    similarity = SequenceMatcher(None, source, chapter, autojunk=False).ratio()

    if added or removed:
        message = (
            f"The chapter {chapter_id} does not have the words of its source. "
            f"Words only in the chapter: {_named(added)}. "
            f"Words only in the source: {_named(removed)}."
        )
    elif similarity < SIMILARITY_FLOOR:
        message = (
            f"The chapter {chapter_id} has the words of its source in a different order. The "
            f"similarity is {similarity:.3f} and must be at least {SIMILARITY_FLOOR}. They "
            f'first differ where the chapter reads "{_context(chapter, shared)}" and the '
            f'source reads "{_context(source, shared)}".'
        )
    else:
        message = ""
    return FidelityResult(
        chapter=chapter_id,
        passed=not message,
        similarity=similarity,
        words_removed=removed,
        words_added=added,
        message=message,
    )


def check_book(root: Path, resource: Resource, chapters: Sequence[ChapterFile]) -> BookFidelity:
    """Compare chapters of a book with a fresh extraction of its committed source file.

    A chapter is matched to a section through the book's extraction profile: the profile gives
    the title that belongs to the chapter's slug, and the extraction gives the section with that
    title.

    Args:
        root: The library root.
        resource: The book.
        chapters: The chapter files to compare.

    Returns:
        One result per chapter, and the sections of the source that no chapter holds. When
        the source file cannot be extracted, the report holds the error and no results.
    """
    profile = resource.extraction_profile
    try:
        book = extract_book(root, resource)
    except IngestError as error:
        return BookFidelity(error=error, source=None, results=())
    # extract_book refuses a book that has no profile, so these are never empty by default.
    assignments = () if profile is None else profile.sections
    accepted = () if profile is None else profile.accepted_differences
    titles = {assignment.slug: assignment.title for assignment in assignments}
    sections = {section.title: section for section in book.sections}

    results: list[FidelityResult] = []
    for chapter_file in chapters:
        chapter = chapter_file.chapter
        title = titles.get(chapter.slug)
        section = None if title is None else sections.get(title)
        if section is not None:
            results.append(compare(chapter.id, section_text(section), chapter_file.body, accepted))
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
    return BookFidelity(error=None, source=book.source, results=tuple(results), missing=missing)


def report_lines(resource: Resource, report: BookFidelity) -> list[str]:
    """Describe a comparison for a person.

    Args:
        resource: The book that was compared.
        report: The outcome of ``check_book`` for that book.

    Returns:
        The lines to print: the source file, one line per chapter with the message of each
        failure below it, one line per section that no chapter holds, every accepted difference
        of the book with its reason, and a count.
    """
    lines = [] if report.source is None else [f"Source: {report.source.as_posix()}"]
    for result in report.results:
        verdict = "pass" if result.passed else "FAIL"
        lines.append(f"  {verdict}  {result.chapter}  similarity {result.similarity:.3f}")
        if not result.passed:
            lines.append(f"        {result.message}")
    lines.extend(f'  MISSING  no chapter holds the section "{title}"' for title in report.missing)
    profile = resource.extraction_profile
    accepted = () if profile is None else profile.accepted_differences
    lines.append(f"Accepted differences: {len(accepted)}")
    lines.extend(
        f"  {difference.chapter}  removed: {', '.join(difference.words_removed) or 'none'}  "
        f"added: {', '.join(difference.words_added) or 'none'}  reason: {difference.reason}"
        for difference in accepted
    )
    failed = sum(not result.passed for result in report.results)
    count = f"Chapters checked: {len(report.results)}. Failed: {failed}."
    if report.missing:
        count += f" Sections with no chapter: {len(report.missing)}."
    lines.append(count)
    return lines


def _strip_inline(text: str) -> str:
    def plain(match: re.Match[str]) -> str:
        if match["escaped"] is not None:
            return match["escaped"]
        if match["code"] is not None:
            return match["code"]
        return _strip_inline(match["text"])

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
