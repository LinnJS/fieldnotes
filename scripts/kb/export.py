"""Exports of a library: a PDF and an EPUB of each mirrored book, and one bundle of the library.

Every export is made from the canonical files of a library, so no second source tree exists.

A book's PDF and EPUB come from one Markdown stream that ``assemble_markdown`` builds in memory:
a Pandoc metadata block, a notice section with the attribution and the full license text, and
then the chapters in order. Pandoc turns the stream into Typst markup, which the Typst compiler
makes into the PDF, and into the EPUB. The stream is read as GitHub-flavored Markdown, which is
the dialect the chapter files are written in, with heading attributes switched on for the
anchors this module adds.

The bundle is a zip archive of the library's own files, with the chapters and the license file
of mirrored books only.

The license gate is asked before anything about a book is read. A book is exported only when
the gate allows it to be mirrored and its recorded status is ``mirrored``.

Pandoc is a system tool and not a Python dependency. ``find_pandoc`` looks for it on the PATH
and checks its version against ``MINIMUM_PANDOC_VERSION``.
"""

import difflib
import hashlib
import json
import re
import shutil
import subprocess
import tempfile
import uuid
import zipfile
from collections.abc import Mapping, Sequence
from pathlib import Path

import typst
import yaml

from kb.catalog import (
    BOOKS_DIR,
    CATALOG_FILE,
    LICENSE_FILE,
    METADATA_FILE,
    TOPICS_DIR,
    ChapterFile,
    Library,
    MirrorStatus,
    Person,
    PinnedSource,
    Resource,
    version_key,
)
from kb.evidence import blob_permalink
from kb.frontmatter import ExtractionStatus
from kb.gate import evaluate
from kb.markdown import backtick_fence
from kb.readpath import BUILD_COMMAND, CATALOG_INDEX, CHAPTERS_INDEX, LLMS_FILE, TOPICS_INDEX

__all__ = [
    "CJK_FONT_FAMILIES",
    "EXPORTS_DIR",
    "GENERATED_FILES",
    "HAND_WRITTEN_FILES",
    "MANIFEST_FILE",
    "MINIMUM_PANDOC_VERSION",
    "TEMPLATES_DIR",
    "ExportError",
    "assemble_markdown",
    "bundle_files",
    "find_cjk_font",
    "find_pandoc",
    "select_books",
    "write_bundle",
    "write_epub",
    "write_pdf",
]

MINIMUM_PANDOC_VERSION: tuple[int, ...] = (3, 14)
"""Oldest Pandoc the exports are known to work with. It is the version they were tested on."""

EXPORTS_DIR = Path("dist") / "exports"
"""Directory under the library root that exports are written to by default."""

TEMPLATES_DIR = Path(__file__).resolve().parents[2] / "templates"
"""Directory of the tooling that holds ``book.typ`` and ``epub.css``."""

CJK_FONT_FAMILIES = (
    "Songti SC",
    "PingFang SC",
    "Hiragino Sans GB",
    "Noto Serif CJK SC",
    "Noto Sans CJK SC",
)
"""Font families the PDF tries for Chinese, Japanese, and Korean text, in order.

The first three ship with macOS. The Noto families are the ones a Linux machine installs.
"""

MANIFEST_FILE = "MANIFEST.json"
"""Name of the bundle entry that lists every other entry."""

HAND_WRITTEN_FILES = ("AGENTS.md", "LICENSES.md")
"""Files at the library root that a person writes and the bundle must carry."""

GENERATED_FILES = (CATALOG_INDEX, TOPICS_INDEX, CHAPTERS_INDEX, LLMS_FILE)
"""Files at the library root that the build command writes and the bundle must carry."""

_PANDOC = "pandoc"
_PANDOC_RELEASES = "https://github.com/jgm/pandoc/releases"
_PANDOC_VERSION = re.compile(r"pandoc(?:\.exe)? (\d+(?:\.\d+)*)")

# GitHub-flavored Markdown is the dialect of the chapter files. Attributes let this module give
# a heading an anchor and leave it unnumbered, and the metadata block carries the title data.
_MARKDOWN_FORMAT = "gfm+attributes+yaml_metadata_block"

