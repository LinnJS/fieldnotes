---
id: hermes-agent-orange-book/platforms-and-self-growing-gateway
resource: hermes-agent-orange-book
title: "23 Platforms and a Self-Growing Gateway"
part: "Part 4: Connecting Everything"
order: 13
section_label: "§13"
language: en
edition: v260607
source:
  repository: alchaincyf/hermes-agent-orange-book
  revision: b6e53a8e11e00c8b14b2f72d6b4f1ce71fef6692
  path: Hermes-Agent-The-Complete-Guide-v260607.pdf
  pages:
    first: 60
    last: 64
extraction_status: machine-extracted
---

# 23 Platforms and a Self-Growing Gateway

*23 Platforms and a Self-Growing Gateway*

Two months ago, this book said "6 first-tier platforms, one unified Gateway process." The official number is now 23 messaging platforms. But the thing that actually changed isn't the count — it's how you add a new platform. It went from "edit the core code" to "drop a folder into a directory."

## First, that number everyone keeps repeating: 23

From Telegram, Discord, Slack, WhatsApp, Signal, SMS, and email, to DingTalk, Feishu, WeCom, WeChat, QQ, and Tencent Yuanbao, then Microsoft Teams, Google Chat, LINE, Matrix, Home Assistant, and finally the 23rd one, ntfy. Pretty much any mainstream IM you can name, Hermes can use as its "front desk."

Let me take some of the mystique out of that number first. 23 is an official round figure, and the boundary is honestly a bit fuzzy. The official docs even count the browser as one of those 23, while the source code also has IRC, an API Server, and Webhook tucked away as access channels. If you actually count the adapters in the source that can hold a conversation with a person, there are at least 24.

So in this book I'll only commit to the official phrasing, "23 messaging platforms," with one caveat: the source code actually has others like IRC that didn't make the list. Writing it this way neither overstates the case nor gives the people who know the details something to nitpick.

These platforms grew in batches, and the official side gave each one a number ("the Nth platform"), so the timeline is clear.

| Platform | Version added | Official count |
| --- | --- | --- |
| Google Chat | v0.13.0 (2026.5.7) | #20 |
| LINE + SimpleX Chat | v0.14.0 (2026.5.16) | up to 22 |
| Microsoft Teams (end-to-end) | v0.14.0 (2026.5.16) | — |
| ntfy | v0.15.0 (2026.5.28) | #23 |

Five conversational platforms added in two months. Back when the old edition was written, there wasn't even an official "Nth platform" count yet — it just listed 6 first-tier platforms and 9 second-tier extensions. A number ballooning isn't a big deal on its own. What matters is that the cost of that ballooning didn't grow along with it. That's what this section is really about.

## From "edit the core" to "drop in a folder"

In that old edition, adding a platform was a heavy lift. You had to go into the core code and edit a pile of if/elif branches: an incoming message had to be checked for which platform it came from, an outgoing message had to be routed to the right platform, and config parsing, user authorization, and status display each needed a line changed for the new platform. The more platforms there were, the more bloated the core got, and editing one spot risked breaking another.

v0.16.0 does it differently. The core has a registry called `PlatformRegistry` (in `gateway/platform_registry.py`). It's a singleton: whoever wants to add a platform just registers themselves with it. When the Gateway receives a message, it checks the registry first, and only falls back to the old built-in path if it finds nothing there.

New platforms no longer get written into the core; instead they live in the `plugins/platforms/` directory — one folder per platform, each holding a `plugin.yaml` and an `adapter.py`. When the plugin starts up, it calls `ctx.register_platform()` to register itself.

Create a new folder → Write adapter + plugin.yaml → Self-register into the Registry → Not a single line of core code changes

The official docs put it bluntly: the plugin path "requires zero changes to core Hermes code." Adapter creation, config parsing, user authorization, cron delivery, message routing, system prompts, status display, the install wizard — this entire set is taken over automatically by the plugin system.

So what exactly does a platform have to spell out for the Registry? That's the job of the `PlatformEntry` data structure. It turns "everything the Gateway needs to know to recognize a platform" into a declarative list of fields. I'll pick out a few of the interesting ones so you can feel how carefully the designer thought this through.

