"""Turn spans of extracted text into the sections of a book.

The functions here are pure. They take spans as plain data and a book's extraction profile, and
they return sections that hold headings, paragraphs, quotes, tables, and code blocks in reading
order. Nothing in this module reads a file.

How the spans are read:

1. Spans on a left-out page are dropped.
2. Spans are grouped into lines by page and baseline, and each line is read left to right. The
   order the spans arrive in does not matter.
3. Each span gets a role from the profile's rules. The rules are tried in order and the first
   one whose font size and indent bounds fit wins. The indent is the left edge of the span's
   line, so a line that is drawn word by word is still one kind of text.
4. A span at the code size inside a line of other text is inline code. A line that holds only
   code is a line of a code block.
5. A span at the section-label size that matches the profile's section-start pattern opens a
   section. The section-title spans that follow it are the title.
6. Lines of one role that follow each other closely are one paragraph, one table row, or one
   code block. A gap wider than ``BREAK_GAP`` times the font size starts a new one.

A span that fits no rule is reported in ``Extraction.unmatched`` and left out of the blocks.
"""

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from kb.catalog import ExtractionProfile, Role, RoleRule
from kb.pdf_spans import Span

__all__ = [
    "BREAK_GAP",
    "SIZE_TOLERANCE",
    "Block",
    "Cell",
    "CodeBlock",
    "Extraction",
    "Run",
    "Section",
    "Table",
    "TextBlock",
    "build_sections",
    "section_text",
]

SIZE_TOLERANCE = 0.1
"""Largest difference between a reported font size and a rule's size that still matches.

pypdf reports 26.66 for a size a profile records as 26.7. Sizes that mean different things are
at least half a point apart in the books seen so far.
"""

BREAK_GAP = 1.65
"""Baseline distance, in multiples of the font size, above which a new paragraph or row starts.

Wrapped lines sit 1.3 to 1.4 font sizes apart in the first book mirrored, paragraphs 1.9 apart,
and table rows 2.4 or more apart. A book set with much looser lines or much tighter paragraphs
needs its paragraphs and rows repaired by hand.
"""

_BASELINE_TOLERANCE = 2.0
_COLUMN_TOLERANCE = 1.0

_TABLE_ROLES = frozenset({Role.TABLE_HEADER, Role.TABLE_CELL})
# A heading or a kicker is never cut by a page break, so only these are joined across one.
_ROLES_JOINED_ACROSS_PAGES = frozenset({Role.LEDE, Role.BODY, Role.QUOTE})

# Closing punctuation, then any closing quotes or brackets, straight or curly.
_SENTENCE_END = re.compile("[.!?:][\"'\u201d\u2019)\\]]*$")
_HYPHEN_END = re.compile(r"\w-$")


@dataclass(frozen=True)
class Run:
    """A stretch of inline text with one treatment.

    Attributes:
        text: The text. Whitespace inside a block is already reduced to single spaces.
        link: Target of the link the text carries, or ``None``.
        code: Whether the text is inline code.
    """

    text: str
    link: str | None = None
    code: bool = False


type Cell = tuple[Run, ...]
"""The inline text of one table cell. An empty tuple is an empty cell."""


@dataclass(frozen=True)
class TextBlock:
    """A block of running text: a lede, a subsection heading, a paragraph, a kicker, or a quote.

    Attributes:
        role: Which of those the block is.
        runs: The inline text. Joining the runs' text gives the block's plain text.
    """

    role: Role
    runs: tuple[Run, ...]

    @property
    def text(self) -> str:
        """The block's text without links or code marks."""
        return _plain(self.runs)


@dataclass(frozen=True)
class Table:
    """A table.

    Attributes:
        header: One cell per column, or ``None`` for a table the source gives no header row.
        rows: The body rows. Every row has one cell per column.
    """

    header: tuple[Cell, ...] | None
    rows: tuple[tuple[Cell, ...], ...]


@dataclass(frozen=True)
class CodeBlock:
    """A block of code.

    Attributes:
        lines: The lines, with their leading spaces. An empty string is an empty line.
    """

    lines: tuple[str, ...]


type Block = TextBlock | Table | CodeBlock


