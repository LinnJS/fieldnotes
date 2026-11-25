---
id: hermes-agent-orange-book/collaboration-patterns-and-cost-control
resource: hermes-agent-orange-book
title: Eight Collaboration Patterns and Per-Card Cost Control
part: "Part 5: Multi-Agent & Orchestration"
order: 17
section_label: "§17"
language: en
edition: v260607
source:
  repository: alchaincyf/hermes-agent-orange-book
  revision: b6e53a8e11e00c8b14b2f72d6b4f1ce71fef6692
  path: Hermes-Agent-The-Complete-Guide-v260607.pdf
  pages:
    first: 77
    last: 82
extraction_status: machine-extracted
---

# Eight Collaboration Patterns and Per-Card Cost Control

*Eight Collaboration Patterns and Per-Card Cost Control*

In the last section we saw through Kanban's "dumb core." This section gets practical: that same set of tasks + links + comments can be assembled into eight completely different multi-Agent collaboration shapes. What's even more interesting is that every card can pin its own model, so cost control for a multi-Agent setup ultimately comes down to individual cards.

## No new primitives, only new combinations

By now you might have an expectation: to cover eight collaboration patterns, surely there have to be eight underlying mechanisms?

It's the exact opposite. The Hermes design docs call these eight patterns P1 through P8, and every one of them is assembled from the same set of parts: tasks, dependency links between tasks, comments on tasks, who's responsible (the assignee), and which workspace it runs in. There's no voting engine built for "voting," no pipeline engine built for "pipelines."

I think that's the most worthwhile thing to learn from this design. A lot of people who build multi-Agent systems get into the habit of bolting a new feature onto every new scenario, until the system bloats to the point nobody can maintain it. Hermes goes the other way: squeeze the primitives down to the bare minimum first, then cover the scenarios through combination.

Let's lay out all eight patterns so you can scan and find the one you want.

| ID | Pattern | Shape | Typical use |
| --- | --- | --- | --- |
| P1 | Fan-out | Same assignee, N sibling tasks with no dependencies, running concurrently | Batch processing: reviewing 50 files in one go |
| P2 | Pipeline | A chain of specialized roles, linked in sequence | Research → edit → write, each doing its own job |
| P3 | Voting / quorum | N different people on the same task, plus an aggregator | Producing multiple drafts, then picking and merging the best |
| P4 | Long-running journal | Same assignee + same shared directory + recurring task | Daily and weekly reports, accumulating into the same store across days |
| P5 | Human-in-the-loop | Block → ask → human answers → unblock → rerun | Stopping at uncertain points to wait for your call |
| P6 | @mention delegation | @ a profile in a message, auto-create a card and assign it | Tossing a job to some Agent on the fly during a conversation |
| P7 | Thread-scoped workspace | Pin the workspace to the directory of the current conversation | This project's work gets done inside this project |
| P8 | Fleet farming | One expert profile + N parallel tasks + one directory per object | One Agent managing 50 accounts |

Out of the eight, the ones I especially want to single out are P1, P3, and P8, because they're the most likely to expose a beginner's trap.

## P1 Fan-out: concurrency is not "in-process clones"

Fan-out sounds the simplest: slice one big job into N pieces and run them all at once. But hidden in here is a fundamental divergence between Hermes and many similar systems — the same old "in-process clone vs. independent OS process" question from the last section (§16). An in-process clone's life is tied to the main Agent; the moment the main Agent finishes, the clone gets silently killed, and even a half-done job evaporates along with it.

Hermes' P1 doesn't work that way. Every task it fans out is a standalone operating-system process. The scheduler atomically claims all N tasks and spawns N real processes. None of them depends on another; if one crashes it doesn't affect the rest, and the crashed one can even be reclaimed and run again.

> **Key point:** "Concurrency" can grow in two ways. One is in-process clones (fragile, dependent on the lifecycle of the upstream SDK), the other is separate, independent OS processes (recoverable when they crash, auditable when they finish). Hermes picks the latter throughout — this is the "dumb core" philosophy from the last section carried into the collaboration layer.

## P3 Voting: let a few Agents argue it out, then bring one in to judge

P3's shape is elegant: N Agents get the same task description but have different assignees (which can be different models, different profiles), and each independently produces an answer. Then an aggregator task links over from those N tasks, puts the several answers side by side, and picks one or merges them.

This trick is especially handy for the kind of task where "one shot isn't necessarily right." For example, have three Agents each write a version of a plan, then have a fourth act as reviewer. It's far more reliable than a single Agent grinding out one version on its own.

While we're here, let me mention a high-level wrapper built into Hermes, called swarm. As the last section said, there's no second scheduler under `hermes kanban swarm` — it's just "combination sugar" assembled from P1 fan-out plus pipeline plus a shared blackboard. One command pulls up the whole formation: "parallel experts + a gatekeeping validator + a synthesizer to wrap things up." The validator only lets things through when the evidence is sufficient; otherwise it bounces the card back and spells out exactly what's still missing.

## P8 Fleet farming: one Agent managing 50 accounts

P8 is the flagship example in the design docs, and the one that best illustrates "don't build a dedicated tool for this."