| Field | The problem it solves |
| --- | --- |
| `max_message_length` | The platform's max length for a single message; anything over it gets smart-chunked automatically |
| `pii_safe` | Whether conversation descriptions need redaction (e.g., don't show SMS phone numbers in plain text) |
| `platform_hint` | Platform guidance injected into the system prompt, e.g., telling the Agent "you're on IRC now, don't use markdown" |
| `standalone_sender_fn` | When a cron job isn't in the same process as the Gateway, spin up a temporary connection to send the message out |
| `apply_yaml_config_fn` | Lets the plugin parse its own config, so the core config.py doesn't have to understand every platform's schema |

Look at that last field and the whole design clicks. The core code deliberately makes itself "dumb" — it intentionally refuses to understand what each platform's config looks like. Understanding it is the plugin's own business. The core only handles "a platform has registered; play by the rules it declared." Each platform's complexity is locked inside its own folder and never seeps into the core.

This line of thinking rhymes with the book's main thread, "the harness grows itself." The Agent's capabilities grow themselves (skill self-improvement), and so does its access layer — one more platform, and the core doesn't move a hair. The Gateway has grown from "one big process with a bunch of platforms baked in" into "a platform host with a registry."

> **A detail:** Discord, Home Assistant, and Mattermost appear in the old built-in enum and also show up under the same names in the new plugins directory. That's not a bug — it's the trail of the historical built-in platforms being migrated to plugins one by one. The new architecture left a compatibility path: if it's not in the registry, fall back to the old route.

## The more platforms you add, the faster it starts

Common sense says more platforms means a slower process start — there's more stuff to bring up. Hermes goes the other way.

The trick is lazy loading. The QQ and Yuanbao adapters are especially heavy: Yuanbao is a reverse-engineered proprietary protocol plus a WebSocket stack, and QQ has to bring up the whole chunked-upload machinery. They used to get eagerly imported on every CLI call, and that one move alone ate about 48 milliseconds and 8MB of memory — even when you weren't using QQ this time.

Now they're loaded only when used. Combine that with v0.14.0 cutting roughly 19 seconds off cold start and v0.15.0 calling 47% fewer functions per conversation, and the Gateway's whole performance story boils down to one rather counterintuitive line: the more platforms you add, the faster it starts.

## "Start on Telegram, continue on Discord" — this line needs fixing

Cross-platform conversation continuity has long been one of Hermes's headline selling points. The old edition just stated the conclusion: you're halfway through a chat on Telegram, switch to Discord, and pick up right where you left off. Sounds like magic.

But I went through the source code, and taken literally, that line will get you into trouble — a reader who knows the details will pick it apart in seconds. I need to explain the real mechanism, or this is an accuracy landmine.

The first layer is session identity. The source code has a function dedicated to generating "a session's unique identity," and it looks like this:

```text
agent:main:{platform}:dm:{chat_id}
agent:main:{platform}:{chat_type}:{chat_id}
```

Notice that this key starts with the platform name. Which means the same person on Telegram and on Discord is, strictly speaking, two different sessions. They don't literally "share one conversation history."

So where does the continuity come from? From another mechanism, called session mirroring in the source code. When a message is sent to a given platform, the system appends a "mirror record" into the target session's conversation log, so the Agent on the receiving side knows what just happened and what was sent.

So what really holds up the "cross-platform continuity" experience is three things layered together.

1. The same Agent, the same memory and Skills

   All 23 platforms share the same Agent instance. Whatever preference you state on any platform goes into the same memory store. Switch platforms, and its understanding of you doesn't reset to zero.

2. Transcript mirroring when messages cross platforms

   As a message flows across platforms, its content gets mirrored into the target session's log, so the Agent on the other side has context and isn't left dumbfounded.

3. The desktop App can reference sessions across profiles

   In the new desktop App you can use `@session` to directly reference another session, stringing conversations from different sources together.

I'm spelling out this layer not to seem rigorous. It's because once you start using it under the assumption that "the same session continues seamlessly," edge cases will leave you confused: why does it sometimes seem to "forget"? Understand the real truth — "shared memory + mirroring" — and you'll know where its capability boundaries actually lie.

> **注意**
>
> While writing this chapter I made a point of listing a few easy traps: don't copy "start on Telegram, continue on Discord" literally; "23" is an official round number, the boundary includes web but not IRC; for a highly volatile figure like GitHub stars, only state the order of magnitude and note the date — don't pin it down. For any outward-facing claim you're unsure of, write conservatively, write the mechanism, but don't write a number you haven't verified.

## What this means

Let me wrap this section. The 23 platforms are the surface; the registry is the substance.

A product willing to design a whole registry mechanism just so "adding a platform doesn't touch the core" is betting that the platform count will keep growing, and growing for a long time. It doesn't want its core to get hacked to pieces at platform #30 or #50. This is a prepayment on the future: write one extra layer of abstraction now, in exchange for countless future "just drop in a folder" conveniences.

For you, the user, the benefit is direct: that niche IM you want to connect — even if the official team never builds it, the community can fill the gap with a single folder, without waiting on the core team's roadmap, and without forking the whole project. The door to access has been thrown wide open.

In the next section we'll look at the other side of the Gateway's evolution. Over these two months it finally grew a face: a native desktop App and a browser-based admin panel. From "a process hiding in the background" into something you can actually click.
