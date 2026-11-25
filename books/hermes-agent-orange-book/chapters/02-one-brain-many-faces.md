---
id: hermes-agent-orange-book/one-brain-many-faces
resource: hermes-agent-orange-book
title: "60-Second Overview: One Brain, Many Faces"
part: "Part 1: What It Is"
order: 2
section_label: "§02"
language: en
edition: v260607
source:
  repository: alchaincyf/hermes-agent-orange-book
  revision: b6e53a8e11e00c8b14b2f72d6b4f1ce71fef6692
  path: Hermes-Agent-The-Complete-Guide-v260607.pdf
  pages:
    first: 8
    last: 11
extraction_status: machine-extracted
---

# 60-Second Overview: One Brain, Many Faces

*One Brain, Many Faces: 60-Second Tour*

You think you're looking at several products: a command line, a desktop app, a web dashboard, twenty-some chatbots. They're actually all the same thing underneath. The whole architecture fits in one sentence: one brain, many faces.

## Start with this diagram

Draw out Hermes's architecture and you get a lone circle in the middle called AIAgent. Around it sits a ring of boxes: the CLI, a TUI built with Ink, an Electron desktop app, a browser-based admin panel, plus twenty-some IM platform adapters. Every box has a line running back to that circle.

> CLI Ink TUI Desktop App AIAgent Web Panel

→ ←

> 23 IM Platforms

The entire takeaway from this diagram is one sentence: none of the boxes on the outside is "another Hermes"—they're all different shells over the same core.

When you chat with it on Telegram, when you chat with it in the desktop app, when you type commands at the command line—you're hitting the same logic in the same AIAgent instance. Swap the face, the brain stays the same.

## What that brain looks like

The AIAgent class is the nerve center of the whole system. It has one glaring trait: its constructor takes around 60 parameters.

Credentials, routing, all sorts of callbacks, session context, budgets, credential pools… all crammed into one constructor. Anyone who has written code will frown at this—the textbooks call it a "god object," a classic example of what not to do. The maintainers don't shy away from it either; the AGENTS.md in the source spells out in black and white that this is a god object.

But it's deliberately designed this way. Later on we'll get into why they'd rather wear that label than break it apart.

This brain exposes only two openings to the outside world. One is `chat(message)` : throw in a sentence, get back a reply—blunt and simple. The other is `run_conversation()` , the full interface, which returns the final reply plus the message list for the entire turn. Every feature you use day to day ultimately funnels down to these two methods.

Internally it runs a synchronous loop—not the trendy async. It comes with interrupt checks, budget tracking, and a one-time grace call. If the model says it wants to call a tool, the loop calls it, stuffs the result back into the message list, and asks the model again; once the model is done talking, the loop ends. By default it runs at most 90 rounds, and that 90-round budget is shared between the main Agent and any sub-agents it spawns.

## Five built-in systems, mapping to the five Harness components

If you read the Harness Engineering orange book, you'll remember the reins framework: instructions, constraints, feedback, memory, orchestration. Back then the discussion was "how you should put reins on your Agent."

What's interesting about Hermes is that it ships all five components as built-in systems out of the box. You don't configure them in—they're already part of its body. Here's the one-to-one mapping:

| Harness What It Is in Hermes In One Line Component |
| --- |
| Instruction layer Skill system markdown skill files, injected as a user message rather than a system prompt |
| Constraint layer Tool-set toggles + sandbox + 6grant the permissions it should have, lock down terminal backendswhat it shouldn't touch |
| Feedback layer Self-improving learning loop +the more it's used the better it gets, and it prunes Curatorstale skills on its own |
| Memory layer SQLite + FTS5 + swappable memorystored locally, full-text indexed, findable across providersessions |
| OrchestrationSub-agent delegation + scheduledone Agent can direct a whole crew of Agents to layertasks + Kanban boarddo the work |

The later chapters of this book basically dig down along these five rows. Each row has its own source code, its own design trade-offs, its own pitfalls. This section just lays out the map so you know roughly where each piece of the puzzle sits.

> Remember this mapping. It's the skeleton of the whole book. Whenever a system later on feels confusing, come back to this table and ask yourself "which reins component is this?"—and it'll usually fall into place.

## Why wear a god object rather than break it into microservices

By now you should have a question. A god object that swallows 60 parameters is obviously "inelegant." These people aren't bad at their craft—why not split it into a few clean microservices?

I thought the same thing at first. Munger has a line: when you hit a decision that seems off, don't rush to call the person stupid—first ask what doing it this way bought them.

What it bought is something especially valuable: behavior that's completely consistent across every platform.

Because all the faces share the same brain, the preferences you tuned in the desktop app, the habits you taught it, the things it remembered—all of it is there when you switch to the command line, or to Telegram. It's not "synced" over; it's literally the same thing, so there simply aren't two copies of state to reconcile. The moment you split it into microservices, you immediately face the whole old grab bag of distributed-systems problems: how to sync state, how to keep messages consistent, which service is the source of truth.

And what really nails this trade-off down are two hard constraints that can't be touched.

| 推 | 荐 | 不推 | 荐 |
| --- | --- | --- | --- |
| The prompt cache must not break. Mid-conversation you absolutely cannot alter the past context, can't swap the tool set, can't rebuild the system prompt—one change and the whole cache is void, and every request has to re-burn tokens. This constraint is even why a Skill gets injected as a user message instead of a system prompt. |  | Tens of thousands of tests can't move. The whole project sits on close to seventeen thousand tests. Restructuring the architecture means moving the foundation, and all those tests get dragged down with it—the engineering cost is unrealistically high. |  |

Put these two constraints side by side and the answer is clear. This really isn't a matter of technical taste —it's engineering realism. When a god object buys you "consistent behavior across every platform," and tearing it out would cost you "a broken cache + tens of thousands of rewritten tests," carrying that weight is actually the smart move.

The v0.16.0 release did a textbook refactor that happens to confirm this restraint. They moved the giant method that drives a single conversation turn—nearly 3,900 lines—wholesale into a standalone module, leaving only a thin forwarder in its place, and deliberately used indirect resolution so that not one of those tens of thousands of tests would break. First make the elephant movable, then talk about dismantling it. No redesign, no change to the shape of state, just relocating it. That's Hermes's architectural character—conservative, pragmatic, with a healthy respect for real costs.

One brain, many faces. That line isn't just a metaphor; it's a thought-through engineering decision forced out by two hard constraints. In the next section we'll change angle and look at what Nous is really after in building a thing like this.
