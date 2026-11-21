"""Typed records for a library and the loader that builds them.

A library is a directory that holds ``catalog.yaml``, one ``books/<id>/metadata.yaml`` per
resource, optional chapter files under ``books/<id>/chapters/``, and topic documents under
``topics/``. The loader takes the library root as an argument, so the same code reads the real
library and a test library.

Every file is validated against its JSON Schema before a record is built from it. The builders
below therefore index into the validated mappings without checking shapes again.
"""

import re
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any, Literal

from kb.frontmatter import Chapter, Topic, load_chapter, load_topic
from kb.schema import LoadError, load_yaml_file

__all__ = [
    "AcceptedDifference",
    "Catalog",
    "ChapterFile",
    "Collection",
    "Edition",
    "EditionPattern",
    "EvidenceKind",
    "ExtractionProfile",
    "GitSource",
    "HostedEdition",
    "Library",
    "LibraryInfo",
    "License",
    "LoadError",
    "MirrorStatus",
    "NewestEdition",
    "OfficialUrls",
    "Permission",
    "Permissions",
    "Person",
    "PinnedSource",
    "Resource",
    "ResourceType",
    "Role",
    "RoleRule",
    "SectionAssignment",
    "Titles",
    "TopicFile",
    "UrlSource",
    "load_catalog",
    "load_chapters",
    "load_library",
    "load_resource",
    "load_topics",
    "version_key",
]

CATALOG_FILE = "catalog.yaml"
BOOKS_DIR = "books"
METADATA_FILE = "metadata.yaml"
LICENSE_FILE = "LICENSE"
"""Name of the upstream license text inside a mirrored book's directory."""
CHAPTERS_DIR = "chapters"
TOPICS_DIR = "topics"

_NOT_DIGITS = re.compile(r"\D+")

# The topics directory also holds a hand-written landing page, which is not a topic document.
TOPIC_INDEX_FILE = "index.md"


class ResourceType(StrEnum):
    """Kind of resource. Only books exist in this version."""

    BOOK = "book"


class MirrorStatus(StrEnum):
    """How much of a resource the library carries."""

    MIRRORED = "mirrored"
    ELIGIBLE = "eligible"
    REFERENCE_ONLY = "reference-only"


class EvidenceKind(StrEnum):
    """Where a resource's license terms were found."""

    LICENSE_FILE = "license-file"
    README_STATEMENT = "readme-statement"
    NONE = "none"


class Permission(StrEnum):
    """Three-valued answer to whether the recorded terms let a reader do something."""

    ALLOWED = "allowed"
    DENIED = "denied"
    UNCLEAR = "unclear"


class Role(StrEnum):
    """What a span of extracted text is."""

    SECTION_LABEL = "section-label"
    SECTION_TITLE = "section-title"
    LEDE = "lede"
    HEADING = "heading"
    BODY = "body"
    KICKER = "kicker"
    QUOTE = "quote"
    TABLE_HEADER = "table-header"
    TABLE_CELL = "table-cell"
    CODE = "code"


@dataclass(frozen=True)
class LibraryInfo:
    """The library's own names and URLs. Every display name comes from here.

    Attributes:
        name: Short machine name of the library.
        title: Display title.
        description: One or two sentences that say what the library is.
        base_url: URL the published site is served from.
        repository: URL of the library's own source repository.
    """

    name: str
    title: str
    description: str
    base_url: str
    repository: str


@dataclass(frozen=True)
class Collection:
    """A named group of resources."""

    id: str
    title: str


@dataclass(frozen=True)
class Catalog:
    """The contents of ``catalog.yaml``.

    Attributes:
        library: The library's own names and URLs.
        license_allowlist: SPDX ids whose books may be mirrored when the license gate passes.
        collections: The collections a resource may belong to.
        resources: Resource ids in display order.
    """

    library: LibraryInfo
    license_allowlist: tuple[str, ...]
    collections: tuple[Collection, ...]
    resources: tuple[str, ...]


@dataclass(frozen=True)
class Titles:
    """A work's title in its original language and in English.

    Attributes:
        original: Title in the language the work was first published in.
        english: English title used for display.
        english_official: Whether the author publishes the English title. When false, the
            cataloger translated the original title and outputs must say so.
    """

    original: str
    english: str
    english_official: bool


@dataclass(frozen=True)
class Person:
    """An author or translator.

    Attributes:
        name: The name in Latin script.
        native_name: The name in its native script, or ``None`` when it does not differ.
        url: The person's own page, or ``None``.
    """

    name: str
    native_name: str | None
    url: str | None


