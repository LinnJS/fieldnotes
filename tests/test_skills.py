"""The agent instructions, the four skills, the evaluation prompts, and the skill exposure check."""

import re
import shutil
from pathlib import Path
from typing import Any

import pytest
import yaml
from kb.checks import Finding, run_checks
from kb.frontmatter import split_frontmatter
from kb.readpath import load_index, resolve

SKILLS = ("add-resource", "audit-agent-setup", "ingest-book", "study")
CANONICAL = Path(".agents") / "skills"
EXPOSED = Path(".claude") / "skills"
RULE = "skill-exposure"

EVAL_CASES = {
    "cold-discovery",
    "topic-route",
    "exact-citation",
    "reference-only-refusal",
    "invented-chapter",
    "out-of-corpus-question",
    "injection-resistance",
    "license-gate",
    "audit-honesty",
}

SKILL_PATH = re.compile(r"\.agents/skills/[a-z0-9-]+/SKILL\.md")
SCRIPT_PATH = re.compile(r"scripts/[A-Za-z0-9_/-]+\.py")


def skill_file(root: Path, skill: str) -> Path:
    return root / CANONICAL / skill / "SKILL.md"


def frontmatter_of(path: Path) -> dict[str, Any]:
    frontmatter, _ = split_frontmatter(path.read_text(encoding="utf-8"))
    data = yaml.safe_load(frontmatter)
    assert isinstance(data, dict)
    return data


def body_of(path: Path) -> str:
    _, body = split_frontmatter(path.read_text(encoding="utf-8"))
    return body


def exposure_findings(root: Path) -> list[Finding]:
    return [finding for finding in run_checks(root) if finding.rule == RULE]


@pytest.fixture
def library_with_skills(library_copy: Path, repo_root: Path) -> Path:
    """Return an editable library that carries a copy of the repository's skills and links."""
    shutil.copytree(repo_root / CANONICAL, library_copy / CANONICAL, symlinks=True)
    shutil.copytree(repo_root / EXPOSED, library_copy / EXPOSED, symlinks=True)
    return library_copy


def test_claude_md_is_exactly_the_import_line(repo_root: Path) -> None:
    assert (repo_root / "CLAUDE.md").read_bytes() == b"@AGENTS.md\n"


def test_agents_md_is_smaller_than_32_kib(repo_root: Path) -> None:
    assert 0 < (repo_root / "AGENTS.md").stat().st_size < 32 * 1024


def test_the_canonical_directory_holds_the_four_skills(repo_root: Path) -> None:
    folders = {path.name for path in (repo_root / CANONICAL).iterdir() if path.is_dir()}

    assert folders == set(SKILLS)


@pytest.mark.parametrize("skill", SKILLS)
def test_skill_folder_name_equals_the_name_in_its_frontmatter(repo_root: Path, skill: str) -> None:
    assert frontmatter_of(skill_file(repo_root, skill))["name"] == skill


@pytest.mark.parametrize("skill", SKILLS)
def test_skill_frontmatter_has_only_name_and_description(repo_root: Path, skill: str) -> None:
    frontmatter = frontmatter_of(skill_file(repo_root, skill))

    assert set(frontmatter) == {"name", "description"}
    assert isinstance(frontmatter["description"], str)
    assert frontmatter["description"].strip()


def test_both_skill_directories_expose_the_same_names(repo_root: Path) -> None:
    exposed = {path.name for path in (repo_root / EXPOSED).iterdir()}

    assert exposed == set(SKILLS)


@pytest.mark.parametrize("skill", SKILLS)
def test_each_link_is_relative_and_resolves_to_the_canonical_folder(
    repo_root: Path, skill: str
) -> None:
    link = repo_root / EXPOSED / skill

    assert link.is_symlink()
    assert link.readlink() == Path(f"../../.agents/skills/{skill}")
    assert link.resolve() == (repo_root / CANONICAL / skill).resolve()


def test_the_repository_has_no_skill_exposure_finding(library_with_skills: Path) -> None:
    assert exposure_findings(library_with_skills) == []


def test_a_library_without_skills_has_no_skill_exposure_finding(library_copy: Path) -> None:
    assert not (library_copy / ".agents").exists()
    assert exposure_findings(library_copy) == []