_NOTICE_ANCHOR = "copy-notice"
_MARKDOWN_SPECIAL = re.compile(r"[\\`*_\[\]<>&#|~{}]")
_COPYRIGHT_LINE = re.compile(r"^[ \t]*(Copyright\b.*\d{4}.*?)[ \t]*$", re.MULTILINE)
_CHAPTER_LINK = re.compile(r"\]\((?P<file>[^)\s#]+\.md)(?:#[^)\s]*)?\)")

# The zip format cannot hold a date before 1980. A fixed date keeps the bundle reproducible.
_ZIP_DATE = (1980, 1, 1, 0, 0, 0)
_ZIP_UNIX = 3
_ZIP_FILE_MODE = 0o644 << 16


class ExportError(Exception):
    """An export cannot go on.

    Attributes:
        message: What is wrong, on one line.
        fix: What to do about it, on one line.
    """

    def __init__(self, message: str, fix: str) -> None:
        """Build the error.

        Args:
            message: What is wrong, on one line.
            fix: What to do about it, on one line.
        """
        self.message = message
        self.fix = fix
        super().__init__(message)


def find_pandoc() -> Path:
    """Find Pandoc on the PATH and check that it is new enough.

    Returns:
        The path of the ``pandoc`` executable.

    Raises:
        ExportError: No ``pandoc`` is on the PATH, or the one found is older than
            ``MINIMUM_PANDOC_VERSION``.
    """
    required = ".".join(str(number) for number in MINIMUM_PANDOC_VERSION)
    found = shutil.which(_PANDOC)
    if found is None:
        raise ExportError(
            f"The PDF and EPUB exports need Pandoc {required} or newer, and no pandoc is on "
            "the PATH.",
            f"Install it with `brew install pandoc` on macOS. On another system, install the "
            f"package from {_PANDOC_RELEASES}.",
        )
    output = subprocess.run(
        [found, "--version"], capture_output=True, text=True, encoding="utf-8", check=False
    ).stdout
    match = _PANDOC_VERSION.match(output)
    version = tuple(int(number) for number in match[1].split(".")) if match else ()
    if version < MINIMUM_PANDOC_VERSION:
        reported = match[1] if match else "unknown"
        raise ExportError(
            f"The pandoc at {found} is version {reported}, and the exports need version "
            f"{required} or newer.",
            f"Upgrade it with `brew upgrade pandoc` on macOS. On another system, install the "
            f"package from {_PANDOC_RELEASES}.",
        )
    return Path(found)


def find_cjk_font() -> str | None:
    """Find the font the PDF will use for Chinese, Japanese, and Korean text.

    Returns:
        The first family of ``CJK_FONT_FAMILIES`` that the Typst compiler can load on this
        machine, or ``None`` when it can load none of them.
    """
    available = set(typst.Fonts().families())
    return next((family for family in CJK_FONT_FAMILIES if family in available), None)


def select_books(library: Library, book_id: str | None = None) -> tuple[Resource, ...]:
    """Choose the books to export and refuse any that may not be exported.

    Args:
        library: The loaded library.
        book_id: Id of one book, or ``None`` for every book recorded as mirrored.

    Returns:
        The one book asked for, or every book whose recorded status is ``mirrored``, in catalog
        order.

    Raises:
        ExportError: No cataloged book has the id, the license gate refuses a chosen book, or
            the book asked for is not recorded as mirrored.
    """
    if book_id is None:
        books = tuple(
            resource
            for resource in library.resources
            if resource.mirror_status is MirrorStatus.MIRRORED
        )
    else:
        try:
            books = (library.resource(book_id),)
        except KeyError:
            nearest = difflib.get_close_matches(book_id, library.catalog.resources)
            hint = f" The nearest ids are: {', '.join(nearest)}." if nearest else ""
            raise ExportError(
                f"No cataloged book has the id {book_id}.{hint}",
                f"Pass an id listed under resources in {CATALOG_FILE}.",
            ) from None
    for book in books:
        _require_mirrored(library, book)
    return books


