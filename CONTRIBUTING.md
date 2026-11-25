# Contributing

This library copies other people's books only where their license allows it, and
it promises readers that a mirrored chapter says what its source says. Most of the
rules below protect one of those two things.

Everyone who takes part is expected to follow the
[Code of Conduct](CODE_OF_CONDUCT.md).

## Ways to contribute

| You want to | Start here |
| --- | --- |
| Report a bug in a command, the site, or an export | The "Tooling bug" issue form |
| Report a chapter that differs from its source | The "Chapter differs from its source" issue form, or [Correct a chapter](#correct-a-chapter) |
| Read a chapter against its source pages | [Correct a chapter](#correct-a-chapter). No chapter is `human-reviewed` yet, so this is a good first contribution. |
| Report a correction the author published | [Report an erratum](#report-an-erratum) |
| Add a book or another resource | The "Propose a resource" issue form, or [Propose a new resource](#propose-a-new-resource) |
| Raise a license or rights concern | The "License or rights concern" issue form. The [README](README.md#for-authors-and-rights-holders) has a private route. |
| Suggest a feature for the tooling | The "Feature request" issue form |
| Ask how something works | The "Question" issue form |
| Report a security problem | [`SECURITY.md`](SECURITY.md). Do not open a public issue. |

The issue forms are at
<https://github.com/LinnJS/fieldnotes/issues/new/choose>. For a change larger
than a correction, open an issue first so the approach can be agreed before you
write it.

## Before you start

```sh
uv sync --locked
uv run pytest
uv run python scripts/validate.py
```

You also need Pandoc 3.14 or newer for the export tests. See the
[README](README.md#install-for-development).

## Correct a chapter

A chapter under `books/<id>/chapters/` is a faithful copy of the pinned source
edition. The fidelity check compares its words, its link destinations, and its
frontmatter with a fresh extraction of the source PDF, and validation fails when
they differ. A link may point only where the source points, and it takes no
title.

You may:

- Fix structure the extraction got wrong: a heading level, a table, a list, a code
  block, a block quote, a missing line break.
- Restore a word that the source page shows and the extraction lost or garbled.
  Record it in the book's `extraction_profile.accepted_differences` with the
  chapter, the words, and the reason.
- Put a block back in the order its page prints when the extraction read it in
  another order, such as two boxes printed side by side. Record it in the book's
  `extraction_profile.accepted_reorders` with the chapter, the page, the block as
  the chapter holds it (`passage`), the block as a fresh draft holds it
  (`extraction`), and the reason. One record holds at most 200 words.
- Change `extraction_status` to `human-reviewed` after you have read the whole
  chapter against the source pages.

You may not:

- Reword, tighten, modernize, or correct the author's prose, even where the author
  made a mistake. A typo in the source stays in the chapter.
- Add text the source does not have. Commentary belongs in `topics/`.
- Change a chapter id. Ids are permanent, so citations keep working.

Run `uv run python scripts/ingest.py --book <id> --check` to see the result.

## Report an erratum

If the author has published a correction, do not edit the chapter text. Add an
entry to the chapter's `errata` list in its frontmatter, with a one-line
description in your own words and the URL where the author states it. The erratum
then appears with the chapter on the site, in the exports, and in the indexes. If
you cannot point to the author's own statement, open an issue with what you found.

## Propose a new resource

Start from the official URL. The `add-resource` skill in
`.agents/skills/add-resource/SKILL.md` walks an agent or a person through it. In
short:

1. Run `uv run python scripts/evidence.py <owner/name>` and copy the commit, the
   blob ids, and the license quote from its output into
   `books/<id>/metadata.yaml`. Do not write them from memory.
2. Record the permissions the statement actually grants, and `unclear` for
   anything it does not say.
3. Set `mirror_status: reference-only` unless the license gate allows more. A new
   record never needs to be higher than that.
4. Add the id to `catalog.yaml`, run `uv run python scripts/build.py`, and run
   validation.

A book is mirrored in a separate pull request, with the `ingest-book` skill. Only
the repository owner merges a change to license evidence, a status, or the
allowlist.

## Write or change a topic

A topic under `topics/` is the library's own text. Its first paragraph is the
scope statement, labeled `**Scope (editorial).**`. Every paragraph after it must
carry a citation token and say only what the cited mirrored chapter says. A
fenced block counts as a paragraph and takes its token on the next line that has
text. A heading longer than 80 characters counts as one too, so keep headings
short. A list item needs no token when it is only a link whose text is the
title, the section label and title, the id, or the file name of the chapter or
topic it points at, or when it is only the resolve instruction for a book id.
Any other link text makes a claim and needs a token. The landing page
`topics/index.md` follows the same rule after its first paragraph. A table there
needs no token unless a row holds a quote. A line that opens with a pipe is a table row
only below a header row and a delimiter row. Map a
chapter to a topic only after reading it. Map a book that is not mirrored only at
the resource level, from what its public description says it covers, and never
state what it says.

Get the token from `python3 scripts/resolve.py <chapter-id>`, and check your file
with `python3 scripts/check_citations.py topics/<file>.md`.

## Translations

The library mirrors translations the author has published. It does not host new
translations of a book, because a translation is an adaptation and needs the same
license evidence as the original. If you have translated a book whose license
allows it, propose it as a new edition with its own evidence.

## Generated files

`index/`, `llms.txt`, and `upstream/` are written by commands. Do not edit them by
hand. After you change a book record, a chapter's frontmatter, a topic, or
`catalog.yaml`, run `uv run python scripts/build.py` and commit the result.

## Open a pull request

1. Fork the repository and create a branch. Name it `type/short-description`,
   such as `fix/chapter-05-table`, with the same types that commits use.
2. Make one logical change. Keep a refactor apart from a change in behavior.
3. Run the checks below and fix what they report.
4. Open the pull request against `main` and fill in the template: the problem,
   the change, and how to verify it.

The repository owner merges every pull request. Nobody else merges, and nothing
is pushed to `main` directly. A change to license evidence, a mirror status, or
the allowlist gets the owner's own reading of the evidence before it merges, so
it can take longer.

By contributing, you agree that your contribution is licensed under the license
that [`LICENSES.md`](LICENSES.md) gives for the part of the repository you
change.

## Checks a pull request must pass

```sh
uv run ruff check .
uv run ruff format --check .
uv run mypy scripts
uv run pytest
uv run python scripts/validate.py
uv run python scripts/build.py --check
uv run python scripts/build.py --site
```

The `Validate` workflow runs the same commands on every pull request, and two
more: the read commands on the runner's own Python with nothing installed.

## What the builds check

A chapter, a topic, a license text, and a record field are text that the library
did not write. The site and the exports render that text with raw HTML, images,
attributes, and reference definitions turned off, and a link keeps its address
only when it is a relative path or uses `http`, `https`, or `mailto`. The site
does this in the MkDocs hook `scripts/site_hooks/outside_text.py`, and the exports
do it in `scripts/kb/export_document.py`, on the document Pandoc parsed. One
feature stays on for the site: the options of a fenced code block, which
`pymdownx.superfences` writes into the page unescaped. Only the check of the built
site refuses what they write. Validation also refuses markup characters in record
fields and titles, and a record field that starts with a mark that Markdown or
Typst reads as the start of a block, such as `-` or `1.` before a space.

Each build then reads back what it wrote. Each check reads the parts named here
and nothing else.

- `scripts/kb/site_check.py` reads every HTML page whole, the page head and the
  theme's markup included, and the search index. It holds each page to a list of
  elements, attributes, and addresses. It does not compare the structure of a
  page with its Markdown, so a list, a table, a heading, or a rule that
  Python-Markdown makes out of text passes. It accepts every other file by its
  extension, its directory, or its name, and does not read it.
- `scripts/kb/export_check.py` reads every member of an EPUB. It reads each XML
  member against a list of elements, attributes, and addresses, compares the
  `mimetype` member with the EPUB type, and accepts the stylesheet by its name
  without reading it.
- For a PDF, the same module reads the entries of the catalog and of each page,
  every link with its action and its address, and every outline item. It compares
  the outline's titles and the block elements of the structure tree with what
  the export computes from the document it checked. The block elements are the
  headings, lists, list items, tables, rows, cells, block quotes, and contents
  entries, and their order is compared, not their nesting. It does not read the
  text drawn on a page, the paragraph and inline elements of the structure tree,
  a rule line, or the attributes of an element.

When one of those parts holds something its check does not allow, the build
fails and deletes its output. When that happens, do not edit the chapter or the
record, and do not widen a list in either check. Report the failure to the owner.

A PDF fails this way when a table cell, a list item, or the text of a link in a
chapter starts with such a mark, because Pandoc's Typst writer does not escape a
mark there. That holds for a faithful chapter too, so report it and leave the
chapter as it is.

## Conventions

- Commits follow Conventional Commits: `type(topic): description`, imperative
  mood, lowercase, no trailing period. The types are `feat`, `fix`, `docs`,
  `style`, `refactor`, `perf`, `test`, `build`, `ci`, `chore`, and `revert`.
- Prose is plain. The documents here use complete sentences and no semicolons
  or em dashes.
- Python is typed, passes `mypy --strict`, and carries Google-style docstrings on
  public symbols.
- Tests run offline. A test that needs the network carries
  `@pytest.mark.network`.
- Ask before adding a dependency.
