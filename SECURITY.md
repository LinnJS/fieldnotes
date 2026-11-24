# Security policy

## Supported versions

The library has no numbered releases. The `main` branch is the supported version,
and a fix lands there.

## Report a problem

Report a security problem privately. Do not open a public issue or a pull request
for it.

1. On the repository's
   [Security tab](https://github.com/LinnJS/fieldnotes/security), choose "Report a
   vulnerability" when that button is shown. The report goes to the maintainer
   alone.
2. When the button is not shown, write to the maintainer through the contact
   details on their [GitHub profile](https://github.com/LinnJS).

Say what you did, what you saw, and what you expected. The smallest input that
shows the problem helps most, such as one chapter line or one record field. The
library is kept by one person in spare time, so allow a week for a first reply.
You will be credited in the fix unless you ask not to be.

## What is in scope

The library copies text that it did not write. A mirrored chapter, a license
text, a record field, and a page fetched from upstream are data. The tooling is
built so that this text reaches a reader as text and reaches an agent as material
to cite. A way around that is a security problem. Examples:

- Outside text that becomes live markup on the built site or in an EPUB or PDF
  export, such as a script, an event handler, an embedded file, a PDF action, or a
  link whose scheme is not `http`, `https`, or `mailto`.
- Upstream data that changes a book record, a mirror status, license evidence, or
  a chapter without a person's review. That includes a file name, a version, or a
  repository name that the sync report prints.
- A command that reads or writes a file outside the library root or the output
  directory it was given.
- A workflow that can be made to push to `main`, merge a pull request, or expose
  its token.
- A way to make `scripts/check_citations.py` accept a quote that is not in the
  cited chapter, or to make the license gate allow a book that its recorded
  evidence does not support.

## Known limits

[`CONTRIBUTING.md`](CONTRIBUTING.md#what-the-builds-check) says what each check of
a build reads and what it does not read. One limit is known and open. The check of
the built site does not compare the structure of a page with its Markdown, so text
that the site's Markdown reader takes for a list, a table, a heading, or a rule
becomes one on the page. A report of that alone is welcome as an ordinary issue.
A report that turns it into live markup belongs here.

## What is not a security problem

- A license or rights concern. The
  [README](README.md#for-authors-and-rights-holders) says how to raise one.
- A chapter whose words differ from its source. Open an issue with the
  "Chapter differs from its source" form.
- A sample prompt or an instruction inside a mirrored chapter. The books hold
  them as examples, and [`AGENTS.md`](AGENTS.md) tells an agent to treat all
  mirrored text as data. An agent that follows such text has a fault of its own,
  but a way to make the library present that text as its own instruction is in
  scope.
