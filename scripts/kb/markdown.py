"""Write sections as chapter files: YAML frontmatter and a Markdown body.

The functions here are pure. They take sections as plain data and return text, and the same
input always gives the same bytes. The frontmatter keys are written in a fixed order, and a
value is quoted only when YAML would read it as something other than the string it is.

A chapter body opens with the section title as a level-one heading. Subsection headings are
level two. A page number is written only from a section's own page range, which comes from the
page index of the source file.
"""

import json
import re
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass

from kb.blocks import Block, Cell, CodeBlock, Run, Section, Table
from kb.catalog import Resource, Role
from kb.frontmatter import ExtractionStatus

__all__ = [
    "UNASSIGNED_PART",
    "ChapterDraft",
    "backtick_fence",
    "draft_chapters",
    "link_target",
    "propose_slug",
    "render_body",
]

UNASSIGNED_PART = "Unassigned"
"""Part written for a section that the book's extraction profile does not list yet."""

_CODE_LANGUAGE = "text"

_ALWAYS_ESCAPED = re.compile(r"[\\`*\[\]<]")
# An underscore inside a word is plain text. One at the edge of a word would open emphasis.
_EDGE_UNDERSCORE = re.compile(r"(?<![A-Za-z0-9])_|_(?![A-Za-z0-9])")
_LIST_NUMBER = re.compile(r"(\d+)([.)])(?=\s|$)")
_BLOCK_MARK = re.compile(r"(#{1,6}|[>+-])(?=\s|$)")
_BACKTICKS = re.compile(r"`+")
_NEEDS_ANGLE_BRACKETS = re.compile(r"[\s()<>]")

_PLAIN_SCALAR = re.compile(r"[A-Za-z][A-Za-z0-9 ._/-]*")
_YAML_WORDS = frozenset({"true", "false", "null", "yes", "no", "on", "off", "y", "n"})


@dataclass(frozen=True)
class ChapterDraft:
    """One chapter file as ingestion would write it.

    Attributes:
        chapter_id: The chapter id, ``<resource-id>/<slug>``.
        slug: The section's slug.
        slug_is_proposed: Whether the slug was made from the title because the book's
            extraction profile assigns the section none. A proposed slug is not recorded
            anywhere until a person adds it to the profile.
        order: Position of the section in the source, starting at 1.
        section: The section the draft was written from.
        file_name: Name of the chapter file, ``NN-<slug>.md``.
        text: The whole file: frontmatter and body.
    """

    chapter_id: str
    slug: str
    slug_is_proposed: bool
    order: int
    section: Section
    file_name: str
    text: str


def draft_chapters(resource: Resource, sections: Sequence[Section]) -> tuple[ChapterDraft, ...]:
    """Write one chapter draft per section of a book.

    A section's slug and part come from the entry of the book's extraction profile that has the
    section's title. A section with no entry gets a slug proposed from its title and the part
    ``UNASSIGNED_PART``. Every draft has the extraction status ``machine-extracted``.

    Args:
        resource: The book. It must have a pinned source and an extraction profile.
        sections: The book's sections in source order.

    Returns:
        The drafts in source order.

    Raises:
        ValueError: The resource has no pinned source or no extraction profile.
    """
    if resource.pinned_source is None or resource.extraction_profile is None:
        raise ValueError(
            f"The resource {resource.id} needs a pinned_source and an extraction_profile "
            "before chapters can be written for it."
        )
    assigned = {assignment.title: assignment for assignment in resource.extraction_profile.sections}
    drafts: list[ChapterDraft] = []
    for order, section in enumerate(sections, start=1):
        assignment = assigned.get(section.title)
        slug = propose_slug(section.title) if assignment is None else assignment.slug
        chapter_id = f"{resource.id}/{slug}"
        pinned = resource.pinned_source
        frontmatter = [
            f"id: {_scalar(chapter_id)}",
            f"resource: {_scalar(resource.id)}",
            f"title: {_scalar(section.title)}",
            f"part: {_scalar(UNASSIGNED_PART if assignment is None else assignment.part)}",
            f"order: {order}",
            f"section_label: {_scalar(section.label)}",
            f"language: {_scalar(pinned.language)}",
            f"edition: {_scalar(pinned.edition)}",
            "source:",
            f"  repository: {_scalar(pinned.repository)}",
            f"  revision: {_scalar(pinned.commit)}",
            f"  path: {_scalar(pinned.path)}",
            "  pages:",
            f"    first: {section.first_page}",
            f"    last: {section.last_page}",
            f"extraction_status: {ExtractionStatus.MACHINE_EXTRACTED.value}",
        ]
        drafts.append(
            ChapterDraft(
                chapter_id=chapter_id,
                slug=slug,
                slug_is_proposed=assignment is None,
                order=order,
                section=section,
                file_name=f"{order:02d}-{slug}.md",
                text="---\n" + "\n".join(frontmatter) + "\n---\n\n" + render_body(section),
            )
        )
    return tuple(drafts)


