"""Shared pytest fixtures."""

import shutil
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURE_LIBRARY_ROOT = REPO_ROOT / "tests" / "fixtures" / "library"


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
    shutil.copytree(FIXTURE_LIBRARY_ROOT, root)
    return root
