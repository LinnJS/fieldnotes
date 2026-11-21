"""Build the generated files of a library: the committed indexes, llms.txt, and the full text.

The committed files are ``index/catalog.json``, ``index/topics.json``, ``index/chapters.jsonl``,
and ``llms.txt``. The read path in ``kb.readpath`` needs nothing else, and its record types are
the shapes written here. The full-text files go to ``dist/`` and are published, not committed.

Every output is a pure function of the library files. Keys are sorted, resources keep catalog
order, chapters keep reading order, and no output holds a timestamp or an absolute path, so two
builds of the same files give the same bytes.

Only a book whose text may be quoted contributes chapters or text. That is a mirrored book the
license gate allows, and ``quote_permitted`` is the one place that decides it.
"""

import json
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from kb.catalog import (
    BOOKS_DIR,
    LICENSE_FILE,
    ChapterFile,
    EvidenceKind,
    Library,
    MirrorStatus,
    Person,
    Resource,
    version_key,
)
from kb.gate import evaluate
from kb.readpath import (
    BUILD_COMMAND,
    CATALOG_INDEX,
    CHAPTERS_INDEX,
    LLMS_FILE,
    TOPICS_INDEX,
    ChapterRecord,
    EditionRef,
    PageRangeRecord,
    PersonRecord,
    ResourceRecord,
    TopicRecord,
    edition_note,
    language_name,
    official_url,
    page_label,
    source_label,
)

__all__ = [
    "AGENT_INSTRUCTIONS_FILE",
    "FULL_TEXT_DIR",
    "FULL_TEXT_FILE",
    "STALE_FIX",
    "BuildError",
    "StaleFile",
    "build_full_text",
    "build_indexes",
    "counted",
    "newer_editions",
    "quote_permitted",
    "stale_files",
    "write_files",
]

AGENT_INSTRUCTIONS_FILE = "AGENTS.md"
FULL_TEXT_FILE = "dist/llms-full.txt"
FULL_TEXT_DIR = "dist/llms-full"

STALE_FIX = (
    f"Run `{BUILD_COMMAND}` and commit the result. Add --root DIRECTORY for a library that is "
    "not the repository root."
)
"""What to do about a committed generated file that is missing or stale."""


class BuildError(Exception):
    """A generated file cannot be built from the library as it stands."""


@dataclass(frozen=True)
class StaleFile:
    """A committed generated file that is not what the build would write.

    Attributes:
        path: The file's path relative to the library root, with forward slashes.
        missing: True when the file does not exist, and false when its bytes differ.
    """

    path: str
    missing: bool


def quote_permitted(resource: Resource, allowlist: Sequence[str]) -> bool:
    """Say whether a book's text is in the library and may be quoted.

    Args:
        resource: The resource record.
        allowlist: SPDX ids the catalog allows to be mirrored.

    Returns:
        True only for a book whose status is mirrored and that the license gate allows to be
        mirrored.
    """
    if resource.mirror_status is not MirrorStatus.MIRRORED:
        return False
    return evaluate(resource, allowlist).permits(MirrorStatus.MIRRORED)


def newer_editions(resource: Resource, version: str) -> list[EditionRef]:
    """List the newest edition of each language that is ahead of a given version.

    Versions are compared as tuples of the integers in them, so ``v10.0`` is ahead of ``v9.2``
    and ``v261020`` is ahead of ``v260615``.

    Args:
        resource: The resource whose newest editions are recorded.
        version: The version to compare against, which is the mirrored edition's.

    Returns:
        One entry per language whose newest version is higher, sorted by language code.
    """
    mirrored = version_key(version)
    return [
        EditionRef(language=newest.language, version=newest.version)
        for newest in sorted(resource.newest_editions, key=lambda newest: newest.language)
        if version_key(newest.version) > mirrored
    ]


