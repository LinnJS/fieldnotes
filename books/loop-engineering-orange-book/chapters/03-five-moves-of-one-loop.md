---
id: loop-engineering-orange-book/five-moves-of-one-loop
resource: loop-engineering-orange-book
title: The Five Moves of One Loop
part: "Part 2 · How It Turns"
order: 3
section_label: "§03"
language: en
edition: v260615
source:
  repository: alchaincyf/loop-engineering-orange-book
  revision: "829aa6084cd68680e7f389bbde9dcaebda7a43e6"
  path: Loop-Engineering-The-Complete-Guide-v260615.pdf
  pages:
    first: 9
    last: 12
extraction_status: machine-extracted
---

# The Five Moves of One Loop

*The Five Moves of One Loop*

Take one turn of a loop apart and there are really only five moves inside. Understand these five and you understand every loop.

The word "loop" is easy to misread. Hear "loop" and what comes to mind is a stretch of code running over and over, spinning without end.

But the loop in loop engineering isn't that idle spin. Every turn, it does something concrete: it finds something worth doing, hands it to the agent, verifies whether the result is right, saves the state, then decides the next step.

Five moves: discovery, handoff, verification, persistence, scheduling. Drop any one and the loop won't turn, or it'll turn but spin in place.

## Threading it through one real example

Addy Osmani is on the Google Chrome team, and he built himself a morning triage loop. This example gets cited a lot because it's concrete enough that every move lands somewhere real.

Here's the whole flow. In the morning an automation kicks off on its own, no click from him. A triage skill reads yesterday's failing CI tests, the issues still open, and the recent commits. It writes the triage results into a markdown file or a Linear board. For every finding worth acting on, it opens an isolated worktree. One sub-agent drafts the fix; a second sub-agent reviews it against the project's skills and tests. A connector automatically opens the PR and updates the ticket. Anything it can't handle goes to an inbox to wait for a human. And that state file stays around, so the next day picks up right here.

The beauty of this loop is that no step needs a human's hand, yet it stops to wait for a human exactly where it should. Everything that can be automated is fully automated; everything it can't handle goes honestly into the inbox. Now let's take that one turn apart by the five moves.

## Move one: discovery

The first thing a loop does on a turn is figure out "what should this turn do."

In Addy's example, the discovery step is the triage skill's job. It reads three things: CI failures, open issues, recent commits. Together those are "what came up in the system worth minding, between yesterday and today."

The key to discovery is letting the agent find its own work, rather than you feeding the work to it. If you manually list "fix these three bugs today" every morning, the loop is still started by you, and it hasn't saved you anything.

There's a detail here that's easy to miss. Addy stresses that the automation triggers a skill, not a big block of instructions. In his words, you trigger a \`$skill-name\`, not a wall of instructions pasted into a cron job nobody will ever update. A skill is knowledge made permanent; when the discovery logic changes, you just change the skill.

How well discovery is done sets the ceiling on the whole loop's quality. If the work it surfaces has no value, the other four moves can be done beautifully and it's still doing useless work, carefully. So this step isn't just "read some stuff." It's teaching the agent to judge what's worth doing and what can be left alone — and that's precisely the hardest part to bake into a skill.

## Move two: handoff

Once you've found the work, you have to hand it off for someone to do. This step is the handoff: moving the task from the "scheduling system" into the hands of the "agent that does the work."

Handoff isn't just shouting "go fix this." Addy's approach is that every finding worth doing gets its own isolated worktree. A worktree is a git mechanism that lets multiple agents change code in separate working directories without stepping on each other.

Why isolate? The next chapter goes into it. For now, one line to remember: two agents changing the same file at once is exactly the same headache as two engineers committing to the same lines. Separate them at handoff time and you've got a lot less conflict to clean up later.

After the handoff, the one doing the actual work is the sub-agent. One drafts the fix and writes a first version of the change. Whether that version is any good isn't for it to say.

There's a design tradeoff worth noticing here. Handoff isn't dumping the whole job on a single agent; it's cutting it into isolated little tasks first, then handing them out separately. The cleaner the tasks are cut, the easier verification and merging are later. One finding maps to one worktree, maps to one clear change — clear boundaries, and easy to pin down whoever goes wrong.

## Move three: verification

This is the step in the whole loop that's easiest to cut corners on, and the one you can least afford to skip.

Addy's design is that after the first sub-agent drafts the fix, a second sub-agent reviews it. The second agent checks against the project's skills and tests, its instructions differ from the first, and sometimes even the model is swapped out.

Why insist on a different agent for review? Because the agent that wrote the code is too soft when grading its own homework. Let it judge what it just wrote and it tends to confidently praise the whole thing — even when, to a human eye, the quality is clearly mediocre. Swap in an agent with different instructions, dedicated to picking holes, and it catches the problems the first agent talked itself into letting through.

Addy puts it bluntly: the hard part of a loop isn't the loop itself, it's putting something inside it that can say no. A loop with no real check is just an agent nodding at itself over and over.

This verification step is that thing that can say no. It decides whether the loop is really doing work or just hypnotizing itself.

## Move four: persistence

Once verification passes, the result has to land somewhere that survives this conversation. That's persistence.

Addy uses two things. The change itself, via a connector, automatically opens a PR and updates the ticket, landing in the code repo and the issue system. Findings it can't handle go into the triage inbox, waiting on a human. And there's a state file running through it all, recording "where it's up to."

The point of persistence is that a loop's memory can't live only in the current context window. Clear the context and the agent forgets everything. But what's written into markdown or a board doesn't forget. The next chapter expands on this when it covers components, and there's a good line there: the agent forgets, the repo doesn't.

Without persistence, every turn of the loop is like opening its eyes for the first time, always starting from zero. With it, what didn't get finished today can be picked up tomorrow.

## Move five: deciding the next step / scheduling

The first four moves — discovery, handoff, verification, persistence — add up to "one turn." But one turn isn't a loop.

What actually makes it a "loop" is the fifth move: scheduling.

Addy's triage loop runs automatically in the morning, no click from him each day. That state file lets findings not finished today carry over to tomorrow, and tomorrow's turn picks up automatically from right here. It's scheduling that turns "I ran it once by hand" into "it keeps turning on its own."

Addy has a line that gets right to it: automation is what makes a loop an actual loop, not just one run you did once.

> **Original:** Automations are what make a loop an actual loop and not just one run you did once.
>
> Automation is what makes a loop a real loop, not just the one time you ran it.

Without scheduling, the first four moves can be done beautifully and it's still a one-off manual job. You run it today on a whim and forget it tomorrow, and it stops. Add scheduling and it turns endlessly on a timer, carrying the thing on for you.

## The five moves, one line each to remember

Put the five moves together and the loop's skeleton is clear.

| Move | What it does | In the triage loop |
| --- | --- | --- |
| Discovery | Find this turn's work on its own | skill reads CI failures / issues / commits |
| Handoff | Hand the task to an agent, isolated | each finding opens a worktree |
| Verification | Swap in another agent to say no | a second sub-agent reviews against tests |
| Persistence | Write state outside the conversation | open PR + inbox + state file |
| Scheduling | Make it turn automatically, round after round | morning automation runs on its own |

This chapter took apart the moves — "what happens in one turn." The next chapter takes apart the parts — "what things you need in hand to build a loop that can turn." The two are two sides of one thing: moves describe the running, parts describe the materials.
