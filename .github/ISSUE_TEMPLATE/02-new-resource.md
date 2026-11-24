---
name: Propose a resource (Markdown)
about: Suggest a book or another resource for the catalog.
title: "resource: "
labels: new-resource
---

<!--
The catalog records facts about a work: its title, its official URL, its
editions, and the license evidence found at a pinned commit. A new record
starts as reference-only. The library holds a work's text only when the
license gate in scripts/kb/gate.py allows it, and only the repository owner
merges a change to license evidence or a status.

Do not paste the text of the work into this issue.
-->

## Official URL

<!-- The author's own page or repository for the work. -->

## Source repository

<!-- owner/name on GitHub, if there is one. -->

## Author

## Where the license is stated

<!--
Keep one. A license file in the repository is the evidence the gate reads.
A README sentence alone leaves a work reference-only.
-->

- A license file in the repository
- A sentence in the README
- A statement on a web page
- No license terms found
- Not sure

## The license statement

<!-- Link to the file, the README line, or the page, and quote only the license statement itself. -->

## Why it belongs in the library

<!-- The topics it covers, and how it relates to the books already in the catalog. -->

## Before you submit

- [ ] I checked that the catalog does not already list this work.
- [ ] I have not pasted the text of the work into this issue.
- [ ] I would like to open the pull request myself with the `add-resource` skill.
