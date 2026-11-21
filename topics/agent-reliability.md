---
id: agent-reliability
title: Agent Reliability
references:
  - resource: loop-engineering-orange-book
    chapter: loop-engineering-orange-book/loops-that-run-while-you-sleep
    note: Reports how Stripe's Minions rely on deterministic context assembly, hard-coded gates, and disposable sandboxes for reliability.
  - resource: loop-engineering-orange-book
    chapter: loop-engineering-orange-book/costs
    note: Names four costs of unattended loops and a guard for each, including budget and retry caps.
  - resource: harness-engineering-orange-book
    note: Its README presents harness engineering as the design work that makes AI agents reliable.
---

# Agent Reliability

**Scope (editorial).** Agent reliability is about whether an agent's work can be depended on when no one watches each step: where errors come from, how they are caught, and what limits keep a failure small. This topic gathers reading on constraints, gates, and the costs of unattended runs.

§06 states the core claim of Stripe's Minions in one sentence: "AI's reliability comes from the quality of the constraints, not the size of the model." [cite:loop-engineering-orange-book/loops-that-run-while-you-sleep@v260615]

§06 describes those constraints. Deterministic code assembles the context before the model starts, hard-coded steps run the linter and the commit so that the agent cannot skip them, and each agent works in a sandbox that is used and discarded. [cite:loop-engineering-orange-book/loops-that-run-while-you-sleep@v260615]

§06 draws a rule from the case: "Anything deterministic logic can solve never goes to a probabilistic model." [cite:loop-engineering-orange-book/loops-that-run-while-you-sleep@v260615]

§07 quotes this warning: "A loop running unattended is also a loop making mistakes unattended." It names four costs that raise no alarm while the loop runs, which are verification debt, comprehension rot, cognitive surrender, and token blowout. [cite:loop-engineering-orange-book/costs@v260615]

Against runaway spending §07 recommends hard caps set before shipping: a budget per run, a daily budget, and a maximum number of retries, so that the loop stops when it reaches the ceiling. [cite:loop-engineering-orange-book/costs@v260615]

## Where to read

- [§06 Loops That Run While You Sleep: Three Real Ones](../books/loop-engineering-orange-book/chapters/06-loops-that-run-while-you-sleep.md)
- [§07 The Costs: Verification Debt, Comprehension Rot, Token Blowout](../books/loop-engineering-orange-book/chapters/07-costs.md)
- `harness-engineering-orange-book`. Run `python3 scripts/resolve.py harness-engineering-orange-book` for its official URL.
