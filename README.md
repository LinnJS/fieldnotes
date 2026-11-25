# Fieldnotes

[![Validate](https://github.com/LinnJS/fieldnotes/actions/workflows/validate.yml/badge.svg?branch=main)](https://github.com/LinnJS/fieldnotes/actions/workflows/validate.yml)
[![Code: MIT](https://img.shields.io/badge/code-MIT-blue.svg)](LICENSE)
[![Prose and catalog: CC BY 4.0](https://img.shields.io/badge/prose%20and%20catalog-CC%20BY%204.0-blue.svg)](LICENSES.md)

An independent community library of AI engineering resources, built so that a
coding agent or a person can find what a book says on a topic, read that section,
and cite it with provenance that can be checked.

The first collection is the AI Orange Books by HuaShu (花叔), published at
<https://www.huasheng.ai/orange-books> and <https://github.com/alchaincyf>.

**This is not an official publication.** The author has not endorsed this project
and is not affiliated with it. Every book belongs to its author. The library holds
the text of a book only when the author's own license file allows redistribution,
and it links to the author's official source for every other book.

**Status.** The library is young. It catalogs 19 books and holds the text of one.
The tooling, the checks, and the agent instructions are complete enough to use.
The documentation site is at <https://linnjs.github.io/fieldnotes/>. See
[Limitations](#limitations).

## Quick start

Nothing needs to be installed. The two read commands run on Python 3.9 or newer
with the standard library alone.

```sh
git clone https://github.com/LinnJS/fieldnotes.git
cd fieldnotes
python3 scripts/resolve.py loop-engineering-orange-book/generator-and-evaluator
```

The command prints the record of that chapter. These are some of its lines.

```text
id: loop-engineering-orange-book/generator-and-evaluator
title: Generator and Evaluator: Why an AI Can't Grade Its Own Code
edition: v260615
edition_behind: true
license_id: MIT
mirror_status: mirrored
quote_permitted: true
path: books/loop-engineering-orange-book/chapters/05-generator-and-evaluator.md
source_pages: 17-20
extraction_status: machine-extracted
citation: HuaShu, "Loop Engineering: Stop Asking Me What It Is" (English ed. v260615), §05 "Generator and Evaluator: Why an AI Can't Grade Its Own Code", source PDF pp. 17-20. [cite:loop-engineering-orange-book/generator-and-evaluator@v260615]
```

From there:

1. Read the chapter at the `path` the record names. Each chapter reads on its own.
2. Quote it word for word, and put the `[cite:...]` token after the quote.
3. Check what you wrote.

```sh
python3 scripts/check_citations.py notes.md
```

The check confirms that every token resolves, and that every quote is in the
cited chapter word for word. It prints
`check_citations: no problems in 1 file.` when the document is clean.

To find a chapter in the first place, start at [`llms.txt`](llms.txt) or
[`topics/index.md`](topics/index.md), or search the mirrored text with
`rg -n "<words>" books/*/chapters/`.

## What the library promises

Three checks back what the library says about a book.

- **A license gate.** A book's text enters the repository only when the author's
  own license file, read at a pinned commit, allows redistribution and adaptation
  under a license on the allowlist. The gate fails closed, so a book whose terms
  are unclear stays reference-only. [`MAINTAINING.md`](MAINTAINING.md#license-policy)
  has the policy table.
- **A fidelity check.** A mirrored chapter is a faithful copy of its pinned source
  edition. Validation compares each chapter's words, link destinations, and
  frontmatter with a fresh extraction of the source PDF, and fails when they
  differ.
- **Citations that can be checked.** Every book and every mirrored chapter has a
  permanent id. A citation token names the id, and `scripts/check_citations.py`
  confirms the token and the quote beside it. An id that does not resolve is an
  error and not a guess.

## What is in the library

The catalog lists 19 books. Two are mirrored, and 17 are reference-only.

| Status | Meaning |
| --- | --- |
| `mirrored` | The text is in this repository as one Markdown file per section, under the author's license. It can be quoted and exported. |
| `eligible` | The recorded license evidence allows mirroring. Nobody has ingested the book yet, so its text is not here. |
| `reference-only` | The library records the book and links to it. Its text is not here and must not be quoted from this library. |

| Book | Id | Status | License evidence |
| --- | --- | --- | --- |
| [Loop Engineering: Stop Asking Me What It Is](https://github.com/alchaincyf/loop-engineering-orange-book) | `loop-engineering-orange-book` | mirrored | MIT (license file) |
| [Hermes Agent 2.0: The Complete Guide](https://github.com/alchaincyf/hermes-agent-orange-book) | `hermes-agent-orange-book` | mirrored | MIT (license file) |
| [OpenAI Codex: The Complete Guide](https://github.com/alchaincyf/codex-orange-book) | `codex-orange-book` | reference-only | CC-BY-NC-SA-4.0 (README statement, no license file) |
| [Claude Code: The Complete Guide](https://github.com/alchaincyf/claude-code-orange-book) | `claude-code-orange-book` | reference-only | CC-BY-NC-SA-4.0 (README statement, no license file) |
| [DeepSeek Harness: From First Boot to Teardown](https://github.com/alchaincyf/deepseek-harness-orange-book) | `deepseek-harness-orange-book` | reference-only | CC-BY-NC-SA-4.0 (README statement, no license file) |
| [3D Vibe Coding Handbook](https://github.com/alchaincyf/3d-vibe-coding-handbook) † | `3d-vibe-coding-handbook` | reference-only | CC-BY-NC-SA-4.0 (README statement, no license file) |
| [Harness Engineering: The Complete Guide](https://github.com/alchaincyf/harness-engineering-orange-book) | `harness-engineering-orange-book` | reference-only | Informal terms in the README |
| [Obsidian + Claude Code: Rebuild Your Second Brain with AI](https://github.com/alchaincyf/obsidian-ai-orange-book) | `obsidian-ai-orange-book` | reference-only | Informal terms in the README |
| [Polymarket: The Complete Guide](https://github.com/alchaincyf/polymarket-orange-book) | `polymarket-orange-book` | reference-only | Informal terms in the README |
| [Agent Skills: The Complete Guide](https://github.com/alchaincyf/agent-skills-orange-book) | `agent-skills-orange-book` | reference-only | Informal terms in the README |
| [OpenClaw: The Complete Guide](https://github.com/alchaincyf/openclaw-orange-book) | `openclaw-orange-book` | reference-only | Informal terms in the README |
| [Claude Code: Source Code Analysis](https://github.com/alchaincyf/claude-code-source-analysis-orange-book) | `claude-code-source-analysis-orange-book` | reference-only | Informal terms in the README |
| [Cursor: From Beginner to Mastery](https://www.huasheng.ai/orange-books/cursor/) † | `cursor-orange-book` | reference-only | No license terms found |
| [Gemma 4: The Complete Guide](https://www.huasheng.ai/orange-books/gemma4/) † | `gemma4-orange-book` | reference-only | No license terms found |
| [Claude Opus 4.7 System Card, Chinese Edition](https://www.huasheng.ai/orange-books/opus-4.7/) † | `opus-4-7-system-card-orange-book` | reference-only | No license terms found |
| [The Founder’s Playbook: Building an AI-Native Startup](https://www.huasheng.ai/orange-books/founders-playbook/) | `founders-playbook-orange-book` | reference-only | No license found. The page says the translation is for personal study only. |
| [Doubao Work: From Beginner to Mastery](https://www.huasheng.ai/orange-books/doubao-work/) † | `doubao-work-orange-book` | reference-only | No license terms found |
| [Amazon Quick Getting Started Orange Book](https://www.huasheng.ai/orange-books/amazon-quick/) † | `amazon-quick-orange-book` | reference-only | No license terms found |
| [From One Sentence to a Phone Skill](https://www.huasheng.ai/orange-books/phone-skill/) † | `phone-skill-orange-book` | reference-only | No license terms found |

† The author publishes no English title for this book. The title shown is this
library's translation of the original.

Each book's full record, with the quoted license statement, the commit it was read
at, and the date it was verified, is in `books/<id>/metadata.yaml`. Licenses were
last verified on 2026-11-20. The mirrored English edition of Loop Engineering is
v260615, and the mirrored English edition of Hermes Agent is v260607. Each is
older than its book's Chinese edition v261020.

Eleven topics under [`topics/`](topics/index.md) give reading paths across the
books. A topic is the library's own text, and each paragraph that reports what a
book says carries a citation to a mirrored chapter.

## Browse it

- **In the repository.** Start at [`llms.txt`](llms.txt) or
  [`topics/index.md`](topics/index.md). Chapters are plain Markdown under
  `books/<id>/chapters/`.
- **On the site.** <https://linnjs.github.io/fieldnotes/> is searchable, with a
  page per chapter, a page per topic, and a catalog card for every book. The
  `Publish` workflow deploys it from the default branch.
  `uv run python scripts/build.py --site` builds the same site into `dist/site/`.
- **As files.** `uv run python scripts/export.py` writes a PDF and an EPUB of each
  mirrored book, and a zip bundle of the whole library, into `dist/exports/`.

## Use it from an agent

[`AGENTS.md`](AGENTS.md) is the instruction file for Claude Code, Codex, Cursor,
and any other agent. `CLAUDE.md` only imports it.

Two commands work in a fresh clone with nothing installed. They need Python 3.9 or
newer and only the standard library.

```sh
python3 scripts/resolve.py loop-engineering-orange-book/generator-and-evaluator
python3 scripts/check_citations.py notes.md
```

The first turns an id into its record, its file path, and a formatted citation.
For an id it does not know, it exits with code 1 and prints the nearest valid ids.
The second checks that every citation in a document resolves and that every quote
matches the cited chapter word for word. Both take `--root` to point at another
copy of the library, and `resolve.py` takes `--json` for one JSON object.

An agent that works in another project can call both commands by their path in a
clone of this repository. They find the library from their own location.

Machine-readable entry points:

| File | Holds |
| --- | --- |
| `llms.txt` | Links to the instructions, the mirrored chapters, the other books, the topics, and the indexes |
| `index/catalog.json` | Every book with its license id, status, editions, and official URLs |
| `index/chapters.jsonl` | One line per mirrored chapter, with its path, source pages, and provenance |
| `index/topics.json` | Every topic with the books and chapters it references |
| `dist/llms-full.txt` | The full text of the mirrored books, built by `scripts/build.py --full` |

Four skills live in `.agents/skills/`, with links under `.claude/skills/`.

| Skill | What it does |
| --- | --- |
| [`add-resource`](.agents/skills/add-resource/SKILL.md) | Adds a book to the catalog from a URL, with license evidence captured at a pinned commit. |
| [`ingest-book`](.agents/skills/ingest-book/SKILL.md) | Mirrors the text of a book whose record is `eligible`. |
| [`audit-agent-setup`](.agents/skills/audit-agent-setup/SKILL.md) | Audits a project's agent setup against the mirrored chapters, with a citation for every finding. |
| [`study`](.agents/skills/study/SKILL.md) | Returns a reading path and study questions for a topic or a book. |

[`evals/prompts.yaml`](evals/prompts.yaml) holds prompts for testing how an agent
uses the library, with the ids a good answer cites and the behavior it avoids. No
command in this repository runs them.

## Install for development

Requirements:

- [uv](https://docs.astral.sh/uv/). It installs Python 3.12 and every Python
  dependency from `uv.lock`.
- [Pandoc](https://pandoc.org/installing.html) 3.14 or newer on the `PATH`, for
  the PDF and EPUB exports. On macOS, run `brew install pandoc`.
- A CJK font for the PDF export, so an author's native-script name prints. macOS
  ships one. On Debian or Ubuntu, install `fonts-noto-cjk`.

```sh
uv sync --locked
uv run pytest
uv run python scripts/validate.py
```

The tests and validation run offline.

## Commands

| Command | What it does |
| --- | --- |
| `uv run python scripts/validate.py` | Checks schemas, the license gate, chapter ids and order, links, topics, skills, chapter fidelity, and index freshness. Offline. |
| `uv run python scripts/build.py` | Rewrites `index/` and `llms.txt` from the canonical files. `--check` fails when they are stale. `--full` writes the full-text files. `--site` builds the site with its downloads. |
| `uv run python scripts/export.py --book <id> --format pdf` | Exports one mirrored book. Formats are `pdf`, `epub`, `bundle`, and `all`. It refuses a book that is not mirrored. |
| `uv run python scripts/ingest.py --book <id>` | Drafts chapter files from a book's pinned source PDF. `--write` adds missing chapters and never overwrites one. `--check` compares chapters with the source. |
| `uv run python scripts/evidence.py <owner/name>` | Prints a repository's head commit, files, license text, and README license lines, with permalinks, for a book record. |
| `uv run python scripts/sync.py --dry-run` | Checks every upstream repository for new editions and license changes, and prints a report. Needs the network. |
| `python3 scripts/resolve.py <id>` | Prints a book's or a chapter's record and citation. No install needed. |
| `python3 scripts/check_citations.py <files>` | Checks citations and quotes in Markdown files. No install needed. |

Every command prints its options with `--help`.

`evidence.py` and `sync.py` call the GitHub API. Set `GH_TOKEN` or `GITHUB_TOKEN`
for the higher rate limit, for example
`GH_TOKEN="$(gh auth token)" uv run python scripts/sync.py --dry-run`.

## Repository layout

| Path | Holds |
| --- | --- |
| `catalog.yaml` | The library's name and URLs, the license allowlist, and the list of cataloged books. |
| `books/<id>/metadata.yaml` | One book's catalog record, with its license evidence and mirror status. |
| `books/<id>/chapters/` | The text of a mirrored book, one Markdown file per section. Only a mirrored book has this directory. |
| `topics/` | The library's own reading paths, one file per topic. |
| `index/` and `llms.txt` | Generated indexes. `scripts/build.py` writes them. |
| `upstream/` | What the last upstream sync saw. `scripts/sync.py` writes it. |
| `scripts/` | The commands. The shared code is the `kb` package under `scripts/kb/`. |
| `schemas/` | JSON Schemas for the catalog, a book record, a chapter's frontmatter, and a topic. |
| `templates/` | The Typst template of the PDF, the EPUB stylesheet, and the site stylesheet. |
| `tests/` | The offline tests and their fixtures. |
| `evals/` | Prompts for evaluating agents that use the library. |
| `.agents/skills/` | The four skills. |
| `docs/plans/` | The design plans the library was built from. |

## How upstream changes arrive

A weekly workflow runs `scripts/sync.py`. It compares each upstream repository
with the catalog and writes what it saw to `upstream/state.json` and
`upstream/report.md`. When something changed, it opens one pull request with the
report. It never edits a chapter, a book record, license evidence, or a status. A
person reads the report and decides. See [`MAINTAINING.md`](MAINTAINING.md).

## Contribute

Corrections, new resources, and translations are welcome. Read
[`CONTRIBUTING.md`](CONTRIBUTING.md) first. The short version: a chapter is a
faithful copy of its source, so a correction may restore what the source says and
may not reword it.

A good first contribution is to read one mirrored chapter against its source PDF
pages and mark it `human-reviewed`. No chapter has had that reading yet.

Everyone who takes part is expected to follow the
[Code of Conduct](CODE_OF_CONDUCT.md).

## Get help

- **A question, a bug, or a proposal.** Open an
  [issue](https://github.com/LinnJS/fieldnotes/issues/new/choose) and pick the
  form that fits.
- **A security problem.** Do not open a public issue. Follow
  [`SECURITY.md`](SECURITY.md).

## For authors and rights holders

If you wrote a book in this catalog, or hold rights in one, you can ask for a
record to be corrected, for a book to be described differently, or for mirrored
text to come down. Open an issue with the "License or rights concern" form. If you
prefer to write privately, use the contact details on the maintainer's
[GitHub profile](https://github.com/LinnJS).

When an author asks for a book to come down, the maintainer withdraws it by the
steps in [`MAINTAINING.md`](MAINTAINING.md#withdraw-a-book). Those steps remove the
text from the repository, the site, and the exports. The text stays in the Git
history unless the maintainer also rewrites it, which that file treats as a
separate decision.

## Limitations

- Two books are mirrored. The library is useful as a catalog for the other 17, and
  as a text source for two.
- Chapters are machine-extracted from the source PDF. Their words match the PDF,
  which a check enforces, but no person has read them against the pages yet.
  Emphasis inside paragraphs and the styling of callout boxes are not reproduced.
- The mirrored English edition of Loop Engineering trails the Chinese edition. The
  author's note says the newer edition corrects errors in the June text, including
  a quote wrongly attributed to Addy Osmani. The passage has not been identified in
  the English text, so no chapter of that book carries an erratum.
- The mirrored English edition of Hermes Agent trails the Chinese edition. The
  author's README says the data-collection inference in the book's §03 is wrong
  and that the Chinese edition corrects it. That chapter records the erratum in
  its frontmatter and keeps the English text as printed.
- The `Upstream sync` workflow starts only from the default branch on a weekly
  schedule and has not run on GitHub yet.
- The check of the built site holds each page to a list of elements, attributes,
  and addresses. It does not compare the structure of a page with its Markdown.
  Text that the site's Markdown reader takes for a list, a table, a heading, or a
  rule therefore becomes one on the page. [`CONTRIBUTING.md`](CONTRIBUTING.md#what-the-builds-check)
  says what each check reads.
- The WorkBuddy reading editions that the author links require a sign-in and were
  not read.
- License records reflect what was found on the date verified. They are not legal
  advice.

## Licenses

The code is MIT. The library's own prose and catalog data are CC BY 4.0. A mirrored
book keeps its author's license, which sits in `books/<id>/LICENSE`. See
[`LICENSES.md`](LICENSES.md) for the map.

## Acknowledgments

The AI Orange Books are the work of HuaShu (花叔). This library exists because the
author published them openly, and two of them under a license that allows a
mirror. Read the books at their source: <https://www.huasheng.ai/orange-books>.