Imagine you need to manage 50 social accounts, each running a maintenance pass every few hours. With the traditional mindset, you'd probably go find an RPA tool and configure a pile of flows. Hermes' approach is: one expert profile, N parallel tasks, one independent workspace directory per account, with a scheduled job generating a card for each account at fixed intervals.

One insta-manager profile → cron creates a card per account each round → One independent workspace per account → Failures auto-reclaimed when the claim lock expires

Whichever account dies in a given round, its claim lock expires on schedule and the next round automatically reclaims and reruns it. Each account's history stays in the task event log, fully auditable.

There's a line in the design docs I really like: this is an RPA-shaped workflow, but without an RPA tool — having no dedicated infrastructure is exactly the feature, not a flaw.

## Pinning models per card: cost control at the finest granularity

Now that we've covered collaboration shapes, let's talk money. Once a multi-Agent setup gets going, token consumption is several times that of a single Agent — that's a real pain point.

Two months ago, Hermes could already have "different sub-Agents use different models," but that was decided once and for all by the parent Agent at delegation time. Now it's upgraded to a finer granularity: every single card can independently specify which model it runs on.

On the task table this maps to a `model_override` field. When the scheduler spawns the worker process for this task, if a model is pinned on the card, it adds `-m` on the command line to carry it through.

| 推荐 | 不推荐 |
| --- | --- |
| Writing boilerplate, running formatting, doing simple classification → pin a cheap, fast model, save money and time | Cracking hard problems, doing critical reasoning, writing the core plan → pin an expensive, strong model, spend where it's worth spending |

The official phrasing is "cheap models do the boilerplate, expensive models do the hard sub-tasks." Behind that line is a very concrete bit of accounting: a workflow with a dozen-odd cards might have only two or three that truly need a top-tier model, while the rest run perfectly fine on a cheap one. The economics of multi-Agent ultimately come down to whether you're willing to tune the model card by card.

> **核心建议**
>
> When designing your own Agent team, don't rush to put every card on the strongest model. Go through the tasks once and sort them by "difficulty": hand the boilerplate and retrieval work to cheap models, and save your top-tier budget for the steps that genuinely require reasoning. For a workflow that runs often, that price difference adds up to a lot.

## goal_mode: pulling the Ralph loop into the core

There's another capability I find quite clever, called goal_mode.

Anyone who's played with Agents may have heard of a trick called Ralph: have the Agent run the same goal over and over, checking after each round whether it's there yet, and if not, keep going until it's done. Previously you had to build the loop yourself on the outside.

Hermes turned it into a switch on the card. Turn on goal_mode for a card, and after each round an auxiliary judge compares this round's output against the card's title and body; if it's not complete, it feeds a continuation prompt back into the same session and keeps going. This continues until the judge nods, or the round budget runs out (20 rounds by default).

This is yet another example of the same idea from the last section: Ralph isn't built as a standalone runtime, it's pulled into the card and turned into a field. Turn it on if you want it, ignore it if you don't.

## Scaling out: multiple boards, multiple tenants, multiple gateways

Finally, let's talk scale. When your Agent team grows from "a few cards" to "several business lines," Hermes gives you three layers of isolation, from coarse to fine granularity.

| Level | Isolation strength | How to use it | When to use it |
| --- | --- | --- | --- |
| Multiple Boards | Hard boundary | Each board gets its own database + workspace directory + scheduling view | Businesses fully separated, invisible to each other |
| Multiple Tenants | Soft namespace | A `tenant` tag within a board for soft filtering | One expert team serving multiple businesses |
| Multiple gateways | Process level | Multiple gateways running concurrently, but only one holds the scheduler | Different profiles each running their own thing, spreading the load |

One official line makes the relationship between the first two layers clear: tenant is soft filtering, the board is the hard isolation boundary. The same expert fleet can serve multiple businesses with different tenant tags, keeping data apart through workspace paths and memory prefixes; if you truly need to split things up so nobody can see anyone else, just open two boards.

The multiple-gateway layer has a trap that's easy to fall into: you can run several gateway processes at once, but only one can hold the scheduler — the rest all have to shut off their own scheduling. The reason isn't complicated: multiple processes fighting over the same SQLite connection would amplify read-write contention. This "keep the core dumb, get scalability through combination" trade-off holds consistent all the way down to this layer.

## Back to one question: how should you design your own team

String this section together and it's really a design checklist you can fill in.

First ask about shape: is your job batch parallel (P1), or a pipeline with an order to it (P2), or does it need multi-draft voting (P3), or long-term accumulation across days (P4)? Then ask about the human-machine boundary: which steps should stop and wait for your call (P5)? Then ask about cost: which cards use the cheap model, and which cards are worth going top-tier on? Finally ask about scale: do you need to open multiple boards to split the business apart?

What impresses me most about all this is that it doesn't force you to learn a pile of new concepts. Eight patterns, per-card cost control, scaling out — underneath it's still the dumb core from the last section: tasks, links, comments, assignees, workspaces. Designing a team is essentially just rearranging and recombining these few parts. In the next section we leave the collaboration layer and look at how Hermes throws itself into the operating system's sandbox — because once you've released this many parallel processes, where the boundaries lie becomes an unavoidable question.
