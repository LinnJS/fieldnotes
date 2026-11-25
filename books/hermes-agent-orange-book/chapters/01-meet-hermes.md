---
id: hermes-agent-orange-book/meet-hermes
resource: hermes-agent-orange-book
title: "Meet Hermes: An Agent That Grows Its Own Skills"
part: "Part 1: What It Is"
order: 1
section_label: "§01"
language: en
edition: v260607
source:
  repository: alchaincyf/hermes-agent-orange-book
  revision: b6e53a8e11e00c8b14b2f72d6b4f1ce71fef6692
  path: Hermes-Agent-The-Complete-Guide-v260607.pdf
  pages:
    first: 4
    last: 7
extraction_status: machine-extracted
---

# Meet Hermes: An Agent That Grows Its Own Skills

*Meet Hermes: The Agent That Grows Its Own Skills*

Let's start by introducing the star of this book. Hermes Agent is an open-source, self-improving AI Agent—it remembers you, writes its own skills out of the experience it accumulates, and keeps working for you in the background while you sleep. Calling it a tool undersells it; it's more like a digital colleague that understands you better the more you use it.

## What can it actually do

Picture the most ordinary scenario. The first time you use it, maybe you just fire off a message on Telegram, or type a command in your terminal, and ask it to write you a scraper script. What it hands back works, but the style might not match yours—how variables get named, how errors get handled, where logs go. It doesn't know you yet, so it falls back on generic conventions.

By the tenth time, though, the picture is completely different. It knows you prefer httpx over requests, knows you like writing logs to a file instead of dumping them to the terminal, knows you hate functions that run too long. Nobody taught it any of this. It learned it from your earlier interactions and wrote it into its own skill library.

That's what makes Hermes special, and here it is in one line: most Agents out there make you fit the harness by hand—writing rules, configuring permissions, curating memory; Hermes ships with the harness already on, and more importantly, that harness grows on its own.

Lay out everything it can do, and it comes to roughly this:

| Capability | What it actually means |
| --- | --- |
| Remembers you | Long-term memory across sessions: who you are, your preferences, where you left off last time—it keeps all of it, so you don't have to explain yourself from scratch every time |
| Writes its own skills | The experience it gains settles into reusable Skills; next time a similar job comes up it just calls them, getting smoother the more you use it |
| Works in the background | It can run scheduled tasks—while you sleep it runs your daily report, watches a code pipeline, keeps an eye on a long-running project |
| Commands a fleet of Agents | A single main Agent can spawn sub-agents to work in parallel, acting as the conductor itself |
| Reachable anywhere | Command line, native desktop App, browser management panel, twenty-some chat platforms—the same it, everywhere |

So rather than call it an "AI assistant," I'd rather call it a digital colleague—a colleague who keeps working for you when you're away, and gets more in sync with you the more you collaborate. What this book sets out to take apart is how this colleague's brain grew, and how it makes itself smarter.

## How does it relate to the ones you already know

You've probably heard a few of these names: Harness, Claude Code, OpenClaw. They sound like the same kind of thing, so let's set up the coordinate system first, before the reading gets muddled.

Harness is a methodology, not a product. If you've read the Harness Engineering orange book, you'll remember it's about how to "build a harness" for an AI Agent: an instruction layer, a constraint layer, a feedback layer, a memory layer, an orchestration layer—five components, a set of ideas. Harness itself isn't a piece of software you can download.

Hermes is the thing that turns that idea into a product. It ships with all five sets of reins already on, so you don't have to configure them one by one. Going further, it turns the harness into infrastructure that grows on its own—this is the most fundamental difference between it and most Agents, and it's the focus of Part Two of this book.

Claude Code and OpenClaw are its peers, but positioned differently. A rough split: Claude Code is interactive coding, where you sit there watching it write code; OpenClaw leans toward "configuration is behavior," where you write up the persona and rules and it runs accordingly; Hermes puts its weight on "autonomous background operation + self-improvement." The three are converging, but their starting points differ.

