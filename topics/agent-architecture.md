---
id: agent-architecture
title: Agent Architecture
references:
  - resource: loop-engineering-orange-book
    chapter: loop-engineering-orange-book/from-prompt-to-context-to-loop
    note: Lays out a four-layer stack of prompt, context, harness, and loop, and says what each layer is responsible for.
  - resource: loop-engineering-orange-book
    chapter: loop-engineering-orange-book/five-moves-of-one-loop
    note: Breaks one turn of a loop into five moves, which are discovery, handoff, verification, persistence, and scheduling.
  - resource: loop-engineering-orange-book
    chapter: loop-engineering-orange-book/six-parts-of-a-loop
    note: Names the six parts a loop is built from and pairs each part with the move it serves.
  - resource: harness-engineering-orange-book
    note: Its README lists a framework part on the five components of a harness.
  - resource: openclaw-orange-book
    note: Its README lists a part on the Gateway-Node-Channel architecture of OpenClaw.
  - resource: claude-code-source-analysis-orange-book
    note: Its README lists an architecture overview of Claude Code and a chapter on its multi-agent architecture.
---

# Agent Architecture

**Scope (editorial).** Agent architecture is the way an agent system is put together: the parts it has, what each part is responsible for, and how control and information pass between them. This topic gathers reading on the structure of single agents and of the systems built around them.

§02 presents four layers that stack: prompt engineering, context engineering, harness engineering, and loop engineering. It says these terms "aren't replacements for each other" and gives each layer one concern, which is one sentence, one window, one run, or a loop that keeps running. [cite:loop-engineering-orange-book/from-prompt-to-context-to-loop@v260615]

§03 takes one turn of a loop apart into five moves: discovery, handoff, verification, persistence, and scheduling. It says that when any one is dropped, the loop will not turn or will spin in place. [cite:loop-engineering-orange-book/five-moves-of-one-loop@v260615]

§04 lists six parts a loop is built from: automations, worktrees, skills, connectors, sub-agents, and memory. It pairs the parts with the moves, so that discovery runs on skills, handoff on worktrees, verification on sub-agents, persistence on memory, and scheduling on automations. [cite:loop-engineering-orange-book/six-parts-of-a-loop@v260615]

## Where to read

- [§02 From Prompt to Context to Loop](../books/loop-engineering-orange-book/chapters/02-from-prompt-to-context-to-loop.md)
- [§03 The Five Moves of One Loop](../books/loop-engineering-orange-book/chapters/03-five-moves-of-one-loop.md)
- [§04 Six Parts: What a Loop Is Built From](../books/loop-engineering-orange-book/chapters/04-six-parts-of-a-loop.md)
- `harness-engineering-orange-book`. Run `python3 scripts/resolve.py harness-engineering-orange-book` for its official URL.
- `openclaw-orange-book`. Run `python3 scripts/resolve.py openclaw-orange-book` for its official URL.
- `claude-code-source-analysis-orange-book`. Run `python3 scripts/resolve.py claude-code-source-analysis-orange-book` for its official URL.
