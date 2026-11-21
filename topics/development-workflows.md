---
id: development-workflows
title: Development Workflows
references:
  - resource: loop-engineering-orange-book
    chapter: loop-engineering-orange-book/what-loop-engineering-really-is
    note: Describes the shift from prompting an agent line by line to designing the loop that prompts it.
  - resource: loop-engineering-orange-book
    chapter: loop-engineering-orange-book/five-moves-of-one-loop
    note: Follows a morning triage loop from failing tests to a pull request for a reviewed fix, with an inbox for what needs a person.
  - resource: loop-engineering-orange-book
    chapter: loop-engineering-orange-book/stay-the-engineer
    note: Argues that the person who builds a loop should keep manual checkpoints and keep exercising judgment.
  - resource: loop-engineering-orange-book
    chapter: loop-engineering-orange-book/build-your-first-loop
    note: Gives five steps for building a first loop and a checklist that ends with a human review point.
  - resource: codex-orange-book
    note: Its README lists a daily workflow part and a chapter on going from idea to shipped product with Codex.
  - resource: claude-code-orange-book
    note: Its README lists a chapter on workflows in Claude Code, including its Plan and Auto modes.
  - resource: 3d-vibe-coding-handbook
    note: Its README describes a full workflow from a one-sentence prompt to a running 3D scene built with AI-generated assets. The book is in Chinese.
  - resource: agent-skills-orange-book
    note: Its README says a skill file records a person's workflow, preferences, and quality standards for an AI assistant to reuse.
---

# Development Workflows

**Scope (editorial).** Development workflows are the repeatable ways people build software with AI agents: how work is found, delegated, reviewed, and merged, and where a person stays involved. This topic gathers reading on daily practice more than on any one tool.

§01 describes a change of position. In the old way a person prompts the agent line by line and it waits for the next line. In the new way the person designs something that runs on a timer, spawns helpers, and feeds its own results back to itself. [cite:loop-engineering-orange-book/what-loop-engineering-really-is@v260615]

§03 walks through a morning triage loop that it credits to Addy Osmani. A triage skill reads failing CI tests, open issues, and recent commits. Each finding worth acting on gets its own worktree, one sub-agent drafts a fix and a second reviews it, and anything the loop cannot handle goes to an inbox to wait for a person. [cite:loop-engineering-orange-book/five-moves-of-one-loop@v260615]

§08 says the decisions about where a manual checkpoint belongs cannot be read out of the loop, and have to be thought through in advance by the person who builds it. It ends on a quoted line: "Build the loop. But build it like someone who intends to stay the engineer, not just the person who presses go." [cite:loop-engineering-orange-book/stay-the-engineer@v260615]

§09 builds a first loop in five steps: run a `/loop`, have it triage CI and issues, add a state file, add an evaluator, and add worktrees. Its checklist asks about a discovery source, a state file, an evaluator, isolation, a token cap, and a human review point. [cite:loop-engineering-orange-book/build-your-first-loop@v260615]

## Where to read

- [§01 Stop Asking: What Loop Engineering Really Is](../books/loop-engineering-orange-book/chapters/01-what-loop-engineering-really-is.md)
- [§03 The Five Moves of One Loop](../books/loop-engineering-orange-book/chapters/03-five-moves-of-one-loop.md)
- [§08 Stay the Engineer, Not Just the One Who Presses Go](../books/loop-engineering-orange-book/chapters/08-stay-the-engineer.md)
- [§09 Build Your First Loop Today](../books/loop-engineering-orange-book/chapters/09-build-your-first-loop.md)
- `codex-orange-book`. Run `python3 scripts/resolve.py codex-orange-book` for its official URL.
- `claude-code-orange-book`. Run `python3 scripts/resolve.py claude-code-orange-book` for its official URL.
- `3d-vibe-coding-handbook`. Run `python3 scripts/resolve.py 3d-vibe-coding-handbook` for its official URL.
- `agent-skills-orange-book`. Run `python3 scripts/resolve.py agent-skills-orange-book` for its official URL.
