"""Export mirrored books as PDF and EPUB, and the whole library as one bundle.

Usage:
    uv run python scripts/export.py [--root DIRECTORY] [--book ID]
        [--format pdf|epub|bundle|all] [--out DIRECTORY]

With no ``--book`` the command exports every book recorded as mirrored, and the bundle once.
With ``--book`` it exports that one book, and ``all`` then means its PDF and its EPUB. The
bundle covers the whole library, so ``--format bundle`` takes no ``--book``.

Files are written to ``dist/exports/`` under the library root unless ``--out`` names another
directory:

- ``<resource-id>-<edition>.pdf`` and ``<resource-id>-<edition>.epub`` for each book.
- ``<library-name>-bundle.zip`` for the bundle.

The license gate is asked before anything is written. A book the gate refuses, a book that is
not recorded as mirrored, and an unknown id each stop the run. The PDF and the EPUB need Pandoc
on the PATH, which is installed once per machine: ``brew install pandoc`` on macOS. The bundle
needs the index files and ``llms.txt`` that ``scripts/build.py`` writes.

The exit code is 0 when every requested file was written and nonzero otherwise.
"""

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from kb.catalog import LoadError, load_library
from kb.export import (
    CJK_FONT_FAMILIES,
    EXPORTS_DIR,
    ExportError,
    find_cjk_font,
    find_pandoc,
    select_books,
    write_bundle,
    write_epub,
    write_pdf,
)

REPO_ROOT = Path(__file__).resolve().parent.parent

FORMATS = ("pdf", "epub", "bundle", "all")


def main(argv: Sequence[str] | None = None) -> int:
    """Write the requested exports and print the path of each file.

    Args:
        argv: Command-line arguments without the program name. The process arguments are used
            when it is ``None``.

    Returns:
        The exit code: 0 when every requested file was written and 1 otherwise.
    """
    parser = argparse.ArgumentParser(
        description="Export mirrored books as PDF and EPUB, and the library as one bundle."
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=REPO_ROOT,
        help="directory that holds catalog.yaml (default: the repository this script is in)",
    )
    parser.add_argument("--book", help="id of one mirrored book (default: every mirrored book)")
    parser.add_argument(
        "--format",
        choices=FORMATS,
        default="all",
        help="what to write (default: all)",
    )
    parser.add_argument(
        "--out",
        type=Path,
        help="directory to write into (default: dist/exports/ under the root)",
    )
    arguments = parser.parse_args(argv)
    if arguments.book is not None and arguments.format == "bundle":
        parser.error("the bundle covers the whole library, so --format bundle takes no --book")

    wants_pdf = arguments.format in ("pdf", "all")
    wants_epub = arguments.format in ("epub", "all")
    wants_bundle = arguments.format == "bundle" or (
        arguments.format == "all" and arguments.book is None
    )
    out_dir: Path = arguments.out if arguments.out is not None else arguments.root / EXPORTS_DIR

    try:
        library = load_library(arguments.root)
        books = select_books(library, arguments.book) if wants_pdf or wants_epub else ()
        pandoc = find_pandoc() if books else None
        # The bundle is written first because it checks the library's own files. A missing one
        # then stops the run before any book is built.
        if wants_bundle:
            print(f"Wrote {write_bundle(library, out_dir)}")
        if pandoc is None:
            if wants_pdf or wants_epub:
                print("No book is recorded as mirrored, so no PDF or EPUB was written.")
            return 0
        if wants_pdf and find_cjk_font() is None:
            print(
                "export: warning: no font for Chinese, Japanese, or Korean text was found, so "
                "those characters will show as empty boxes in the PDF. The fonts looked for "
                f"are: {', '.join(CJK_FONT_FAMILIES)}. Install one of them and run the command "
                "again.",
                file=sys.stderr,
            )
        for book in books:
            if wants_pdf:
                print(f"Wrote {write_pdf(library, book, out_dir, pandoc)}")
            if wants_epub:
                print(f"Wrote {write_epub(library, book, out_dir, pandoc)}")
    except LoadError as error:
        return _fail(
            str(error),
            "Correct the file so that it loads. scripts/validate.py lists everything that is "
            "wrong with a library.",
        )
    except ExportError as error:
        return _fail(error.message, error.fix)
    return 0


def _fail(message: str, fix: str) -> int:
    print(f"export: {message}\n  fix: {fix}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
