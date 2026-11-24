"""Check every cataloged repository against GitHub and record what it shows.

Usage::

    GH_TOKEN="$(gh auth token)" uv run python scripts/sync.py [--root DIRECTORY] [--dry-run]

The command writes ``upstream/state.json`` and ``upstream/report.md`` and nothing else. It never
edits a book's metadata, chapters, license evidence, or mirror status. With ``--dry-run`` it
prints the report to standard output and writes no file.

The exit code is 1 when every checked book ended in error, or when the library or the state file
cannot be read. It is 0 otherwise, including when the report holds findings.

A token is read from ``GITHUB_TOKEN`` or ``GH_TOKEN`` when one is set. Without one GitHub allows
60 requests an hour. The token is never printed.
"""

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from kb.schema import LoadError
from kb.sync import (
    REPORT_FILE,
    STATE_FILE,
    UPSTREAM_DIR,
    Classification,
    StateError,
    render_report,
    summary_line,
    sync_library,
    write_run,
)
from kb.upstream import Fetch, GitHubClient, fetch_with_urllib, token_from_environment

REPO_ROOT = Path(__file__).resolve().parent.parent


def main(argv: Sequence[str] | None = None, fetch: Fetch = fetch_with_urllib) -> int:
    """Check every cataloged repository against GitHub and write or print the report.

    Args:
        argv: The command-line arguments without the program name. ``sys.argv`` is used when it
            is omitted.
        fetch: The function that performs each HTTP request.

    Returns:
        The exit status: 1 when every checked book ended in error or the library could not be
        read, and 0 otherwise.
    """
    parser = argparse.ArgumentParser(
        description="Check every cataloged repository against GitHub and record what it shows."
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=REPO_ROOT,
        help="directory that holds catalog.yaml (default: the repository this script is in)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="print the report to standard output and write no file",
    )
    arguments = parser.parse_args(argv)

    client = GitHubClient(fetch, token_from_environment())
    try:
        run = sync_library(arguments.root, client)
    except (LoadError, StateError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1

    if arguments.dry_run:
        sys.stdout.write(render_report(run.results))
    else:
        write_run(arguments.root, run)
        print(summary_line(run.results))
        print(f"sync: wrote {UPSTREAM_DIR}/{STATE_FILE} and {UPSTREAM_DIR}/{REPORT_FILE}.")

    for result in run.results:
        if result.classification is Classification.ERROR:
            print(f"error: {result.resource_id}: {result.message}", file=sys.stderr)
    if run.rate_limit is not None:
        print(f"error: {run.rate_limit}", file=sys.stderr)
    if run.all_failed:
        print(
            "error: no repository could be checked. Fix the cause above and run the command again.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
