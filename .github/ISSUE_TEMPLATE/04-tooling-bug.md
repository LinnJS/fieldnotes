---
name: Tooling bug (Markdown)
about: A command, a check, the site, an export, or a topic does something wrong.
title: "bug: "
labels: bug
---

<!--
If the site or export read-back check fails on a chapter or a record, do not
edit the chapter or widen a list in the check. Report the failure here with
the full output.

For a chapter that differs from its source, use the "Chapter differs from its
source" template instead.
-->

## Area

<!-- Keep one. -->

- Validation (scripts/validate.py)
- Indexes and llms.txt (scripts/build.py)
- Site (scripts/build.py --site)
- Exports (PDF, EPUB, bundle)
- Ingestion (scripts/ingest.py)
- Upstream sync or evidence capture
- resolve.py or check_citations.py
- Agent instructions or skills
- A topic misstates the chapter it cites
- Workflows
- Other

## Command

<!-- The exact command you ran, from the repository root. -->

```sh

```

## What happened

<!-- Paste the full output. Remove any token or credential first. -->

```text

```

## What you expected

## Environment

<!-- Paste the output of these commands. -->

```text
$ git rev-parse --short HEAD
$ uname -sr
$ python3 --version
$ uv --version
$ pandoc --version | head -n 1
```