## By the way, it's gotten almost absurdly popular

Now that we've covered what it is, here's a tangent that's hard to skip: the buzz around this project right now is genuinely high.

Its GitHub stars have already crossed one hundred and eighty thousand. It made Dealroom's list of the fastest-growing open-source Agent frameworks of 2026. Every time you open the repo, the number is still climbing.

> **One number to feel the pace of iteration:** the latest version, v0.16.0, is backed by over eight hundred commits, more than five hundred merged PRs, and over a hundred and seventy contributors. And this is just a minor release. Once an open-source community's flywheel starts spinning, the acceleration is frightening.

I've felt firsthand just how fast it iterates. Two months ago I wrote the first edition of this book, and back then Hermes was still a geek toy that ran in your terminal and was operated remotely over Telegram. Two months and nine versions later, it has grown a native desktop App, a full browser-based management panel, and Simplified Chinese support, with the team calling this version "The Surface Release." In one line: the core hasn't changed, but it went from something only command-line veterans could touch into a product where you send a friend an installer and they double-click to use it.

But let me be clear: fast updates are just the surface, not the point of this book. Every month the AI world has products sprinting ahead; fast on its own isn't interesting. What makes Hermes worth a whole book is the stable core behind that speed—an Agent that builds its own harness, and a harness that grows on its own. We'll get into that bit by bit later.

Let me also place myself here, so you don't think this is something I crammed together by looking things up. These past two years I've poured almost everything into AI Agents and skills: my open-source 女娲.skill now has over twenty thousand stars, huashu-design for design work has sixteen thousand, the self-evolving 达尔文.skill has over three thousand, and the first edition of this book itself racked up over four thousand stars on GitHub. Self-improving Agents and self-evolving skills are what I work on and play with every single day. So I've basically been watching every step Hermes took over these two months, live, on the ground.

## Should you migrate off OpenClaw

If you're currently using OpenClaw, read this section on its own, because it might bear directly on whether you should make a move.

Something big happened with OpenClaw these past two months. Its founder, Peter Steinberger, announced he was joining OpenAI, and the project itself was handed over to a non-profit foundation to steward. By sheer size, OpenClaw is still bigger than Hermes right now—stars are roughly double. But with the soul of the project gone and the project itself folded into a foundation, you can visibly see the community's growth momentum weakening.

And over on the Hermes side, they made a pretty interesting move. They didn't stop at the verbal sparring of "I'm better than OpenClaw"; instead, they rolled out the moving-day carpet right inside the product. There's a command in the source code called `hermes claw migrate`, and the README has a whole section teaching you how to migrate over from OpenClaw: persona settings, memory, user profile, custom skills, command allowlist, per-platform config, API keys—it auto-detects your local OpenClaw directory and moves everything over in one shot.

> **核心建议**
>
> Whether to migrate—my advice is don't rush to a conclusion. Later in this book I'll walk through Hermes's memory, skills, and security mechanisms in depth; deciding whether it's worth migrating after you've read that beats guessing on a whim now. But one thing you can note already: Hermes has already pushed the technical cost of migrating down to almost nothing, and that in itself is a signal.

## What this book takes you to see is the core beneath the face

So this book isn't going to spend too much ink praising how good-looking this new face is. A product going from geek toy to mass-market tool—that story isn't rare.

What's actually worth your time is the core beneath the face—a self-improving Agent that builds its own harness, with a harness that grows on its own. It will remember what kind of person you are, will write new skills out of experience, and will run scheduled tasks while you sleep, like a digital colleague.

Nous Research has an official line that Hermes is "the only Agent with a built-in learning loop." That's their own claim, and when I quote it I have to flag clearly that it's an official self-description, not a neutral conclusion. But the learning loop itself has already gone from an "idea" to a "mechanism" you can point to in the source code—and that part is real.

In the next section, I'll spend sixty seconds drawing you a panoramic picture: this one brain, these many faces—how exactly do they fit together. Once you've seen that picture, every subsystem you read about afterward will have somewhere to hang.
