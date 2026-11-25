---
id: hermes-agent-orange-book/three-ways-to-talk
resource: hermes-agent-orange-book
title: Three Ways to Talk to It
part: "Part 4: Connecting Everything"
order: 14
section_label: "§14"
language: en
edition: v260607
source:
  repository: alchaincyf/hermes-agent-orange-book
  revision: b6e53a8e11e00c8b14b2f72d6b4f1ce71fef6692
  path: Hermes-Agent-The-Complete-Guide-v260607.pdf
  pages:
    first: 65
    last: 68
extraction_status: machine-extracted
---

# Three Ways to Talk to It

*Three Ways to Talk to It*

Two months ago, if you wanted to use Hermes, you had to open a terminal first. Today you can send an installer straight to a friend who doesn't write a line of code and have them double-click to run it. This release is officially called The Surface Release, and everything it grew is about giving you a body you can actually touch.

## First, how this section differs from the last one

The last section was about the inside of the Gateway: 23 platforms, the registry, how sessions resume. That's backstage stuff.

This section is about the front of house: where exactly you talk to Hermes from. Same brain, same memory and Skills, but now it has three faces. I call them three postures, and each one is really a different usage habit underneath.

IM platforms → Native desktop app → Browser admin panel

These three faces aren't mutually exclusive. You can write code in the desktop app during the day, keep chatting over Telegram from bed at night, and your wife can tweak a config for you from the browser panel. They all point at the same Agent.

## Posture one: casual chat in IM

This is Hermes' earliest and most iconic posture. Deploy it on a cheap cloud box that stays up 24/7, then fire off messages to it from Telegram, Discord, Lark, or WeChat whenever you feel like it.

I've written this narrative before in the earlier book, so I won't repeat it. The essence is that the Agent lives in the cloud and you can summon it from anywhere. You're on the subway, you remember you need to scrape some data, you pull out your phone and send a message. No need to boot up the laptop, no need to fire up a VPN.

The problem is just as obvious: IM is a chat box. You can talk to it, but you can't conveniently configure it inside a chat box. Changing a platform's API key, turning a tool on, checking what it has remembered about you—doing all that inside a conversation bubble is awkward.

That's exactly what the next two faces are here to solve.

## Posture two: a native desktop app, and it can connect to a remote

The biggest draw of v0.16.0 is a genuine native desktop app. The official line is pretty blunt: this thing "didn't exist a week ago," and it was hammered out in a single week across 100 PRs and 159 commits.

It's an Electron app, one-click installable on macOS, Linux, and Windows, with in-app auto-update. Drag files into the chat, paste images straight from the clipboard, summon the command palette with Cmd+K, switch models inline from the status bar—all the desktop niceties you'd expect.

But the genuinely clever part isn't "they built a client." It's that this client doesn't have to run Hermes locally.

You can point the desktop app on your laptop at a remote Gateway: your own homelab, a hosted box, even a teammate's server. It connects over an encrypted WebSocket, and you log in with OAuth or a username and password.

> **This is "thin client + heavy compute, separated":** the laptop only runs a lightweight GUI, while the heavy Agent—the one that actually eats compute and holds your API key—runs where it belongs. Your MacBook's fan stays quiet; the real work happens on the server.

I think this step is an upgrade on the old book's narrative. The standard move used to be "$5 VPS + Telegram"—a cheap cloud box runs the Agent, your phone is the remote control. Now there's a smoother path: the VPS runs the Gateway, and the desktop app is the decent-looking front end.

Add another layer: each profile can point at a different remote host, you can run sessions from multiple profiles concurrently in one window, and you can even reference another conversation across profiles with `@session`. One laptop hooked up to both your personal box and your work box, with no collisions.

## Posture three: a full-featured admin panel in the browser

The third face is the browser panel. It's grown from that bare-bones "view-only sessions" page of the past into a complete admin backend.

The core value is one sentence: what used to require SSHing into the server to edit config.yaml now takes a few clicks in a web page.

| Panel module | What it does | The old way |
| --- | --- | --- |
| Channels page | Configure every messaging platform (Telegram/Discord/Slack…) from the web | SSH and edit config.yaml |
| MCP catalog | Click to enable/disable each MCP server from the web | Hand-write the mcp_servers config |
| Credentials & Webhooks | Manage keys, create webhooks and hooks | Configure them one by one on the command line |
| Memory & Gateway control | Tune memory config, control the Gateway, one-click Debug Share | Dig through logs, restart by hand |

Login is pluggable too: OIDC or username and password, your call. That means a team can share one Gateway, with each person having their own login and managing their own stuff from the web.

## Worth a mention: ACP, getting it inside your editor

Beyond the three postures there's a fourth entry point, pointed in a somewhat different direction, and it deserves its own mention.

Hermes built an ACP adapter that, via the Agent Client Protocol, lets it plug into VS Code, Zed, and JetBrains as the backend Agent. It doesn't try to take over the editor; it goes to be the swappable Agent behind the editor.

The engineering trade-off on this line is interesting. In the editor scenario, Hermes uses a deliberately trimmed-down toolset called `hermes-acp`, which cuts the IM-only capabilities—sending messages, reading things aloud, popping up clarification bubbles—and keeps only what's relevant to writing code: terminal, file read/write, patching, browser, Skill, memory.

So inside the editor it doesn't text you and doesn't recite poetry; it focuses on writing code. The install is clean too, a one-click `uvx` install with no npm dependencies dragged along. Zed's ACP Registry already lists it, so Zed users can use it with a single click.

> **核心建议**
>
> If you're already on Claude Code or Cursor, you can think of the ACP line like this: Hermes wants to be the "swappable brain" inside your editor. Your editor stays the same, the Agent doing the work behind it becomes Hermes—and that Agent carries the memory and Skills you've accumulated across platforms.

## 16 languages, and a complete Simplified Chinese

The last change is real good news for Chinese readers. On the localization axis, two months ago there was nothing; now there's a catalog of 16 languages.

There's a detail I quite like: the scope of its translation is deliberately kept thin. i18n only translates the high-frequency static copy that Hermes itself outputs: approval prompts, the replies for a handful of slash commands, that kind of thing. Agent-generated content, logs, errors, tool output—all of it stays in English.

Why not translate everything? Because translation drifts, and drift can pollute the Agent's behavioral judgment. Limiting translation to the "interface shell" and never touching the "thinking core" is a restrained and professional decision.

The desktop app goes further, shipping a complete Simplified Chinese UI: chat window, sidebar, settings, command center, cron, platform config, Skills, profiles—the whole interface is translated. The Chinese community contributors are driving it. English is still the default, but Simplified Chinese is now a first-class citizen.

## What this section really changes

Put the three faces together with ACP and Simplified Chinese, and you'll see that Hermes' lower bound of audience has been pulled down a long way.

In the old book, it was for geeks: you had to know the command line, know how to set up a VPS, be able to read English error messages. That bar kept the vast majority of people out.

It's different now. The official line nails it—you used to want to recommend Hermes to a friend, and you'd watch their eyes "slowly glaze over"; now you can just send them the installer and have them double-click to run it.

This isn't a technical upgrade, it's an expansion of the audience. The same self-improving brain that only terminal jockeys could raise before is now something ordinary people can touch too. A book about "how an Agent gets smarter" has to add a line at this section: it's also working hard to become usable by anyone.

In the next part, we'll shift the perspective from "how you use it" to "how it commands others," and look at how one Agent orchestrates a whole crowd of Agents.
