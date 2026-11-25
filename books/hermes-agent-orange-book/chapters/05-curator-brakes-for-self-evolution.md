---
id: hermes-agent-orange-book/curator-brakes-for-self-evolution
resource: hermes-agent-orange-book
title: "Curator: Brakes for Self-Evolution"
part: "Part 2: The Reins Grow Themselves"
order: 5
section_label: "§05"
language: en
edition: v260607
source:
  repository: alchaincyf/hermes-agent-orange-book
  revision: b6e53a8e11e00c8b14b2f72d6b4f1ce71fef6692
  path: Hermes-Agent-The-Complete-Guide-v260607.pdf
  pages:
    first: 22
    last: 26
extraction_status: machine-extracted
---

# Curator: Brakes for Self-Evolution

*Curator: Brakes for Self-Evolution*

An agent that writes its own Skills will sooner or later write a pile of junk. Hermes's answer isn't «just make fewer» — it's hiring a janitor who clocks in on its own schedule, never deletes anything, and backs everything up before it lifts a finger.

## Sort out one question first

In the last section we saw that after every conversation Hermes forks a background review that turns whatever it just learned into a Skill. Sounds great, but my first reaction was worry: won't it just keep piling them up, until it's hoarded dozens of nearly identical little junk Skills?

That worry is justified. You fix a bug today, it saves one; tomorrow you switch projects, hit a similar pitfall, and it saves another. A week later the Skills directory is littered with a dozen files that have different names and eighty percent overlapping content. Every time the agent needs to pick a Skill, it has to dig through this pile of near-duplicates — wasting tokens and easy to pick wrong.

This isn't hypothetical. The background-review prompt contains one line with a pretty aggressive attitude: «Most sessions should produce at least one Skill update; doing nothing is a missed learning opportunity, not a neutral outcome.» A system told to «learn as much as possible» inevitably comes with the side effect of «learning too much.»

Curator exists for exactly that side effect. It was born in v0.12.0, the version the team flat-out named «The Curator release,» with a confident subtitle: Hermes Agent now maintains itself. It had started maintaining itself.

> Continuing the metaphor from §04: background review handles proliferation, Curator handles apoptosis — and Curator is precisely the «apoptosis engine» we're taking apart here. Karpathy has said something similar: for a learning system, forgetting matters as much as learning.

## How it gets woken up

Curator isn't a scheduled job that runs forever in the background. There's no cron daemon in the source; it relies on «idle triggering»: it checks in passing when the CLI starts up and on gateway ticks, and only if it's been long enough since the last run, and the agent has been idle long enough, does it fork a background process to do the work.

By default both gates have to pass:

> ≥ 7 days since last run agent idle ≥ 2 hours fork one maintenance run

\+ →

There's also a detail I rather like: after a fresh install, the very first tick doesn't do anything right away. It records the «last run time» as right now, forcing itself to wait out a full 7-day cycle. The comment puts it bluntly: messing with your Skill library the moment you've just run `hermes update` would be a terrible experience. You get a whole week to pin the ones you care about and opt out of the ones you don't want.

## Two phases: pure function first, then the LLM

When Curator actually gets to work, it splits into two steps. The first step calls no large model at all — it's a pure-function state machine that mechanically advances each Skill through its lifecycle based on «how long since this Skill was last used.»

> active stale archived

unused 30 days → unused 90 days →

What's interesting about this state machine is that it's reversible and deterministic. A Skill marked stale snaps back to active the moment it gets used once more. No mysticism, no large-model judgment, just arithmetic on timestamps. A pinned Skill skips this step entirely — no matter how long it sits, it won't be touched.

Why deliberately avoid the LLM in step one? My guess is to separate «things rules can decide for certain» from «things that need judgment.» Whether to archive is purely a matter of time; having a model judge that is just a waste of money and less reliable. The work that actually requires taste is saved for step two.

Only in the second step does it fork an agent running on the helper model, sending it to patrol the Skills the agent itself created and decide, one by one: keep, tweak, merge with another, or archive. This step has «opinions,» and the set of opinions below is Curator's biggest evolution over two months.

## From «find duplicates and delete» to «build an umbrella»

Early on you'd assume Curator does deduplication: find two similar things, delete one. But the very first line of the v0.16.0 review prompt rejects that reading: «This is an umbrella-building consolidation, not a passive audit, and not duplicate-finding.»

Where's the difference? Dedup thinks «are these two alike?»; umbrella-building thinks «would a human maintainer write this as a few independent Skills, or as one Skill with a few sub-sections?» The prompt even explicitly forbids using «each Skill has different trigger words» as an excuse not to merge — different triggers are no reason; if it belongs under one umbrella, it gets collected.

There are three concrete moves:

| Move | When to use it | How |
| --- | --- | --- |
| Merge into an existing umbrella | There's already a big enough Skill to serve as the umbrella | Patch the sibling Skill's unique points in, archive the sibling |
| Build a new umbrella | No existing umbrella covers it | Create a new class-level SKILL.md and pull the scattered ones in |
| Demote to a sub-file | Narrow content but valuable | Demote it to references/templates/scripts under the umbrella |

This shift actually has a real product sensibility to it. It encodes «what a good knowledge base looks like» — a very hard-to-quantify kind of human taste — into a piece of automated maintenance logic. There's one line in the prompt I especially like: «Hundreds of narrow Skills each handling one session's specific bug is the library's failure, not its feature.»

## The four-layer brake design

By this point you may, like me, feel an instinctive unease: letting an AI automatically edit and archive my Skill library — what if it gets it wrong? What if it archives something important to me?

This is exactly the core of §05. Curator isn't automation with the gas pedal floored; its brakes are heavy — heavy enough that I think they're worth going through one by one.

## Layer one: never delete, only archive

The source file header states an invariant: Never auto-deletes — only archives. Archive is recoverable. What «archive» means is moving the Skill directory into `~/.hermes/skills/.archive/` , ready to `restore` at any time. Curator has no «delete» action; the harshest thing it can do is move something into the drawer next door.

## Layer two: snapshot before acting

Before every formal maintenance run, Curator first tars the entire skills directory into a tar.gz snapshot — including `.archive/` — and stores it in `.curator_backups/` , with a UTC timestamp for a filename.

| 注意 |
| --- |

> This means that even if this round archives something wrong, a single `hermes curator rollback` undoes the whole round — including what it archived this time and what was archived before, all recovered. The snapshot stores the old archives too, so the rollback is genuine «time travel,» not just undoing the most recent step.

## Layer three: dry-run preview

Don't trust it to run on its own? `hermes curator run --dry-run` makes it list everything it plans to do this round, without touching a single character of your library. You review the report, and if it looks OK, you do a live run.

This maps onto Martin Fowler's well-known framework: the relationship between a human and an automated system can be in the loop (hands-on for everything), on the loop (supervising from the side, able to intervene), or out of the loop (fully hands-off). Hermes clearly chose on the loop — you don't have to watch its every step, but the report is reviewable at any time and the result is reversible at any time. It hasn't kicked you out.

## Layer four: provenance locks the blast radius

The most elegant one is here. How does Curator know which Skills it may touch and which it must not touch at all? It relies on each Skill's «origin» marker.

| Skill origin | Who made it | Can Curator touch it? |
| --- | --- | --- |
| bundled | Ships with Hermes out of the box | Off by default (optional pruning since v0.16.0) |
| hub-installed | Installed from the community marketplace | Always exempt, never touched automatically |
| user-requested in the foreground | You explicitly asked the agent to write it | Yours; Curator never lays a finger on it |
| made by the agent's background review | Forked off and created by the agent itself | This is Curator's only jurisdiction |

Under the hood it relies on a contextvar: when the background-review fork runs, the write source is tagged `background_review` , and only Skills created from this source get stamped `created_by: agent` and fall under Curator's jurisdiction. Anything you hand-wrote or installed is always safe.

This sentence is worth pausing on: the blast radius of the agent's self-evolution is strictly locked inside its own private plot. The only things it can reclaim are the things it grew itself. Between your property and its property there's a property line drawn at the source-code level.

| 核 | 心 | 建议 |
| --- | --- | --- |

> One easily confused detail: pinning a Skill blocks deletion, archiving, and merging — not content improvement. A pinned Skill can still be improved by Curator; pin protects «it won't disappear,» not «it won't change.»

## What this brake answers

«Will self-evolution spin out of control» is the question hanging over every system of this kind. Many products answer it vaguely — nothing more than «we have safety mechanisms» and «we monitor continuously.» Hermes's answer is a set of concrete designs you can point to in the source and read aloud.

| 推 | 荐 | 不推 | 荐 |
| --- | --- | --- | --- |
| Never delete (archive-only, recoverable) + tar.gz snapshot before each run + dry-run preview + provenance locking the blast radius. Each one answers a specific «what if it goes wrong.» |  | «We have a comprehensive safety mechanism that guarantees the controllability of the self-evolution process»: reassuring to hear, useless when something actually breaks. |  |

I think this is the right way to «install brakes.» Brakes don't limit how fast the car can go — they're what makes you dare to drive it fast. Precisely because it never deletes, can roll back, and can't touch your stuff, that aggressive «learn as much as possible» review dares to actually be aggressive. Without this set of brakes, you simply wouldn't dare let an AI automatically edit your tool library.

In the next section we'll look at the most counterintuitive stroke in this whole self-evolution: on top of all the rules about «what to learn,» Hermes also wrote a dedicated blacklist of «what not to learn.» For a self-evolving agent, the real danger isn't failing to learn — it's learning the wrong thing and then using that wrong rule to keep rejecting itself.