def assemble_markdown(library: Library, resource: Resource) -> str:
    """Build the one Markdown stream that a book's PDF and EPUB are made from.

    The stream opens with a Pandoc metadata block. A notice section follows, with the
    attribution, the source, the edition, the extraction status, the notices recorded for the
    book, and the full license text. The chapters come last, in reading order and without their
    frontmatter. Under each chapter title the stream names the chapter's part, says when the
    chapter is machine-extracted, and shows each recorded erratum with its source.

    A link from one chapter to another chapter file of the same book is pointed at that
    chapter's heading, so it works inside the export.

    Args:
        library: The loaded library.
        resource: The book.

    Returns:
        The stream, in the Markdown dialect this module hands to Pandoc.

    Raises:
        ExportError: The book may not be exported, or its license file is missing.
    """
    pinned = _require_mirrored(library, resource)
    license_text = _read_license(library.root, resource)
    chapters = _chapter_files(library, resource)
    anchors = {file.path.name: f"chapter-{file.path.stem}" for file in chapters}
    sections = [
        _metadata_block(library, resource, pinned, license_text),
        _notice_section(library, resource, pinned, chapters, license_text),
        *(_chapter_section(file, anchors) for file in chapters),
    ]
    return "\n\n".join(sections) + "\n"


def write_pdf(library: Library, resource: Resource, out_dir: Path, pandoc: Path) -> Path:
    """Write a book's PDF.

    Pandoc writes Typst markup through ``templates/book.typ``, and the Typst compiler makes the
    PDF. The compiler draws a character as an empty box when no installed font has it, and it
    does not fail. ``find_cjk_font`` tells a caller beforehand whether that will happen.

    Args:
        library: The loaded library.
        resource: The book.
        out_dir: Directory to write into. It is created when it does not exist.
        pandoc: The Pandoc executable, as ``find_pandoc`` returns it.

    Returns:
        The file written, ``<out_dir>/<resource-id>-<edition>.pdf``.

    Raises:
        ExportError: The book may not be exported, its license file is missing, or Pandoc or
            the Typst compiler fails.
    """
    markdown = assemble_markdown(library, resource)
    target = _book_file(library, resource, out_dir, "pdf")
    font_variables = [f"--variable=cjk-font={family}" for family in CJK_FONT_FAMILIES]
    with tempfile.TemporaryDirectory() as scratch:
        source = Path(scratch) / "book.typ"
        _run_pandoc(
            pandoc,
            markdown,
            "--to=typst",
            "--standalone",
            f"--template={TEMPLATES_DIR / 'book.typ'}",
            "--wrap=none",
            f"--variable=pdf-author={_typst_string(_person_name(resource.author))}",
            *font_variables,
            f"--output={source}",
        )
        try:
            typst.compile(str(source), output=str(target))
        except typst.TypstError as error:
            raise ExportError(
                f"The Typst compiler could not make the PDF of {resource.id}. {error}",
                "Correct templates/book.typ, or the chapter the message points at, and run "
                "the command again.",
            ) from error
    return target


def write_epub(library: Library, resource: Resource, out_dir: Path, pandoc: Path) -> Path:
    """Write a book's EPUB.

    Pandoc writes an EPUB 3 file with ``templates/epub.css``, one content file per chapter, and
    a navigation document.

    Args:
        library: The loaded library.
        resource: The book.
        out_dir: Directory to write into. It is created when it does not exist.
        pandoc: The Pandoc executable, as ``find_pandoc`` returns it.

    Returns:
        The file written, ``<out_dir>/<resource-id>-<edition>.epub``.

    Raises:
        ExportError: The book may not be exported, its license file is missing, or Pandoc
            fails.
    """
    markdown = assemble_markdown(library, resource)
    target = _book_file(library, resource, out_dir, "epub")
    _run_pandoc(
        pandoc,
        markdown,
        "--to=epub3",
        f"--css={TEMPLATES_DIR / 'epub.css'}",
        "--split-level=1",
        "--number-sections",
        f"--output={target}",
    )
    return target


