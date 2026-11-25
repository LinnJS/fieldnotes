---
id: hermes-agent-orange-book/delegate-task-to-kanban
resource: hermes-agent-orange-book
title: From delegate_task to a Kanban Platform
part: "Part 5: Multi-Agent & Orchestration"
order: 15
section_label: "§15"
language: en
edition: v260607
source:
  repository: alchaincyf/hermes-agent-orange-book
  revision: b6e53a8e11e00c8b14b2f72d6b4f1ce71fef6692
  path: Hermes-Agent-The-Complete-Guide-v260607.pdf
  pages:
    first: 69
    last: 72
extraction_status: machine-extracted
---

# From delegate_task to a Kanban Platform

*From delegate_task to a Kanban Platform*

Two months ago, Hermes's multi-agent capability was a single function. Two months later it had become a whole persistent Kanban platform backed by SQLite. The funny part is that the repo holds a manifesto, in black and white, declaring "design only, don't touch the kernel" — and what actually shipped fed that manifesto until it was more than twice its original size.

## The old-book era: one tool was the entire estate

Flip back to the old book from two months ago, and Hermes's multi-agent chapter was honestly pretty thin. It had a single primitive, called `delegate_task` .

The mechanism is easy to grasp: the parent agent forks a short-lived child agent, hands it a task, and then blocks waiting for the return. The child runs in an isolated session, spits back a summary, and then vanishes. Three concurrent at most. You could let different child agents use different models — a strong model for reasoning, a fast model for search — and that was about it.

This is a standard fork-join structure. It's a good fit for short, self-contained reasoning subtasks. But it can't hold up the kinds of work that have become more and more common in the community: an engineering pipeline that runs for hours, a loop that automatically produces a daily report every morning, a persistent assistant you want to name and raise for months. All of these need something that "lives past a single API call," and `delegate_task` can't give you that.

## The design doc that said "DESIGN ONLY"

On April 25, 2026, Nous Research dropped a PDF in the repo called the Hermes Kanban v1 spec. When I first read its title page, I was a little surprised.

On the Abstract of that title page, a few sentences were written with absolute conviction:

> From the design doc (title page): Status: DESIGN ONLY. No implementation accompanies this document. / The kernel requires no changes to `run_agent.py` , no new core tools.

Translated: this is only a design, no implementation comes with it. The kernel needs no changes to a single line of `run_agent.py` , and no new core tools.

The whole spec carries this restraint-to-the-point-of-obsession minimalism. It draws the boundaries of the kernel crisply, as if measured with a ruler:

| Dimension | What the v1 design doc promised |
| --- | --- |
| State machine | Exactly 6 states: todo / ready / running / blocked / done / archived |
| Database tables | The original text says "exactly four tables" — precisely 4 |
| New core tools | Zero. Not one allowed |
| CLI commands | One subcommand |
| Everything else | One skill, one cron job, done |

The dispatcher in the spec was also deliberately designed to be "dumb." It does exactly three things: recompute which tasks are ready, atomically claim a task via CAS, and spawn a worker process. No smart routing, no budgeting, no approvals. All the clever work is pushed up to the profiles and plugins above it.

It's a beautiful design. The problem is, it couldn't keep itself in check.

## The reversal: two months, 104 PRs, manifesto fed fat

By v0.16.0, I went through the code that actually shipped against this spec, line by line. The gap was wide enough to be a little funny.

| 推 | 荐 | 不推 | 荐 |
| --- | --- | --- | --- |
| The design doc said: 6 states · 4 tables · 0 new tools · 1 CLI subcommand |  | The shipped code is: 9 states · 7 tables · a whole kanban\_\* toolset · 30+ CLI subcommands |  |

Every single one was breached. The state machine grew three extras: `triage` (someone casually tossing in a rough idea), `scheduled` (tasks waiting on time, not on people), and `review` (a review gate). The tables went from 4 to 7, and the column count of the core `tasks` table alone exploded from a dozen or so to around thirty.

The biggest slap to the face is that line, "no new core tools." In the actual code, every time the dispatcher spawns a worker, it stuffs the whole set of `kanban_show` , `kanban_complete` , `kanban_block` tools straight into its schema. These are exactly the new core tools.

That milestone happened at v0.15.0, and the official release notes put it bluntly: "Kanban grew into a real multi-agent platform — 104 PRs." A minimalist design manifesto, fed mouthful by mouthful by real-world demand across 104 PRs into a platform.

| 核 | 心 | 建议 |
| --- | --- | --- |

> This gap between "design doc vs. shipped implementation" is itself one of the best specimens for watching how an open-source project evolves. It says one thing: restraint is a posture, but the shape of real users' work keeps pouring stuff into the kernel. A team that can write "exactly four tables" will, two months later, push the tables to 7 anyway — because someone actually wants to use it to manage 50 Instagram accounts. This isn't a design failure; it's design negotiating with reality.

## delegate_task didn't die, it got demoted

Someone might ask: if Kanban is this strong, has `delegate_task` been retired?

No. It's still here. The source repeatedly stresses that a Kanban worker can still call `delegate_task` within its own single run. What changed is its position. It went from "the entirety of multi-agent" down to a "function-call-level" sub-capability, while Kanban became the "queue-level" collaboration substrate. The two coexist, and the division of labor is hard-coded by the project into a single sentence.

This dividing line is worth remembering, and it's clean:

| Dimension | delegate_task | Kanban |
| --- | --- | --- |
| Form | RPC call (fork → join) | Persistent message queue + state machine |
| Parent agent | Blocks until the child returns | Fire-and-forget, done once it's created |
| Child identity | Anonymous child agent, no persistent self | Named profile, its own memory/skill/history |
| Recoverable | No — a failure is a failure | Can unblock and rerun after block; auto-reclaim on crash |
| Can a human step in | No, headless the whole way | comment/block/reassign at any time |
| Agents per task | One per call | N over a task's lifetime (retries/reviews/follow-ups) |
| Audit | Lost the moment the parent context compacts | SQLite rows kept forever |

How to choose? The project gives one criterion that's especially worth memorizing: does this handoff need to live past a single API loop, and be visible to others? If yes, put it on the board; if no, use delegate. One sentence draws the boundary between the two primitives cleanly.

In plain terms: `delegate_task` is a single function call, forgotten the moment it returns; Kanban is a persistent work queue, where every handoff is a row that any profile (or you, the human) can read and edit.

## From "function" to "infrastructure"

String this reversal together and Hermes's multi-agent evolution path over these two months is actually quite clear.

> delegate_taskv1 spec104 PRs

→ → →

> one functionminimalist manifestofed fat

> Kanban persistent Kanban platform

A Kanban platform backed by SQLite, cross-process, able to survive a single point of failure. It has automatic task decomposition, swarm topologies, scheduled tasks, per-task model overrides, circuit-breaker retries, multi-tenancy, and multiple boards. The next few sections will unpack each of these one by one.

But in this section I just want you to first remember the reversal itself. The weakest chapter in the old book has now become the most substantial Part in the whole book. And the reason it's this substantial is precisely because the spec started out thinking too restrained. Restraint gave it a clean kernel, and reality then forced a whole platform to grow on top of that kernel.

In the next section we'll drill into the kernel of this platform and look at that dispatcher designed to be "dumb" — where exactly its dumbness lies, and why that dumbness is precisely what lets it hold up in production.
