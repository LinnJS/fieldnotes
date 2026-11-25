---
id: agent-security
title: Agent Security
references:
  - resource: hermes-agent-orange-book
    chapter: hermes-agent-orange-book/operating-system-boundary
    note: Argues that the operating system is the only real security boundary for an agent, treats in-process checks such as the approval gate and output redaction as heuristics, and describes sandbox backends and credential stripping.
  - resource: hermes-agent-orange-book
    chapter: hermes-agent-orange-book/promptware-defense-and-observability
    note: Describes how Hermes Agent scans memory recall, tool results, and skill installation for injected instructions, and how it records agent behavior for later audit.
  - resource: deepseek-harness-orange-book
    note: Its README lists a section on what DeepSeek Harness is allowed to touch, and names permission approval before writes among its first-hand tests. The book is in Chinese.
  - resource: openclaw-orange-book
    note: Its README lists a part on the security model of OpenClaw and its known incidents.
  - resource: claude-code-source-analysis-orange-book
    note: Its README lists a chapter on the permission system of Claude Code.
---

# Agent Security

**Scope (editorial).** Agent security is about limiting what an agent is able to do and protecting it from misuse: permission rules, sandboxes and operating system boundaries, and defenses against instructions hidden in the material an agent reads. This topic gathers reading on security models and known incidents.

## Where to read

- [§19 The Only Boundary Is the Operating System](../books/hermes-agent-orange-book/chapters/19-operating-system-boundary.md)
- [§20 Promptware Defense and Observability](../books/hermes-agent-orange-book/chapters/20-promptware-defense-and-observability.md)
- `deepseek-harness-orange-book`. Run `python3 scripts/resolve.py deepseek-harness-orange-book` for its official URL.
- `openclaw-orange-book`. Run `python3 scripts/resolve.py openclaw-orange-book` for its official URL.
- `claude-code-source-analysis-orange-book`. Run `python3 scripts/resolve.py claude-code-source-analysis-orange-book` for its official URL.