@dataclass(frozen=True)
class HostedEdition:
    """A reading edition the author hosts outside the site and the repository."""

    name: str
    url: str
    note: str | None


@dataclass(frozen=True)
class OfficialUrls:
    """The author's own locations for a work.

    Attributes:
        site: The work's page on the author's site, or ``None``.
        repository: The upstream repository's web page, or ``None`` for a work with no repository.
        hosted_editions: Reading editions hosted elsewhere.
    """

    site: str | None
    repository: str | None
    hosted_editions: tuple[HostedEdition, ...]


@dataclass(frozen=True)
class GitSource:
    """An upstream Git repository.

    Attributes:
        kind: Always ``"git"``.
        repository: The repository as ``owner/name``.
        default_branch: The branch upstream publishes on.
        head_commit: Head of the default branch when the record was last verified by hand.
    """

    kind: Literal["git"]
    repository: str
    default_branch: str
    head_commit: str


@dataclass(frozen=True)
class UrlSource:
    """An upstream that is a web page and not a repository.

    Attributes:
        kind: Always ``"url"``.
        url: The page the work is published on.
    """

    kind: Literal["url"]
    url: str


@dataclass(frozen=True)
class Edition:
    """One edition that upstream publishes.

    Attributes:
        language: Language code of the edition.
        version: The edition's version, or ``None`` when upstream gives it none.
        format: Lowercase file format such as ``pdf``.
        path: Path inside the upstream repository, or the file's URL for a URL source.
        blob_sha: Git blob id of the file at the recorded head commit, or ``None`` for a URL
            source.
    """

    language: str
    version: str | None
    format: str
    path: str
    blob_sha: str | None


@dataclass(frozen=True)
class EditionPattern:
    """The filename regex that recognizes one language's editions.

    Attributes:
        language: Language code the pattern is for.
        pattern: Regex with a named capture group called ``version``.
    """

    language: str
    pattern: str


@dataclass(frozen=True)
class NewestEdition:
    """The newest upstream version in one language."""

    language: str
    version: str


@dataclass(frozen=True)
class License:
    """License evidence that a person read at the permalink.

    Attributes:
        spdx: SPDX license id, or ``None`` when the terms name no SPDX license.
        evidence: Where the terms were found.
        statement: The terms quoted verbatim in their original language, or ``None`` when no
            terms were found.
        permalink: Link to the quoted file at a full commit SHA, or ``None``.
        blob_sha: Git blob id of the quoted file, or ``None``.
        commit: Commit the evidence was read at, or ``None``.
        verified_on: Date a person verified the evidence, as ``YYYY-MM-DD``.
        departs_from_template: Whether the license text differs from the SPDX template.
        locations_checked: Every place that was searched for terms. It is never empty when no
            terms were found.
    """

    spdx: str | None
    evidence: EvidenceKind
    statement: str | None
    permalink: str | None
    blob_sha: str | None
    commit: str | None
    verified_on: str
    departs_from_template: bool
    locations_checked: tuple[str, ...]


@dataclass(frozen=True)
class Permissions:
    """What the recorded terms let a reader do.

    Attributes:
        redistribution: Whether copies may be passed on.
        adaptation: Whether the work may be changed or converted.
        commercial_use: Whether commercial use is permitted.
        attribution_required: Whether the author must be credited.
        share_alike: Whether adaptations must carry the same license.
        third_party_rights: Whether the work contains material whose rights the author cannot
            grant.
    """

    redistribution: Permission
    adaptation: Permission
    commercial_use: Permission
    attribution_required: bool
    share_alike: bool
    third_party_rights: bool


@dataclass(frozen=True)
class PinnedSource:
    """The exact upstream file a mirrored or eligible book is extracted from.

    Attributes:
        repository: Upstream Git repository as ``owner/name``.
        commit: Full commit SHA the file was taken at.
        path: Path of the file inside the upstream repository.
        sha256: SHA-256 of the file in lowercase hex.
        edition: Version of the pinned edition.
        language: Language code of the pinned edition.
        local_path: Committed copy of the file, relative to the book directory, such as
            ``source/book.pdf``. It is ``None`` until the file is committed.
    """

    repository: str
    commit: str
    path: str
    sha256: str
    edition: str
    language: str
    local_path: str | None


