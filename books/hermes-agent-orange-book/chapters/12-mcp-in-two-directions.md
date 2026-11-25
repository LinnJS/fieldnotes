---
id: hermes-agent-orange-book/mcp-in-two-directions
resource: hermes-agent-orange-book
title: MCP in Two Directions
part: "Part 4: Connecting Everything"
order: 12
section_label: "§12"
language: en
edition: v260607
source:
  repository: alchaincyf/hermes-agent-orange-book
  revision: b6e53a8e11e00c8b14b2f72d6b4f1ce71fef6692
  path: Hermes-Agent-The-Complete-Guide-v260607.pdf
  pages:
    first: 55
    last: 59
extraction_status: machine-extracted
---

# MCP in Two Directions

*MCP in Two Directions*

Most people understand MCP as a one-way street: you point your own agent at someone else's tools. Hermes makes it two-way—it's both a client that browses an official store and installs plugins with one click, and a server that Claude Code or Cursor can call back into. One protocol, two directions—that's the change most worth talking about these past two months.

## First, let's get straight what "direction" means

MCP is a connection protocol that defines how an agent and an external tool talk to each other. Almost every tutorial covers only one direction: your agent acts as the client, connects to an external MCP server, and pulls in its tools to use.

That's correct, but it's only half the story. A protocol has two ends, and Hermes occupies both.

Here's a more down-to-earth analogy. MCP is like a USB-C port: your computer can plug in a USB drive and read its data (acting as host), and it can also plug into another computer and be read as an external drive itself (acting as device). Hermes is both host and device. It can call external MCP servers, and it can turn itself into an MCP server so other agents can call it.

Direction 1 Hermes as client calls external server ↔ Same MCP protocol ↔ Direction 2 Hermes as server called by other agents

Let's pull these two directions apart, and along the way cover the third thing sandwiched in between— the officially reviewed catalog.

## Direction 1: Hermes as a client calling external servers

This capability has been around since older versions, but the foundation is solid. From the source code, it supports three transports, corresponding to three deployment shapes of a server.

| Transport | Where it runs | Typical scenario |
| --- | --- | --- |
| stdio | Local subprocess | Tools installed locally; spawn a process and talk over standard input/output |
| HTTP (StreamableHTTP) | Remote service | Cloud-hosted MCP, like Linear and other products that bundle their own service |
| SSE | Remote service (streaming) | Long-lived connections where the server needs to keep pushing |

The config lives under `mcp_servers` in `~/.hermes/config.yaml`. Once connected, an external server's tools get registered into Hermes's own tool table, and the model calls them exactly the same way it calls built-in tools. This matters—to the model, "web_search" and some tool from an external MCP look identical; it doesn't need to know where the tool came from.

Per-server, you can also tune the details: timeout, whether this server's tools can run concurrently, whether to send a Bearer auth header, whether to let the server initiate LLM requests back. These are the screws you'd actually turn in a real production environment.

The part that really shows craftsmanship is OAuth. Hermes implements the full MCP OAuth 2.1 handshake: dynamic client registration (DCR), PKCE, and automatic token refresh are all there. This means with a remote MCP that has its own OAuth—like Linear—you install nothing locally; the first time your agent calls it, the authorization flow runs automatically, the token gets fetched, and when it expires it renews itself. It takes the annoying chore of "connecting to an external service that needs a login" and makes it nearly invisible to the user.

## The thing sandwiched in between: from "find it yourself" to "official store"

Hooking up MCP in older versions had a hidden barrier: you had to go find a trustworthy MCP server on GitHub yourself, read its docs yourself, and write the config yourself. Pick the wrong one, configure it wrong, connect to a problematic server—the risk was all yours.

The new version closes this gap with a Nous officially reviewed catalog. It works just like its skill catalog: type `hermes mcp` to enter an interactive picker, choose one, install with one click, fill in the credentials it prompts for during install, and those get written automatically into your local `.env`.

> **"In the catalog = reviewed"**: every MCP that makes it into this official catalog has been merged through PR review. That means Nous has done a trust-screening pass for you, and you no longer have to gamble on whether some unfamiliar GitHub repo is safe.

Here I have to stick to the facts. I've seen material claiming "MCP lets Hermes connect to 6,000-plus apps," but I couldn't find a primary source for that number in the v0.16.0 source code or release notes, so I can't write it that way. The accurate framing is two sentences:

First, on capability: Hermes can connect to any MCP server (all three of stdio/HTTP/SSE work). The README puts it as "Connect any MCP server." In theory it can reach the entire MCP ecosystem.

