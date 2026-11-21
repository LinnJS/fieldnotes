"""The two read commands run on the standard library alone, on the Python that macOS ships."""

import ast
import runpy
import subprocess
import sys
from pathlib import Path

import pytest

SYSTEM_PYTHON = Path("/usr/bin/python3")
READ_PATH_FILES = ("kb/readpath.py", "resolve.py", "check_citations.py")
HULL = "fixture-mirrored-book/folding-the-hull"

BLOCKED_IMPORT = """\
import sys

for name in ("yaml", "jsonschema", "pypdf"):
    sys.modules[name] = None
sys.path.insert(0, sys.argv[1])

import kb.readpath
import check_citations
import resolve

loaded = sorted(name for name in ("yaml", "jsonschema", "pypdf") if sys.modules.get(name))
print("imported", loaded)
"""


def system_python_version() -> tuple[int, int] | None:
    """Return the version of the system interpreter, or None when there is none."""
    if not SYSTEM_PYTHON.exists():
        return None
    result = subprocess.run(
        [str(SYSTEM_PYTHON), "-c", "import sys; print(*sys.version_info[:2])"],
        capture_output=True,
        text=True,
        check=False,
        env={},
    )
    if result.returncode != 0:
        return None
    major, minor = result.stdout.split()
    return int(major), int(minor)


def run_system_python(
    repo_root: Path, script: str, *arguments: str
) -> subprocess.CompletedProcess[str]:
    """Run a script with no environment at all, so no virtualenv or PYTHONPATH can help it."""
    return subprocess.run(
        [str(SYSTEM_PYTHON), str(repo_root / "scripts" / script), *arguments],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
        env={},
        cwd="/",
    )


def test_the_read_path_imports_with_every_third_party_module_blocked(repo_root: Path) -> None:
    result = subprocess.run(
        [sys.executable, "-c", BLOCKED_IMPORT, str(repo_root / "scripts")],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.stderr == ""
    assert result.stdout.splitlines() == ["imported []"]


def test_the_read_path_files_import_only_the_standard_library_and_each_other(
    repo_root: Path,
) -> None:
    for name in READ_PATH_FILES:
        tree = ast.parse((repo_root / "scripts" / name).read_text(encoding="utf-8"))
        imported: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                assert node.level == 0, name
                assert node.module is not None, name
                imported.add(node.module)
        outside = {
            module
            for module in imported
            if module != "kb.readpath" and module.partition(".")[0] not in sys.stdlib_module_names
        }
        assert outside == set(), name


@pytest.mark.parametrize("script", ["resolve.py", "check_citations.py"])
def test_an_interpreter_older_than_3_9_is_told_the_required_version(
    repo_root: Path, script: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sys, "version_info", (3, 8, 18, "final", 0))

    with pytest.raises(SystemExit) as exit_info:
        runpy.run_path(str(repo_root / "scripts" / script), run_name="loaded_by_a_test")

    assert exit_info.value.code == f"{script} needs Python 3.9 or newer, and this is Python 3.8.18."


def test_both_commands_give_correct_output_under_the_system_python(
    repo_root: Path, fixture_library_root: Path, tmp_path: Path
) -> None:
    version = system_python_version()
    if version is None or version >= (3, 12):
        pytest.skip("needs /usr/bin/python3 older than 3.12")
    root = str(fixture_library_root)
    good = tmp_path / "good.md"
    good.write_text(
        '"A paper boat begins as a rectangle and ends as a promise that it will float." '
        f"[cite:{HULL}]\n",
        encoding="utf-8",
    )
    bad = tmp_path / "bad.md"
    bad.write_text(
        '"A paper boat begins as a square and ends as a promise that it will float." '
        f"[cite:{HULL}]\n",
        encoding="utf-8",
    )

    resolved = run_system_python(repo_root, "resolve.py", "--root", root, HULL)
    unknown = run_system_python(repo_root, "resolve.py", "--root", root, "no-such-book")
    passed = run_system_python(repo_root, "check_citations.py", "--root", root, str(good))
    failed = run_system_python(repo_root, "check_citations.py", "--root", root, str(bad))

    assert resolved.stderr == ""
    assert resolved.returncode == 0
    assert resolved.stdout.splitlines()[-1] == (
        'citation: Fixture Author, "Paper Boat Engineering (Test Fixture)" (English ed. v1.0.0), '
        '§01 "Folding the Hull", source PDF pp. 3-4. '
        "[cite:fixture-mirrored-book/folding-the-hull@v1.0.0]"
    )
    assert unknown.returncode == 1
    assert 'No resource or chapter has the id "no-such-book".' in unknown.stderr
    assert passed.returncode == 0
    assert passed.stdout == ""
    assert failed.returncode == 1
    assert failed.stdout.splitlines() == [
        f"{bad}:1: The quote is not in {HULL} word for word: "
        '"A paper boat begins as a square and ends as a promise that it will float."'
    ]