@dataclass(frozen=True)
class RoleRule:
    """One rule that gives a span of extracted text its role.

    Attributes:
        role: The role a matching span gets.
        font_size: Font size in points as the extractor reports it. The consumer compares it
            with a small tolerance.
        min_indent: Smallest left position in points the rule matches, inclusive, or ``None``
            for no lower bound.
        max_indent: Largest left position in points the rule matches, inclusive, or ``None``
            for no upper bound.
    """

    role: Role
    font_size: float
    min_indent: float | None
    max_indent: float | None


@dataclass(frozen=True)
class SectionAssignment:
    """The slug and part fixed for one section, found by the section's title."""

    title: str
    slug: str
    part: str


@dataclass(frozen=True)
class AcceptedDifference:
    """Word differences between a chapter and a fresh extraction that a person has accepted.

    Attributes:
        chapter: Id of the chapter the difference belongs to.
        words_removed: Words the extraction has and the chapter leaves out.
        words_added: Words the chapter has and the extraction lacks.
        reason: Why the difference is faithful to the source.
    """

    chapter: str
    words_removed: tuple[str, ...]
    words_added: tuple[str, ...]
    reason: str


@dataclass(frozen=True)
class ExtractionProfile:
    """How to turn a book's pinned source file into chapters.

    Attributes:
        roles: Rules tried in order, where the first match gives a span its role.
        section_start: Regex that a section-label span must match to start a new section.
        excluded_pages: Pages left out of extraction, counted from 1.
        sections: The slug and part fixed for each section.
        accepted_differences: Word differences a person has accepted, per chapter.
    """

    roles: tuple[RoleRule, ...]
    section_start: str
    excluded_pages: tuple[int, ...]
    sections: tuple[SectionAssignment, ...]
    accepted_differences: tuple[AcceptedDifference, ...]


@dataclass(frozen=True)
class Resource:
    """Everything recorded about one resource in its ``metadata.yaml``.

    Attributes:
        id: Unique id that names the work. It equals the directory name under ``books/``.
        type: Kind of resource.
        collection: Id of the collection the resource belongs to.
        title: Original and English titles.
        author: The author.
        translator: The translator, or ``None`` when upstream names none.
        languages: Languages the work is published in upstream.
        official_urls: The author's own locations for the work.
        site_slug: The slug the author's site uses for the work, or ``None``.
        upstream: Where the work is published.
        editions: Every edition upstream publishes.
        edition_patterns: One filename regex per language.
        newest_editions: The newest upstream version per language.
        license: The license evidence.
        permissions: What the recorded terms permit.
        mirror_status: The status the owner has approved. The license gate decides the highest
            status allowed.
        pinned_source: The pinned source file, or ``None`` for a book that has none.
        extraction_profile: How to extract chapters, or ``None`` for a book that has no profile.
        notices: Free-text notices shown with the resource.
    """

    id: str
    type: ResourceType
    collection: str
    title: Titles
    author: Person
    translator: Person | None
    languages: tuple[str, ...]
    official_urls: OfficialUrls
    site_slug: str | None
    upstream: GitSource | UrlSource
    editions: tuple[Edition, ...]
    edition_patterns: tuple[EditionPattern, ...]
    newest_editions: tuple[NewestEdition, ...]
    license: License
    permissions: Permissions
    mirror_status: MirrorStatus
    pinned_source: PinnedSource | None
    extraction_profile: ExtractionProfile | None
    notices: tuple[str, ...]


@dataclass(frozen=True)
class ChapterFile:
    """One chapter file of a library.

    Attributes:
        path: The file's path relative to the library root.
        chapter: The frontmatter record.
        body: The Markdown below the frontmatter.
    """

    path: Path
    chapter: Chapter
    body: str


@dataclass(frozen=True)
class TopicFile:
    """One topic document of a library.

    Attributes:
        path: The file's path relative to the library root.
        topic: The frontmatter record.
        body: The Markdown below the frontmatter.
    """

    path: Path
    topic: Topic
    body: str


@dataclass(frozen=True)
class Library:
    """A fully loaded library.

    Attributes:
        root: The library root the records were loaded from.
        catalog: The contents of ``catalog.yaml``.
        resources: Every cataloged resource, in catalog order.
        chapters: Every chapter file, by catalog order of its book and then by file name.
        topics: Every topic document, by file name.
    """

    root: Path
    catalog: Catalog
    resources: tuple[Resource, ...]
    chapters: tuple[ChapterFile, ...]
    topics: tuple[TopicFile, ...]

    def resource(self, resource_id: str) -> Resource:
        """Return the resource with the given id.

        Args:
            resource_id: Id of a cataloged resource.

        Returns:
            The resource record.

        Raises:
            KeyError: No cataloged resource has that id.
        """
        for resource in self.resources:
            if resource.id == resource_id:
                return resource
        raise KeyError(resource_id)

    def chapters_of(self, resource_id: str) -> tuple[ChapterFile, ...]:
        """Return the chapter files whose frontmatter names the given resource, in file order.

        Args:
            resource_id: Id of a resource.

        Returns:
            The matching chapter files. The tuple is empty for a book with no chapters.
        """
        return tuple(
            chapter_file
            for chapter_file in self.chapters
            if chapter_file.chapter.resource == resource_id
        )


