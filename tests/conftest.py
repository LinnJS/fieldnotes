"""Shared pytest fixtures."""

import shutil
from pathlib import Path

import pytest
import typst

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURE_LIBRARY_ROOT = REPO_ROOT / "tests" / "fixtures" / "library"
SAMPLE_BOOK = REPO_ROOT / "tests" / "fixtures" / "sample-book.typ"

# The fixture library carries none of these, so each test library that is exported or built
# into a site gets its own.
ROOT_FILES = {
    "AGENTS.md": "# Agent guide\n\nInvented for automated tests.\n",
    "LICENSES.md": "# Licenses\n\nInvented for automated tests.\n",
    "llms.txt": "# Fixture Library\n",
    "index/catalog.json": '{"resources": []}\n',
    "index/topics.json": '{"topics": []}\n',
    "index/chapters.jsonl": '{"id": "fixture-mirrored-book/folding-the-hull"}\n',
}


def write_root_files(root: Path) -> None:
    """Write the root files a whole build reads into a copy of the fixture library."""
    for name, text in ROOT_FILES.items():
        (root / name).parent.mkdir(exist_ok=True)
        (root / name).write_text(text, encoding="utf-8")


def compile_sample_book(directory: Path, edition: str) -> Path:
    """Compile the fixture book with the fonts the Typst compiler embeds and return the PDF."""
    path = directory / f"sample-book-edition-{edition}.pdf"
    typst.compile(
        str(SAMPLE_BOOK),
        output=str(path),
        ignore_system_fonts=True,
        sys_inputs={"edition": edition},
    )
    return path


@pytest.fixture(scope="session")
def repo_root() -> Path:
    """Return the repository root."""
    return REPO_ROOT


@pytest.fixture(scope="session")
def fixture_library_root() -> Path:
    """Return the root of the committed synthetic library. Tests must not write to it."""
    return FIXTURE_LIBRARY_ROOT


@pytest.fixture
def library_copy(tmp_path: Path) -> Path:
    """Return the root of a private copy of the synthetic library that a test may edit."""
    root = tmp_path / "library"
    # Running a command by hand with the fixture library as its root leaves a build directory
    # there. Git ignores it, and a copy must not carry it.
    shutil.copytree(FIXTURE_LIBRARY_ROOT, root, ignore=shutil.ignore_patterns("build", "dist"))
    return root


@pytest.fixture(scope="session")
def sample_book_pdf(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Return a fresh compilation of the fixture book, which the committed source PDF must match."""
    return compile_sample_book(tmp_path_factory.mktemp("sample-book"), "1")


@pytest.fixture(scope="session")
def second_edition_pdf(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Return the fixture book's later edition, which inserts a section before the last one."""
    return compile_sample_book(tmp_path_factory.mktemp("sample-book"), "2")
