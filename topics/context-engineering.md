---
id: context-engineering
title: Context Engineering
references:
  - resource: loop-engineering-orange-book
    chapter: loop-engineering-orange-book/from-prompt-to-context-to-loop
    note: Defines context engineering as deciding what goes into the model's window, and places it between prompt engineering and harness engineering.
  - resource: loop-engineering-orange-book
    chapter: loop-engineering-orange-book/loops-that-run-while-you-sleep
    note: Describes how Stripe's Minions assemble context with deterministic code before the model starts.
  - resource: claude-code-orange-book
    note: Its README lists a chapter on prompting and context engineering in Claude Code.
  - resource: claude-code-source-analysis-orange-book
    note: Its README lists a chapter on context management for long conversations in Claude Code.
---

# Context Engineering

**Scope (editorial).** Context engineering is the choice of what a model sees at the moment it works: what is retrieved, what is summarized, what is left out, and who or what does the selecting. This topic gathers reading on filling and managing a limited context window.

§02 defines context engineering as the layer that asks what should go into the window so that the model can solve the problem. It names three tasks: which references to retrieve, how to summarize long material, and which stale information to clear out. [cite:loop-engineering-orange-book/from-prompt-to-context-to-loop@v260615]

§02 gives the reason this is a layer of its own. The model's window is limited, and "stuffing in the wrong thing is worse than stuffing in too little." [cite:loop-engineering-orange-book/from-prompt-to-context-to-loop@v260615]

In its account of Stripe's Minions, §06 says a deterministic orchestrator assembles the context before the model starts. It scans links in the message, pulls Jira, finds docs, and searches out the relevant code. The chapter calls letting the model find its own context "the least controllable part." [cite:loop-engineering-orange-book/loops-that-run-while-you-sleep@v260615]

## Where to read

- [§02 From Prompt to Context to Loop](../books/loop-engineering-orange-book/chapters/02-from-prompt-to-context-to-loop.md)
- [§06 Loops That Run While You Sleep: Three Real Ones](../books/loop-engineering-orange-book/chapters/06-loops-that-run-while-you-sleep.md)
- `claude-code-orange-book`. Run `python3 scripts/resolve.py claude-code-orange-book` for its official URL.
- `claude-code-source-analysis-orange-book`. Run `python3 scripts/resolve.py claude-code-source-analysis-orange-book` for its official URL.
