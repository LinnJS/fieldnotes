"""Chapter and topic files: YAML frontmatter records and the Markdown body below them.

A chapter or topic file opens with a ``---`` line, holds YAML up to the next ``---`` line, and
continues with Markdown. The loaders here validate the YAML against its schema and return a frozen
record together with the body.
"""

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

from kb.schema import LoadError, SchemaName, parse_yaml, read_text, validate

_FENCE = "---"


class ExtractionStatus(StrEnum):
    """How far review of a chapter has gone."""

    MACHINE_EXTRACTED = "machine-extracted"
    HUMAN_REVIEWED = "human-reviewed"


@dataclass(frozen=True)
class PageRange:
    """First and last page of a section, counted from 1 in the source file's own page index."""

    first: int
    last: int


@dataclass(frozen=True)
class ChapterSource:
    """Where a chapter's text came from.

    Attributes:
        repository: Upstream Git repository as ``owner/name``.
        revision: Full commit SHA of the pinned source.
        path: Path of the source file inside the upstream repository.
        pages: The pages the section spans in the source file.
    """

    repository: str
    revision: str
    path: str
    pages: PageRange


@dataclass(frozen=True)
class Erratum:
    """A known upstream erratum. It is recorded beside the text and never applied to it."""

    description: str
    source_url: str


@dataclass(frozen=True)
class Chapter:
    """The frontmatter of one chapter file.

    Attributes:
        id: Chapter id in the form ``<resource-id>/<slug>``. It never changes.
        resource: Id of the resource the chapter belongs to.
        title: Section title.
        part: Name of the part of the book that holds the section.
        order: Reading position within the book, starting at 1.
        section_label: The label the source prints for the section.
        language: Language code of the text.
        edition: Version of the edition the text was taken from.
        source: Where the text came from.
        extraction_status: How far review has gone.
        errata: Known upstream errata, empty when there are none.
    """

    id: str
    resource: str
    title: str
    part: str
    order: int
    section_label: str
    language: str
    edition: str
    source: ChapterSource
    extraction_status: ExtractionStatus
    errata: tuple[Erratum, ...]

    @property
    def slug(self) -> str:
        """The part of the id after the slash, which the chapter's file name ends with."""
        return self.id.partition("/")[2]


@dataclass(frozen=True)
class TopicReference:
    """One reference from a topic to a resource.

    Attributes:
        resource: Id of the referenced resource.
        chapter: Chapter id when the reference points at one chapter, otherwise ``None``.
        note: Why the reference is relevant, in the library's own words.
    """

    resource: str
    chapter: str | None
    note: str


@dataclass(frozen=True)
class Topic:
    """The frontmatter of one topic document."""

    id: str
    title: str
    references: tuple[TopicReference, ...]


def split_frontmatter(text: str) -> tuple[str, str]:
    """Split a Markdown document into its YAML frontmatter and its body.

    Args:
        text: The whole document.

    Returns:
        The YAML between the two fence lines, and the body with leading blank lines removed.

    Raises:
        ValueError: The text does not open with a ``---`` line, or that fence is never closed.
    """
    lines = text.split("\n")
    if lines[0].rstrip() != _FENCE:
        raise ValueError("The file must start with a '---' line that opens the frontmatter.")
    for index in range(1, len(lines)):
        if lines[index].rstrip() == _FENCE:
            frontmatter = "\n".join(lines[1:index])
            body = "\n".join(lines[index + 1 :]).lstrip("\n")
            return frontmatter, body
    raise ValueError("The frontmatter is never closed by a second '---' line.")


def load_chapter(path: Path) -> tuple[Chapter, str]:
    """Load one chapter file.

    Args:
        path: The chapter's Markdown file.

    Returns:
        The chapter's frontmatter record and its Markdown body.

    Raises:
        LoadError: The file cannot be read, has no frontmatter, holds malformed YAML, breaks the
            chapter schema, or has an id that does not begin with its resource id.
    """
    data, body = _load(path, "chapter")
    chapter = _chapter(data)
    prefix = f"{chapter.resource}/"
    if not chapter.id.startswith(prefix):
        raise LoadError(
            path,
            f"The chapter id {chapter.id!r} must begin with {prefix!r}, its resource id and a "
            "slash.",
            json_path="$.id",
        )
    return chapter, body


def load_topic(path: Path) -> tuple[Topic, str]:
    """Load one topic document.

    Args:
        path: The topic's Markdown file.

    Returns:
        The topic's frontmatter record and its Markdown body.

    Raises:
        LoadError: The file cannot be read, has no frontmatter, holds malformed YAML, or breaks
            the topic schema.
    """
    data, body = _load(path, "topic")
    return _topic(data), body


def _load(path: Path, schema: SchemaName) -> tuple[dict[str, Any], str]:
    try:
        frontmatter, body = split_frontmatter(read_text(path))
    except ValueError as error:
        raise LoadError(path, f"The frontmatter could not be found. {error}") from error
    return validate(parse_yaml(frontmatter, path), schema, path), body


def _chapter(data: dict[str, Any]) -> Chapter:
    source = data["source"]
    return Chapter(
        id=data["id"],
        resource=data["resource"],
        title=data["title"],
        part=data["part"],
        order=int(data["order"]),
        section_label=data["section_label"],
        language=data["language"],
        edition=data["edition"],
        source=ChapterSource(
            repository=source["repository"],
            revision=source["revision"],
            path=source["path"],
            pages=PageRange(first=int(source["pages"]["first"]), last=int(source["pages"]["last"])),
        ),
        extraction_status=ExtractionStatus(data["extraction_status"]),
        errata=tuple(
            Erratum(description=erratum["description"], source_url=erratum["source_url"])
            for erratum in data.get("errata", ())
        ),
    )


def _topic(data: dict[str, Any]) -> Topic:
    return Topic(
        id=data["id"],
        title=data["title"],
        references=tuple(
            TopicReference(
                resource=reference["resource"],
                chapter=reference.get("chapter"),
                note=reference["note"],
            )
            for reference in data["references"]
        ),
    )
