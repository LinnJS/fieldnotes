---
id: hermes-agent-orange-book/three-engines-of-self-improvement
resource: hermes-agent-orange-book
title: "Build, Repair, Continue: Three Engines of Self-Improvement"
part: "Part 2: The Reins Grow Themselves"
order: 4
section_label: "§04"
language: en
edition: v260607
source:
  repository: alchaincyf/hermes-agent-orange-book
  revision: b6e53a8e11e00c8b14b2f72d6b4f1ce71fef6692
  path: Hermes-Agent-The-Complete-Guide-v260607.pdf
  pages:
    first: 17
    last: 21
extraction_status: machine-extracted
---

# Build, Repair, Continue: Three Engines of Self-Improvement

*Build, Repair, Continue: Three Engines of Self-Improvement*

The old book said "the harness grows on its own." Two months later, having read the source, I can point at a strand and tell you who's growing it, who trims it when it grows crooked, and how to recover when the trim goes wrong. It went from a slogan to three engines running in the background, each minding its own patch.

## First, the debt that book left two months ago

When the last edition of the Hermes Orange Book wrote up the learning loop, the version it described was v0.7.0. My phrasing back then was pretty vague: an agent that "writes memories and builds skills." Meaning it could self-evolve, but if you asked "which file exactly, which trigger condition, running on which thread," I couldn't answer. At that point it was essentially still an idea, plus a main agent that prompts nudged toward saving things.

In these two months it jumped eight versions, all the way to v0.16.0. I read the source line by line and found that the idea had been engineered into real infrastructure. The cleanest way to split it is three verbs: build, repair, continue.

> BuildRepairContinue

→ →

> Background ReviewCuratorGoals / Ralph Loop

Build is when, after each turn of conversation, it quietly forks a sub-agent to do a retrospective and decide what was learned this time and which skill to write it into. Repair is a maintainer that wakes itself up once every seven days to merge, archive, and package the skill library the agent has built. Continue is when a goal isn't finished and the agent gives itself an extension, running several turns in a row instead of answering once and stopping.

The three engines run on three completely different time scales. This section first lays out where each of the three machines sits; the next two sections dig deeper into the two most interesting ones.

## Anything that can self-evolve must also be able to self-clean

Before taking the engines apart, I want to give you an angle for looking at this whole mechanism, otherwise it's easy to treat it as a pile of scattered background tasks.

An agent that grows its own skills has an unavoidable side effect: every time it solves a new problem it wants to save a lesson, and after a few months it has accumulated dozens or hundreds of narrow, duplicate skills. Each was only useful for that one bug at the time, and together they're a pile of garbage polluting the catalog and burning tokens for nothing. A system that only adds and never subtracts will eventually be crushed by itself.

So what really makes the Hermes setup work isn't that it builds, but that it pairs building with cleaning. The analogy that popped into my head while reading the source was biological cells: they have to both proliferate and undergo apoptosis. Proliferation lets the tissue grow; apoptosis clears out aged, faulty, and unneeded cells. A tissue that only grows and never dies has a name for it: a tumor. Hermes's background review handles proliferation, the Curator handles apoptosis, and the two are a matched pair that show up together.

With this angle in mind, the three engines fall into place.

## Engine One · Build: the post-turn background retrospective

This engine corresponds to `agent/background_review.py` in the source. The way it works is stated plainly in the file's header comment: after each turn of conversation ends, the main agent may fork a daemon thread, take a snapshot of that conversation and replay it, then ask itself one question: was there any skill or memory worth saving or revising this time?

The key is that it runs after the main reply has gone out. The source comment specifically explains why: the retrospective must never compete with the user's task for the model's attention. So it's best-effort, silently skipped on failure, never dragging down the main flow. While you're talking to it, you can't feel that there's a clone writing notes behind the scenes.

What triggers it isn't one counter but two, and the two are staggered. This detail, I think, really shows that the designer thought clearly about "there are two kinds of knowledge."

| Counter | Counts by | Default threshold | Which kind of knowledge it manages |
| --- | --- | --- | --- |
| Memory nudge | Conversation turns | Every 10 turns | Who you are, what you're currently doing |
| Skill nudge | Tool iterations this turn | Every 10 iterations | How this kind of work should be done |

Why memory by "turns" and skill by "tool iterations"? I thought about it, and the logic is subtle. A complex task might only go back and forth once or twice in conversation, while internally running dozens of tool calls. That kind of work is more likely to deposit a piece of procedural knowledge about "how to do this kind of thing," so using tool-iteration count as the yardstick makes sense. Memory is "who you are," skill is "how to do things," and the two kinds of knowledge are measured with two different rulers. Both thresholds can be changed in the config.

The most quote-worthy part of this engine is the prompt it uses when reviewing skills. I've pulled out the core lines, and this is almost a piece of engineering methodology on "how an AI should write rules for itself."

> Learning should be the default: the prompt literally says, "Be ACTIVE, most sessions should produce at least one skill update… A retrospective that does nothing is a missed learning opportunity, not a neutral outcome." It defines "not learning" as a dereliction of duty, not the safe default option.