@dataclass(frozen=True)
class Section:
    """One section of a book, which becomes one chapter file.

    Attributes:
        label: The label the source prints for the section, such as a section number.
        title: The section title on one line.
        first_page: Page the section's label is on, counted from 1.
        last_page: Page the section's last text is on, counted from 1.
        blocks: The section's content below the title, in reading order.
    """

    label: str
    title: str
    first_page: int
    last_page: int
    blocks: tuple[Block, ...]


@dataclass(frozen=True)
class Extraction:
    """The result of reading a book's spans.

    Attributes:
        sections: The sections in the order the source prints them.
        unmatched: Spans that are in no section, in reading order. A span lands here when its
            font size fits no rule of the profile, when it stands before the first section,
            when it has the section-label size and does not match the section-start pattern,
            or when it has the section-title size and does not follow a label.
    """

    sections: tuple[Section, ...]
    unmatched: tuple[Span, ...]


def build_sections(spans: Iterable[Span], profile: ExtractionProfile) -> Extraction:
    """Classify spans by the profile's rules and assemble them into sections.

    Args:
        spans: The spans of a book, in any order.
        profile: The book's extraction profile.

    Returns:
        The sections and the spans that fit nowhere.

    Raises:
        re.error: The profile's section-start pattern is not a valid regular expression.
    """
    section_start = re.compile(profile.section_start)
    excluded = set(profile.excluded_pages)
    unmatched: list[Span] = []
    builders: list[_SectionBuilder] = []
    for line_spans in _lines(span for span in spans if span.page not in excluded):
        for line in _classify(line_spans, profile.roles, unmatched):
            if line.role is Role.SECTION_LABEL:
                label = _plain(_runs(line.parts()))
                if section_start.search(label):
                    builders.append(_SectionBuilder(label, line.page))
                    continue
            elif builders and builders[-1].add(line):
                continue
            unmatched.extend(line.visible_spans())
    return Extraction(
        sections=tuple(builder.finish() for builder in builders), unmatched=tuple(unmatched)
    )


def section_text(section: Section) -> str:
    """Return the plain text of a section: its title and every block, one block per line.

    The section label is left out, because a chapter file carries it in its frontmatter and not
    in its text.

    Args:
        section: The section.

    Returns:
        The title, then each paragraph, table row, and code line on a line of its own.
    """
    lines = [section.title]
    for block in section.blocks:
        if isinstance(block, TextBlock):
            lines.append(block.text)
        elif isinstance(block, CodeBlock):
            lines.extend(block.lines)
        else:
            rows = block.rows if block.header is None else (block.header, *block.rows)
            lines.extend(" ".join(_plain(cell) for cell in row if cell) for row in rows)
    return "\n".join(lines)


type _Part = tuple[str, str | None, bool]
"""Text as the source holds it, the link it carries, and whether it is inline code."""


@dataclass(frozen=True)
class _Piece:
    """A span and whether it is code inside a line of other text."""

    span: Span
    inline_code: bool = False

    def part(self) -> _Part:
        return (self.span.text, self.span.link, self.inline_code)


@dataclass(frozen=True)
class _Line:
    """The spans of one line that belong to one block."""

    page: int
    y: float
    role: Role
    size: float
    pieces: tuple[_Piece, ...]

    def parts(self) -> list[_Part]:
        return [piece.part() for piece in self.pieces]

    def visible_spans(self) -> list[Span]:
        return [piece.span for piece in self.pieces if piece.span.text.strip()]


def _lines(spans: Iterable[Span]) -> list[list[Span]]:
    """Group spans that share a page and a baseline, top line first and left span first."""
    lines: list[list[Span]] = []
    for span in sorted(spans, key=lambda span: (span.page, -span.y)):
        if (
            lines
            and lines[-1][0].page == span.page
            and lines[-1][0].y - span.y <= _BASELINE_TOLERANCE
        ):
            lines[-1].append(span)
        else:
            lines.append([span])
    return [sorted(line, key=lambda span: span.x) for line in lines]


def _role(size: float, indent: float, rules: Sequence[RoleRule]) -> Role | None:
    for rule in rules:
        if (
            abs(size - rule.font_size) <= SIZE_TOLERANCE
            and (rule.min_indent is None or indent >= rule.min_indent)
            and (rule.max_indent is None or indent <= rule.max_indent)
        ):
            return rule.role
    return None


