---
id: hermes-agent-orange-book/dumb-core-userspace-decoration
resource: hermes-agent-orange-book
title: "Dumb Core, Userspace Decoration"
part: "Part 5: Multi-Agent & Orchestration"
order: 16
section_label: "§16"
language: en
edition: v260607
source:
  repository: alchaincyf/hermes-agent-orange-book
  revision: b6e53a8e11e00c8b14b2f72d6b4f1ce71fef6692
  path: Hermes-Agent-The-Complete-Guide-v260607.pdf
  pages:
    first: 73
    last: 76
extraction_status: machine-extracted
---

# Dumb Core, Userspace Decoration

*Dumb Core, Userspace Decoration*

A multi-agent platform that looks complicated, yet its core only does three dumb things. Hermes pushes everything clever out to the edges and keeps for itself a scheduler so plain it's almost stubborn. That Unix sense of taste is exactly what most sharply separates it from those "in-process agent swarms."

## Start with what the scheduler actually does

The heart of the Kanban board system is a process called the dispatcher. The name sounds imposing, but it's really just a cron job: it wakes up every so often, scans the board, and gets to work.

You can count the things it's able to do on one hand. Three, total.

> Recompute who's ready Atomically claim a task Spawn a worker process

→ →

Recompute ready means checking which tasks have all their upstream dependencies done and can start. Atomic claim means grabbing the lock on a task with a single line of SQL, `WHERE status='ready' AND claim_lock IS NULL` , relying on the database's row-level contention to guarantee that at most one claimant wins the same task. Spawn worker means launching an OS process to execute it.

That's the three. Nothing more.

All those fancy tricks you'd expect from multi-agent collaboration, smart routing, budget allocation, approval governance, who-goes-first, the dispatcher handles none of them. It doesn't know which task matters more, doesn't know whether to hand work to the cheapest model or the most expensive, doesn't fret about what happens if two workers butt heads. All of that judgment gets pushed somewhere it has no reach: into the profile's system prompt, into the plugins the user installs, into the config the card carries with itself.

> That's the whole meaning of "dumb core": the core only guarantees that the mechanism is correct (a task won't be claimed by two processes at once, a dead worker gets reclaimed), while policy, who to dispatch, how much to spend, whether a human needs to approve, is all handed off to userspace. Separating mechanism from policy is a rule Unix has lived by for fifty years.

## Why keep the core dumb on purpose

Pushing the smarts outward sounds like laziness, but it's actually restraint.

I've seen too many systems die from "the core got too smart." Once you let the scheduler start understanding the business, understanding which task should go first, understanding how to split a budget, understanding when to call in a human, it becomes impossible to change. Every new scenario means going back to touch the most central, most untouchable part. Hermes does the opposite: the core is so dumb it has no business knowledge, so it almost never needs changing; want to add a new trick, go add it in userspace, and the core doesn't budge.

Interestingly, Nous set this philosophy against a contemporary system for contrast. In April 2026, Google's Gemini Enterprise split the agent stack into two planes: a "governance control plane" for approvals and compliance, and a "speed execution plane" for getting work done. Hermes deliberately lives only on the execution plane, never touching governance inside the core at all, whoever wants it installs it themselves via a plugin. One chose the full governance suite big companies want, the other chose the simplicity developers want. Different trade-offs, but each is internally consistent.

## swarm: a "combinator sugar" with no new runtime

Hermes has a one-shot command for spinning up multiple agents, `hermes kanban swarm` . You give it a goal, pick a few roles, and it lays out a collaboration web: several expert workers running in parallel, a verifier as gatekeeper, a synthesizer to wrap up.

First-timers assume there must be a dedicated swarm engine hiding behind this. There isn't.

The swarm module opens by stating it outright: deliberately no second scheduler. All it does is write a fixed-shape task graph into the existing Kanban core.

