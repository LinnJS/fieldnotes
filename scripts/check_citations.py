"""Check the citations and quotes of Markdown documents against the library.

Usage:
    python3 scripts/check_citations.py [--root DIRECTORY] FILE [FILE ...]

The command needs Python 3.9 or newer and nothing else. It reads the committed indexes and the
chapter files of the library this script is in, or of the library named by ``--root``.

Three things are checked. Every ``[cite:<id>]`` token must resolve, and an ``@<edition>`` in it
must be the indexed edition. Every quote must appear word for word in the chapter it cites,
where white space, emphasis markers, inline code markers, and backslash escapes are ignored. A
quote that starts or ends inside a word of the chapter does not match. Nothing may be quoted
from a book that is not mirrored.

A quote is a Markdown or HTML block quote, or a span in quotation marks in a paragraph that
holds a token. The marks are straight double quotes, curly double quotes, the corner brackets
「」 and 『』, and the HTML element <q>. A span counts when it holds four words or more, or six
characters or more of a script written without spaces, which are Han, Hiragana, Katakana, and
Hangul. A span is checked against the first token after it in its paragraph, and against the
nearest token before it when none follows. A block quote needs a token in its paragraph or on
the next line.

Each problem is printed to standard output as ``FILE:LINE: message``. A one-line summary goes to
standard error. The exit code is 1 when there is any problem and 0 when there is none.
"""

from __future__ import annotations

import sys

# The check runs before the import below, which an older interpreter cannot load. Ruff calls
# the comparison outdated because Python 3.9 is the oldest version these files target.
if sys.version_info < (3, 9):  # noqa: UP036
    sys.exit(
        "check_citations.py needs Python 3.9 or newer, and this is Python "
        + ".".join(str(part) for part in sys.version_info[:3])
        + "."
    )

import argparse
from collections.abc import Sequence
from pathlib import Path

from kb.readpath import ReadPathError, check_text, load_index

REPO_ROOT = Path(__file__).resolve().parent.parent


def main(argv: Sequence[str] | None = None) -> int:
    """Check every given document and print each problem.

    Args:
        argv: Command-line arguments without the program name. The process arguments are used
            when it is ``None``.

    Returns:
        The exit code: 1 when any problem exists or a file cannot be read, and 0 otherwise.
    """
    parser = argparse.ArgumentParser(
        description="Check the citations and quotes of Markdown documents against the library."
    )
    parser.add_argument("files", nargs="+", type=Path, metavar="FILE", help="a Markdown document")
    parser.add_argument(
        "--root",
        type=Path,
        default=REPO_ROOT,
        help="directory that holds index/ (default: the repository this script is in)",
    )
    arguments = parser.parse_args(argv)

    count = 0
    try:
        index = load_index(arguments.root)
        for path in arguments.files:
            try:
                text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError) as error:
                print(f"{path}:1: The file cannot be read as UTF-8 text. {error}")
                count += 1
                continue
            for problem in check_text(index, text):
                print(f"{path}:{problem.line}: {problem.message}")
                count += 1
    except ReadPathError as error:
        print(f"check_citations: {error}", file=sys.stderr)
        return 1

    files = "1 file" if len(arguments.files) == 1 else f"{len(arguments.files)} files"
    if count == 0:
        print(f"check_citations: no problems in {files}.", file=sys.stderr)
        return 0
    noun = "problem" if count == 1 else "problems"
    print(
        f"check_citations: {count} {noun} in {files}. Quote the chapter file word for word, and "
        "take ids from scripts/resolve.py.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