Second, the officially reviewed catalog currently lists only two:

| MCP in the catalog | Connection method | Notes |
| --- | --- | --- |
| Linear | Remote HTTP + native OAuth 2.1 | Zero local install, `hermes mcp install linear`, authorize and go |
| n8n | stdio bridge (git clone + venv) | Exposes 11 tools, only 8 read-only ones on by default; write operations (activate/deactivate, read container logs, etc.) are trimmed out by default, turn them on as needed |

The default config for n8n is worth a closer look. By default it turns off every tool that changes anything, leaving only the read-only ones; if you want write operations you have to flip them on yourself. This is a "least privilege by default" stance—you get the read capability up front, and you have to explicitly ask for the write capability. That kind of restraint is uncommon in agent tooling.

In the latest version, this catalog has also moved into the browser-based admin panel. You enable/disable right on the web page, no more SSH-ing into the server to edit config.yaml. For people who'd rather not touch the command line, that's a meaningful step.

## Direction 2: Hermes exposing itself as an MCP server

This is the direction most easily overlooked, but the one I find most interesting.

Type one line, `hermes mcp serve`, and Hermes starts a stdio MCP server. Now it's no longer the one calling tools, but the one being called. Tools that are themselves MCP clients—Claude Code, Cursor, Codex—can turn around and use Hermes as an external tool.

What capabilities does it expose? Counting in the source code, there are 10 tools, all centered on the idea of "conversations": list all current conversations, read the message history of a conversation, send a message into a conversation, poll for new events, manage approval requests, plus one tool to list all channels. And these operations are cross-platform—every conversation you've connected on Telegram, Discord, or Lark can be accessed uniformly through this one MCP interface.

In plain terms: from inside Claude Code, you can directly read and reply to your Telegram conversation with Hermes. Hermes becomes a "conversation hub," and other agents that connect in through MCP can operate the whole pile of messaging platforms it manages.

> **核心建议**
>
> There's a fun line in the source comments saying this interface "mirrors OpenClaw's 9-tool MCP bridge," with Hermes adding one extra channel-listing tool to round it out to 10. This is business as usual in open source—you see a good interface shape from a competitor and build one just like it, only more complete. When writing a book, this kind of firsthand detail is far more persuasive than a vague "powerful features."

## When to use MCP, when to use native tools

Having covered both directions, there's a practical question to answer: many external products in Hermes (Spotify, Lark, Home Assistant, and so on) are written directly as native tools, skipping MCP; whereas Linear and n8n go through MCP. They're all about connecting external services—so why are some native and some MCP?

From the trade-offs in the source code, I distilled a rough rule of thumb.

| 推 | 荐 | 不推 | 荐 |
| --- | --- | --- | --- |
| Use MCP: MCP server (Linear comes with its own remote MCP, so just connect to it—why rewrite the whole thing); ② with no upper limit on count, so you can't write native tools one by one; frequently, and it's less hassle to let the server side maintain it. | ① the service already ships an official what you want to connect is "any" third party, ③ the tool set changes | Use native tools: wants to polish deeply for a best-in-class experience (Spotify's seven tools cover playback/devices/playlists and are smoother than an MCP bridge); Hermes internals (Lark docs, for instance, have to work with the memory system); frequently and is latency-sensitive, so you want one fewer layer of MCP protocol overhead. | ① this integration is one Hermes ② it needs tight coupling with ③ it's called |

Bottom line, MCP is the solution for "breadth," native tools are the solution for "depth". To connect to a lot, connect to a mess of things, connect to what others have already built—use MCP. To connect precisely, connect deeply, and control the experience yourself—write a native tool. Hermes keeps both paths open, and I don't think that's fence-sitting; it's playing to each one's strengths against different needs.

There's one more consideration hidden in the progressive tool disclosure from the previous chapter. Connect enough MCPs and dozens or hundreds of tool definitions will blow up the model's context. So Hermes defaults to "expose on demand" for MCP tools—rather than listing them all to the model, it has the model search first, then call. This also explains why not everything should be crammed into MCP: core, high-frequency capabilities are made into resident native tools, while peripheral, long-tail capabilities go through MCP and load on demand. The two mechanisms work together so the context doesn't get eaten alive by tool definitions.

In the next chapter we leave the tool layer and look at another dimension of what Hermes connects: it can now talk to you across more than twenty platforms, and the Gateway that stitches them together is itself something that grows on its own.