def backtick_fence(text: str) -> str:
    """Return a code fence that no run of backticks in the text can close.

    Returns:
        A run of backticks one longer than the longest run in the text, and at least three.
    """
    longest = max((len(ticks) for ticks in _BACKTICKS.findall(text)), default=0)
    return "`" * max(3, longest + 1)


def render_body(section: Section) -> str:
    """Render a section as the Markdown body of a chapter file.

    Returns:
        The title as a level-one heading and then each block, with one empty line between
        blocks and one line break at the end.
    """
    blocks = [f"# {_inline((Run(section.title),))}", *(_block(block) for block in section.blocks)]
    return "\n\n".join(blocks) + "\n"


def propose_slug(title: str) -> str:
    """Make a kebab-case slug from a section title.

    Returns:
        The title in lowercase ASCII letters and digits with single hyphens between words.
        Accents and apostrophes are dropped. A title with no letter or digit gives ``section``.
    """
    ascii_title = unicodedata.normalize("NFKD", title).encode("ascii", "ignore").decode("ascii")
    words = re.sub(r"[^a-z0-9]+", "-", ascii_title.lower().replace("'", "")).strip("-")
    return words or "section"


def _scalar(value: str) -> str:
    """Write a string as a YAML scalar, quoted unless it is plainly a string."""
    if (
        _PLAIN_SCALAR.fullmatch(value)
        and value.lower() not in _YAML_WORDS
        and value == value.strip()
    ):
        return value
    # A JSON string is a valid YAML double-quoted scalar.
    return json.dumps(value, ensure_ascii=False)


def _block(block: Block) -> str:
    if isinstance(block, Table):
        return _table(block)
    if isinstance(block, CodeBlock):
        return _code(block)
    text = _inline(block.runs)
    if block.role is Role.HEADING:
        return f"## {text}"
    if block.role is Role.KICKER:
        return f"*{text}*"
    text = _LIST_NUMBER.sub(r"\1\\\2", text, count=1) if _LIST_NUMBER.match(text) else text
    text = f"\\{text}" if _BLOCK_MARK.match(text) else text
    return f"> {text}" if block.role is Role.QUOTE else text


def _inline(runs: Sequence[Run]) -> str:
    return "".join(_run(run) for run in runs)


def _run(run: Run) -> str:
    if run.code:
        longest = max((len(ticks) for ticks in _BACKTICKS.findall(run.text)), default=0)
        fence = "`" * (longest + 1)
        text = f"{fence} {run.text} {fence}" if longest else f"`{run.text}`"
    else:
        text = _EDGE_UNDERSCORE.sub(r"\\_", _ALWAYS_ESCAPED.sub(r"\\\g<0>", run.text))
    if run.link is None:
        return text
    return f"[{text}]({link_target(run.link)})"


def link_target(target: str) -> str:
    """Write a link target of the source as the destination of a Markdown link.

    Returns:
        The destination. One that holds white space, a parenthesis, or an angle bracket is put
        in angle brackets, with any angle bracket of its own percent-encoded.
    """
    if _NEEDS_ANGLE_BRACKETS.search(target):
        return "<" + target.replace("<", "%3C").replace(">", "%3E") + ">"
    return target


def _table(table: Table) -> str:
    width = max(len(row) for row in (table.header or (), *table.rows))
    header: tuple[Cell, ...] = table.header or ((),) * width
    lines = [_row(header), "| " + " | ".join(["---"] * width) + " |"]
    lines.extend(_row(row) for row in table.rows)
    return "\n".join(lines)


def _row(cells: Sequence[Cell]) -> str:
    return "| " + " | ".join(_inline(cell).replace("|", "\\|") for cell in cells) + " |"


def _code(block: CodeBlock) -> str:
    fence = backtick_fence("\n".join(block.lines))
    return "\n".join([f"{fence}{_CODE_LANGUAGE}", *block.lines, fence])