def load_catalog(root: Path) -> Catalog:
    """Load and validate ``catalog.yaml``.

    Args:
        root: The library root.

    Returns:
        The catalog record.

    Raises:
        LoadError: The file cannot be read, is not well-formed YAML, or breaks the catalog schema.
    """
    data = load_yaml_file(root / CATALOG_FILE, "catalog")
    library = data["library"]
    return Catalog(
        library=LibraryInfo(
            name=library["name"],
            title=library["title"],
            description=library["description"],
            base_url=library["base_url"],
            repository=library["repository"],
        ),
        license_allowlist=tuple(data["license_allowlist"]),
        collections=tuple(
            Collection(id=collection["id"], title=collection["title"])
            for collection in data["collections"]
        ),
        resources=tuple(data["resources"]),
    )


def load_resource(root: Path, resource_id: str) -> Resource:
    """Load and validate ``books/<resource_id>/metadata.yaml``.

    Args:
        root: The library root.
        resource_id: Id of the resource, which is also its directory name.

    Returns:
        The resource record.

    Raises:
        LoadError: The file cannot be read, is not well-formed YAML, breaks the resource schema,
            or records an id other than its directory name.
    """
    path = root / BOOKS_DIR / resource_id / METADATA_FILE
    data = load_yaml_file(path, "resource")
    if data["id"] != resource_id:
        raise LoadError(
            path,
            f"The id {data['id']!r} must equal the directory name {resource_id!r}.",
            json_path="$.id",
        )
    return _resource(data)


def load_chapters(root: Path, resource_id: str) -> tuple[ChapterFile, ...]:
    """Load every chapter file under ``books/<resource_id>/chapters/``.

    Args:
        root: The library root.
        resource_id: Id of the resource, which is also its directory name.

    Returns:
        The chapter files in file name order. The tuple is empty when the directory is missing.

    Raises:
        LoadError: A chapter file cannot be read or its frontmatter is invalid.
    """
    chapters: list[ChapterFile] = []
    for path in sorted((root / BOOKS_DIR / resource_id / CHAPTERS_DIR).glob("*.md")):
        chapter, body = load_chapter(path)
        chapters.append(ChapterFile(path=path.relative_to(root), chapter=chapter, body=body))
    return tuple(chapters)


def load_topics(root: Path) -> tuple[TopicFile, ...]:
    """Load every topic document under ``topics/``.

    The landing page ``topics/index.md`` is not a topic document and is skipped.

    Args:
        root: The library root.

    Returns:
        The topic documents in file name order. The tuple is empty when the directory is missing.

    Raises:
        LoadError: A topic document cannot be read or its frontmatter is invalid.
    """
    topics: list[TopicFile] = []
    for path in sorted((root / TOPICS_DIR).glob("*.md")):
        if path.name == TOPIC_INDEX_FILE:
            continue
        topic, body = load_topic(path)
        topics.append(TopicFile(path=path.relative_to(root), topic=topic, body=body))
    return tuple(topics)


def load_library(root: Path) -> Library:
    """Load a whole library: the catalog, every cataloged resource, its chapters, and the topics.

    Args:
        root: The library root, which is the directory that holds ``catalog.yaml``.

    Returns:
        The loaded library.

    Raises:
        LoadError: Any file cannot be read or is invalid. Loading stops at the first failure.
    """
    catalog = load_catalog(root)
    return Library(
        root=root,
        catalog=catalog,
        resources=tuple(load_resource(root, resource_id) for resource_id in catalog.resources),
        chapters=tuple(
            chapter_file
            for resource_id in catalog.resources
            for chapter_file in load_chapters(root, resource_id)
        ),
        topics=load_topics(root),
    )


def version_key(version: str) -> tuple[int, ...]:
    """Split a dotted or date-style version into numbers that order the way upstream means.

    Args:
        version: A version as an edition records it, such as ``v260615`` or ``2.0.1``.

    Returns:
        Each run of digits as a number, so ``2.10`` sorts after ``2.9``.
    """
    return tuple(int(part) for part in _NOT_DIGITS.split(version) if part)


