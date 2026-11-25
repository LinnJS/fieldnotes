"""Turn a book's pinned source PDF into chapter drafts, or check its chapters against the PDF.

Usage:
    uv run scripts/ingest.py --book ID [--root DIRECTORY] [--write | --check]

With no flag the command writes one draft per section to ``build/ingest/<book>/`` under the
library root and prints the sections it found, the pages, the text that fits no rule of the
book's extraction profile, and the slugs it proposes for sections the profile does not list.

``--write`` also copies each draft into ``books/<book>/chapters/`` when the book has no chapter
with that id yet. It never changes an existing chapter. It prints a diff from each existing
chapter to its draft, for a person to apply by hand.

``--check`` writes nothing. It compares the book's chapters with a fresh extraction of the
source file and prints the result for each chapter.

The license gate is asked before any source file is read, and the source file's SHA-256 is
compared with the metadata before anything is written. The exit code is 0 on success and 1 when
the book is refused, the source does not verify, a chapter was not written, or a chapter fails
the check.
"""

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from kb.catalog import (
    BOOKS_DIR,
    CATALOG_FILE,
    METADATA_FILE,
    LoadError,
    Resource,
    load_catalog,
    load_chapters,
    load_resource,
)
from kb.fidelity import check_book, report_lines
from kb.ingest import (
    IngestError,
    check_gate,
    extract_book,
    summary_lines,
    write_chapters,
    write_drafts,
)
from kb.markdown import draft_chapters

REPO_ROOT = Path(__file__).resolve().parent.parent


def main(argv: Sequence[str] | None = None) -> int:
    """Ingest one book or check its chapters, and print what was done.

    Args:
        argv: Command-line arguments without the program name. The process arguments are used
            when it is ``None``.

    Returns:
        The exit code: 0 on success and 1 on any failure.
    """
    parser = argparse.ArgumentParser(
        description="Turn a book's pinned source PDF into chapter drafts, or check its chapters."
    )
    parser.add_argument("--book", required=True, help="id of a cataloged book")
    parser.add_argument(
        "--root",
        type=Path,
        default=REPO_ROOT,
        help="directory that holds catalog.yaml (default: the repository this script is in)",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--write",
        action="store_true",
        help="copy drafts into the book where no chapter with that id exists yet",
    )
    mode.add_argument(
        "--check",
        action="store_true",
        help="only compare the book's chapters with a fresh extraction of the source",
    )
    arguments = parser.parse_args(argv)

    try:
        catalog = load_catalog(arguments.root)
        if arguments.book not in catalog.resources:
            raise IngestError(
                f"The book {arguments.book} is not listed under resources in {CATALOG_FILE}.",
                "Pass the id of a cataloged book, or add the book to the catalog first.",
            )
        resource = load_resource(arguments.root, arguments.book)
        check_gate(resource, catalog.license_allowlist)
        if arguments.check:
            return _check(arguments.root, resource)
        return _ingest(arguments.root, resource, write=arguments.write)
    except LoadError as error:
        return _fail(
            str(error),
            "Correct the file so that it loads. scripts/validate.py lists everything that is "
            "wrong with a library.",
        )
    except IngestError as error:
        return _fail(error.message, error.fix)


def _ingest(root: Path, resource: Resource, *, write: bool) -> int:
    book = extract_book(root, resource)
    drafts = draft_chapters(resource, book.sections)
    directory = write_drafts(root, resource.id, drafts)
    print(_title(resource))
    for line in summary_lines(resource, book, drafts):
        print(line)
    print(f"Drafts written: {directory.as_posix()}/")
    if not write:
        return 0

    report = write_chapters(root, resource.id, drafts)
    for path in report.created:
        print(f"Created: {path.as_posix()}")
    for path in report.unchanged:
        print(f"Unchanged: {path.as_posix()}")
    for path, diff in report.differing:
        print(f"Differs from its draft and was left as it is: {path.as_posix()}")
        print(diff, end="")
    for draft in report.unassigned:
        print(f"Not written, because its slug is only proposed: {draft.file_name}")
    if report.unassigned:
        return _fail(
            f"{len(report.unassigned)} of {len(drafts)} sections have no slug assigned, so "
            "their chapters were not written.",
            "Add each section to extraction_profile.sections in "
            f"{BOOKS_DIR}/{resource.id}/{METADATA_FILE} with its title, slug, and part, and run "
            "the command again.",
        )
    return 0


def _check(root: Path, resource: Resource) -> int:
    report = check_book(root, resource, load_chapters(root, resource.id))
    if report.error is not None:
        return _fail(report.error.message, report.error.fix)
    print(_title(resource))
    for line in report_lines(resource, report):
        print(line)
    failed = sum(not result.passed for result in report.results)
    if failed:
        return _fail(
            f"{failed} of {len(report.results)} chapters do not match the source file.",
            "Restore the wording of the source in each chapter that failed. If a chapter is "
            "right and the extraction is wrong, list the words under accepted_differences in "
            f"{BOOKS_DIR}/{resource.id}/{METADATA_FILE} with the chapter id and a reason. If a "
            "chapter holds a block in the order its page prints and the extraction reads it in "
            "another order, record it under accepted_reorders with the chapter id, the page, "
            "the block as the chapter holds it, the block as a fresh draft holds it, and a "
            "reason.",
        )
    mislabeled = sum(bool(result.frontmatter) for result in report.results)
    if mislabeled:
        return _fail(
            f"The frontmatter of {mislabeled} of {len(report.results)} chapters does not "
            "describe the source file.",
            "Restore each field named above to the value the pinned source gives. The drafts "
            f"in build/ingest/{resource.id}/ hold the right frontmatter.",
        )
    if report.missing:
        return _fail(
            f"{len(report.missing)} of the source file's sections have no chapter.",
            f"Run `uv run python scripts/ingest.py --book {resource.id} --write` to add the "
            "missing chapters.",
        )
    if report.unmatched:
        return _fail(
            f"Text of the source file fits no role rule in {len(report.unmatched)} places, so "
            "no chapter holds it.",
            "Add a role rule for its font size to extraction_profile.roles in "
            f"{BOOKS_DIR}/{resource.id}/{METADATA_FILE}, or list its page under excluded_pages "
            "when the page is not part of the book's text.",
        )
    return 0


def _title(resource: Resource) -> str:
    pinned = resource.pinned_source
    if pinned is None:
        return f"ingest: {resource.id}"
    return f"ingest: {resource.id}, edition {pinned.edition}, language {pinned.language}"


def _fail(message: str, fix: str) -> int:
    print(f"ingest: {message}\n  fix: {fix}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