def build_indexes(library: Library) -> dict[str, str]:
    """Build the text of every committed generated file.

    Args:
        library: The loaded library. Records that failed to load may be missing from it, and the
            files are then built from what is there.

    Returns:
        The text of each file by its path relative to the library root, for
        ``index/catalog.json``, ``index/topics.json``, ``index/chapters.jsonl``, and ``llms.txt``.
    """
    resources, chapters, topics = _records(library)
    info = library.catalog.library
    catalog = {
        "library": {
            "name": info.name,
            "title": info.title,
            "description": info.description,
            "base_url": info.base_url,
            "repository": info.repository,
        },
        "license_allowlist": list(library.catalog.license_allowlist),
        "collections": [
            {"id": collection.id, "title": collection.title}
            for collection in library.catalog.collections
        ],
        "resources": resources,
    }
    return {
        CATALOG_INDEX: _json_document(catalog),
        TOPICS_INDEX: _json_document({"topics": topics}),
        CHAPTERS_INDEX: "".join(_json_line(chapter) for chapter in chapters),
        LLMS_FILE: _llms_text(library, resources, chapters, topics),
    }


def build_full_text(library: Library) -> dict[str, str]:
    """Build the full-text files: one per mirrored book, and one that joins them.

    Each book's segment opens with its title, author, edition, source repository and revision,
    license id, and the full license text from the book's directory. Each chapter follows under
    a header line that carries its id and source pages, with its errata. A book whose text may
    not be quoted contributes nothing.

    Args:
        library: The loaded library.

    Returns:
        The text of each file by its path relative to the library root: ``dist/llms-full.txt``
        and one ``dist/llms-full/<resource-id>.txt`` per mirrored book.

    Raises:
        BuildError: A mirrored book has no readable license file, so its text cannot be
            published with its license.
    """
    info = library.catalog.library
    files: dict[str, str] = {}
    segments: list[str] = []
    for resource in library.resources:
        if not quote_permitted(resource, library.catalog.license_allowlist):
            continue
        segment = _book_segment(library, resource)
        files[f"{FULL_TEXT_DIR}/{resource.id}.txt"] = segment
        segments.append(segment)
    opening = (
        f"{info.title}: full text of the mirrored books\n"
        "\n"
        "Each book below opens with its own license, which is the author's and covers that "
        "book's text. The license of this library's code and original prose does not apply to "
        "it. Books that are cataloged and not mirrored are absent from this file.\n"
    )
    files[FULL_TEXT_FILE] = "\n".join([opening, *segments])
    return files


def stale_files(library: Library) -> list[StaleFile]:
    """Compare the committed generated files with what the build would write now.

    Args:
        library: The loaded library.

    Returns:
        One entry per committed file that is missing or whose bytes differ, in a fixed order.
        The list is empty when every file is fresh.
    """
    stale: list[StaleFile] = []
    for name, text in build_indexes(library).items():
        path = library.root / name
        if not path.is_file():
            stale.append(StaleFile(path=name, missing=True))
        elif path.read_bytes() != text.encode("utf-8"):
            stale.append(StaleFile(path=name, missing=False))
    return stale


def write_files(root: Path, files: Mapping[str, str]) -> None:
    """Write generated files under a library root, creating directories as needed.

    Args:
        root: The library root.
        files: The text of each file by its path relative to the root.
    """
    for name, text in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        # Bytes are written so that no platform translates the line endings.
        path.write_bytes(text.encode("utf-8"))


