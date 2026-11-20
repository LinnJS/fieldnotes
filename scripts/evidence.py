"""Print the license evidence a GitHub repository shows at one commit.

Usage::

    GH_TOKEN="$(gh auth token)" uv run python scripts/evidence.py <owner/name> [--ref <commit>]

The output is plain text: the default branch, the head commit, every file with its Git blob id,
the full text of each license file, each README line that speaks about license terms with its
line number and permalink, and the files that look like editions. Copy quotes, blob ids, and
permalinks into a book's ``metadata.yaml`` from this output and from nowhere else.

A token is read from ``GITHUB_TOKEN`` or ``GH_TOKEN`` when one is set. Without one GitHub allows
60 requests an hour. The token is never printed.
"""

import argparse
import re
import sys
from collections.abc import Sequence

from kb.evidence import capture, render
from kb.upstream import (
    Fetch,
    GitHubClient,
    UpstreamError,
    fetch_with_urllib,
    token_from_environment,
)

_REPOSITORY = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
_COMMIT = re.compile(r"^[0-9a-f]{40}$")


def _repository(value: str) -> str:
    if not _REPOSITORY.match(value):
        raise argparse.ArgumentTypeError(f"{value!r} is not a repository in the form owner/name.")
    return value


def _commit(value: str) -> str:
    if not _COMMIT.match(value):
        raise argparse.ArgumentTypeError(
            f"{value!r} is not a full commit SHA of 40 lowercase hex characters."
        )
    return value


def main(argv: Sequence[str] | None = None, fetch: Fetch = fetch_with_urllib) -> int:
    """Run the command.

    Args:
        argv: The command-line arguments without the program name. ``sys.argv`` is used when it
            is omitted.
        fetch: The function that performs each HTTP request.

    Returns:
        The exit status: 0 when the capture was printed and 1 when GitHub could not supply it.
    """
    parser = argparse.ArgumentParser(
        description="Print the license evidence a GitHub repository shows at one commit."
    )
    parser.add_argument("repository", type=_repository, help="the repository as owner/name")
    parser.add_argument(
        "--ref",
        type=_commit,
        help="full SHA of the commit to read (default: the head of the default branch)",
    )
    arguments = parser.parse_args(argv)

    client = GitHubClient(fetch, token_from_environment())
    try:
        captured = capture(client, arguments.repository, arguments.ref)
    except UpstreamError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    sys.stdout.write(render(captured))
    return 0


if __name__ == "__main__":
    sys.exit(main())
