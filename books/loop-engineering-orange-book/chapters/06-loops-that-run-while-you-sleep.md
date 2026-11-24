---
id: loop-engineering-orange-book/loops-that-run-while-you-sleep
resource: loop-engineering-orange-book
title: "Loops That Run While You Sleep: Three Real Ones"
part: "Part 3 · Where It Runs, What It Costs"
order: 6
section_label: "§06"
language: en
edition: v260615
source:
  repository: alchaincyf/loop-engineering-orange-book
  revision: "829aa6084cd68680e7f389bbde9dcaebda7a43e6"
  path: Loop-Engineering-The-Complete-Guide-v260615.pdf
  pages:
    first: 21
    last: 24
extraction_status: machine-extracted
---

# Loops That Run While You Sleep: Three Real Ones

*Three Real Loops*

Everything so far has been "how you should build one." This chapter only looks at "who actually built one and has it running." Three public cases, from one person's morning to a company shipping a thousand-plus PRs a week.

These three cases differ wildly in scale, but the skeleton is the same: a trigger presses start for you, a set of constraints keeps it from running off the rails, and a human checkpoint at the end. Once you've seen all three, you'll notice that "running while you sleep" was never about how strong the model is—it's about how solid that skeleton is.

## 1. Addy's morning: a triage loop that actually runs

Addy Osmani has described a loop of his own. Not a hypothetical—something that happens automatically every morning.

§03 already broke down the flow: at dawn an automation wakes itself up, reads CI and issues, opens a worktree, has sub-agents draft and review, opens a PR automatically when things pass, drops anything uncertain into an inbox for a human, and writes the state into a file for the next day. I'll only flag one detail §03 didn't stress: the automation invokes a skill, rather than gluing a huge block of instructions into the schedule. Addy's line on this stings a bit.

> **Original:** you fire $skill-name instead of pasting a giant wall of instructions into a schedule that nobody will ever update.

You fire a $skill-name, instead of pasting a giant wall of instructions into a schedule. Paste that in, and nobody's ever going to update it again.

This is what a loop one person can run looks like. One person, one machine, getting the grunt work done for you every morning.

## 2. Stripe's Minions: 1,300 PRs a week

To push a loop to enterprise scale, the case most worth studying is Stripe's Minions.

Put the number out front: more than 1,300 PRs merged a week, not one line written by hand. These details come from Stripe engineer Steve Kaliski on the podcast How I AI.

The trigger is light. You @ the Minion bot in Slack, or add an emoji reaction to a message, and then you're done thinking about it (fire-and-forget).

But what really makes it reliable isn't the light trigger—it's the stretch before the LLM wakes up. Before the model starts thinking, a deterministic orchestrator assembles the context first: it scans links in the message, pulls Jira, finds docs, and uses Sourcegraph plus MCP to search out the relevant code. By the time the agent takes the stage, all the materials it needs are already laid out on the table.

Why does this step matter? Because letting the LLM go find its own context is the least controllable part. It might search wrong, miss things, or make things up to fill in an answer. Stripe's move is to take "find the materials"—work whose rules you can hard-code—out of the LLM's hands and give it to deterministic code. The LLM only handles the part it's genuinely good at: writing code with all the materials in front of it. Anything deterministic logic can solve never goes to a probabilistic model. Where you draw that line directly decides whether the loop is reliable.

The most counterintuitive part is underneath. Minions isn't built on some stronger model. It's a fork of the open-source tool Goose. The core claim is one sentence: AI's reliability comes from the quality of the constraints, not the size of the model.

Its architecture is six layers, with deterministic gates and LLM creative steps interlocking in alternation. The agent finishes the code, a hard-coded pipeline runs the linter, and the agent can't skip past it; the agent fixes the lint; once fixed, a hard-coded step runs git commit. The sandbox is Devbox, running on EC2—"cattle not pets," used and discarded, not kept as a pet.

