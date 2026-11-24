"""The license gate decides the highest mirror status a resource may hold."""

from dataclasses import replace
from pathlib import Path

import pytest
from kb.catalog import (
    EvidenceKind,
    License,
    MirrorStatus,
    OfficialUrls,
    Permission,
    Permissions,
    Person,
    PinnedSource,
    Resource,
    ResourceType,
    Titles,
    UrlSource,
    load_library,
)
from kb.gate import GateDecision, evaluate

ALLOWLIST = ("MIT",)
PINNED_COMMIT = "1" * 40
LATER_COMMIT = "2" * 40

MIT_LICENSE_FILE = License(
    spdx="MIT",
    evidence=EvidenceKind.LICENSE_FILE,
    statement="Permission is hereby granted, free of charge, to any person obtaining a copy",
    permalink=f"https://example.invalid/author/book/blob/{PINNED_COMMIT}/LICENSE",
    blob_sha="a" * 40,
    commit=PINNED_COMMIT,
    verified_on="2026-11-20",
    departs_from_template=False,
    locations_checked=("LICENSE",),
)

OPEN_PERMISSIONS = Permissions(
    redistribution=Permission.ALLOWED,
    adaptation=Permission.ALLOWED,
    commercial_use=Permission.ALLOWED,
    attribution_required=True,
    share_alike=False,
    third_party_rights=False,
)

PINNED_SOURCE = PinnedSource(
    repository="author/book",
    commit=PINNED_COMMIT,
    path="Book-v1.0.0.pdf",
    sha256="3" * 64,
    edition="v1.0.0",
    language="en",
    local_path=None,
)


def make_resource(
    *,
    license_block: License = MIT_LICENSE_FILE,
    permissions: Permissions = OPEN_PERMISSIONS,
    pinned_source: PinnedSource | None = PINNED_SOURCE,
) -> Resource:
    """Build a resource whose gate-relevant blocks are the ones given."""
    return Resource(
        id="gate-test-book",
        type=ResourceType.BOOK,
        collection="test-books",
        title=Titles(original="Gate Test Book", english="Gate Test Book", english_official=True),
        author=Person(name="Test Author", native_name=None, url=None),
        translator=None,
        languages=("en",),
        official_urls=OfficialUrls(site=None, repository=None, hosted_editions=()),
        site_slug=None,
        upstream=UrlSource(kind="url", url="https://example.invalid/book"),
        editions=(),
        edition_patterns=(),
        newest_editions=(),
        license=license_block,
        permissions=permissions,
        mirror_status=MirrorStatus.REFERENCE_ONLY,
        pinned_source=pinned_source,
        extraction_profile=None,
        notices=(),
    )


def test_allowlisted_license_file_at_pinned_commit_with_open_permissions_allows_mirrored() -> None:
    decision = evaluate(make_resource(), ALLOWLIST)

    assert decision.allowed is MirrorStatus.MIRRORED
    assert "MIT" in decision.reason


def test_allowlisted_license_stated_only_in_readme_allows_reference_only() -> None:
    readme_only = replace(MIT_LICENSE_FILE, evidence=EvidenceKind.README_STATEMENT)

    decision = evaluate(make_resource(license_block=readme_only), ALLOWLIST)

    assert decision.allowed is MirrorStatus.REFERENCE_ONLY
    assert "README" in decision.reason
    assert "license file" in decision.reason


def test_license_off_the_allowlist_allows_reference_only_and_names_the_allowlist() -> None:
    non_commercial = replace(MIT_LICENSE_FILE, spdx="CC-BY-NC-SA-4.0")

    decision = evaluate(make_resource(license_block=non_commercial), ALLOWLIST)

    assert decision.allowed is MirrorStatus.REFERENCE_ONLY
    assert "CC-BY-NC-SA-4.0" in decision.reason
    assert "allowlist" in decision.reason
    assert "MIT" in decision.reason


def test_informal_statement_with_no_spdx_id_allows_reference_only() -> None:
    informal = replace(
        MIT_LICENSE_FILE,
        spdx=None,
        evidence=EvidenceKind.README_STATEMENT,
        statement="This work is shared for educational purposes.",
    )

    decision = evaluate(make_resource(license_block=informal), ALLOWLIST)

    assert decision.allowed is MirrorStatus.REFERENCE_ONLY
    assert "SPDX" in decision.reason


