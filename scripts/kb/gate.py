"""The license gate: the one rule that decides how much of a resource the library may carry.

Every command that ingests, validates, indexes, builds, or exports asks this module. None of them
restates the rule, so a change to the policy is a change to this file and its tests.

The gate reads only what is recorded for the resource. It never looks at upstream, so a license
change observed there cannot alter a decision until a person updates the record.
"""

from collections.abc import Sequence
from dataclasses import dataclass

from kb.catalog import EvidenceKind, MirrorStatus, Permission, Resource

_RANK = {
    MirrorStatus.REFERENCE_ONLY: 0,
    MirrorStatus.ELIGIBLE: 1,
    MirrorStatus.MIRRORED: 2,
}


@dataclass(frozen=True)
class GateDecision:
    """The gate's answer for one resource.

    Attributes:
        allowed: The highest mirror status the resource may hold.
        reason: One or two sentences that say why, for a person to read.
    """

    allowed: MirrorStatus
    reason: str

    def permits(self, status: MirrorStatus) -> bool:
        """Say whether a resource with this decision may hold the given status.

        Args:
            status: The status a record claims or a command needs.

        Returns:
            True when the status is the allowed one or a lower one. Reference-only is the lowest
            and mirrored is the highest.
        """
        return _RANK[status] <= _RANK[self.allowed]


def evaluate(resource: Resource, allowlist: Sequence[str]) -> GateDecision:
    """Decide the highest mirror status a resource's recorded evidence allows.

    The conditions are checked in a fixed order and the first one that holds gives the answer:

    1. The record flags third-party rights.
    2. No terms were found anywhere checked.
    3. The terms name no SPDX license.
    4. The SPDX license is not on the allowlist.
    5. The license is stated somewhere other than a license file.
    6. The license file was not read at the pinned source commit, or redistribution and
       adaptation are not both allowed.

    A resource that meets none of them may be mirrored.

    Args:
        resource: The resource record.
        allowlist: SPDX ids the catalog allows to be mirrored.

    Returns:
        The highest status allowed, which is either mirrored or reference-only, and the reason.
    """
    terms = resource.license
    permissions = resource.permissions
    pinned = resource.pinned_source

    if permissions.third_party_rights:
        return _refuse("The record flags third-party rights that the author cannot grant.")
    if terms.evidence is EvidenceKind.NONE:
        return _refuse("No license terms were found at any location checked.")
    if terms.spdx is None:
        return _refuse("The recorded terms are informal and name no SPDX license.")
    if terms.spdx not in allowlist:
        listed = ", ".join(allowlist) if allowlist else "empty"
        return _refuse(f"The license {terms.spdx} is not on the allowlist, which is: {listed}.")
    if terms.evidence is not EvidenceKind.LICENSE_FILE:
        return _refuse(
            f"The license {terms.spdx} is stated only in a README. "
            "The gate requires a license file."
        )
    if pinned is None:
        return _refuse(
            "No pinned source is recorded, so the license file cannot be tied to a source commit."
        )
    if terms.commit != pinned.commit:
        return _refuse(
            f"The license file was read at commit {terms.commit}, "
            f"and the pinned source is at commit {pinned.commit}."
        )
    if (
        permissions.redistribution is not Permission.ALLOWED
        or permissions.adaptation is not Permission.ALLOWED
    ):
        return _refuse(
            f"The record says redistribution is {permissions.redistribution.value} and "
            f"adaptation is {permissions.adaptation.value}. Both must be allowed."
        )
    return GateDecision(
        allowed=MirrorStatus.MIRRORED,
        reason=(
            f"The license {terms.spdx} is on the allowlist, the evidence is a license file at "
            "the pinned source commit, and redistribution and adaptation are both allowed."
        ),
    )


def _refuse(reason: str) -> GateDecision:
    return GateDecision(allowed=MirrorStatus.REFERENCE_ONLY, reason=reason)
