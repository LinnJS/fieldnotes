---
id: loop-engineering-orange-book/six-parts-of-a-loop
resource: loop-engineering-orange-book
title: "Six Parts: What a Loop Is Built From"
part: "Part 2 · How It Turns"
order: 4
section_label: "§04"
language: en
edition: v260615
source:
  repository: alchaincyf/loop-engineering-orange-book
  revision: "829aa6084cd68680e7f389bbde9dcaebda7a43e6"
  path: Loop-Engineering-The-Complete-Guide-v260615.pdf
  pages:
    first: 13
    last: 16
extraction_status: machine-extracted
---

# Six Parts: What a Loop Is Built From

*Six Parts: What It Takes to Build a Loop*

The last chapter took apart the moves; this one takes apart the parts. Addy groups what it takes to build a loop into six things. Miss any one and the loop limps somewhere.

Moves describe "what happens in one turn"; parts describe "what you need to have in hand for it to turn at all."

The two line up. Discovery runs on skills, handoff on worktrees, verification on sub-agents, persistence on memory, scheduling on automations. This chapter lays out the six parts one by one, each making three things clear: what it is, why you need it, and what Addy says about it.

## Part one: Automations (automation / scheduling)

An automation is the thing that gets the loop moving on its own. It hangs off a schedule or a trigger, and when the time comes it discovers and triages automatically, no human standing by to press a button.

Why does it come first? Because it's the root of the word "loop." Without scheduling, the set of things in your hand is just one run, not a loop. Addy's triage running automatically in the morning in the last chapter (as described in §03) is exactly automation at work.

> **Original:** Automations are what make a loop an actual loop and not just one run you did once.
>
> Automation is what makes a loop a real loop, not just the one time you ran it.

Note one detail. What the automation triggers should be a skill, not a whole wall of instructions. Paste a big block of prompt into a cron job and nobody will ever update it again; trigger a named skill, and when the logic changes you just change the skill.

Scheduling comes in more than one form. Some runs on your own machine, which has to stay on; some runs in the cloud, turning even when your machine is off. The two differ quite a bit, and a later chapter is dedicated to how to choose your scheduling. For now, just remember: automation is the loop's engine, and if the engine doesn't fire, the other five parts are just decoration.

## Part two: Worktrees (git worktree isolation)

A worktree is a built-in git mechanism that lets you open multiple mutually independent working directories in the same repo. Each agent changes code in its own worktree without interfering with the others.

Why do you need it? Because once a loop runs multiple agents at once, file write conflicts are only a matter of time. Two agents fighting to change the same file — that's a headache you've probably had a taste of.

> **Original:** Two agents writing the same file is the exact same headache as two engineers committing to the same lines.
>
> Two agents writing the same file at once is the exact same headache as two engineers committing to the same lines.

Worktrees separate parallel agents and avoid the conflict before it happens, instead of merging a pile of clashing changes after the fact. In the last chapter's handoff step, each finding opening its own worktree is this part doing its job.

The value of this part scales up with parallelism. A loop running only one agent at a time can take or leave worktrees. But once you want it to fix five bugs in parallel in the morning, with five agents each making their own changes, no isolation means five sets of changes tangled together, and in the end nobody knows which line is whose. Worktrees turn parallelism from "runs but messy" into "runs and clean."

## Part three: Skills (reusing knowledge via SKILL.md)

A skill makes project knowledge permanent in a single file (SKILL.md), so the agent can reach for it every time instead of re-deriving the context on every turn.

Why do you need it? Because without making it permanent, every run you have to tell the agent all over again "what this project is, what the rules are, where the traps are." This cost of explaining over and over has a name from Addy: intent debt.

A skill is paying off that debt. Write down what you've thought through once, and every turn afterward skips re-deriving it. Why the discovery step is a triage skill rather than a bare prompt comes down to this too — a skill can be reused and maintained, a wall of prompt can't.

## Part four: Plugins & Connectors (MCP connectors)

A connector is the interface that hooks the loop to the outside world. The issue tracker, the database, the staging environment's API, Slack — they all come in through it. The technical foundation is MCP (Model Context Protocol).