def test_no_terms_anywhere_checked_allows_reference_only() -> None:
    no_terms = License(
        spdx=None,
        evidence=EvidenceKind.NONE,
        statement=None,
        permalink=None,
        blob_sha=None,
        commit=None,
        verified_on="2026-11-20",
        departs_from_template=False,
        locations_checked=("https://example.invalid/book",),
    )

    decision = evaluate(make_resource(license_block=no_terms, pinned_source=None), ALLOWLIST)

    assert decision.allowed is MirrorStatus.REFERENCE_ONLY
    assert "No license terms" in decision.reason


def test_third_party_rights_flag_allows_reference_only_despite_allowlisted_license_file() -> None:
    flagged = replace(OPEN_PERMISSIONS, third_party_rights=True)

    decision = evaluate(make_resource(permissions=flagged), ALLOWLIST)

    assert decision.allowed is MirrorStatus.REFERENCE_ONLY
    assert "third-party" in decision.reason


def test_evidence_read_at_another_commit_than_the_pinned_source_allows_reference_only() -> None:
    read_later = replace(MIT_LICENSE_FILE, commit=LATER_COMMIT)

    decision = evaluate(make_resource(license_block=read_later), ALLOWLIST)

    assert decision.allowed is MirrorStatus.REFERENCE_ONLY
    assert LATER_COMMIT in decision.reason
    assert PINNED_COMMIT in decision.reason


def test_missing_pinned_source_allows_reference_only() -> None:
    decision = evaluate(make_resource(pinned_source=None), ALLOWLIST)

    assert decision.allowed is MirrorStatus.REFERENCE_ONLY
    assert "pinned source" in decision.reason


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("redistribution", Permission.UNCLEAR),
        ("redistribution", Permission.DENIED),
        ("adaptation", Permission.UNCLEAR),
        ("adaptation", Permission.DENIED),
    ],
)
def test_redistribution_and_adaptation_must_both_be_allowed(field: str, value: Permission) -> None:
    restricted = replace(OPEN_PERMISSIONS, **{field: value})

    decision = evaluate(make_resource(permissions=restricted), ALLOWLIST)

    assert decision.allowed is MirrorStatus.REFERENCE_ONLY
    assert field in decision.reason


def test_denied_commercial_use_does_not_block_an_allowlisted_license() -> None:
    non_commercial = replace(OPEN_PERMISSIONS, commercial_use=Permission.DENIED)

    decision = evaluate(make_resource(permissions=non_commercial), ALLOWLIST)

    assert decision.allowed is MirrorStatus.MIRRORED


def test_the_first_matching_row_gives_the_reason() -> None:
    flagged = replace(OPEN_PERMISSIONS, third_party_rights=True)
    non_commercial = replace(MIT_LICENSE_FILE, spdx="CC-BY-NC-SA-4.0")

    decision = evaluate(make_resource(license_block=non_commercial, permissions=flagged), ALLOWLIST)

    assert "third-party" in decision.reason
    assert "allowlist" not in decision.reason


def test_the_allowlist_is_an_input_and_not_a_constant() -> None:
    resource = make_resource()

    assert evaluate(resource, ()).allowed is MirrorStatus.REFERENCE_ONLY
    assert evaluate(resource, ("Apache-2.0",)).allowed is MirrorStatus.REFERENCE_ONLY
    assert evaluate(resource, ("Apache-2.0", "MIT")).allowed is MirrorStatus.MIRRORED


def test_a_decision_permits_its_own_status_and_every_lower_one() -> None:
    mirrored = GateDecision(allowed=MirrorStatus.MIRRORED, reason="Allowed.")
    reference_only = GateDecision(allowed=MirrorStatus.REFERENCE_ONLY, reason="Refused.")

    assert mirrored.permits(MirrorStatus.MIRRORED)
    assert mirrored.permits(MirrorStatus.ELIGIBLE)
    assert mirrored.permits(MirrorStatus.REFERENCE_ONLY)
    assert reference_only.permits(MirrorStatus.REFERENCE_ONLY)
    assert not reference_only.permits(MirrorStatus.ELIGIBLE)
    assert not reference_only.permits(MirrorStatus.MIRRORED)


def test_the_fixture_library_books_get_the_statuses_they_record(
    fixture_library_root: Path,
) -> None:
    library = load_library(fixture_library_root)
    allowlist = library.catalog.license_allowlist

    mirrored = evaluate(library.resource("fixture-mirrored-book"), allowlist)
    reference_only = evaluate(library.resource("fixture-reference-book"), allowlist)

    assert mirrored.allowed is MirrorStatus.MIRRORED
    assert reference_only.allowed is MirrorStatus.REFERENCE_ONLY
