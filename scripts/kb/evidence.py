"""Capture the license evidence a repository shows at one commit.

A person, or an agent working for one, records a book's license from what this module prints and
never from memory. The capture reads a repository at an explicit commit and reports the facts a
catalog record needs: the commit, every file with its Git blob id, the full text of each license
file, each README line that speaks about license terms with its line number, and the files that
look like editions of the book. Each quoted file comes with a permalink at that commit.

The capture finds text. It does not interpret it. Deciding which license applies and what it
permits stays with the person who reads the output.
"""

import re
from dataclasses import dataclass
from pathlib import PurePosixPath
from urllib.parse import quote

from kb.upstream import GitHubClient, TreeEntry

__all__ = [
    "Capture",
    "EditionFile",
    "LicenseFile",
    "LicenseLine",
    "ReadmeLine",
    "blob_permalink",
    "capture",
    "license_lines",
    "render",
]

LICENSE_FILE_NAMES = frozenset({"license", "license.md", "license.txt", "copying"})
README_SUFFIXES = frozenset({"", ".md", ".markdown", ".txt", ".rst"})
EDITION_SUFFIXES = frozenset({".pdf", ".epub", ".html"})

# 许可 and 授权 mean license or permission, 协议 means agreement, and 版权 means copyright. They
# are the words the cataloged READMEs use to head their terms.
_LICENSE_TERMS = re.compile(r"license|许可|协议|版权|授权", re.IGNORECASE)
_HEADING = re.compile(r"^ {0,3}(#{1,6})(?:[ \t]+|$)")
_FENCE = re.compile(r"^ {0,3}(```|~~~)")
_README_STEM = re.compile(r"^readme(?:[._-].*)?$", re.IGNORECASE)


@dataclass(frozen=True)
class LicenseLine:
    """One line of a README that speaks about license terms.

    Attributes:
        number: The line's number in the file, counted from 1.
        heading: The heading the line stands under when that heading mentions license terms. It
            is ``None`` for a line that mentions license terms outside any such section.
        text: The line with surrounding whitespace removed.
    """

    number: int
    heading: str | None
    text: str


@dataclass(frozen=True)
class LicenseFile:
    """A license file found in the tree.

    Attributes:
        path: Path of the file from the repository root.
        blob_sha: Git blob id of the file.
        permalink: Link to the file at the captured commit.
        text: The file's full text.
    """

    path: str
    blob_sha: str
    permalink: str
    text: str


@dataclass(frozen=True)
class ReadmeLine:
    """One README line that speaks about license terms, with where to find it.

    Attributes:
        path: Path of the README from the repository root.
        blob_sha: Git blob id of the README.
        number: The line's number in the file, counted from 1.
        heading: The license heading the line stands under, or ``None`` for a line that mentions
            license terms outside any such section.
        text: The line with surrounding whitespace removed.
        permalink: Link to the line in the README's source view at the captured commit.
    """

    path: str
    blob_sha: str
    number: int
    heading: str | None
    text: str
    permalink: str


@dataclass(frozen=True)
class EditionFile:
    """A file that looks like an edition of the book.

    Attributes:
        path: Path of the file from the repository root.
        format: Lowercase file format, which is ``pdf``, ``epub``, or ``html``.
        blob_sha: Git blob id of the file.
        size: Size of the file in bytes.
    """

    path: str
    format: str
    blob_sha: str
    size: int


@dataclass(frozen=True)
class Capture:
    """Everything captured from one repository at one commit.

    Attributes:
        repository: The repository as ``owner/name``, spelled the way GitHub spells it.
        default_branch: The repository's default branch.
        head_commit: The commit at the head of the default branch when the capture ran.
        commit: The commit the tree and every file were read at.
        tree: Every file at the commit.
        license_files: Each license file with its text.
        readmes: Every README that was read, whether or not it speaks about license terms.
        readme_lines: Each README line that speaks about license terms.
        editions: The files that look like editions of the book.
    """

    repository: str
    default_branch: str
    head_commit: str
    commit: str
    tree: tuple[TreeEntry, ...]
    license_files: tuple[LicenseFile, ...]
    readmes: tuple[TreeEntry, ...]
    readme_lines: tuple[ReadmeLine, ...]
    editions: tuple[EditionFile, ...]


def blob_permalink(repository: str, commit: str, path: str, line: int | None = None) -> str:
    """Build the link to a file, or to one of its lines, at a commit.

    A link to a line opens the file's source view, because GitHub ignores line anchors on a
    rendered Markdown file.

    Args:
        repository: The repository as ``owner/name``.
        commit: The full commit SHA.
        path: Path of the file from the repository root.
        line: A line number counted from 1, or ``None`` to link to the whole file.

    Returns:
        The permalink, with the path percent-encoded.
    """
    link = f"https://github.com/{repository}/blob/{commit}/{quote(path, safe='/')}"
    return link if line is None else f"{link}?plain=1#L{line}"


