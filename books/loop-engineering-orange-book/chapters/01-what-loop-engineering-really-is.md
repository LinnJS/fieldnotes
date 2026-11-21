---
id: loop-engineering-orange-book/what-loop-engineering-really-is
resource: loop-engineering-orange-book
title: "Stop Asking: What Loop Engineering Really Is"
part: "Part 1 · What It Is"
order: 1
section_label: "§01"
language: en
edition: v260615
source:
  repository: alchaincyf/loop-engineering-orange-book
  revision: "829aa6084cd68680e7f389bbde9dcaebda7a43e6"
  path: Loop-Engineering-The-Complete-Guide-v260615.pdf
  pages:
    first: 3
    last: 5
extraction_status: machine-extracted
---

# Stop Asking: What Loop Engineering Really Is

*Stop Asking: What Loop Engineering Really Is*

Another XX Engineering? What's different this time is that it doesn't teach you how to do the work. It tells you to stop doing the work yourself.

## Here we go again

The Prompt Engineering courses are still selling, the ink on Context Engineering isn't dry yet, and I just finished a whole book on Harness Engineering. Now Loop Engineering shows up too.

Over the past year a string of "XX Engineering" terms has popped up, almost keeping pace with model releases. You want to roll your eyes. I get it.

But this one is a little different. It's not about doing the work better. It's about pulling you out of the position of doing the work entirely.

The earlier terms all assumed you were sitting at the keyboard, directing the agent line by line. Loop engineering deletes that assumption. You're no longer inside the loop. You're outside it, building the loop.

## A one-line definition

The person who named the term and wrote it up is Addy Osmani, an engineer on the Google Chrome team. His definition is short, so I'll just give you his words.

> **Original:** Loop engineering is replacing yourself as the person who prompts the agent. You design the system that does it instead.

In plain terms: loop engineering means swapping out "the person who prompts the agent" — from you, to a system. You no longer feed it line by line; you design the system that feeds it for you.

The weight of that sentence is on "replacing yourself." It's not about writing a better prompt, or managing context more precisely. It's about moving you, the person, out of that position.

This is a shift of position. You used to be the engine; now you're the person who designs the engine. What you write is no longer the words for the agent — it's a thing that automatically sends words to the agent.

## Within one week, three people lit the fuse

This term wasn't dreamed up out of nowhere one day. In one week in June 2026, several groups of people ran into the same thing at almost the same time, and only then did it get a name.

What really set it off was a post from Peter Steinberger (the author of OpenClaw) in June. The post shot up past 8 million views.

> **Original:** You shouldn't be prompting coding agents anymore. You should be designing loops that prompt your agents.

You shouldn't be prompting coding agents anymore. You should be designing the loops that prompt your agents.

At almost the same time, Boris Cherny (from Anthropic, the lead on Claude Code) was saying the same thing.

> **Original:** I don't prompt Claude anymore. I have loops running that prompt Claude and figuring out what to do. My job is to write loops.

I don't prompt Claude anymore. I have a bunch of loops running, and they prompt Claude and figure out what to do. My job is to write loops.

The one who actually named it was Addy Osmani, the Google Chrome engineer. On June 7 he wrote it up on his personal blog under the title Loop Engineering, pulling in what Steinberger and Cherny had said, and synced it to Substack the next day. One ignition, one echo, one name — all within a week.

## These three lines are saying the same thing

Stack the three of them together and you'll see they're pointing at the same move.

Cherny says "my job is to write loops." Steinberger says "design the loops." Osmani says "design the system that feeds it for you." The keyword is the same in all three: what you design has shifted from a single behavior of the agent to the entire system that drives the agent.

That's why three people who weren't comparing notes all landed on the same word in one week. It's not a coincidence. They were each doing similar work, and at some point they realized they needed a shared name to talk about it.

Same as vibe coding back then. You can laugh at how crude the term is, but it did turn a way of working into something you could actually discuss. Loop engineering is the same deal.

## From "you prompt the agent" to "you design the system that prompts the agent"

Let me break this shift into the two simplest sentences so it sticks.

The old world: you sit there and prompt the agent line by line. It finishes one thing, stops, and waits for your next line. You're the human clock inside the loop, and every tick has to come from you.

The new world: you design something that ticks on its own, tick after tick. It runs on a timer, spawns little helpers to do the work, and feeds its own results back to itself. You're no longer in the loop. You're outside it, watching it turn.

Addy's next line nails the relationship.

> **Original:** Loop engineering sits one floor above the harness.

Loop engineering sits one floor above the harness. The harness below handles arming a single agent run; the loop above makes it run itself over and over. How to build that floor is the subject of the next chapter.

By now you can probably feel that this isn't just another reskinned buzzword. It marks a change of identity: from the person who operates the agent to the person who schedules the agent.

Your value used to be in "knowing how to direct." Now the directing is taken over by a loop you wrote yourself. Your value moves to "knowing how to build loops, and how to put a check inside the loop that can say no." Why that last part is the hardest thing of all, we'll get to in time.
