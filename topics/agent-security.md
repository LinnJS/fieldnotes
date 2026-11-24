---
id: agent-security
title: Agent Security
references:
  - resource: hermes-agent-orange-book
    note: Its README lists a part on deployment, security, and boundaries for Hermes Agent, including the operating system boundary and what it calls Promptware defense.
  - resource: deepseek-harness-orange-book
    note: Its README lists a section on what DeepSeek Harness is allowed to touch, and names permission approval before writes among its first-hand tests. The book is in Chinese.
  - resource: openclaw-orange-book
    note: Its README lists a part on the security model of OpenClaw and its known incidents.
  - resource: claude-code-source-analysis-orange-book
    note: Its README lists a chapter on the permission system of Claude Code.
---

# Agent Security

**Scope (editorial).** Agent security is about limiting what an agent is able to do and protecting it from misuse: permission rules, sandboxes and operating system boundaries, and defenses against instructions hidden in the material an agent reads. This topic gathers reading on security models and known incidents.

No mirrored chapter covers this topic yet, and the books listed below are read at their official sources.

## Where to read

- `hermes-agent-orange-book`. Run `python3 scripts/resolve.py hermes-agent-orange-book` for its official URL.
- `deepseek-harness-orange-book`. Run `python3 scripts/resolve.py deepseek-harness-orange-book` for its official URL.
- `openclaw-orange-book`. Run `python3 scripts/resolve.py openclaw-orange-book` for its official URL.
- `claude-code-source-analysis-orange-book`. Run `python3 scripts/resolve.py claude-code-source-analysis-orange-book` for its official URL.
