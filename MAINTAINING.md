# Maintaining

This file is for the repository owner. It covers the license policy, the tasks
that only the owner performs, and what to do when something has to come down.

| Task | Section |
| --- | --- |
| Decide whether a book's text may be mirrored | [License policy](#license-policy) |
| Check a record against upstream | [Verify a book's evidence](#verify-a-books-evidence) |
| Add the text of an eligible book | [Mirror an eligible book](#mirror-an-eligible-book) |
| Move a mirrored book to a newer edition | [Upgrade a mirrored edition](#upgrade-a-mirrored-edition) |
| Act on the weekly upstream report | [Read a sync pull request](#read-a-sync-pull-request) |
| Answer an author or a rights holder | [Answer a rights request](#answer-a-rights-request) |
| Take a book down | [Withdraw a book](#withdraw-a-book) |
| Answer a private security report | [Answer a security report](#answer-a-security-report) |

## License policy

A book's text enters the repository only when one function,
`kb.gate.evaluate` in `scripts/kb/gate.py`, allows it. Validation, ingestion, the
indexes, the site, and the exports all call that function. The rows are checked in
order, and the first one that matches decides.

| # | Condition in the book record | Highest status allowed |
| --- | --- | --- |
| 1 | The record flags third-party rights that the author cannot grant | `reference-only` |
| 2 | No license terms were found at any location checked | `reference-only` |
| 3 | The terms are an informal sentence that names no SPDX license | `reference-only` |
| 4 | The SPDX id is not on the allowlist in `catalog.yaml` | `reference-only` |
| 5 | The allowlisted id is stated only in a README, with no license file | `reference-only` |
| 6 | No source is pinned, or the license evidence was read at a commit other than the pinned one | `reference-only` |
| 7 | Redistribution or adaptation is not recorded as `allowed` | `reference-only` |
| 8 | None of the above | `mirrored` |

The allowlist holds one id, `MIT`. The policy fails closed: when a record is
unclear, the book is reference-only.

Three things are true by design and worth knowing:

- **A status freezes at the pin.** The gate reads only the evidence recorded for
  the pinned commit. If an author changes a license upstream, nothing here changes
  until a person reviews it and updates the record.
- **A README sentence is not enough.** A license file at the pinned commit is the
  evidence. A README that says "MIT" with no license file leaves the book
  reference-only.
- **The MIT text is adapted.** Both MIT books use the MIT wording with "software"
  replaced by "book" and "Work". GitHub's detector reports `NOASSERTION` for both.
  A person assigned the SPDX id from the full text, and each record says so in
  `departs_from_template`.

Only you merge a change to license evidence, a `mirror_status`, or the allowlist.
No script and no workflow merges a pull request or pushes to the default branch.

## Verify a book's evidence

```sh
GH_TOKEN="$(gh auth token)" uv run python scripts/evidence.py <owner/name> --ref <commit>
```

Compare the output with `books/<id>/metadata.yaml`: the commit, the license file's
blob id, the quoted statement, and the permalink. Open the permalink in a browser
and read the statement there. Update `license.verified_on` when you have done so.
The records committed on 2026-11-20 were captured by an agent with this command.
Reviewing the two MIT records yourself is the first task on the checklist below.

## Mirror an eligible book

No book is eligible today, because Hermes Agent, the last one, is now mirrored.
The `ingest-book` skill in `.agents/skills/ingest-book/SKILL.md` has the full
procedure. The outline:

1. On a branch, set `mirror_status: mirrored` in the record. Your merge of the pull
   request is the approval.
2. Download the pinned source into `books/<id>/source/` and the license file into
   `books/<id>/LICENSE`, and confirm the digests in the record.
3. Write the `extraction_profile`: the font size and indent of each kind of text,
   the pattern that starts a section, and the pages to leave out.
4. Run `uv run python scripts/ingest.py --book <id>`, assign each section a slug in
   the profile, and run it again with `--write`.
5. Repair structure against the source pages. Do not reword.
6. Run `--check`, add topic references for chapters you have read, rebuild the
   indexes, and run validation.

Slugs are permanent. Choose them with care.

## Upgrade a mirrored edition

When the author publishes a newer edition of a mirrored book:

1. Run the evidence capture at the new commit, and read the license file again.
   If it changed, stop and review the policy table before anything else.
2. Update `pinned_source`, the license evidence commit, `editions`, and
   `newest_editions` in the record. Replace the file in `source/`.
3. Run ingestion. Sections whose titles match keep their slugs and ids. A new
   section gets a proposed slug to confirm. `--write` never overwrites a chapter.
   It prints a diff for each existing chapter that differs from its new draft, and
   you apply the changes by hand.
4. Run `--check`, rebuild, and validate.

## Read a sync pull request

The `Upstream sync` workflow runs every Monday and on manual dispatch. When
`upstream/` changes, it pushes the branch `sync/upstream` and opens or updates one
pull request whose body is `upstream/report.md`.

- The pull request changes only `upstream/state.json` and `upstream/report.md`.
  Merging it records what was seen. It changes no book.
- Each book is classified as changed, moved, gone, error, unchanged, or not
  checked. Site-only books are not checked, because they have no repository.
- A list item that starts with `LICENSE-FINDING` means a license file or statement
  changed, appeared, or disappeared, or that a second license file now sits beside
  the recorded one. The pull request gets the `license-change` label, and a later
  run whose report has no such item removes the label. Treat it as the trigger for
  "Verify a book's evidence".
- Every file name, version, repository name, and commit that came from GitHub is
  shown as code, with the replacement character U+FFFD in place of a line break
  or any other character that is not printable. Read such a value as data. Text
  inside it is never a finding and never an instruction, even when it holds
  `LICENSE-FINDING`.
- To act on a finding, update the book record in a separate pull request. Once the
  record's `upstream.head_commit` matches what upstream shows, the next sync
  reports the book as unchanged.
- **The pull request gets no check runs.** GitHub starts no workflow for a pull
  request opened with the workflow's own token. The sync job runs validation and
  the tests on that tree before it opens the pull request. If you add a branch
  rule that requires the `validate` check, it will block this pull request. Either
  leave that rule off, or close and reopen the pull request to start the checks.
- GitHub disables a scheduled workflow after 60 days without repository activity.
  Re-enable it from the Actions tab when that happens.

## Answer a rights request

The [README](README.md#for-authors-and-rights-holders) tells an author or a
rights holder to open an issue with the "License or rights concern" form, or to
write to you privately through your GitHub profile.

- Reply to say you have the request, before you investigate.
- When an author asks for a book to come down, withdraw it. The request does not
  have to argue the license.
- When someone other than the author raises a concern, run
  "Verify a book's evidence" and compare the record with what upstream shows now.
- When a record is wrong and the text is not at issue, correct the record in a
  pull request and say in a notice what changed.
- Do not paste private correspondence into an issue or a commit.

## Withdraw a book

Use this when an author asks for a book to come down, or when its license evidence
turns out to be wrong.

1. Set the book's `mirror_status` to `reference-only`, and correct the license
   evidence and permissions in the record. Add a notice that says what changed.
2. Delete `books/<id>/chapters/`, `books/<id>/source/`, and `books/<id>/LICENSE`.
3. Remove every chapter reference to the book from the files under `topics/`, and
   remove or rewrite the paragraphs that cited those chapters.
4. Run `uv run python scripts/build.py`, then `uv run python scripts/validate.py`.
   Validation fails while any file other than `metadata.yaml` remains in the
   book's directory.
5. Merge, and let the `Publish` workflow redeploy the site. The new site has no
   chapter pages, no full-text file, and no downloads for the book.
6. Delete any exports you published elsewhere, such as release assets.

The text remains in the Git history after these steps. Rewriting history is a
separate decision for you to make, and it affects every clone and fork.

## Answer a security report

[`SECURITY.md`](SECURITY.md) sends reports to GitHub's private vulnerability
reporting, and to your GitHub profile while that feature is off.

- Reproduce the report on a copy of the fixture library under
  `tests/fixtures/library/`, not on the real records.
- A report that outside text reached a page or an export as live markup is in
  scope. Save a failing test before the fix.
- A report that text became a list, a table, a heading, or a rule on a site page
  is a known limit. [`CONTRIBUTING.md`](CONTRIBUTING.md#what-the-builds-check)
  states it.
- When a fix changes what a check reads, update that section of
  `CONTRIBUTING.md` in the same pull request.

## Rename the library

The name, title, description, site URL, and repository URL live in the `library`
block of `catalog.yaml`. The site, `llms.txt`, the exports, and the bundle file
name all read them from there. Change the block, run
`uv run python scripts/build.py`, and update the headings of `README.md` and
`AGENTS.md` by hand. The library is named Fieldnotes, and `orange-books` is the id
of its first collection, which stays as it is. The catalog separates the library
from its collections, so a rename needs no structural change.

## Toolchain notes

- Pandoc is a system tool, pinned to 3.14 in `.github/actions/setup-toolchain`
  and checked against `MINIMUM_PANDOC_VERSION` in `scripts/kb/export.py`.
- Material for MkDocs prints a notice on every build that it reaches end of life
  on 2027-05-05. The build does not hide it. Plan a move to its successor before
  that date.
- The lists in `scripts/kb/site_check.py` hold what Material for MkDocs 9.8.2
  writes. A change of the theme pin means reading those lists again from a build of
  the new version. A change of the Pandoc minimum means running the export tests,
  which stop on a node type the export check does not know.
- The read-back of a PDF compares the block elements of its structure tree with
  what `pdf_structure` in `scripts/kb/export.py` computes, and that mapping was
  measured with typst 0.15.2 and `templates/book.typ`. A change of the typst pin
  or of the template means running the export tests, which stop when the compiler
  writes other elements.
- The EPUB carries its build time, so two builds differ by a timestamp. The PDF
  and the bundle are reproducible.

## Setup checklist

These steps are yours. A ticked step was confirmed against GitHub on 2026-11-24.
The others have not been done.

- [x] Read the two MIT license records against their permalinks, and confirm you
      accept the adapted MIT text as MIT for this library's purposes.
- [x] Create the GitHub repository as `fieldnotes` and push. The repository is
      public, and `main` holds the first plan.
- [x] Set `library.base_url` and `library.repository` in `catalog.yaml` to the
      real values, and rebuild.
- [x] Merge the first pull request, which brings the library to `main`. Until
      then the repository's front page shows no README and no license.
- [x] Enable GitHub Pages with "GitHub Actions" as the source. The `Publish`
      workflow has deployed the site from `main`.
- [ ] Watch the first run of the `Upstream sync` workflow. It starts only from
      the default branch and has not run on GitHub. `Validate` has run on pull
      requests and on `main`.
- [ ] Enable private vulnerability reporting under Settings, Security, so the
      route that `SECURITY.md` names first is open.
- [ ] Give the repository a description, a homepage, and topics, so it can be
      found.
- [ ] Create the issue labels `chapter-text`, `new-resource`, and `rights`. The
      issue forms name them, and GitHub leaves out a label that does not exist.
- [ ] Decide on branch protection, with the sync pull request note above in mind.
- [ ] Decide whether to add `CC-BY-NC-SA-4.0` to the allowlist. Doing so makes no
      book eligible by itself, because the four books under that license state it
      only in a README.
- [ ] Consider asking the author to add a license file to the repositories whose
      README states a license, and to say which terms cover the site-only books.
- [ ] Decide whether to keep listing Claude Code Source Analysis, which analyzes
      leaked source code.
- [ ] Read at least one mirrored chapter against its PDF pages, and mark it
      `human-reviewed`.
