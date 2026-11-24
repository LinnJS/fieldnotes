"""Write the generated files of a library, or check that the committed ones are fresh.

Usage:
    uv run python scripts/build.py [--root DIRECTORY] [--check | --full | --site]

With no flag the command writes the four committed files: ``index/catalog.json``,
``index/topics.json``, ``index/chapters.jsonl``, and ``llms.txt``.

``--check`` writes nothing. It builds the same four files in memory and prints one line for each
committed file that is missing or whose bytes differ.

``--full`` writes the full text of the mirrored books to ``dist/llms-full.txt`` and to one
``dist/llms-full/<resource-id>.txt`` per book. Those files are published and not committed.

``--site`` builds the documentation site into ``dist/site/`` and makes everything the site needs
first. It writes the full-text files, exports the bundle and the PDF and EPUB of every mirrored
book to ``dist/exports/``, stages the pages into ``build/site-src/``, writes
``build/mkdocs.yml``, and runs ``mkdocs build --strict``. The first step that fails stops the run,
and the message names the step. The exports need Pandoc on the PATH, and the bundle needs
``AGENTS.md`` and ``LICENSES.md`` at the library root. Material for MkDocs prints a notice about
its end of life on standard error at each build. The notice is not a warning, so it does not fail
the strict build, and Material leaves it out when ``NO_MKDOCS_2_WARNING=1`` is set in the
environment.

The exit code is 0 on success and 1 when the library cannot be loaded, a file cannot be built,
``--check`` finds a file that is not fresh, or a step of ``--site`` fails.
"""

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from kb.catalog import Library, LoadError, load_library
from kb.indexes import (
    STALE_FIX,
    BuildError,
    build_full_text,
    build_indexes,
    stale_files,
    write_files,
)
from kb.site import SiteError, build_site

REPO_ROOT = Path(__file__).resolve().parent.parent


def main(argv: Sequence[str] | None = None) -> int:
    """Build or check the generated files of a library and print what was done.

    Args:
        argv: Command-line arguments without the program name. The process arguments are used
            when it is ``None``.

    Returns:
        The exit code: 0 on success and 1 on any failure.
    """
    parser = argparse.ArgumentParser(
        description="Write the generated files of a library, or check that they are fresh."
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=REPO_ROOT,
        help="directory that holds catalog.yaml (default: the repository this script is in)",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--check",
        action="store_true",
        help="write nothing, and fail when a committed generated file is missing or stale",
    )
    mode.add_argument(
        "--full",
        action="store_true",
        help="write the full text of the mirrored books to dist/",
    )
    mode.add_argument(
        "--site",
        action="store_true",
        help="build the documentation site into dist/site/, with the exports it links",
    )
    arguments = parser.parse_args(argv)

    try:
        library = load_library(arguments.root)
        if arguments.check:
            return _check(library)
        if arguments.site:
            print(f"built: {build_site(library).relative_to(library.root).as_posix()}")
            return 0
        files = build_full_text(library) if arguments.full else build_indexes(library)
    except LoadError as error:
        print(
            f"build: {error} Correct the file, confirm with `uv run python scripts/validate.py`, "
            "and run the command again.",
            file=sys.stderr,
        )
        return 1
    except BuildError as error:
        print(f"build: {error}", file=sys.stderr)
        return 1
    except SiteError as error:
        print(
            f"build: the site build stopped at the {error.step} step. {error.message}",
            file=sys.stderr,
        )
        return 1

    write_files(library.root, files)
    for name in files:
        print(f"wrote: {name}")
    return 0


def _check(library: Library) -> int:
    stale = stale_files(library)
    for file in stale:
        print(f"{'missing' if file.missing else 'stale'}: {file.path}")
    if not stale:
        print("build: the committed generated files are fresh.", file=sys.stderr)
        return 0
    noun = "file is" if len(stale) == 1 else "files are"
    print(f"build: {len(stale)} generated {noun} not fresh. {STALE_FIX}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
