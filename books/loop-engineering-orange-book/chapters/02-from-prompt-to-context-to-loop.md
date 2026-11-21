---
id: loop-engineering-orange-book/from-prompt-to-context-to-loop
resource: loop-engineering-orange-book
title: From Prompt to Context to Loop
part: "Part 1 · What It Is"
order: 2
section_label: "§02"
language: en
edition: v260615
source:
  repository: alchaincyf/loop-engineering-orange-book
  revision: "829aa6084cd68680e7f389bbde9dcaebda7a43e6"
  path: Loop-Engineering-The-Complete-Guide-v260615.pdf
  pages:
    first: 6
    last: 8
extraction_status: machine-extracted
---

# From Prompt to Context to Loop

*The Triple Jump: From Prompt to Context to Loop*

Four layers in the stack, each minding one thing. See the boundaries and you'll know where the loop sits, and why it's the floor on top.

## The four-layer stack, laid out first

That string of "XX Engineering" terms the AI world has coined over the past two years aren't replacements for each other. They stack. One on top of the next, each minding something bigger.

Let me put the table up first, then walk through it layer by layer.

| Layer | What it minds | Core question |
| --- | --- | --- |
| Prompt engineering | Writing one good prompt | What should I tell the model |
| Context engineering | What goes in the window right now | What to retrieve, summarize, clear out |
| Harness engineering | Arming a single run | Which tools, which actions allowed, what counts as done |
| Loop engineering | Scheduling on top of the harness | How to make it run itself over and over |

Each layer up, what you have to worry about gets one size bigger. From "one sentence" to "one window," then to "one run," and finally to "a whole loop that runs itself." Let's take them one at a time.

## Layer one: Prompt, the words you write for the model

The bottom layer, and the one everyone knows best. Prompt engineering minds "what should I tell the model."

You weigh the wording, give examples, set a role, tune the tone. Its boundary is clear: it's this one time, the chunk of text you hand the model. Hand it in, the model spits something out, done.

The trouble with this layer is that it assumes you're present every time, handing it in yourself every time. One prompt solves one thing, and the next thing needs you to write another.

## Layer two: Context, what goes in the window right now

One layer up, the question changes. It's no longer "what do I say," but "what should go into this window right now so the model can actually crack the problem."

That's context engineering. What references to retrieve, how to summarize the long stuff, which stale information to clear out. It minds not your words, but the entire field of view the model can see at the moment.

This is its own layer because the model's window is limited, and stuffing in the wrong thing is worse than stuffing in too little. Give it a window full of noise and the best prompt in the world is wasted.

## Layer three: Harness, the full kit for a single run

Up again, to harness engineering. This layer minds what an agent needs to carry when it runs once.

Which tools to give it, which actions to let it touch, when to load context, how to recover when it fails, what state counts as "done." The harness only minds what an agent can do in a single run, and where it gets stopped.

I unpacked this layer across an entire book elsewhere, so I won't repeat it here. Just remember its position: the harness is the layer below the loop. It arms a single run of the agent, but it doesn't make that run repeat itself.

## Layer four: Loop, making it run itself over and over

At the top, loop engineering. With the first three layers done, you've got an agent that's fully equipped and can run cleanly once. But it stops when it's done, waiting for you to strike the next tick.

The loop layer is about automating that "waiting for you" away too. Addy's line says it cleanest.

> **Original:** Loop engineering sits one floor above the harness.

Loop engineering sits one floor above the harness. The floor below arms a single run; this floor makes it run itself over and over.

As for how it runs, Addy gives a picture too: it runs on a timer, spawns helpers, feeds itself. Three verbs in his words, and I'll explain them one by one.

## One floor up, what's actually added

Harness and loop often get talked about as one thing, but what they mind is a floor apart. I'll draw the line using Addy's three verbs.

**"Runs on a timer."** The harness arms a single run, which you have to trigger. The loop fits it with a timer, so it wakes up on schedule and gets to work, no button-press from you. This is the first sense of "runs itself over and over."

**"Spawns helpers."** Once a loop is turning, it splits off sub-agents to do parallel work. One drafts a change, another does nothing but pick it apart in review. The harness cares about how a single agent is armed; the loop cares about how a crowd of agents coordinates and who supervises whom.

**"Feeds itself."** This is the crucial one. What the loop produces becomes its own input for the next round. Yesterday's findings get written into a file; this morning it wakes up, reads that file first, and carries on. It has memory that spans single conversations, which is why it's called a loop and not a one-off task you happened to run many times.

Addy has a line that gets at this relationship: automation is what makes a loop an actual loop, not some run you did once by hand. Without "waking itself up and picking up the baton," what's left is just pressing the harness many times by hand.

## Why bother splitting it this finely

You might ask, is it really necessary to split it this fine? Isn't it just more and more automated?

It's necessary. Because each layer fails in a different way, and the check that can say no has to be installed in a different place.

A prompt goes wrong, you see it on the spot and fix a line. Context loaded wrong, the model answers off, and you'll likely catch that too. But by the loop layer, it runs while you sleep, changes code you never looked at, and feeds its own errors into the next round — and you might not find out for days.

The higher the layer, the farther you are from the scene, and the longer the mistakes pile up. That's exactly why the real difficulty of loop engineering is never building the loop, but putting something inside it that can stop it. This topic is the main event of the chapters ahead.

Remember this stack and you've got enough: prompt minds one sentence, context minds one window, harness minds one run, loop makes it keep running. Your position is climbing this stack layer by layer, from the person who writes the words to the person who builds the loop.
