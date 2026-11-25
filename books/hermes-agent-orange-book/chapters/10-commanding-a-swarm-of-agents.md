---
id: hermes-agent-orange-book/commanding-a-swarm-of-agents
resource: hermes-agent-orange-book
title: One Agent Commanding a Swarm of Agents
part: "Part 3: How It Remembers You"
order: 10
section_label: "§10"
language: en
edition: v260607
source:
  repository: alchaincyf/hermes-agent-orange-book
  revision: b6e53a8e11e00c8b14b2f72d6b4f1ce71fef6692
  path: Hermes-Agent-The-Complete-Guide-v260607.pdf
  pages:
    first: 45
    last: 48
extraction_status: machine-extracted
---

# One Agent Commanding a Swarm of Agents

*One Agent Commanding a Swarm of Agents*

In the previous sections, a skill was always a knowledge document, telling the agent "here's how this should be done." In this section it becomes something else: a conductor's baton. Hermes wraps Claude Code, Codex, OpenHands, OpenCode, and Grok all into callable skills, then steps back and takes the role of commander-in-chief.

## A picture: it doesn't write the code, it hands out the work

Imagine you ask Hermes to build a feature. It can of course roll up its sleeves and do it itself — fire up the terminal, write files, run tests. But in v0.16.0 it has one more option: outsource the job.

Under the directory `skills/autonomous-ai-agents/`, the source ships four built-in skills. They don't teach Hermes "how to write Python" — they teach it how to call another coding agent to write it for you. Claude Code is one, Codex is one, OpenCode is one, and Hermes itself has one too (used to contribute code back to its own body).

| Skill | Version | Who it commands to do the work |
| --- | --- | --- |
| `claude-code` | 2.2.0 | Delegates coding to the Claude Code CLI (build a feature / open a PR) |
| `codex` | 1.0.0 | Delegates coding to the OpenAI Codex CLI |
| `opencode` | 1.2.0 | Delegates coding to the OpenCode CLI (can hook up multiple providers) |
| `hermes-agent` | 2.1.0 | Configure, extend, and contribute code to Hermes itself |

The optional directory holds even more: OpenHands, Grok's Build CLI, antigravity-cli. Once they're installed, Hermes has a whole lineup of coding agents it can dispatch.

You → Hermes (commander) → Pick a skill → Claude Code / Codex / OpenHands… → Code / PR comes back

This structure is a bit counterintuitive. We've always thought of Claude Code and Codex as "the terminal" — the agent you talk to directly. But in Hermes's eyes, they're "subordinates." Whoever sits at the front and takes in your request is the commander; the other agents are just wrenches in its toolbox.

Why do it this way? Because different agents each have their own temperament. Claude-native work goes to claude-code, OpenAI-native work goes to codex, and when you need to swap models you reach for something else. Hermes doesn't have to learn the strengths of every vendor's model — it just needs to know "who to hand this job to." A commander's skill is dispatching, not doing it by hand.

## Dissecting a template: what the OpenHands skill looks like

Of all these orchestration skills, the OpenHands one is the most carefully written, and I want to pull it out as a specimen. If you want to know "what a good skill actually looks like," copy this one and you won't go wrong.

First, what it does: OpenHands is model-agnostic — behind it you can plug in any provider LiteLLM supports, OpenAI, Anthropic, OpenRouter, DeepSeek, Ollama, vLLM, all of them. So this skill's positioning is crystal clear: if you want Claude native, take claude-code; if you want OpenAI native, take codex; only when you want to mix and match models does OpenHands's turn come up. The skill makes that decision for you right at the top. That's the first detail — a good skill tells you "when not to use it."

Read on, and the level of engineering is where it gets genuinely scary. Let me list out a few of its key design choices.

| Design | What it does | Why it's a template |
| --- | --- | --- |
| Real flag table | Provides a table of available parameters, annotated "verified against `openhands --help`, CLI 1.16.0" | Not written from memory and guesswork — checked line by line against the help docs |
| Negative list | Spells out which flags don't exist (no `--model` / `--max-iterations` / `--workspace` / `--sandbox`) | Proactively tells the caller "don't try these, trying is just an error" — saves a whole round of trial and error |
| A full Pitfalls section | LiteLLM's noisy warnings, banner spam, the model slug being LiteLLM's rather than the provider's, `pip install openhands-ai` installing the wrong package (that's legacy V0) | Writes down every pit it has stepped in, so those who come after step right around them |
| Platform gating | `[linux, macos]` gating, since OpenHands upstream needs WSL on Windows | On incompatible systems the skill simply goes invisible and doesn't pollute the index |

The invocation is restrained too: through the `terminal` tool it fires one headless line, `openhands --headless --json --override-with-envs --exit-without-confirmation`. No fancy wrapping — just get the command line right and mark the pits clearly.

> **The test of a good skill:** it's not about how much "what to do" it writes, but how much "what not to do" it writes. The negative list, the Pitfalls, the "when not to use me" — those three are what turn a document from "looks correct" into "actually runs correctly." A skill that only lists the right steps is a manual that's never been battle-tested.

There's also a key shift hidden here in this section. A skill is no longer just "knowledge written for an agent to read" — it can also be a wrapper around an external CLI. The OpenHands skill is essentially a thin layer of glue: it translates the agent's intent into a command line that another agent can understand. The boundary of what a skill is has been quietly pushed wider.

## A skill that evolves: darwinian-evolver

Orchestrating other agents is one way to play; letting a skill optimize things for you is another. In the optional research directory there's a `darwinian-evolver`, a thin wrapper around Imbue's open-source darwinian_evolver, an LLM-driven evolutionary search loop.

You use it like this: you give it a fitness function (a scorer), and it optimizes some artifact in an evolutionary way — could be a prompt, a regex, a line of SQL, a small chunk of code. It generates a batch of variants, scores them, keeps the high scorers, mutates again, and climbs the hill round after round.

Be clear that this is not the same thing as Hermes's built-in self-improvement. The built-in self-improvement changes the skill library itself; darwinian-evolver changes any "thing with a scorer" you happen to have. One faces inward, one faces outward. Come to think of it, this hill-climbing plus independent judging plus evolutionary-tree approach is the same lineage as the darwin skill I built myself: given an objective score, let the machine climb generation by generation on its own — steadier than tuning it by hand.

One detail I quite admire: it handles the upstream with clean license isolation. Imbue's library is AGPL-3.0, and the skill only calls its command line through subprocess, deliberately not importing the upstream's classes, so it's just "calling" rather than "merging" — drawing the boundary of a viral license crisp and clear. If you want an example of how a skill should deal with a license-unfriendly external dependency, this is it.

## Bridging forward

Let's step back and look at this section. Earlier we covered how skills get built, improved, and freeloaded off open standards. By here, the skill has shown its second face: it's not just knowledge, it's also the interface through which agents dispatch one another.

Once a skill can be a wrapper for "calling another agent," an interesting question floats up — if Hermes can command Claude Code, can it command a whole swarm of agents at once, splitting up the work and running in parallel? Once the baton is in hand, the natural next step is forming up the squad.

That's exactly what Part 5 ahead will unfold: from `delegate_task` spawning a sub-agent with an isolated context, to a swarm of agents queuing up to claim tasks off a Kanban board. Skills make "dispatching" callable; multi-agent orchestration makes it scalable. This section is the prelude to that chapter.
