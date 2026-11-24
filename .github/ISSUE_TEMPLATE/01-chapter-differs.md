---
name: Chapter differs from its source (Markdown)
about: A mirrored chapter differs from its source PDF, or the author has published a correction.
title: "chapter: "
labels: chapter-text
---

<!--
A chapter under books/<id>/chapters/ is a faithful copy of the pinned source
edition. A correction may restore what the source says. It may never reword,
shorten, modernize, or correct the author's prose. A typo in the source stays
in the chapter.

If the author has published a correction, the library records it as an
erratum beside the chapter and keeps the text as the source printed it.
-->

## Kind of problem

<!-- Keep one. -->

- Extraction error: the chapter differs from the pinned source PDF
- Erratum: the author has published a correction
- Other

## Chapter id

<!-- Confirm it with `python3 scripts/resolve.py <id>`. -->

## Source pages

<!-- The page numbers in the source PDF. The chapter frontmatter lists them. -->

## What the chapter says

<!-- Copy the passage from the chapter file exactly. -->

```markdown

```

## What the source shows

<!--
For an extraction error, describe what the source page shows, such as a
heading level, a table, a list, or a lost word. For an erratum, describe the
author's correction in your own words.
-->

## Where the author states the correction

<!-- Required for an erratum. Link to the author's own statement. -->

## Before you submit

- [ ] I compared the chapter with the pinned source edition named in its frontmatter, not with a newer edition.
- [ ] I am not asking to reword, shorten, or improve the author's text.