def bundle_files(library: Library) -> tuple[Path, ...]:
    """List the files the bundle holds.

    The bundle holds the catalog, ``AGENTS.md``, ``LICENSES.md``, the committed indexes,
    ``llms.txt``, every Markdown file under ``topics/``, and the ``metadata.yaml`` of every
    cataloged book. For a mirrored book it also holds the chapters and the license file. It
    holds nothing else from a book directory, so a source file is never in it.

    Args:
        library: The loaded library.

    Returns:
        The files, relative to the library root and sorted by their POSIX path.

    Raises:
        ExportError: A required file is missing from the library root, the license gate refuses
            a book recorded as mirrored, or a mirrored book has no license file.
    """
    root = library.root
    hand_written = [name for name in HAND_WRITTEN_FILES if not (root / name).is_file()]
    generated = [name for name in GENERATED_FILES if not (root / name).is_file()]
    if hand_written or generated:
        fixes = []
        if generated:
            fixes.append(f"Run `{BUILD_COMMAND}` to write the index files and llms.txt.")
        if hand_written:
            fixes.append(
                f"Add {', '.join(hand_written)} at the library root. A person writes these "
                "files, and no command makes them."
            )
        raise ExportError(
            f"The bundle needs files that are missing from {root}: "
            f"{', '.join([*hand_written, *generated])}.",
            " ".join(fixes),
        )

    files = {Path(name) for name in (CATALOG_FILE, *HAND_WRITTEN_FILES, *GENERATED_FILES)}
    files.update(path.relative_to(root) for path in (root / TOPICS_DIR).glob("*.md"))
    files.update(Path(BOOKS_DIR) / resource.id / METADATA_FILE for resource in library.resources)
    for book in select_books(library):
        _read_license(root, book)
        files.add(_license_path(book))
        files.update(file.path for file in _chapter_files(library, book))
    return tuple(sorted(files, key=lambda path: path.as_posix()))


def write_bundle(library: Library, out_dir: Path) -> Path:
    """Write the bundle: one zip archive of the files ``bundle_files`` lists.

    The first entry is ``MANIFEST.json``, an object whose ``files`` key lists every other entry
    with its ``path``, its ``sha256`` in lowercase hex, and its ``size`` in bytes. The other
    entries follow in the order of ``bundle_files``. Every entry carries the same fixed date,
    so the same library gives the same bytes.

    Args:
        library: The loaded library.
        out_dir: Directory to write into. It is created when it does not exist.

    Returns:
        The file written, ``<out_dir>/<library-name>-bundle.zip``.

    Raises:
        ExportError: ``bundle_files`` refuses the library.
    """
    entries = [
        (path.as_posix(), (library.root / path).read_bytes()) for path in bundle_files(library)
    ]
    manifest = {
        "files": [
            {"path": name, "sha256": hashlib.sha256(data).hexdigest(), "size": len(data)}
            for name, data in entries
        ]
    }
    manifest_bytes = (json.dumps(manifest, indent=2) + "\n").encode()

    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / f"{library.catalog.library.name}-bundle.zip"
    with zipfile.ZipFile(target, "w") as archive:
        for name, data in [(MANIFEST_FILE, manifest_bytes), *entries]:
            entry = zipfile.ZipInfo(name, date_time=_ZIP_DATE)
            entry.compress_type = zipfile.ZIP_DEFLATED
            # The host system and the file mode are fixed too. Left alone, they would differ
            # between the machines that build the bundle.
            entry.create_system = _ZIP_UNIX
            entry.external_attr = _ZIP_FILE_MODE
            archive.writestr(entry, data)
    return target


def _require_mirrored(library: Library, resource: Resource) -> PinnedSource:
    """Return the pinned source of a book that may be exported, and refuse any other book."""
    decision = evaluate(resource, library.catalog.license_allowlist)
    pinned = resource.pinned_source
    # The gate refuses a book with no pinned source, so the first test only narrows the type.
    if pinned is None or not decision.permits(MirrorStatus.MIRRORED):
        raise ExportError(
            f"The license gate does not allow {resource.id} to be exported. {decision.reason}",
            "Export only a mirrored book. If the license record in "
            f"{BOOKS_DIR}/{resource.id}/{METADATA_FILE} is wrong, correct it.",
        )
    if resource.mirror_status is not MirrorStatus.MIRRORED:
        raise ExportError(
            f"The book {resource.id} passes the license gate and its mirror_status is "
            f"{resource.mirror_status.value}, so it is not yet mirrored and has nothing to "
            "export.",
            "Ingest the book and have the owner set mirror_status to mirrored, then export it.",
        )
    return pinned


