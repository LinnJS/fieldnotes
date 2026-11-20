# Licenses in this repository

This repository holds work under more than one license. No single license covers
all of it. The table says which license applies to each part.

| Part | Paths | License | Copyright holder |
| --- | --- | --- | --- |
| Code and configuration | `scripts/`, `tests/`, `schemas/`, `templates/`, `.github/`, `mkdocs.yml`, `pyproject.toml` | MIT, in [`LICENSE`](LICENSE) | Justin Linn |
| Original prose and catalog data | `README.md`, `CONTRIBUTING.md`, `MAINTAINING.md`, `AGENTS.md`, `topics/`, `.agents/skills/`, `catalog.yaml`, `books/*/metadata.yaml`, `index/`, `upstream/` | [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). The license statements quoted in metadata belong to their authors. | Justin Linn |
| Mirrored works | `books/<id>/chapters/`, `books/<id>/source/` | The work's own license, in `books/<id>/LICENSE` | The work's author |

## Mirrored works

A mirrored work keeps the license its author gave it. The repository's MIT
license does not apply to it. Each mirrored work carries its upstream license
text and copyright notice in its own directory, and every export and full-text
file repeats them.

A work appears under `books/<id>/chapters/` only when its recorded license
evidence passes the license gate that `scripts/validate.py` enforces. Every
other cataloged work is reference-only. Its `metadata.yaml` links to the
author's official source and holds none of the work's text beyond the quoted
license statement.

## Test fixtures

`tests/fixtures/github/` holds trimmed recordings of GitHub API responses for the
Loop Engineering repository, including its MIT license text and excerpts of its
README. They are the author's words, kept under that repository's MIT license.
Everything under `tests/fixtures/library/` is invented for the tests.

## Attribution

The first collection in this library is the AI Orange Books by HuaShu (花叔),
published at <https://www.huasheng.ai/orange-books> and
<https://github.com/alchaincyf>. This project is an independent community
effort. The author has not endorsed it.