def test_removing_one_symlink_produces_a_skill_exposure_finding(library_with_skills: Path) -> None:
    (library_with_skills / EXPOSED / "study").unlink()

    findings = exposure_findings(library_with_skills)

    assert [finding.file for finding in findings] == [".claude/skills/study"]
    assert "ln -s ../../.agents/skills/study .claude/skills/study" in findings[0].fix


def test_a_link_to_another_folder_produces_a_skill_exposure_finding(
    library_with_skills: Path,
) -> None:
    link = library_with_skills / EXPOSED / "study"
    link.unlink()
    link.symlink_to("../../.agents/skills/add-resource")

    findings = exposure_findings(library_with_skills)

    assert [finding.file for finding in findings] == [".claude/skills/study"]


def test_a_name_exposed_without_a_canonical_folder_produces_a_finding(
    library_with_skills: Path,
) -> None:
    (library_with_skills / EXPOSED / "fold-a-boat").symlink_to("../../.agents/skills/study")

    findings = exposure_findings(library_with_skills)

    assert [finding.file for finding in findings] == [".claude/skills/fold-a-boat"]


def test_a_frontmatter_name_that_differs_from_the_folder_produces_a_finding(
    library_with_skills: Path,
) -> None:
    path = skill_file(library_with_skills, "study")
    path.write_text(
        "---\nname: revise\ndescription: Returns a reading path.\n---\n\n# Study\n",
        encoding="utf-8",
    )

    findings = exposure_findings(library_with_skills)

    assert [finding.file for finding in findings] == [".agents/skills/study/SKILL.md"]
    assert "revise" in findings[0].message


def test_a_frontmatter_key_besides_name_and_description_produces_a_finding(
    library_with_skills: Path,
) -> None:
    path = skill_file(library_with_skills, "study")
    path.write_text(
        "---\nname: study\ndescription: Returns a reading path.\nallowed-tools: Read\n---\n",
        encoding="utf-8",
    )

    findings = exposure_findings(library_with_skills)

    assert [finding.file for finding in findings] == [".agents/skills/study/SKILL.md"]
    assert "allowed-tools" in findings[0].message


def test_a_skill_folder_without_a_readable_skill_file_produces_a_finding(
    library_with_skills: Path,
) -> None:
    skill_file(library_with_skills, "study").unlink()

    findings = exposure_findings(library_with_skills)

    assert [finding.file for finding in findings] == [".agents/skills/study/SKILL.md"]


def test_every_skill_path_in_the_agents_md_routing_table_exists(repo_root: Path) -> None:
    text = (repo_root / "AGENTS.md").read_text(encoding="utf-8")
    rows = [line for line in text.splitlines() if line.startswith("|")]
    routed = {path for row in rows for path in SKILL_PATH.findall(row)}

    assert routed == {f".agents/skills/{skill}/SKILL.md" for skill in SKILLS}
    for path in routed:
        assert (repo_root / path).is_file(), path


@pytest.mark.parametrize("skill", SKILLS)
def test_every_script_path_in_a_skill_body_exists(repo_root: Path, skill: str) -> None:
    mentioned = set(SCRIPT_PATH.findall(body_of(skill_file(repo_root, skill))))

    assert mentioned, "A skill refers to repository scripts by path."
    for path in mentioned:
        assert (repo_root / path).is_file(), path


def test_every_id_in_the_evaluation_prompts_resolves(repo_root: Path) -> None:
    data = yaml.safe_load((repo_root / "evals" / "prompts.yaml").read_text(encoding="utf-8"))
    prompts = data["prompts"]
    index = load_index(repo_root)

    assert {prompt["id"] for prompt in prompts} == EVAL_CASES
    assert len(prompts) == len(EVAL_CASES)
    for prompt in prompts:
        assert prompt["prompt"].strip()
        assert prompt["good_answer"].strip()
        assert prompt["expected_ids"] or prompt["forbidden_ids"] or prompt["forbidden_behavior"]
        for identifier in [*prompt["expected_ids"], *prompt["forbidden_ids"]]:
            # resolve raises ResolveError for an id that names nothing.
            assert resolve(index, identifier) is not None, identifier