def _chapter_files(library: Library, resource: Resource) -> list[ChapterFile]:
    """Return the chapter files in a book's own directory, in reading order."""
    return sorted(library.chapters_of(resource.id), key=lambda file: file.chapter.order)


def _license_path(resource: Resource) -> Path:
    return Path(BOOKS_DIR) / resource.id / LICENSE_FILE


def _read_license(root: Path, resource: Resource) -> str:
    path = _license_path(resource)
    try:
        return (root / path).read_text(encoding="utf-8")
    except FileNotFoundError:
        raise ExportError(
            f"The mirrored book {resource.id} has no license file at {path.as_posix()}.",
            "Copy the upstream license text into that file. Every export must carry it.",
        ) from None


def _book_file(library: Library, resource: Resource, out_dir: Path, suffix: str) -> Path:
    pinned = _require_mirrored(library, resource)
    out_dir.mkdir(parents=True, exist_ok=True)
    return out_dir / f"{resource.id}-{pinned.edition}.{suffix}"


def _run_pandoc(pandoc: Path, markdown: str, *options: str) -> None:
    result = subprocess.run(
        [str(pandoc), f"--from={_MARKDOWN_FORMAT}", *options],
        input=markdown,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    if result.returncode != 0:
        raise ExportError(
            f"Pandoc stopped with exit code {result.returncode}. {result.stderr.strip()}",
            "Correct what the Pandoc message points at and run the command again.",
        )


def _metadata_block(
    library: Library, resource: Resource, pinned: PinnedSource, license_text: str
) -> str:
    """Write the Pandoc metadata block. Pandoc reads each text value as Markdown."""
    title, other_title = _titles(resource, pinned)
    spdx = resource.license.spdx
    rights = [f"{spdx} license."] if spdx else []
    rights.extend(_COPYRIGHT_LINE.findall(license_text))
    info = library.catalog.library
    metadata: dict[str, object] = {"title": _plain(title)}
    if other_title is not None:
        metadata["subtitle"] = _plain(other_title)
    metadata["author"] = [_plain(_person_name(resource.author))]
    if resource.translator is not None:
        translator = _plain(_person_name(resource.translator))
        metadata["translator"] = translator
        metadata["contributor"] = [{"role": "trl", "text": translator}]
    metadata["lang"] = pinned.language
    metadata["rights"] = _plain(" ".join(rights))
    metadata["source"] = blob_permalink(pinned.repository, pinned.commit, pinned.path)
    # The same book and edition always get the same identifier, so a reader treats a rebuilt
    # file as the same publication.
    identifier = uuid.uuid5(uuid.NAMESPACE_URL, f"{info.name}/{resource.id}/{pinned.edition}")
    metadata["identifier"] = f"urn:uuid:{identifier}"
    metadata["edition"] = _plain(f"Edition {pinned.edition}, language {pinned.language}")
    metadata["unofficial"] = _plain(_unofficial_statement(library))
    block = yaml.safe_dump(metadata, allow_unicode=True, sort_keys=False, width=1000)
    return f"---\n{block}---"


def _unofficial_statement(library: Library) -> str:
    return (
        f"This is an unofficial copy made by {library.catalog.library.title}, an independent "
        "community library. The author has not endorsed this copy or the library."
    )


def _titles(resource: Resource, pinned: PinnedSource) -> tuple[str, str | None]:
    """Return the title in the language of the pinned edition, and the other title if any."""
    english = resource.title.english
    if not resource.title.english_official:
        english = f"{english} (title translated by the library)"
    title, other = (
        (english, resource.title.original)
        if pinned.language == "en"
        else (resource.title.original, english)
    )
    return title, (None if other == title else other)


def _person_name(person: Person) -> str:
    if person.native_name is None:
        return person.name
    return f"{person.name} ({person.native_name})"


def _person_line(label: str, person: Person) -> str:
    link = "" if person.url is None else f", <{person.url}>"
    return f"- **{label}:** {_plain(_person_name(person))}{link}"


def _notice_section(
    library: Library,
    resource: Resource,
    pinned: PinnedSource,
    chapters: Sequence[ChapterFile],
    license_text: str,
) -> str:
    urls = resource.official_urls
    permalink = blob_permalink(pinned.repository, pinned.commit, pinned.path)
    machine_extracted = sum(
        file.chapter.extraction_status is ExtractionStatus.MACHINE_EXTRACTED for file in chapters
    )

    facts = [_person_line("Author", resource.author)]
    if resource.translator is not None:
        facts.append(_person_line("Translator", resource.translator))
    facts.append(f"- **Edition:** {_plain(pinned.edition)}, language {_plain(pinned.language)}")
    facts.extend(
        f"- **Newer edition:** The {_plain(newest.language)} edition {_plain(newest.version)} "
        "is newer than this copy. This copy does not hold its changes."
        for newest in resource.newest_editions
        if newest.language != pinned.language
        and version_key(newest.version) > version_key(pinned.edition)
    )
    facts.append(
        f"- **Source:** the file [{_plain(pinned.path)}]({permalink}) in the repository "
        f"{_plain(pinned.repository)}, at commit {pinned.commit}"
    )
    if urls.site is not None:
        facts.append(f"- **Official site:** <{urls.site}>")
    if urls.repository is not None:
        facts.append(f"- **Official repository:** <{urls.repository}>")
    for hosted in urls.hosted_editions:
        note = "" if hosted.note is None else f". {_plain(hosted.note)}"
        facts.append(f"- **Official hosted edition:** {_plain(hosted.name)}, <{hosted.url}>{note}")
    facts.append(
        f"- **Extraction:** {machine_extracted} of {len(chapters)} chapters are "
        "machine-extracted. A program converted a machine-extracted chapter from the source "
        "file, and no person has compared it with the source yet, so it can hold conversion "
        "errors. Each machine-extracted chapter says so under its title."
    )
    if resource.license.spdx is not None:
        facts.append(f"- **License:** {_plain(resource.license.spdx)}, printed in full below")

    blocks = [
        f"# About this copy {{#{_NOTICE_ANCHOR} .unnumbered}}",
        _plain(_unofficial_statement(library)),
        "\n".join(facts),
    ]
    if resource.notices:
        blocks.append(f"## Notices {{#{_NOTICE_ANCHOR}-notices .unnumbered}}")
        blocks.append("\n".join(f"- {_plain(notice)}" for notice in resource.notices))
    blocks.append(f"## License {{#{_NOTICE_ANCHOR}-license .unnumbered}}")
    blocks.append(
        "The work keeps the license its author gave it, which follows in full. The license of "
        f"{_plain(library.catalog.library.title)} does not apply to the work."
    )
    blocks.append(_code_block(license_text))
    return "\n\n".join(blocks)


def _chapter_section(chapter_file: ChapterFile, anchors: Mapping[str, str]) -> str:
    """Write one chapter: its heading with an anchor, the library's notes, and its body.

    Args:
        chapter_file: The chapter. Its body opens with the title as a level-one heading.
        anchors: The heading anchor of each chapter of the book, by chapter file name.
    """
    chapter = chapter_file.chapter
    heading, _, text = chapter_file.body.partition("\n")
    blocks = [
        f"{heading.rstrip()} {{#{anchors[chapter_file.path.name]}}}",
        f"**{_plain(chapter.part)}**",
    ]
    if chapter.extraction_status is ExtractionStatus.MACHINE_EXTRACTED:
        blocks.append(
            "> **Machine-extracted.** No person has compared this chapter with the source file yet."
        )
    blocks.extend(
        f"> **Erratum.** {_plain(erratum.description)} Source: <{erratum.source_url}>"
        for erratum in chapter.errata
    )

    def retarget(link: re.Match[str]) -> str:
        anchor = anchors.get(link["file"])
        return link[0] if anchor is None else f"](#{anchor})"

    blocks.append(_CHAPTER_LINK.sub(retarget, text).strip("\n"))
    return "\n\n".join(blocks)


def _plain(text: str) -> str:
    """Escape text from a record so that Markdown shows it as written, on one line."""
    return _MARKDOWN_SPECIAL.sub(r"\\\g<0>", " ".join(text.split()))


def _code_block(text: str) -> str:
    """Fence text verbatim, with a fence longer than any run of backticks inside it."""
    fence = backtick_fence(text)
    lines = text.strip("\n")
    return f"{fence}\n{lines}\n{fence}"


def _typst_string(text: str) -> str:
    """Write text as a Typst string literal."""
    escaped = text.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'
