"""The validation command prints findings and reports them through its exit code."""

import json
import subprocess
import sys
from pathlib import Path

import pytest
import validate

REFERENCE = "fixture-reference-book"

# The link sits on line 11 of the file, counted from the opening frontmatter fence.
TOPIC_WITH_BROKEN_LINK = """\
---
id: tea-service
title: Tea Service
references:
  - resource: fixture-reference-book
    note: Listed for its subject only.
---

# Tea Service

See [the kettle guide](kettle-guide.md) for more.
"""


def run_command(repo_root: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(repo_root / "scripts" / "validate.py"), *arguments],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )


def break_library(root: Path) -> None:
    """Add a source file to the reference-only book and a broken link to a topic."""
    (root / "books" / REFERENCE / "source").mkdir()
    (root / "books" / REFERENCE / "source" / "book.pdf").write_bytes(b"%PDF-1.7\n")
    (root / "topics" / "tea-service.md").write_text(TOPIC_WITH_BROKEN_LINK, encoding="utf-8")


def test_a_clean_library_prints_no_findings_and_exits_zero(
    repo_root: Path, fixture_library_root: Path
) -> None:
    result = run_command(repo_root, "--root", str(fixture_library_root))

    assert result.returncode == 0
    assert result.stdout == ""
    assert result.stderr.splitlines() == ["validate: no findings."]


def test_a_broken_library_prints_each_finding_and_exits_one(
    repo_root: Path, library_copy: Path
) -> None:
    break_library(library_copy)

    result = run_command(repo_root, "--root", str(library_copy))

    assert result.returncode == 1
    lines = result.stdout.splitlines()
    assert len(lines) == 6
    assert lines[0].startswith("[gate-content] books/fixture-reference-book/source/book.pdf: ")
    assert lines[1].startswith("  fix: ")
    assert lines[2].startswith("[index-stale] index/topics.json: ")
    assert lines[3].startswith("  fix: ")
    assert lines[4].startswith("[link-missing-target] topics/tea-service.md:11: ")
    assert lines[5].startswith("  fix: ")
    assert result.stderr.splitlines() == [
        "validate: 3 findings. Apply each fix and run the command again."
    ]


def test_json_prints_one_object_per_finding_with_every_field(
    repo_root: Path, library_copy: Path
) -> None:
    break_library(library_copy)

    result = run_command(repo_root, "--root", str(library_copy), "--json")

    assert result.returncode == 1
    records = [json.loads(line) for line in result.stdout.splitlines()]
    assert [(record["rule"], record["file"], record["line"]) for record in records] == [
        ("gate-content", "books/fixture-reference-book/source/book.pdf", None),
        ("index-stale", "index/topics.json", None),
        ("link-missing-target", "topics/tea-service.md", 11),
    ]
    for record in records:
        assert list(record) == ["rule", "file", "message", "fix", "line"]
        assert record["message"]
        assert record["fix"]


def test_malformed_yaml_is_reported_as_a_finding_and_not_a_traceback(
    repo_root: Path, library_copy: Path
) -> None:
    (library_copy / "catalog.yaml").write_text("library: [\n", encoding="utf-8")

    result = run_command(repo_root, "--root", str(library_copy))

    assert result.returncode == 1
    assert result.stdout.startswith("[invalid-file] catalog.yaml: ")
    assert "Traceback" not in result.stderr
    assert result.stderr.splitlines() == [
        "validate: 1 finding. Apply each fix and run the command again."
    ]


def test_main_returns_the_exit_code(
    fixture_library_root: Path, library_copy: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    break_library(library_copy)

    assert validate.main(["--root", str(fixture_library_root)]) == 0
    assert validate.main(["--root", str(library_copy)]) == 1
    capsys.readouterr()
