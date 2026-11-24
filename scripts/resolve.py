"""Turn a resource id or a chapter id into its record and a formatted citation.

Usage:
    python3 scripts/resolve.py [--root DIRECTORY] [--json] ID

The command needs Python 3.9 or newer and nothing else. It reads the committed indexes of the
library this script is in, or of the library named by ``--root``, so it can be called from any
directory.

For a chapter id it prints the record as ``key: value`` lines and ends with the formatted
citation. For a resource id it prints the record, the official URLs, whether the text may be
quoted, and the chapter ids when the book is mirrored. ``--json`` prints the record as one JSON
object instead, with a ``citation`` key for a chapter.

The exit code is 0 when the id resolves and 1 when it does not. An unknown id prints the three
nearest ids. A chapter id under a book that is not mirrored prints the book's official URL.
"""

from __future__ import annotations

import sys

# The check runs before the import below, which an older interpreter cannot load. Ruff calls
# the comparison outdated because Python 3.9 is the oldest version these files target.
if sys.version_info < (3, 9):  # noqa: UP036
    sys.exit(
        "resolve.py needs Python 3.9 or newer, and this is Python "
        + ".".join(str(part) for part in sys.version_info[:3])
        + "."
    )

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

from kb.readpath import (
    ReadPathError,
    ResolveError,
    load_index,
    record_json,
    record_lines,
    resolve,
)

REPO_ROOT = Path(__file__).resolve().parent.parent


def main(argv: Sequence[str] | None = None) -> int:
    """Resolve one id and print its record.

    Args:
        argv: Command-line arguments without the program name. The process arguments are used
            when it is ``None``.

    Returns:
        The exit code: 0 when the id resolves and 1 otherwise.
    """
    parser = argparse.ArgumentParser(
        description="Turn a resource id or a chapter id into its record and a formatted citation."
    )
    parser.add_argument("id", help="a resource id, or a chapter id such as <resource-id>/<slug>")
    parser.add_argument(
        "--root",
        type=Path,
        default=REPO_ROOT,
        help="directory that holds index/ (default: the repository this script is in)",
    )
    parser.add_argument("--json", action="store_true", help="print the record as one JSON object")
    arguments = parser.parse_args(argv)

    try:
        index = load_index(arguments.root)
        resolved = resolve(index, arguments.id)
    except ReadPathError as error:
        print(f"resolve: {error}", file=sys.stderr)
        return 1
    except ResolveError as error:
        print(f"resolve: {error}", file=sys.stderr)
        return 1

    if arguments.json:
        print(json.dumps(record_json(resolved), ensure_ascii=False, sort_keys=True))
    else:
        for line in record_lines(index, resolved):
            print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