def _person(data: dict[str, Any]) -> Person:
    return Person(name=data["name"], native_name=data["native_name"], url=data["url"])


def _upstream(data: dict[str, Any]) -> GitSource | UrlSource:
    if data["kind"] == "git":
        return GitSource(
            kind="git",
            repository=data["repository"],
            default_branch=data["default_branch"],
            head_commit=data["head_commit"],
        )
    return UrlSource(kind="url", url=data["url"])


def _license(data: dict[str, Any]) -> License:
    return License(
        spdx=data["spdx"],
        evidence=EvidenceKind(data["evidence"]),
        statement=data["statement"],
        permalink=data["permalink"],
        blob_sha=data["blob_sha"],
        commit=data["commit"],
        verified_on=data["verified_on"],
        departs_from_template=data["departs_from_template"],
        locations_checked=tuple(data["locations_checked"]),
    )


def _permissions(data: dict[str, Any]) -> Permissions:
    return Permissions(
        redistribution=Permission(data["redistribution"]),
        adaptation=Permission(data["adaptation"]),
        commercial_use=Permission(data["commercial_use"]),
        attribution_required=data["attribution_required"],
        share_alike=data["share_alike"],
        third_party_rights=data["third_party_rights"],
    )


def _pinned_source(data: dict[str, Any] | None) -> PinnedSource | None:
    if data is None:
        return None
    return PinnedSource(
        repository=data["repository"],
        commit=data["commit"],
        path=data["path"],
        sha256=data["sha256"],
        edition=data["edition"],
        language=data["language"],
        local_path=data["local_path"],
    )


def _optional_float(value: float | None) -> float | None:
    return None if value is None else float(value)


def _extraction_profile(data: dict[str, Any] | None) -> ExtractionProfile | None:
    if data is None:
        return None
    return ExtractionProfile(
        roles=tuple(
            RoleRule(
                role=Role(rule["role"]),
                font_size=float(rule["font_size"]),
                min_indent=_optional_float(rule.get("min_indent")),
                max_indent=_optional_float(rule.get("max_indent")),
            )
            for rule in data["roles"]
        ),
        section_start=data["section_start"],
        excluded_pages=tuple(int(page) for page in data["excluded_pages"]),
        sections=tuple(
            SectionAssignment(title=section["title"], slug=section["slug"], part=section["part"])
            for section in data["sections"]
        ),
        accepted_differences=tuple(
            AcceptedDifference(
                chapter=difference["chapter"],
                words_removed=tuple(difference["words_removed"]),
                words_added=tuple(difference["words_added"]),
                reason=difference["reason"],
            )
            for difference in data["accepted_differences"]
        ),
    )


def _resource(data: dict[str, Any]) -> Resource:
    urls = data["official_urls"]
    translator = data["translator"]
    return Resource(
        id=data["id"],
        type=ResourceType(data["type"]),
        collection=data["collection"],
        title=Titles(
            original=data["title"]["original"],
            english=data["title"]["english"],
            english_official=data["title"]["english_official"],
        ),
        author=_person(data["author"]),
        translator=None if translator is None else _person(translator),
        languages=tuple(data["languages"]),
        official_urls=OfficialUrls(
            site=urls["site"],
            repository=urls["repository"],
            hosted_editions=tuple(
                HostedEdition(name=hosted["name"], url=hosted["url"], note=hosted.get("note"))
                for hosted in urls["hosted_editions"]
            ),
        ),
        site_slug=data["site_slug"],
        upstream=_upstream(data["upstream"]),
        editions=tuple(
            Edition(
                language=edition["language"],
                version=edition["version"],
                format=edition["format"],
                path=edition["path"],
                blob_sha=edition["blob_sha"],
            )
            for edition in data["editions"]
        ),
        edition_patterns=tuple(
            EditionPattern(language=language, pattern=pattern)
            for language, pattern in data["edition_patterns"].items()
        ),
        newest_editions=tuple(
            NewestEdition(language=language, version=version)
            for language, version in data["newest_editions"].items()
        ),
        license=_license(data["license"]),
        permissions=_permissions(data["permissions"]),
        mirror_status=MirrorStatus(data["mirror_status"]),
        pinned_source=_pinned_source(data.get("pinned_source")),
        extraction_profile=_extraction_profile(data.get("extraction_profile")),
        notices=tuple(data.get("notices", ())),
    )
