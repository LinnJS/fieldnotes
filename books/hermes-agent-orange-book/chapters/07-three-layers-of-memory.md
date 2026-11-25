---
id: hermes-agent-orange-book/three-layers-of-memory
resource: hermes-agent-orange-book
title: "Three Layers of Memory: From Goldfish to Old Friend"
part: "Part 3: How It Remembers You"
order: 7
section_label: "§07"
language: en
edition: v260607
source:
  repository: alchaincyf/hermes-agent-orange-book
  revision: b6e53a8e11e00c8b14b2f72d6b4f1ce71fef6692
  path: Hermes-Agent-The-Complete-Guide-v260607.pdf
  pages:
    first: 31
    last: 35
extraction_status: machine-extracted
---

# Three Layers of Memory: From Goldfish to Old Friend

*Three Layers of Memory: From Goldfish to Old Friend*

Most AI tools handle memory by letting the chat log pile up longer and longer, until it no longer fits in the context window. Hermes does memory differently: it distills experience into notes you can keep using indefinitely, and to save you money, what it actually shows the model is still "yesterday's version."

## The Goldfish That Forgets, and the Old Friend Who Remembers

I have a crude test for whether an Agent is any good: use it ten times in a row and see whether it still recognizes you.

Most tools are goldfish, with a seven-second memory. This time you tell it your project uses httpx, not requests, and next time it writes requests for you anyway. It's not being disobedient, it genuinely doesn't remember. Every new session, it's a blank slate.

What Hermes wants to be is the old friend: you don't have to reintroduce yourself every time, it knows who you are, what you're working on, what you can't stand. Pulling that off takes more than "stuffing the history into the context." The longer you talk, the longer the context gets, and in the end you're right back to that goldfish stuffed to death.

The real fix is layering. Split "what was just said," "the stable facts about you," and "how to do a particular thing" into three different kinds of memory, each with its own storage, each minding its own business. That's Hermes' three-layer memory.

| Layer | What it handles | Where it lives | Analogy |
| --- | --- | --- | --- |
| Session memory (episodic) | What was said, and when | SQLite + FTS5 full-text index | A searchable chat log |
| Persistent memory (semantic) | Stable facts about you and your environment | MEMORY.md + USER.md, two files | Sticky notes on your desk |
| Skill memory (procedural) | How to do a specific thing | Markdown under skills/ | A written operating manual |

This section focuses on that middle layer. Session memory gets its own section next, where there's a much better story to tell; Skill memory I already laid the groundwork for back when we covered the learning loop. Persistent memory is the piece that got fleshed out most thoroughly over the past couple of months. The old version brushed it off with a single phrase, "SQLite state," and now it's grown into a rather thoughtful system.

## Two Files, Kept Cleanly Apart

Persistent memory is really just two markdown files, sitting in `~/.hermes/memories/` . One is MEMORY.md, the other USER.md.

Two files isn't about looking tidy. MEMORY.md holds the Agent's own notes: the conventions of this project, the quirks of some tool, the trap it fell into last time. USER.md holds the picture of you: name, role, preferences, the way you talk. One is "things I (the Agent) remember," the other is "my understanding of you."

Both stores have a character budget, and once they're full the Agent has to make trade-offs. MEMORY.md is about 2,200 characters, USER.md about 1,375 characters, together under a thousand Chinese characters. The limit is deliberate. More memory isn't better; a wall plastered with sticky notes is the same as none. Forced to keep only what truly deserves keeping, the Agent stays precise instead.

> One detail: it counts characters, not tokens. The comment in the source says it plainly: character count has nothing to do with the model, and swapping models won't change it. That kind of restraint, refusing to bend to any particular model's tokenizer, is the personality of the whole product.

## Writes to Disk Are Live, What the Model Sees Is Frozen

This is my favorite design choice in persistent memory, and one the old book never mentioned at all.

Start with a contradiction. Memory obviously has to be persistent: whatever you save this turn should hit the disk immediately so it isn't lost. But memory also has to be fed to the model, where it gets packed into the system prompt. Here's the problem: if memory changes halfway through a session, the system prompt changes with it, and then the prefix cache is blown.

The prefix cache is the lifeline for saving money and latency. On every inference, that long, fixed run of prompt at the very beginning (system prompt, tool definitions, memory) can hit the cache directly, with no need to recompute. Change a single character in the middle and the cache is void from that character onward, so every following turn pays again and waits again. Over a long conversation, that bill adds up fast.

Hermes' fix is clever: writes to disk are live, what the model sees is frozen.

> Session startsMid-session writeSystem prompt

→ → →

> memory frozen into a snapshothits disk immediatelystays unchanged

> Next session snapshot refreshed

