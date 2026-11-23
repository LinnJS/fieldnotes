# Contributing

This library copies other people's books only where their license allows it, and
it promises readers that a mirrored chapter says what its source says. Most of the
rules below protect one of those two things.

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
short. The landing page `topics/index.md` follows the same rule after its first
paragraph. A table there needs no token unless a row holds a quote, and a
link-only list item needs none. A line that opens with a pipe is a table row
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

The `validate` workflow runs the same commands.

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
  theme's markup included, and the search index. It accepts every other file by
  its extension, its directory, or its name, and does not read it.
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
  or the attributes of an element.

When one of those parts holds something that the library, the pinned theme, and
the export do not write, the build fails and deletes its output. When that
happens, do not edit the chapter or the record, and do not widen a list in either
check. Report the failure to the owner.

A PDF fails this way when a table cell, a list item, or the text of a link in a
chapter starts with such a mark, because Pandoc's Typst writer does not escape a
mark there. That holds for a faithful chapter too, so report it and leave the
chapter as it is.

## Conventions

- Commits follow Conventional Commits: `type(topic): description`, imperative
  mood, lowercase, no trailing period.
- Python is typed, passes `mypy --strict`, and carries Google-style docstrings on
  public symbols.
- Tests run offline. A test that needs the network carries
  `@pytest.mark.network`.
- Ask before adding a dependency.