> Planning root task (done the moment it's built) Parallel expert workers

→ →

> Verifier gate Synthesizer wrap-up

→

Every line and every state in that graph is a primitive the board already had: fan-out parallelism, pipeline serialization, dependency links between tasks. Even the "blackboard" where workers share information is no new storage, it's just a structured JSON comment on the root task, later writes overwrite earlier ones, with a note of who wrote it. The dashboard, the notifications, the command line, not one component needs new code for swarm, because it never built anything new.

So what is swarm, fundamentally? It's a combinator sugar stirred together from a few old ingredients: fan-out plus pipeline plus blackboard. Syntactically you get a complex topology from a single command, yet there's no new runtime running underneath. It's a lovely example of "adding a high-level capability without touching the core": want more capability, go assemble it in userspace, don't stuff an engine into the core.

## NanoClaw: a cautionary tale worth remembering

At this point we need to bring out a counterexample, to see clearly why Hermes is so dogged about this.

There's a project called NanoClaw that bills itself as the first personal assistant to support "in-process subagents." Its multi-agent setup works like this: the team-lead lives in its own process and, through a query interface in the upstream SDK, hatches a bunch of subagents to help with the work. Sounds elegant, all the agents in one process, no inter-process communication hassle.

The problem is lifecycle. The lives of these subagents are held in the hands of that query interface. When that round of the team-lead's call ends, the subagents get killed silently. Even if one is halfway done, with files not yet flushed to disk. Nous's design doc records this pitfall, with one brutal line: looks like it succeeded, actually produced zero files.

Hermes carved this lesson into a heading in its design doc, "Key invariant: no in-process subagent swarms." The gist of its own words:

> Every coordinating worker is an OS process under the user's control, not a subagent inside some SDK query's lifecycle. When a worker exits, cleanly or by crash or by force-kill, its claim lock expires, and on the next dispatcher scan the task gets reclaimed. Not a single lifecycle that we don't own.

That line, "not a single lifecycle that we don't own," is the keystone of the whole philosophy. Hermes would rather bear the clunky costs of inter-process communication, heartbeat checks, and crash recovery than hand a worker's life to an upstream SDK it can't control.

| 推 | 荐 | 不推 | 荐 |
| --- | --- | --- | --- |
| Hermes: each worker is an independent OS process. A worker dies (crash / killed / clean exit), the claim lock expires automatically, and the task is reassigned. Lifecycle fully in your own hands; the worst case is rerunning once, never silently losing results. |  | NanoClaw-style in-process swarm: a subagent's life hangs on the upstream SDK's query lifecycle. The moment that round of the team-lead ends, the subagent is killed silently, half-finished work just evaporates, "looks like it succeeded, produced zero." |  |

The OpenClaw family of designs that emphasize in-process agent swarms share the same fragility. It's not that in-process is necessarily wrong. What I'm getting at is this: when your agent's life and death depend on a lifecycle you don't own, you've buried a time bomb. Hermes chose the path that looks clunkier but is actually more honest: the boundary is the OS process, and that's all.

## So is delegate_task still useful

If the board is this powerful, should we toss the old delegate_task? It wasn't tossed. The previous section (§15) already laid out the division of labor between the two, point by point, and the criterion is one line: does this handoff need to outlive a single API loop and be visible to others? If yes, use the board; if no, use delegate_task.

Here I'll just add one point the last section didn't spell out: the two can be nested. A worker on the board can, within a single run of its own, still call delegate_task to do some internal reasoning. A function call nested inside a persistent queue, each doing its own job, and this is precisely another expression of "dumb core": Kanban didn't swallow delegate_task, it just wrapped a persistent shell around it.

## What this taste is worth

Looking back, Hermes's "dumb core, userspace decoration" saves more than just lines of code.

What it saves is the cost of future change. A dumb core means a stable core, which means adding swarm, adding new collaboration modes, adding new cost-control policies, none of it requires going back to touch the most central part. The clever stuff lives in userspace; when it breaks, goes stale, or you want to swap it, swap it anytime, and the core never notices.

One layer deeper, what it saves is the risk of losing control over lifecycle. Insisting that "every worker is an OS process I own" looks clunky, but it buys you a worst case that's just rerunning once, instead of NanoClaw's silent wipe to zero. A core that pushes complexity outward and guards its boundaries tightly tends to outlive a clever core that wants to think of everything for you.

In the next section we'll actually put this foundation to use, seeing how eight collaboration patterns grow out of these few dumb primitives, and how to tally the multi-agent cost card by card.
