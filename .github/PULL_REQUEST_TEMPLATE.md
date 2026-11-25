<!--
Title: type(topic): description, in Conventional Commits form, imperative
mood, lowercase, with no trailing period.
Example: fix(export): compare the pdf structure tree
-->

## Problem

<!-- What is wrong or missing today, and who it affects. -->

Closes #

## Change

<!-- What this pull request does, and why this way. -->

## How to verify

<!-- The commands you ran and what they printed, or the steps a reviewer can follow. -->

## Kind of change

<!-- Check every one that applies. -->

- [ ] Chapter repair (structure, a restored word recorded in `accepted_differences`, or a block put back in page order recorded in `accepted_reorders`)
- [ ] Erratum
- [ ] New resource record
- [ ] Mirror a book, or upgrade a mirrored edition
- [ ] License evidence, a mirror status, or the allowlist
- [ ] Topic
- [ ] Tooling, site, or exports
- [ ] Documentation
- [ ] Workflow or repository configuration

## Checks

The `Validate` workflow runs these. Run them before you ask for review.

- [ ] The title follows `type(topic): description`.
- [ ] `uv run ruff check .` and `uv run ruff format --check .` pass.
- [ ] `uv run mypy scripts` passes.
- [ ] `uv run pytest` passes.
- [ ] `uv run python scripts/validate.py` prints no findings.
- [ ] `uv run python scripts/build.py --check` passes, so the generated files are fresh.
- [ ] `uv run python scripts/build.py --site` passes.

## Library rules

<!-- Check each one that applies to this change, and leave the rest unchecked. -->

- [ ] No chapter is reworded, shortened, or corrected. An edit restores what the source page shows.
- [ ] No chapter id is changed.
- [ ] Every commit, blob id, and license quote in a book record is copied from the output of `scripts/evidence.py`, and no status is set above what `scripts/kb/gate.py` allows.
- [ ] No generated file under `index/`, `llms.txt`, or `upstream/` is edited by hand.
- [ ] A new or changed topic passes `python3 scripts/check_citations.py`.
- [ ] A test that needs the network carries `@pytest.mark.network`.
- [ ] No new dependency, or the owner agreed to it first.
