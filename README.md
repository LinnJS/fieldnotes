# Fieldnotes

An independent community library of AI engineering resources, built so that a
coding agent or a person can find what a book says on a topic, read that section,
and cite it with provenance that can be checked.

The first collection is the AI Orange Books by HuaShu (花叔), published at
<https://www.huasheng.ai/orange-books> and <https://github.com/alchaincyf>.

**This is not an official publication.** The author has not endorsed this project
and is not affiliated with it. Every book belongs to its author. The library holds
the text of a book only when the author's own license file allows redistribution,
and it links to the author's official source for every other book.

## What is in the library

The catalog lists 19 books. One is mirrored, one is eligible to be mirrored, and
17 are reference-only.

| Status | Meaning |
| --- | --- |
| `mirrored` | The text is in this repository as one Markdown file per section, under the author's license. It can be quoted and exported. |
| `eligible` | The recorded license evidence allows mirroring. Nobody has ingested the book yet, so its text is not here. |
| `reference-only` | The library records the book and links to it. Its text is not here and must not be quoted from this library. |

| Book | Id | Status | License evidence |
| --- | --- | --- | --- |
| [Loop Engineering: Stop Asking Me What It Is](https://github.com/alchaincyf/loop-engineering-orange-book) | `loop-engineering-orange-book` | mirrored | MIT (license file) |
| [Hermes Agent 2.0: The Complete Guide](https://github.com/alchaincyf/hermes-agent-orange-book) | `hermes-agent-orange-book` | eligible | MIT (license file) |
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
v260615, which is older than the Chinese edition v261020.

## Browse it

- **In the repository.** Start at [`llms.txt`](llms.txt) or
  [`topics/index.md`](topics/index.md). Chapters are plain Markdown under
  `books/<id>/chapters/`.
- **On the site.** `uv run python scripts/build.py --site` builds a searchable site
  into `dist/site/`, with a page per chapter, a page per topic, and a catalog card
  for every book. The site is planned for <https://linnjs.github.io/fieldnotes/>
  and is not published yet.
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
The second checks that every citation in a document resolves and that every quote
matches the cited chapter word for word.

Machine-readable entry points:

| File | Holds |
| --- | --- |
| `llms.txt` | Links to the instructions, the mirrored chapters, the other books, the topics, and the indexes |
| `index/catalog.json` | Every book with its license id, status, editions, and official URLs |
| `index/chapters.jsonl` | One line per mirrored chapter, with its path, source pages, and provenance |
| `index/topics.json` | Every topic with the books and chapters it references |
| `dist/llms-full.txt` | The full text of the mirrored books, built by `scripts/build.py --full` |

Four skills live in `.agents/skills/`, with links under `.claude/skills/`:
`add-resource`, `ingest-book`, `audit-agent-setup`, and `study`.

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

`evidence.py` and `sync.py` call the GitHub API. Set `GH_TOKEN` or `GITHUB_TOKEN`
for the higher rate limit, for example
`GH_TOKEN="$(gh auth token)" uv run python scripts/sync.py --dry-run`.

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

## Limitations

- One book is mirrored. The library is useful as a catalog for the other 18, and
  as a text source for one.
- Chapters are machine-extracted from the source PDF. Their words match the PDF,
  which a check enforces, but no person has read them against the pages yet.
  Emphasis inside paragraphs and the styling of callout boxes are not reproduced.
- The mirrored English edition of Loop Engineering trails the Chinese edition. The
  author's note says the newer edition corrects errors in the June text, including
  a quote wrongly attributed to Addy Osmani. The passage has not been identified in
  the English text, so no chapter carries an erratum.
- The workflows have not run on GitHub yet, and the site is not published.
- The WorkBuddy reading editions that the author links require a sign-in and were
  not read.
- License records reflect what was found on the date verified. They are not legal
  advice.

## Licenses

The code is MIT. The library's own prose and catalog data are CC BY 4.0. A mirrored
book keeps its author's license, which sits in `books/<id>/LICENSE`. See
[`LICENSES.md`](LICENSES.md) for the map.
