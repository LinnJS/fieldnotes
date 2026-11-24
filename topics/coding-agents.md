---
id: coding-agents
title: Coding Agents
references:
  - resource: loop-engineering-orange-book
    chapter: loop-engineering-orange-book/generator-and-evaluator
    note: Explains Claude Code's /goal command, where a fresh model decides whether the stop condition is met, and notes how Codex reaches the same capability.
  - resource: loop-engineering-orange-book
    chapter: loop-engineering-orange-book/loops-that-run-while-you-sleep
    note: Compares the scheduling features of Claude Code and Codex, from local /loop to cloud runs.
  - resource: loop-engineering-orange-book
    chapter: loop-engineering-orange-book/build-your-first-loop
    note: Walks through Claude Code's /loop, /goal, and worktree commands, with a table of the matching Codex features as of June 2026.
  - resource: codex-orange-book
    note: Its README calls it a guide to OpenAI Codex across its CLI, desktop app, cloud, IDE extension, and Chrome extension forms.
  - resource: claude-code-orange-book
    note: Its README calls it a guide to Claude Code, Anthropic's terminal AI programming tool, from installation to shipping products.
  - resource: claude-code-source-analysis-orange-book
    note: Its README says it examines the design decisions behind Claude Code, based on source code exposed in March 2026.
---

# Coding Agents

**Scope (editorial).** Coding agents are AI tools that read, write, and run code in a developer's repository and terminal. This topic gathers reading on what these tools can do, how their features compare, and how they are operated.

§09 introduces `/loop` as a built-in Claude Code command that reruns the same task on a time interval. It notes that the command is session-scoped, that recurring tasks expire after 7 days, and that it stops when the machine is turned off. [cite:loop-engineering-orange-book/build-your-first-loop@v260615]

§05 describes Claude Code's `/goal` command, which lets an agent run until a condition is met. It says a small fast model checks the condition after each turn, so that completion is decided by a fresh model and not by the one doing the work. [cite:loop-engineering-orange-book/generator-and-evaluator@v260615]

§06 compares where scheduled work runs. Local `/loop` and desktop scheduled tasks need the machine on, while Cloud Routines run in Anthropic's cloud on a fresh clone with a minimum interval of one hour. On the Codex side it names the Automations tab as the counterpart. [cite:loop-engineering-orange-book/loops-that-run-while-you-sleep@v260615]

§09's status table for June 2026 sets Claude Code features beside Codex ones. It warns that `/loop` and `/goal` belong to Claude Code and not to Codex. [cite:loop-engineering-orange-book/build-your-first-loop@v260615]

## Where to read

- [§05 Generator and Evaluator: Why an AI Can't Grade Its Own Code](../books/loop-engineering-orange-book/chapters/05-generator-and-evaluator.md)
- [§06 Loops That Run While You Sleep: Three Real Ones](../books/loop-engineering-orange-book/chapters/06-loops-that-run-while-you-sleep.md)
- [§09 Build Your First Loop Today](../books/loop-engineering-orange-book/chapters/09-build-your-first-loop.md)
- `codex-orange-book`. Run `python3 scripts/resolve.py codex-orange-book` for its official URL.
- `claude-code-orange-book`. Run `python3 scripts/resolve.py claude-code-orange-book` for its official URL.
- `claude-code-source-analysis-orange-book`. Run `python3 scripts/resolve.py claude-code-source-analysis-orange-book` for its official URL.
