---
id: harness-engineering
title: Harness Engineering
references:
  - resource: loop-engineering-orange-book
    chapter: loop-engineering-orange-book/from-prompt-to-context-to-loop
    note: Defines the harness as the layer that equips a single agent run, and separates it from the loop layer above it.
  - resource: hermes-agent-orange-book
    chapter: hermes-agent-orange-book/three-engines-of-self-improvement
    note: Describes the three background mechanisms through which Hermes Agent grows its own harness, which are a post-turn review that writes skills and memory, a curator that maintains the skill library, and a goal loop that keeps a session running until a judge finds the goal met.
  - resource: hermes-agent-orange-book
    chapter: hermes-agent-orange-book/curator-brakes-for-self-evolution
    note: Describes the curator that consolidates and archives the skills an agent wrote for itself, and its safeguards of archiving instead of deleting, a snapshot before each run, a dry run, and a limit to agent-created skills.
  - resource: deepseek-harness-orange-book
    note: Its README describes a first-hand run of DeepSeek's open-source agent harness that records its system prompt and default boot manifest. The book is in Chinese.
  - resource: harness-engineering-orange-book
    note: Its README calls it a practical guide to harness engineering, which it describes as designing constraints, instructions, feedback loops, memory systems, and orchestration layers for agents.
  - resource: claude-code-source-analysis-orange-book
    note: Its README lists a chapter on the harness skeleton of Claude Code and a closing chapter titled The Harness Engineering Playbook.
---

# Harness Engineering

**Scope (editorial).** Harness engineering is the design of everything that surrounds a model during one agent run: the instructions it starts with, the tools and actions it is allowed, the feedback it receives, and the condition under which it stops. This topic gathers reading on what a harness contains and how one is built.

§02 places harness engineering third in a stack of four layers. It says this layer covers what an agent needs when it runs once: which tools it is given, which actions it may take, when context is loaded, how it recovers from failure, and what state counts as done. [cite:loop-engineering-orange-book/from-prompt-to-context-to-loop@v260615]

§02 draws the line between the harness and the loop above it. In its words, the harness "arms a single run of the agent, but it doesn't make that run repeat itself." [cite:loop-engineering-orange-book/from-prompt-to-context-to-loop@v260615]

§02 says its author treated the harness layer at book length elsewhere and does not repeat that material. [cite:loop-engineering-orange-book/from-prompt-to-context-to-loop@v260615]

## Where to read

- [§02 From Prompt to Context to Loop](../books/loop-engineering-orange-book/chapters/02-from-prompt-to-context-to-loop.md)
- [§04 Build, Repair, Continue: Three Engines of Self-Improvement](../books/hermes-agent-orange-book/chapters/04-three-engines-of-self-improvement.md)
- [§05 Curator: Brakes for Self-Evolution](../books/hermes-agent-orange-book/chapters/05-curator-brakes-for-self-evolution.md)
- `deepseek-harness-orange-book`. Run `python3 scripts/resolve.py deepseek-harness-orange-book` for its official URL.
- `harness-engineering-orange-book`. Run `python3 scripts/resolve.py harness-engineering-orange-book` for its official URL.
- `claude-code-source-analysis-orange-book`. Run `python3 scripts/resolve.py claude-code-source-analysis-orange-book` for its official URL.
