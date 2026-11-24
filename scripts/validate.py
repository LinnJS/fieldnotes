"""Check a library offline and print everything that is wrong with it.

Usage:
    uv run scripts/validate.py [--root DIRECTORY] [--json]

Each finding is printed to standard output as two lines, or as one JSON object per line with
``--json``. A one-line summary goes to standard error. The exit code is 1 when there is any
finding and 0 when there is none.
"""

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from kb.checks import run_checks

REPO_ROOT = Path(__file__).resolve().parent.parent


def main(argv: Sequence[str] | None = None) -> int:
    """Run every check on a library and print the findings.

    Args:
        argv: Command-line arguments without the program name. The process arguments are used
            when it is ``None``.

    Returns:
        The exit code: 1 when any finding exists and 0 otherwise.
    """
    parser = argparse.ArgumentParser(
        description="Check a library offline and print everything that is wrong with it."
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=REPO_ROOT,
        help="directory that holds catalog.yaml (default: the repository this script is in)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="print one JSON object per finding, one per line",
    )
    arguments = parser.parse_args(argv)

    findings = run_checks(arguments.root)
    for finding in findings:
        print(finding.to_json() if arguments.json else finding.to_text())

    if not findings:
        print("validate: no findings.", file=sys.stderr)
        return 0
    noun = "finding" if len(findings) == 1 else "findings"
    print(
        f"validate: {len(findings)} {noun}. Apply each fix and run the command again.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