What it comes down to: the memory you save this turn really is written to disk on the spot, and won't be lost. But it doesn't enter the model's head right away, it waits until the next session begins to be injected as a fresh snapshot. The payoff is that the prefix cache for this whole conversation stays intact.

In the source it keeps two sets of state: one is the frozen snapshot, dedicated to feeding the system prompt; the other is the live entries, which is what tool responses reflect. One is responsible for stability, the other for truth, and they don't step on each other. To me this is the kind of design that only comes out once you've thought it through, not complicated, but the idea is dead on.

## Memory Is an Attack Surface

Once you have persistent memory that carries over across sessions, you've added a headache few others have bothered with: memory itself can be poisoned.

Picture a malicious instruction slipping into some conversation, getting treated by the Agent as a "preference worth remembering," and being stored into MEMORY.md. Because memory enters the system prompt as a frozen snapshot and persists across sessions, that one piece of dirty data can poison an entire later session, or several. That's far more dangerous than a one-off prompt injection: it has staying power.

Hermes' answer is "two security checks at the door":

`1` Scan on write The moment a memory is about to be saved to disk, it first runs through threat-pattern detection, and suspicious content is stopped at the door.

`2` Scan again when loading into the snapshot Any entry that matches a threat gets replaced with a `[BLOCKED: …]` placeholder in the snapshot, so the model never sees the original text; but the live state keeps the original, so you can still inspect it yourself and delete it yourself.

This defense isn't a wheel reinvented by the memory layer alone. The threat patterns come from the same source file, shared with tool-result scanning and context-file scanning. The later chapter on security devotes itself to unpacking this "three chokepoints against injection" system; memory is just one of them, so consider this a bit of foreshadowing.

There's an even plainer safeguard too: if another process (some patch tool, a shell append, a manual edit of yours, or another concurrent session) writes something into MEMORY.md that it can't parse back, the memory tool refuses to write, first backing up the current state into a `.bak` file and prompting you to resolve the conflict first. Better to stop and raise the alarm than silently overwrite your data.

| 核 | 心 | 建议 |
| --- | --- | --- |

> The subtext of this design is: the more powerful memory gets, the more it must be treated as untrustworthy input. An Agent that remembers you forever has to also be an Agent that doubts its own memory. Capability and vigilance grow together.

## Comparing It With Claude Code's auto-memory

By now you might be thinking of Claude Code's memory. It also has a MEMORY.md, read at the start of every session to learn who you are and what you're doing. I use it every day, and the experience really is good. The two are alike, but the underlying mindset isn't quite the same.

| Dimension | Claude Code auto-memory | Hermes persistent memory |
| --- | --- | --- |
| Carrier | A single MEMORY.md (about a 200-line cap) | MEMORY.md + USER.md, two stores, each with its own character budget |
| Facts / profile | Mixed into one file | "About the environment" and "about you" physically separated |
| Write timing | Triggered (you say "remember," or a condition is met) | nudge periodic reminders + grab-and-save before context is lost |
| Cache-friendly | Generally stable within a session | Explicitly frozen snapshot, designed for the prefix cache |
| Anti-injection | Lighter | Scan on write + scan on load + BLOCKED placeholder |

No rush to crown a winner. Claude Code's memory is lighter and handier, because it runs on the desktop you're watching, and if something goes sideways you fix it on the spot. Hermes makes memory this heavy because its setup is a digital colleague living in the cloud, on duty 24 hours with nobody watching. Something nobody is watching has to grow its own immune system. The same MEMORY.md filename, backed by two different deployment realities.

It also has two little behavioral mechanisms. One is called nudge, which every ten turns or so reminds the Agent, "anything worth saving?", so it doesn't get so caught up in the work that it forgets to take notes. The other is called flush, which right before context is about to be lost (the moment of compaction, reset, or exit) gives the Agent one more shot at grabbing and saving memories, but only triggers if this conversation ran long enough (six turns by default), to avoid recording short, content-free chats.

## Beyond the Three Layers, an Optional Fourth

Strictly speaking, memory isn't just three layers. The three are built in: out of the box, zero config, fully local, free. Beyond them, Hermes leaves an optional add-on slot: an external memory provider, doing deeper cross-session user modeling, something like Honcho.

This layer isn't on by default; you have to go into `hermes memory setup` and pick one to install, and you might also need to configure an API key. There are currently eight candidates sitting side by side in the directory, but the hard rule is that only one can be on at a time: more than that gets rejected, to keep a pile of backends from fighting each other and blowing up the tool list.

This arrangement says a lot about Hermes' trade-offs: the basic job of remembering you, it handles for you out of the box, no matter whether you've installed any other services; want fancier user modeling, the door is open, but you have to walk through it yourself.

In the next section we dive into the first layer, session memory. There's a story there I especially want to tell: Hermes took a job that never should have gone to a large model and pulled it back out of the large model's hands, and the result was faster, more accurate, and free.