"Cattle not pets," that old ops line, fits perfectly here. Each agent's working environment is a head of cattle that can be swapped out anytime, not a cat you keep. If one breaks, you don't fix it—you spin up a new one. This design lets a thousand-plus agents run at once without stepping on each other, because no environment is "precious" and untouchable. The quality of the constraints shows up in these unglamorous engineering decisions, not in model parameters.

| Step | Who does it |
| --- | --- |
| trigger | human (Slack @ or emoji) |
| assemble context | deterministic orchestrator (not the LLM) |
| write code | LLM agent |
| run linter / commit | hard-coded pipeline (agent can't skip) |
| review those 1,300 PRs | human |

Note the last row. The human didn't leave—the human changed desks. Those 1,300 PRs are still reviewed by engineers; the time just moved from "writing" to "reviewing." Which lands right on the previous chapter's point: the more a loop can produce code you didn't write, the more critical the part that can say "no." Stripe hands half the "no" to hard-coded gates and leaves the other half to humans.

## 3. So what does "running while you sleep" actually rely on?

"Let the loop run while you sleep" is the sexiest line of this whole wave. But you have to say it precisely.

Local /loop, desktop scheduled tasks—they all need your machine on. Turn the machine off and the loop stops. If you really want it to run with the machine off, with you asleep, the right answer is something else: Cloud Routines, or GitHub Actions schedule triggers.

|  | Cloud Routines | Desktop scheduled task | /loop |
| --- | --- | --- | --- |
| where it runs | Anthropic cloud | your machine | your machine |
| machine on? | no | yes | yes |
| session open? | no | no | yes |
| min interval | 1 hour | 1 minute | 1 minute |
| see local files? | no (fresh clone) | yes | yes |

Reading this table is simple. Want it frequent, want it to see local files? Use local /loop, at the cost of keeping the machine on. Want it to run with the machine off, not tied to local state? Go to the cloud, at the cost of a one-hour minimum interval and a clean clone every time. No single scheduler does it all. Which one you pick depends on whether your loop is glued to the local machine or can leave it.

Two concrete scenarios. You want a loop to check a local dev server every minute—that can only be local /loop. The cloud can't see that process on your machine, and the interval can't go below a minute. Flip it: you want it to scan the repo's open issues at 3 a.m. every night and open PRs where warranted. That work shouldn't be tied to your laptop at all. Laptops get their lids closed, lose power, get carried out the door. For that, GitHub Actions schedule triggers or Cloud Routines are the right answer—they run on a machine that's always awake while you sleep.

"Running while you sleep" gets distorted so easily because a lot of people treat local /loop as the whole of it. Local /loop is "let it run a few extra rounds for me while I'm here." Cloud scheduling is "it runs even when I'm not." Two different things—don't mix them.

The scheduling itself isn't mysterious. /loop uses standard cron expressions, five fields, one-minute minimum granularity; if it annoys you, set CLAUDE_CODE_DISABLE_CRON=1 and it's all off. This layer has long been ops common sense. Loop engineering didn't reinvent it—it just hung an agent on top.

On the Codex side, the counterpart is the Automations tab. You can set daily, weekly, or use custom cron. It runs in a dedicated background worktree, and the results collect in a Triage inbox for you to look at when you're back. Same logic: a local automation also needs the machine on, running with it off relies on the cloud, and Codex's own cloud Jobs are still on the roadmap.

Put these three cases together and they form one line: an individual can build one (Addy's morning), a company can scale it (Stripe's thousand PRs), and there's a ready-made layer of scheduling to choose from (local or cloud). Loop engineering isn't a future concept. It's already on many people's machines and in many companies' CI, running every day.

A few widely circulated numbers are best treated with caution when you see them. Things like "around 90% of Claude Code is written by itself" or "Nubank migrated a million lines of ETL with a 12x speedup" are mostly secondhand summaries—take them as a rough reference, don't take them too seriously. The details of this chapter's three cases can all be traced to firsthand sources, and that holds up under scrutiny better than one impressive-sounding big number.

Next chapter we switch angles and look at the cost of all this. A loop running unattended is also a loop making mistakes unattended.