def _classify(
    spans: Sequence[Span], rules: Sequence[RoleRule], unmatched: list[Span]
) -> list[_Line]:
    """Split one line into the stretches that belong to different blocks.

    Most lines are one stretch. A section label and the title beside it are two. Code-size
    spans join the stretch they stand in, and a line of nothing but code is one stretch of code.
    """
    visible = [span for span in spans if span.text.strip()]
    if not visible:
        return []
    indent = min(span.x for span in visible)
    stretches: list[tuple[Role, list[tuple[Span, Role]]]] = []
    for span in spans:
        role = _role(span.size, indent, rules)
        if role is None:
            if span.text.strip():
                unmatched.append(span)
        elif stretches and role in (Role.CODE, stretches[-1][0]):
            stretches[-1][1].append((span, role))
        elif stretches and stretches[-1][0] is Role.CODE:
            # The line opened with inline code, which belongs to the text that follows it.
            stretches[-1] = (role, [*stretches[-1][1], (span, role)])
        else:
            stretches.append((role, [(span, role)]))

    lines: list[_Line] = []
    for role, members in stretches:
        pieces = tuple(
            _Piece(span, inline_code=role is not Role.CODE and span_role is Role.CODE)
            for span, span_role in members
        )
        line = _Line(
            page=spans[0].page,
            y=spans[0].y,
            role=role,
            size=next((piece.span.size for piece in pieces if not piece.inline_code), 0.0),
            pieces=pieces,
        )
        if line.visible_spans():
            lines.append(line)
    return lines


def _continues(pending: Sequence[_Line], line: _Line) -> bool:
    """Say whether a line belongs to the block that the pending lines are forming."""
    previous = pending[-1]
    if line.role in _TABLE_ROLES:
        # A header row below body rows opens another table.
        return previous.role in _TABLE_ROLES and not (
            line.role is Role.TABLE_HEADER
            and any(earlier.role is Role.TABLE_CELL for earlier in pending)
        )
    if line.role is not previous.role:
        return False
    if line.role is Role.CODE:
        return True
    if line.page == previous.page:
        return previous.y - line.y <= BREAK_GAP * line.size
    # Across a page break the gap says nothing, so the text decides: a paragraph that stops
    # without closing punctuation is still going.
    return line.role in _ROLES_JOINED_ACROSS_PAGES and not _SENTENCE_END.search(
        _plain(_runs(previous.parts())).rstrip()
    )


class _SectionBuilder:
    """Collects the lines of one section and turns each group of lines into a block."""

    def __init__(self, label: str, page: int) -> None:
        self._label = label
        self._first_page = page
        self._last_page = page
        self._title: list[_Line] = []
        self._blocks: list[Block] = []
        self._pending: list[_Line] = []

    def add(self, line: _Line) -> bool:
        """Take a line into the section, or return False for a line that has no place in it."""
        if line.role is Role.SECTION_TITLE:
            if self._blocks or self._pending:
                return False
            self._title.append(line)
        else:
            if self._pending and not _continues(self._pending, line):
                self._flush()
            self._pending.append(line)
        self._last_page = line.page
        return True

    def finish(self) -> Section:
        self._flush()
        return Section(
            label=self._label,
            title=_plain(_runs(_joined([line.parts() for line in self._title]))),
            first_page=self._first_page,
            last_page=self._last_page,
            blocks=tuple(self._blocks),
        )

    def _flush(self) -> None:
        if not self._pending:
            return
        role = self._pending[0].role
        if role in _TABLE_ROLES:
            self._blocks.append(_table(self._pending))
        elif role is Role.CODE:
            self._blocks.append(_code_block(self._pending))
        else:
            parts = _joined([line.parts() for line in self._pending])
            self._blocks.append(TextBlock(role=role, runs=_runs(parts)))
        self._pending = []


def _code_block(lines: Sequence[_Line]) -> CodeBlock:
    text: list[str] = []
    for index, line in enumerate(lines):
        previous = lines[index - 1] if index else None
        if (
            previous is not None
            and previous.page == line.page
            and previous.y - line.y > BREAK_GAP * line.size
        ):
            text.append("")
        text.append("".join(piece.span.text for piece in line.pieces).rstrip())
    return CodeBlock(lines=tuple(text))


