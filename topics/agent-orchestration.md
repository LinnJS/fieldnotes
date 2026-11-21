---
id: agent-orchestration
title: Agent Orchestration
references:
  - resource: loop-engineering-orange-book
    chapter: loop-engineering-orange-book/five-moves-of-one-loop
    note: Describes handing each finding to a sub-agent in its own worktree, and scheduling as the move that makes a loop repeat.
  - resource: loop-engineering-orange-book
    chapter: loop-engineering-orange-book/six-parts-of-a-loop
    note: Covers automations, worktrees, and sub-agents as the parts that start a loop, isolate parallel agents, and separate writing from judging.
  - resource: loop-engineering-orange-book
    chapter: loop-engineering-orange-book/loops-that-run-while-you-sleep
    note: Shows the deterministic orchestrator and gates of Stripe's Minions, and compares local and cloud scheduling.
  - resource: hermes-agent-orange-book
    note: Its README lists a part on multi-agent work and orchestration in Hermes Agent, from delegated tasks to a Kanban platform.
  - resource: claude-code-orange-book
    note: Its README lists multi-agent collaboration among its advanced practice chapters.
  - resource: harness-engineering-orange-book
    note: Its README names orchestration layers among the things a harness designer builds, and lists a hands-on section on orchestration.
  - resource: claude-code-source-analysis-orange-book
    note: Its README lists a chapter on the multi-agent architecture of Claude Code.
---

# Agent Orchestration

**Scope (editorial).** Agent orchestration is the coordination of more than one agent or agent run: how work is divided and handed out, how parallel workers are kept apart, who reviews whom, and what triggers the next run. This topic gathers reading on multi-agent structure and scheduling.

§03 describes handoff as cutting a job into isolated tasks before giving them out. In its example every finding worth acting on gets its own git worktree, one sub-agent drafts the fix, and a second sub-agent reviews it. [cite:loop-engineering-orange-book/five-moves-of-one-loop@v260615]

§04 explains why parallel agents need isolation, and gives the reason in a quoted line: "Two agents writing the same file is the exact same headache as two engineers committing to the same lines." [cite:loop-engineering-orange-book/six-parts-of-a-loop@v260615]

§04 says the key use of sub-agents is to split the one that writes from the one that judges, where the judge has different instructions and sometimes a different model. [cite:loop-engineering-orange-book/six-parts-of-a-loop@v260615]

§06 reports that Stripe's Minions alternate deterministic gates with model steps. After the agent finishes the code, a hard-coded pipeline runs the linter and the agent cannot skip it. The chapter also compares schedulers, and says local scheduling needs the machine on while cloud scheduling runs with the machine off. [cite:loop-engineering-orange-book/loops-that-run-while-you-sleep@v260615]

## Where to read

- [§03 The Five Moves of One Loop](../books/loop-engineering-orange-book/chapters/03-five-moves-of-one-loop.md)
- [§04 Six Parts: What a Loop Is Built From](../books/loop-engineering-orange-book/chapters/04-six-parts-of-a-loop.md)
- [§06 Loops That Run While You Sleep: Three Real Ones](../books/loop-engineering-orange-book/chapters/06-loops-that-run-while-you-sleep.md)
- `hermes-agent-orange-book`. Run `python3 scripts/resolve.py hermes-agent-orange-book` for its official URL.
- `claude-code-orange-book`. Run `python3 scripts/resolve.py claude-code-orange-book` for its official URL.
- `harness-engineering-orange-book`. Run `python3 scripts/resolve.py harness-engineering-orange-book` for its official URL.
- `claude-code-source-analysis-orange-book`. Run `python3 scripts/resolve.py claude-code-source-analysis-orange-book` for its official URL.