More interesting is how it defines a learning signal. Mitchell Hashimoto has a habit when using Claude Code: every time the agent makes a mistake, he adds a rule to CLAUDE.md. Hermes automated this, and made "mistake" concrete as the user's tone of displeasure—"stop doing X," "this is too verbose," "don't format it this way," "why are you explaining again," "just give me the answer." It lists these frustration signals as first-class learning signals and requires that they be encoded on the spot into a pitfall or step inside a skill.

It also has a priority gradient for editing skills, rather than creating a new one at the first sign of trouble: first edit the skill that was just loaded this turn, then edit an existing broad category, then add a sub-file under that category, and only create a new one when there's truly no matching category. This gradient exists precisely to stop skills from ballooning endlessly—if you can patch an old one, don't build a new one. And a newly created skill's name must be "class-level"; naming it after some PR number, some error string, or some code name that only exists today is forbidden. The source puts it bluntly: if the name only makes sense for today's task, then it's wrong.

## Engine Two · Repair: the Curator, the maintainer that wakes once every seven days

The second engine is the Curator, with source in `agent/curator.py` . This thing didn't exist at all in the old book; it was born in v0.12.0, a version the team named The Curator release, whose release notes opened with: Hermes can now maintain itself.

What it does is exactly the "apoptosis" half mentioned above: merging, archiving, and packaging the skill library the agent created itself, pure maintenance, learning nothing new. If background review notices two overlapping skills during a retrospective, it won't merge them itself; it just "makes a note and hands it to the curator for bulk processing." The two engines' duties are drawn very clearly in the source.

The Curator's trigger rhythm is completely different from the first engine. It doesn't rely on a cron daemon; it relies on idle detection: by default it runs at most once every 7 days, and only acts after the agent has been idle for 2 full hours. There's also a very thoughtful gate: on a fresh install or right after an update, it won't immediately mess with your skill library on the first tick; instead it seeds "last run time" as "now" and only really runs after a full cycle has passed. The designer's reasoning: making big changes to a user's library right after an update is too abrupt.

It does its work in two stages, and the first stage uses no large model at all. A pure-function state machine that mechanically advances each skill's lifecycle by its "last activity time":

> activestale

→ 30 days unused → → 90 days unused →

> activestale

> archived archived

Once a stale skill is used again, it automatically revives back to active. A pinned skill never participates in automatic transitions. This stage doesn't burn a single token; it's pure timestamp pushing. The second stage is the large-model retrospective, forking an agent to actually judge which skills should be merged and which archived.

The Curator has the most details and the heaviest brakes of all three engines, and the next section of this book is devoted to taking it apart, including its philosophical pivot from "finding duplicates" to "building umbrellas," and that never-delete, snapshot-a-tar.gz-before-running, fully-rollbackable safety design. For now, just remember where it sits among the three engines: the one in charge of pruning.

## Engine Three · Continue: the Goals Ralph Loop

The first two engines change the agent's cross-session capability. The third is different; it changes the agent's persistence within a single session. The source is in `hermes_cli/goals.py` , and the comments call it "Hermes's Ralph loop."

The mechanism isn't complicated: a goal is a user-given objective that stays in effect across multiple turns. After each turn ends, a tiny judge call asks an auxiliary model one question: was this goal satisfied by the reply just now? If not, Hermes feeds a "keep going" prompt back into the same session and continues running, until the goal is done, the turn budget is exhausted, the user calls a halt, or the user sends a new message.

It has a few restrained designs I quite admire. The extension prompt is just an ordinary user message appended in—it doesn't touch the system prompt, doesn't swap the toolset—so the prefix cache doesn't get invalidated, saving money. If the judge ever breaks, it chooses to fail-open, that is, "continue," because a broken judge can't be allowed to jam progress, and the turn budget backstops it anyway. Any real message you send at any time preempts the extension prompt.

| 核 | 心 | 建议 |
| --- | --- | --- |

> The first two engines make the agent "understand you better the more you use it"; the third makes it "lock onto a goal and not let go." Building capability, repairing capability, continuing drive—the three together are what makes a complete "agent that builds its own harness."

## Three engines, one panorama

Put the three machines side by side and the differences are obvious at a glance. They run on three time scales, each minding one thing, none stealing another's work.

| Engine | Verb | Trigger rhythm | What it does | Where it runs |
| --- | --- | --- | --- | --- |
| Background Review | Build | Every 10 turns / 10 tool iterations | Decide what was learned → write memory, build/edit skill | Background thread forked after the main reply |
| Curator | Repair | Default every 7 days + 2 hours idle | Merge, archive, package the skill library | Independently forked agent, using an auxiliary model |
| Goals / Ralph Loop | Continue | Judged once after each turn | Extend when a goal isn't done, run several turns in a row | Within the same session, appended prompt |

This is the biggest change in this closed loop over two months. The old book described an agent that "should be able to self-evolve"; v0.16.0 is an engineering system with triggers, with state machines, with boundaries, with brakes. It went from a vague promise to infrastructure where you can point at every line in the source and interrogate it.

Of the three engines, build and continue are relatively easy to grasp; the one most worth expanding on is "repair," which hides the two most restrained and most counterintuitive design choices in this whole self-improvement system. In the next section we'll drill into the Curator and see, for an agent that self-cleans, exactly where the brakes are.