def _table(lines: Sequence[_Line]) -> Table:
    """Build a table from its lines. Columns come from x positions and rows from line gaps."""
    columns = _columns(lines)
    # Each cell collects its text line by line, because a cell may wrap.
    header: list[list[list[_Part]]] | None = None
    rows: list[list[list[list[_Part]]]] = []
    previous: _Line | None = None
    for line in lines:
        starts_row = (
            previous is None
            or previous.role is not line.role
            or previous.page != line.page
            or previous.y - line.y > BREAK_GAP * line.size
        )
        if line.role is Role.TABLE_HEADER:
            if header is None:
                header = [[] for _ in columns]
            row = header
        else:
            if starts_row:
                rows.append([[] for _ in columns])
            row = rows[-1]
        cells: dict[int, list[_Part]] = {}
        for piece in line.pieces:
            cells.setdefault(_column(piece.span.x, columns), []).append(piece.part())
        for index, parts in cells.items():
            row[index].append(parts)
        previous = line
    return Table(
        header=None if header is None else tuple(_runs(_joined(cell)) for cell in header),
        rows=tuple(tuple(_runs(_joined(cell)) for cell in row) for row in rows),
    )


def _columns(lines: Sequence[_Line]) -> list[float]:
    """Return the left edge of each column.

    The first line of the table, which is the header row when there is one, sets the columns.
    A header may leave its first cell empty, so text further left in a later line adds a column
    in front.
    """
    columns: list[float] = []
    for span in lines[0].visible_spans():
        if not columns or span.x - columns[-1] > _COLUMN_TOLERANCE:
            columns.append(span.x)
    leftmost = min(span.x for line in lines for span in line.visible_spans())
    if columns[0] - leftmost > _COLUMN_TOLERANCE:
        columns.insert(0, leftmost)
    return columns


def _column(x: float, columns: Sequence[float]) -> int:
    """Return the index of the last column that starts at or left of a position."""
    return max(
        (index for index, left in enumerate(columns) if left <= x + _COLUMN_TOLERANCE), default=0
    )


def _joined(lines: Sequence[Sequence[_Part]]) -> list[_Part]:
    """Join the lines of one block with a space, or with nothing after a hyphen.

    A line that ends in a hyphen was broken inside a hyphenated word. The hyphen is kept,
    because the source does not say whether the word has one when it is not broken.
    """
    parts: list[_Part] = []
    for line in lines:
        if parts:
            before = "".join(text for text, _, _ in parts).rstrip()
            after = "".join(text for text, _, _ in line).lstrip()
            if _HYPHEN_END.search(before) and after[:1].isalnum():
                parts = _stripped(parts, end=True)
                line = _stripped(line, end=False)
            else:
                parts.append((" ", None, False))
        parts.extend(line)
    return parts


def _stripped(parts: Sequence[_Part], *, end: bool) -> list[_Part]:
    """Remove the whitespace at one end of a sequence of parts."""
    kept = list(parts)
    edge = -1 if end else 0
    while kept and not kept[edge][0].strip():
        kept.pop(edge)
    if kept:
        text, link, code = kept[edge]
        kept[edge] = (text.rstrip() if end else text.lstrip(), link, code)
    return kept


def _runs(parts: Iterable[_Part]) -> tuple[Run, ...]:
    """Merge parts into runs, with whitespace reduced to single spaces between words.

    A space between a linked or code run and its neighbor is given to the plain text, so that a
    link or a code mark never begins or ends with a space.
    """
    runs: list[Run] = []
    space_pending = False
    for text, link, code in parts:
        words = text.split()
        if not words:
            space_pending = space_pending or bool(text)
            continue
        core = " ".join(words)
        space = bool(runs) and (space_pending or text[0].isspace())
        same = bool(runs) and runs[-1].link == link and runs[-1].code == code
        if same:
            runs[-1] = Run(runs[-1].text + (" " if space else "") + core, link, code)
        else:
            if space:
                if link is None and not code:
                    core = " " + core
                elif runs[-1].link is None and not runs[-1].code:
                    runs[-1] = Run(runs[-1].text + " ")
                else:
                    runs.append(Run(" "))
            runs.append(Run(core, link, code))
        space_pending = text[-1].isspace()
    return tuple(runs)


def _plain(runs: Iterable[Run]) -> str:
    return "".join(run.text for run in runs)