def license_lines(text: str) -> tuple[LicenseLine, ...]:
    """Find the lines of a Markdown README that speak about license terms.

    A heading mentions license terms when it contains "License" in any letter case, or one of the
    Chinese words 许可, 协议, 版权, or 授权. Every non-blank line under such a heading is
    returned, up to the next heading of the same or a higher level. A line that contains one of
    those words outside such a section is returned too, with no heading. Text inside a fenced code
    block is never read as a heading.

    Args:
        text: The README's text.

    Returns:
        The matching lines in file order.
    """
    found: list[LicenseLine] = []
    section_heading: str | None = None
    section_level = 0
    fence: str | None = None
    # Lines are split on the newline character alone, which is how GitHub numbers them. Other
    # separators that str.splitlines honors would shift the numbers away from its line anchors.
    for number, raw in enumerate(text.split("\n"), start=1):
        line = raw.strip()
        fence_match = _FENCE.match(raw)
        if fence_match and fence in (None, fence_match.group(1)):
            fence = None if fence else fence_match.group(1)
        heading_match = None if fence or fence_match else _HEADING.match(raw)
        if heading_match:
            level = len(heading_match.group(1))
            if section_heading is not None and level <= section_level:
                section_heading = None
            if section_heading is None and _LICENSE_TERMS.search(line):
                section_heading, section_level = line, level
                continue
        if not line:
            continue
        if section_heading is not None:
            found.append(LicenseLine(number=number, heading=section_heading, text=line))
        elif _LICENSE_TERMS.search(line):
            found.append(LicenseLine(number=number, heading=None, text=line))
    return tuple(found)


def capture(client: GitHubClient, repository: str, ref: str | None = None) -> Capture:
    """Read a repository's license evidence at one commit.

    Args:
        client: The client to read through.
        repository: The repository as ``owner/name``.
        ref: The full SHA of the commit to read. The head of the default branch is read when it
            is omitted.

    Returns:
        The captured facts.

    Raises:
        NotFoundError: GitHub has no such repository, commit, or file.
        RateLimitedError: The GitHub rate limit is used up.
        UpstreamError: GitHub could not be reached or gave an unusable answer.
    """
    info = client.repository(repository)
    name = info.full_name
    head_commit = client.branch_head(name, info.default_branch)
    commit = ref or head_commit
    tree = client.tree(name, commit)

    license_files = tuple(
        LicenseFile(
            path=entry.path,
            blob_sha=entry.blob_sha,
            permalink=blob_permalink(name, commit, entry.path),
            text=client.file_text(name, commit, entry.path),
        )
        for entry in tree
        if PurePosixPath(entry.path).name.lower() in LICENSE_FILE_NAMES
    )
    readmes = tuple(entry for entry in tree if _is_readme(entry.path))
    readme_lines = tuple(
        ReadmeLine(
            path=entry.path,
            blob_sha=entry.blob_sha,
            number=line.number,
            heading=line.heading,
            text=line.text,
            permalink=blob_permalink(name, commit, entry.path, line.number),
        )
        for entry in readmes
        for line in license_lines(client.file_text(name, commit, entry.path))
    )
    editions = tuple(
        EditionFile(
            path=entry.path,
            format=PurePosixPath(entry.path).suffix.lower().removeprefix("."),
            blob_sha=entry.blob_sha,
            size=entry.size,
        )
        for entry in tree
        if PurePosixPath(entry.path).suffix.lower() in EDITION_SUFFIXES
    )
    return Capture(
        repository=name,
        default_branch=info.default_branch,
        head_commit=head_commit,
        commit=commit,
        tree=tree,
        license_files=license_files,
        readmes=readmes,
        readme_lines=readme_lines,
        editions=editions,
    )


def render(captured: Capture) -> str:
    """Write a capture as plain text for a person or an agent to copy from.

    Everything below the head commit line depends only on the evidence commit, so two captures of
    the same commit print the same text.

    Args:
        captured: The capture to write.

    Returns:
        The report, ending in a newline.
    """
    lines = [
        f"Repository: {captured.repository}",
        f"Default branch: {captured.default_branch}",
        f"Head commit: {captured.head_commit}",
        f"Evidence commit: {captured.commit}",
        "",
        f"== Tree: {len(captured.tree)} files (blob SHA, size in bytes, path) ==",
    ]
    lines.extend(f"{entry.blob_sha}  {entry.size:>10}  {entry.path}" for entry in captured.tree)

    lines += ["", f"== License files: {len(captured.license_files)} =="]
    if not captured.license_files:
        lines.append("No file named LICENSE, LICENSE.md, LICENSE.txt, or COPYING is in the tree.")
    for license_file in captured.license_files:
        lines += [
            "",
            f"File: {license_file.path}",
            f"Blob SHA: {license_file.blob_sha}",
            f"Permalink: {license_file.permalink}",
            "----- BEGIN TEXT -----",
            *license_file.text.rstrip("\n").split("\n"),
            "----- END TEXT -----",
        ]

    lines += ["", f"== README files: {len(captured.readmes)} =="]
    for readme in captured.readmes:
        lines += ["", f"File: {readme.path}", f"Blob SHA: {readme.blob_sha}"]
        in_file = [line for line in captured.readme_lines if line.path == readme.path]
        if not in_file:
            lines.append("No line speaks about license terms.")
        heading: str | None = ""
        for line in in_file:
            if line.heading != heading:
                heading = line.heading
                lines.append(
                    "Lines that mention license terms outside a license heading:"
                    if heading is None
                    else f'Lines under the heading "{heading}":'
                )
            lines += [f"  L{line.number}: {line.text}", f"    {line.permalink}"]

    lines += ["", f"== Edition files: {len(captured.editions)} (blob SHA, format, path) =="]
    lines.extend(
        f"{edition.blob_sha}  {edition.format:<4}  {edition.path}" for edition in captured.editions
    )
    return "\n".join(lines) + "\n"


def _is_readme(path: str) -> bool:
    name = PurePosixPath(path)
    return name.suffix.lower() in README_SUFFIXES and bool(_README_STEM.match(name.stem))