Why do you need it? Because a loop that can only see the filesystem can do too little. It has to be able to read tickets, query databases, open PRs, and send notifications before it's really running work for you.

> **Original:** A loop that can only see the filesystem is a tiny loop.
>
> A loop that can only see the filesystem is a very small loop.

MCP has another upside: cross-tool compatibility. A connector you wrote on the Codex side can often be dropped straight onto the Claude Code side and used as is. In the persistence step, the connector automatically opening PRs and updating tickets is this part doing the cleanup.

Looked at another way, connectors decide the loop's "radius of vision." Hook up only the filesystem and all it sees is a few directories. Hook up the issue tracker and it knows what work is still undone; hook up the database and it can query real data; hook up Slack and it can tell you the results. Every external system you add stretches the chain the loop can complete on its own.

## Part five: Sub-agents (separating the generator and the judge)

The key use of sub-agents is splitting "the one that writes" and "the one that judges" into two. One agent generates; another, with different instructions and sometimes a different model, picks holes.

Why insist on splitting them? Because when one agent is both player and referee, the referee plays favorites.

> **Original:** The model that wrote the code is way too nice grading its own homework. A second agent with different instructions and sometimes a different model catches the stuff the first one talked itself into.
>
> The model that wrote the code is too polite grading its own homework. Swap in an agent with different instructions and sometimes a different model, and it catches what the first one talked itself into.

Verification is trustworthy precisely because the judge and the generator aren't the same one. That "thing that can say no" from the last chapter, mapped to a part, is this second sub-agent.

There's a counterintuitive point worth noting. You might think that to make an agent critique its own work, you have to pour effort into training the generator. But in practice it's the opposite: tuning an independent judge to be picky enough is far easier than getting the generator to be hard on its own work. That's also why a loop would rather keep an extra agent around than let one agent review and audit itself.

## Part six: Memory (persistent state)

The sixth part, Addy calls it Memory, not Persistent State. It's the loop's memory that lives outside a single conversation — a markdown file, or a Linear board.

Why do you need it? Because the moment an agent's context window is cleared, it remembers nothing. For a loop to pick up today where it left off yesterday, the memory can't sit only in the context; it has to land on disk.

> **Original:** The agent forgets, the repo doesn't. The memory has to be on disk and not in the context.
>
> The agent forgets, the repo doesn't. The memory has to be on disk, not in the context.

The state file written into markdown or a board in the persistence step is this part. It gives the loop continuity. Without it, every turn opens its eyes anew after amnesia.

There's a subtle but important distinction here. Memory isn't context. Context is what the agent can see this round, and it gets flushed when the window refreshes. Memory is what's written to disk, still there across rounds, across days, across the whole conversation's lifetime. A loop that wants to run long-term doesn't rely on stretching the context bigger; it relies on settling what should be remembered onto disk, then reading it back when needed.

## Six-part quick reference

Six parts, mapped to five moves, all in one table.

| Part | What it is | Maps to move | One-line quote |
| --- | --- | --- | --- |
| Automations | Runs automatically off a schedule/trigger | Scheduling | make a loop an actual loop |
| Worktrees | Isolated working dirs for parallel agents | Handoff | same headache as two engineers |
| Skills | Make project knowledge permanent, pay off intent debt | Discovery | fire $skill-name, not a wall of instructions |
| Connectors | MCP hookup to external systems | Persistence / Discovery | only see the filesystem is a tiny loop |
| Sub-agents | Generator separated from judge | Verification | too nice grading its own homework |
| Memory | Persistent state on disk | Persistence | the agent forgets, the repo doesn't |

With all six parts in place, a loop that can turn itself has a skeleton. Automation makes it move, worktrees keep it from fighting itself, skills keep it from redoing work, connectors let it see outside, sub-agents let it correct itself, memory lets it remember.

But building it is only the start. Whether a loop that can turn turns well or badly is another matter. The same set of parts, built by two people, can come out completely opposite. That's the cost and the anti-patterns we'll get into next.
