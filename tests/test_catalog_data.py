"""The real catalog at the repository root records all 19 books with usable license evidence."""

import re
from pathlib import Path

import pytest
from kb.catalog import EvidenceKind, Library, MirrorStatus, load_library
from kb.gate import evaluate

EXPECTED_IDS = (
    "loop-engineering-orange-book",
    "hermes-agent-orange-book",
    "codex-orange-book",
    "claude-code-orange-book",
    "deepseek-harness-orange-book",
    "3d-vibe-coding-handbook",
    "harness-engineering-orange-book",
    "obsidian-ai-orange-book",
    "polymarket-orange-book",
    "agent-skills-orange-book",
    "openclaw-orange-book",
    "claude-code-source-analysis-orange-book",
    "cursor-orange-book",
    "gemma4-orange-book",
    "opus-4-7-system-card-orange-book",
    "founders-playbook-orange-book",
    "doubao-work-orange-book",
    "amazon-quick-orange-book",
    "phone-skill-orange-book",
)

BOOKS_WITH_AN_ALLOWLISTED_LICENSE_FILE = {
    "loop-engineering-orange-book",
    "hermes-agent-orange-book",
}

COMMIT_SHA = re.compile(r"(?<![0-9a-f])[0-9a-f]{40}(?![0-9a-f])")


@pytest.fixture(scope="module")
def library(repo_root: Path) -> Library:
    return load_library(repo_root)


def test_catalog_lists_the_19_books_once_each_in_order(library: Library) -> None:
    ids = [resource.id for resource in library.resources]

    assert len(ids) == 19
    assert len(set(ids)) == 19
    assert tuple(ids) == EXPECTED_IDS


def test_no_book_claims_more_than_the_license_gate_allows(library: Library) -> None:
    allowlist = library.catalog.license_allowlist

    over_claimed = [
        resource.id
        for resource in library.resources
        if not evaluate(resource, allowlist).permits(resource.mirror_status)
    ]

    assert over_claimed == []


def test_the_gate_allows_mirroring_only_for_the_two_books_with_an_mit_license_file(
    library: Library,
) -> None:
    allowlist = library.catalog.license_allowlist

    allowed = {
        resource.id
        for resource in library.resources
        if evaluate(resource, allowlist).allowed is MirrorStatus.MIRRORED
    }

    assert allowlist == ("MIT",)
    assert allowed == BOOKS_WITH_AN_ALLOWLISTED_LICENSE_FILE


def test_every_evidence_permalink_is_pinned_to_the_commit_the_evidence_was_read_at(
    library: Library,
) -> None:
    with_evidence = [
        resource
        for resource in library.resources
        if resource.license.evidence is not EvidenceKind.NONE
    ]

    assert len(with_evidence) == 12
    for resource in with_evidence:
        permalink = resource.license.permalink
        assert permalink is not None, resource.id
        assert COMMIT_SHA.findall(permalink) == [resource.license.commit], resource.id


def test_every_book_without_terms_lists_the_locations_that_were_checked(
    library: Library,
) -> None:
    without_terms = [
        resource
        for resource in library.resources
        if resource.license.spdx is None and resource.license.statement is None
    ]

    assert len(without_terms) == 7
    for resource in without_terms:
        assert len(resource.license.locations_checked) >= 2, resource.id
        assert all(location.strip() for location in resource.license.locations_checked)


def test_a_book_that_is_not_mirrored_holds_nothing_but_its_metadata(library: Library) -> None:
    not_mirrored = [
        resource
        for resource in library.resources
        if resource.mirror_status in (MirrorStatus.REFERENCE_ONLY, MirrorStatus.ELIGIBLE)
    ]

    assert not_mirrored
    for resource in not_mirrored:
        directory = library.root / "books" / resource.id
        assert sorted(path.name for path in directory.iterdir()) == ["metadata.yaml"], resource.id