def _json_document(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _json_line(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n"


def _records(
    library: Library,
) -> tuple[list[ResourceRecord], list[ChapterRecord], list[TopicRecord]]:
    """Build every index record, with resources in catalog order and chapters in reading order."""
    allowlist = library.catalog.license_allowlist
    quotable = {resource.id: quote_permitted(resource, allowlist) for resource in library.resources}
    loaded = {resource.id: resource for resource in library.resources}

    topics_of_resource: defaultdict[str, list[str]] = defaultdict(list)
    topics_of_chapter: defaultdict[str, list[str]] = defaultdict(list)
    topics: list[TopicRecord] = []
    for topic_file in library.topics:
        topic = topic_file.topic
        for reference in topic.references:
            if topic.id not in topics_of_resource[reference.resource]:
                topics_of_resource[reference.resource].append(topic.id)
            if reference.chapter and topic.id not in topics_of_chapter[reference.chapter]:
                topics_of_chapter[reference.chapter].append(topic.id)
        topics.append(
            TopicRecord(
                id=topic.id,
                title=topic.title,
                path=topic_file.path.as_posix(),
                references=[
                    {
                        "resource": reference.resource,
                        "chapter": reference.chapter,
                        "note": reference.note,
                        # A reference to an id the catalog does not hold is a validation
                        # finding. Here it is indexed as a book with nothing to quote.
                        "mirror_status": (
                            loaded[reference.resource].mirror_status.value
                            if reference.resource in loaded
                            else None
                        ),
                        "license_id": (
                            loaded[reference.resource].license.spdx
                            if reference.resource in loaded
                            else None
                        ),
                        "quote_permitted": quotable.get(reference.resource, False),
                    }
                    for reference in topic.references
                ],
                mirrored_chapters=len(
                    {
                        reference.chapter
                        for reference in topic.references
                        if reference.chapter and quotable.get(reference.resource, False)
                    }
                ),
            )
        )

    resources: list[ResourceRecord] = []
    chapters: list[ChapterRecord] = []
    for resource in library.resources:
        book_chapters = [
            _chapter_record(resource, chapter_file, topics_of_chapter)
            for chapter_file in _reading_order(library, resource)
            if quotable[resource.id]
        ]
        chapters.extend(book_chapters)
        resources.append(
            _resource_record(
                resource,
                quotable[resource.id],
                [chapter["id"] for chapter in book_chapters],
                topics_of_resource[resource.id],
            )
        )
    return resources, chapters, topics


def _reading_order(library: Library, resource: Resource) -> list[ChapterFile]:
    return sorted(
        library.chapters_of(resource.id),
        key=lambda chapter_file: (chapter_file.chapter.order, chapter_file.path.as_posix()),
    )


def _person_record(person: Person) -> PersonRecord:
    return PersonRecord(name=person.name, native_name=person.native_name, url=person.url)


def _resource_record(
    resource: Resource, quotable: bool, chapter_ids: list[str], topic_ids: list[str]
) -> ResourceRecord:
    urls = resource.official_urls
    pinned = resource.pinned_source if quotable else None
    directory = f"{BOOKS_DIR}/{resource.id}"
    newer = newer_editions(resource, pinned.edition) if pinned else []
    return ResourceRecord(
        id=resource.id,
        type=resource.type.value,
        collection=resource.collection,
        title={
            "original": resource.title.original,
            "english": resource.title.english,
            "english_official": resource.title.english_official,
        },
        author=_person_record(resource.author),
        translator=_person_record(resource.translator) if resource.translator else None,
        languages=list(resource.languages),
        official_urls={
            "site": urls.site,
            "repository": urls.repository,
            "hosted_editions": [
                {"name": hosted.name, "url": hosted.url, "note": hosted.note}
                for hosted in urls.hosted_editions
            ],
        },
        newest_editions={newest.language: newest.version for newest in resource.newest_editions},
        license_id=resource.license.spdx,
        license_evidence=resource.license.evidence.value,
        license_permalink=resource.license.permalink,
        mirror_status=resource.mirror_status.value,
        quote_permitted=quotable,
        edition=pinned.edition if pinned else None,
        edition_language=pinned.language if pinned else None,
        edition_behind=bool(newer),
        newer_editions=newer,
        source=(
            {"repository": pinned.repository, "revision": pinned.commit, "path": pinned.path}
            if pinned
            else None
        ),
        path=directory if quotable else None,
        license_path=f"{directory}/{LICENSE_FILE}" if quotable else None,
        chapters=chapter_ids,
        topics=topic_ids,
        notices=list(resource.notices),
    )


def _chapter_record(
    resource: Resource, chapter_file: ChapterFile, topics_of_chapter: Mapping[str, list[str]]
) -> ChapterRecord:
    chapter = chapter_file.chapter
    newer = newer_editions(resource, chapter.edition)
    return ChapterRecord(
        id=chapter.id,
        path=chapter_file.path.as_posix(),
        title=chapter.title,
        part=chapter.part,
        order=chapter.order,
        section_label=chapter.section_label,
        resource=resource.id,
        language=chapter.language,
        edition=chapter.edition,
        edition_behind=bool(newer),
        newer_editions=newer,
        license_id=resource.license.spdx,
        mirror_status=resource.mirror_status.value,
        # Only a book whose text may be quoted has chapter records at all.
        quote_permitted=True,
        source={
            "repository": chapter.source.repository,
            "revision": chapter.source.revision,
            "path": chapter.source.path,
            "pages": {"first": chapter.source.pages.first, "last": chapter.source.pages.last},
        },
        extraction_status=chapter.extraction_status.value,
        errata=[
            {"description": erratum.description, "source_url": erratum.source_url}
            for erratum in chapter.errata
        ],
        topics=list(topics_of_chapter.get(chapter.id, [])),
    )


def _edition_phrase(language: str, edition: str, newer: list[EditionRef]) -> str:
    """Name an edition in a sentence fragment, and say which editions are ahead of it."""
    phrase = f"{language_name(language)} edition {edition}"
    if not newer:
        return phrase
    ahead = " and ".join(
        f"the newest {language_name(ref['language'])} edition {ref['version']}" for ref in newer
    )
    return f"{phrase}, which is behind {ahead}"


def _llms_text(
    library: Library,
    resources: list[ResourceRecord],
    chapters: list[ChapterRecord],
    topics: list[TopicRecord],
) -> str:
    info = library.catalog.library
    lines = [
        f"# {info.title}",
        "",
        f"> {' '.join(info.description.split())}",
        "",
        'The text of a book is in this library only when the book has a "Mirrored book" '
        "section below, and each of those books carries its author's own license. Every other "
        "book is cataloged with a link to the author's official source. Resolve an id to its "
        "record and citation with `python3 scripts/resolve.py <id>`, and check the citations "
        "of a document with `python3 scripts/check_citations.py <file>`.",
        "",
        "## Agent instructions",
        "",
        f"- [{AGENT_INSTRUCTIONS_FILE}]({AGENT_INSTRUCTIONS_FILE}): How to search this library, "
        "read a chapter, quote it, and cite it.",
    ]

    for resource in resources:
        if not resource["quote_permitted"]:
            continue
        edition = _edition_phrase(
            resource["edition_language"] or "",
            resource["edition"] or "",
            resource["newer_editions"],
        )
        lines += [
            "",
            f"## Mirrored book: {resource['title']['english']}",
            "",
            f"- [Book record]({resource['path']}/metadata.yaml): `{resource['id']}`, by "
            f"{resource['author']['name']}. {edition}. License {resource['license_id']}.",
            f"- [License]({resource['license_path']}): The author's license text and copyright "
            "notice, which cover this book.",
        ]
        lines += [
            f"- [{chapter['section_label']} {chapter['title']}]({chapter['path']}): "
            f"`{chapter['id']}`, {source_label(chapter['source']['path'])} "
            f"{page_label(chapter['source']['pages'])}."
            for chapter in chapters
            if chapter["resource"] == resource["id"]
        ]

    linked = [resource for resource in resources if not resource["quote_permitted"]]
    if linked:
        lines += [
            "",
            "## Books that are not mirrored",
            "",
            "These books are cataloged with their license evidence. Read them at the author's "
            "official source, and do not quote them from this library.",
            "",
        ]
        lines += [_linked_book_line(resource) for resource in linked]

    if topics:
        lines += ["", "## Topics", ""]
        lines += [
            f"- [{topic['title']}]({topic['path']}): `{topic['id']}`, "
            f"{counted(len(topic['references']), 'reference')}."
            for topic in topics
        ]

    lines += [
        "",
        "## Indexes",
        "",
        f"- [{CATALOG_INDEX}]({CATALOG_INDEX}): Every book with its license id, mirror status, "
        "quote-permitted flag, editions, and official URLs.",
        f"- [{CHAPTERS_INDEX}]({CHAPTERS_INDEX}): One JSON object per line for each mirrored "
        "chapter, with its id, path, source pages, and errata.",
        f"- [{TOPICS_INDEX}]({TOPICS_INDEX}): Every topic with the books and chapters it "
        "references.",
    ]
    return "\n".join(lines) + "\n"


def counted(count: int, noun: str) -> str:
    """Write a count with its noun, in the plural unless the count is one."""
    return f"{count} {noun}" if count == 1 else f"{count} {noun}s"


def _linked_book_line(resource: ResourceRecord) -> str:
    title = resource["title"]
    url = official_url(resource)
    name = f"[{title['english']}]({url})" if url else title["english"]
    original = (
        "" if title["original"] == title["english"] else f" Original title: {title['original']}."
    )
    translated = (
        "" if title["english_official"] else " The English title is this library's translation."
    )
    if resource["license_id"]:
        terms = f"license {resource['license_id']}"
    elif resource["license_evidence"] == EvidenceKind.NONE.value:
        terms = "no license terms found"
    else:
        terms = "informal terms that name no SPDX license"
    return (
        f"- {name}: `{resource['id']}`, {resource['mirror_status']}, {terms}."
        f"{original}{translated} Its text is not in this library."
    )


def _book_segment(library: Library, resource: Resource) -> str:
    """Build one mirrored book's full text, opening with its attribution and license."""
    license_path = library.root / BOOKS_DIR / resource.id / LICENSE_FILE
    try:
        license_text = license_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as error:
        raise BuildError(
            f"{BOOKS_DIR}/{resource.id}/{LICENSE_FILE} cannot be read, and a mirrored book is "
            "published only with its license. Add the upstream license text under that name."
        ) from error

    chapters = _reading_order(library, resource)
    pinned = resource.pinned_source
    author = resource.author
    lines = [
        f"Book: {resource.title.english}",
        f"Resource id: {resource.id}",
        "Author: "
        + (f"{author.name} ({author.native_name})" if author.native_name else author.name),
    ]
    if pinned is not None:
        newer = newer_editions(resource, pinned.edition)
        lines.append(f"Edition: {language_name(pinned.language)} edition {pinned.edition}")
        note = edition_note(pinned.language, pinned.edition, newer)
        if note:
            lines.append(f"Edition note: {note}")
        lines.append(f"Source: {pinned.repository} at revision {pinned.commit}, file {pinned.path}")
    lines += [f"Notice: {notice}" for notice in resource.notices]
    lines += [
        f"License: {resource.license.spdx}. The full license text follows. It is the author's "
        "and it covers this book.",
        "",
        license_text.strip("\n"),
    ]
    for chapter_file in chapters:
        chapter = chapter_file.chapter
        pages = PageRangeRecord(first=chapter.source.pages.first, last=chapter.source.pages.last)
        lines += [
            "",
            f"[chapter: {chapter.id} | {chapter.section_label} | "
            f"{source_label(chapter.source.path)} {page_label(pages)} | "
            f"{chapter.extraction_status.value}]",
        ]
        lines += [
            f"Known upstream erratum, recorded and not applied to the text: "
            f"{erratum.description} Source: {erratum.source_url}"
            for erratum in chapter.errata
        ]
        lines += ["", chapter_file.body.strip("\n")]
    return "\n".join(lines) + "\n"
