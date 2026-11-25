---
id: memory-and-state-management
title: Memory and State Management
references:
  - resource: loop-engineering-orange-book
    chapter: loop-engineering-orange-book/five-moves-of-one-loop
    note: Presents persistence as one of five moves, where results and a state file are written outside the conversation.
  - resource: loop-engineering-orange-book
    chapter: loop-engineering-orange-book/six-parts-of-a-loop
    note: Describes memory as state on disk that outlives the context window, and separates memory from context.
  - resource: loop-engineering-orange-book
    chapter: loop-engineering-orange-book/build-your-first-loop
    note: Shows how to give a first loop a state file so that unfinished work carries over to the next run.
  - resource: hermes-agent-orange-book
    chapter: hermes-agent-orange-book/three-layers-of-memory
    note: Describes three layers of agent memory, and how persistent memory is written to disk at once but shown to the model as a snapshot frozen for the session and scanned for injected content.
  - resource: hermes-agent-orange-book
    chapter: hermes-agent-orange-book/session-search
    note: Describes session search that returns stored messages from a full-text index instead of LLM summaries, and how it handles Chinese text.
  - resource: harness-engineering-orange-book
    note: Its README names memory systems among the things a harness designer builds, and lists a hands-on section on capability and memory.
  - resource: obsidian-ai-orange-book
    note: Its README describes an AI-maintained personal knowledge base of Markdown files, and says several AI tools store their memory as Markdown.
  - resource: openclaw-orange-book
    note: Its README lists the memory system, workspace, and sessions of OpenClaw in its architecture part.
  - resource: claude-code-source-analysis-orange-book
    note: Its README lists a chapter on the memory system of Claude Code.
---

# Memory and State Management

**Scope (editorial).** Memory and state management cover what an agent keeps between turns, sessions, and days, and where it keeps it. This topic gathers reading on state files, memory systems, and the difference between what sits in the context window and what is stored outside it.

§03 defines persistence as landing a result somewhere that survives the conversation. Its example opens a pull request, puts findings the loop cannot handle in an inbox for a person, and keeps a state file that records where the loop is up to. [cite:loop-engineering-orange-book/five-moves-of-one-loop@v260615]

§04 quotes this line on where memory belongs: "The agent forgets, the repo doesn't. The memory has to be on disk and not in the context." [cite:loop-engineering-orange-book/six-parts-of-a-loop@v260615]

§04 separates memory from context. Context is what the agent can see in the current round, and it is flushed when the window refreshes. Memory is what is written to disk, and it is still there across rounds and days. [cite:loop-engineering-orange-book/six-parts-of-a-loop@v260615]

§09 makes a state file the third step of a first loop: a Markdown file that holds every finding and how far each has been handled. It says a Linear board or an issue list works as well, because state has to live outside any single conversation. [cite:loop-engineering-orange-book/build-your-first-loop@v260615]

## Where to read

- [§03 The Five Moves of One Loop](../books/loop-engineering-orange-book/chapters/03-five-moves-of-one-loop.md)
- [§04 Six Parts: What a Loop Is Built From](../books/loop-engineering-orange-book/chapters/04-six-parts-of-a-loop.md)
- [§09 Build Your First Loop Today](../books/loop-engineering-orange-book/chapters/09-build-your-first-loop.md)
- [§07 Three Layers of Memory: From Goldfish to Old Friend](../books/hermes-agent-orange-book/chapters/07-three-layers-of-memory.md)
- [§08 Session Search: Taking Back the Work LLMs Should Not Do](../books/hermes-agent-orange-book/chapters/08-session-search.md)
- `harness-engineering-orange-book`. Run `python3 scripts/resolve.py harness-engineering-orange-book` for its official URL.
- `obsidian-ai-orange-book`. Run `python3 scripts/resolve.py obsidian-ai-orange-book` for its official URL.
- `openclaw-orange-book`. Run `python3 scripts/resolve.py openclaw-orange-book` for its official URL.
- `claude-code-source-analysis-orange-book`. Run `python3 scripts/resolve.py claude-code-source-analysis-orange-book` for its official URL.
