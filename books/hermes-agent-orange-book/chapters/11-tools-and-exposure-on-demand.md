---
id: hermes-agent-orange-book/tools-and-exposure-on-demand
resource: hermes-agent-orange-book
title: "64 Tools and Exposure on Demand"
part: "Part 4: Connecting Everything"
order: 11
section_label: "§11"
language: en
edition: v260607
source:
  repository: alchaincyf/hermes-agent-orange-book
  revision: b6e53a8e11e00c8b14b2f72d6b4f1ce71fef6692
  path: Hermes-Agent-The-Complete-Guide-v260607.pdf
  pages:
    first: 49
    last: 54
extraction_status: machine-extracted
---

# 64 Tools and Exposure on Demand

*64 Tools and Exposure on Demand*

The README says "40+ tools." I counted 64 in the source. The gap isn't just a difference in how you count—behind it sits a far more interesting design choice: the more tools you have, the less you can afford to dump all of them on the model at once.

## Get the numbers straight first

The old book said Hermes had "40+ tools," which was the official README's public-facing figure. This time I went into the source and used grep to count the registry's registered entries. The tools the model can actually call number 64. If you throw in the spotify set that registers through the plugin path, it's roughly 71.

The numbers don't line up because two concepts got conflated, and we need to pry them apart.

| 推 | 荐 | 不推 | 荐 |
| --- | --- | --- | --- |
| Tool like web_search, terminal, image_generate. There are 64 of these. | : the actual function the model can call. Things | Toolset example, web={web_search, web_extract}. There are about 50 of these. | : an alias that bundles tools into groups. For |

Why split them into two layers? Because "what to expose to the model" and "how to organize by function" are two different things. Tools are the atoms; toolsets are the combo meals. As you'll see, this layering is exactly the foundation for "exposure on demand."

## Five categories: the panorama of 64 tools

Group these 64 tools by function and you can see what Hermes is actually capable of. I read through toolsets.py and the individual tool files, and they sort into five categories.

| Category | Representative tools | Capability |
| --- | --- | --- |
| Execution | terminal, execute_code, read_file, patch, computer_use | Run commands, read and write files, edit code. computer_use drives the desktop in the background without grabbing your mouse |
| Information | web_search, web_extract, browser\_\* (12 of them), x_search | Search the web, scrape content, open a browser. browser is the big one—its sub-tools alone number 12 |
| Media | image_generate, video_generate, video_analyze, text_to_speech | Generate images, generate video, watch video, synthesize speech. Each exposes a single unified entry point |
| Memory and planning | memory, skills_list, todo, cronjob, session_search | Cross-session memory, managing Skills, to-dos, scheduled jobs, digging through history |
| Coordination | delegate_task, mixture_of_agents, kanban\_\* (9 of them) | Dispatch sub-agents, blend multiple models, coordinate a swarm of agents through a Kanban board |

One detail here is worth pulling out. Several of the old book's claims are now out of date. The old book described the coordination category as "at most 3 concurrent sub-agents, at most 3 levels deep." In the source, that limit has been lifted. Concurrency defaults to 3 but you can crank it as high as you like, and the depth cap is gone too. The old book also listed a category of "rl tools"; nowadays the RL environment lives in its own separate directory and doesn't enter the agent's tool surface at all. Citing limits from an old version when writing a book is an easy way to wipe out—this is a pothole I hit while reading the source.

## The point isn't quantity—it's "show up only when needed"

Sixty-four tools. If you stuffed the definitions of all 64 into the system prompt on every turn, what would happen?

The context gets blown out by tool definitions. Before the model even starts working, just reading the tool manuals eats up a big chunk of context. Worse, the more tools there are, the higher the odds the model picks the wrong one.

Hermes's answer is two layers of gating. The first layer is toolset grouping; the second is called progressive tool disclosure. Let's start with the first.

Many tools don't show up unconditionally—they carry a `check_fn` gating function and only enter the model's visible tool list when runtime conditions are met. Let me give a few real examples so you can see how restrained this design is.

> A few examples of check_fn gating: send_message only appears when the gateway is running; the Home Assistant tools only appear if you've configured HASS_TOKEN; computer_use only appears if the desktop driver is installed; the 9 kanban tools only appear when you've been spawned by the Kanban scheduler. Not installed, not configured, not triggered—and the model simply can't see them.

There's also one safety narrowing that I think is cleverly designed. In a webhook scenario—say someone opens a PR or leaves a comment that triggers Hermes—the content may come from an untrusted third party. In that scenario Hermes exposes only the four safest tools (search, extract, view images, ask for clarification), and grants zero local execution privileges. Because the text in a webhook may hide a prompt injection, and if the model gets tricked into running terminal, it's game over. This writes the threat model directly into the tool-exposure rules.

## Progressive tool disclosure: a lesson learned from OpenClaw

The second gating layer is new in v0.16.0. It's called progressive tool disclosure—exposing tools on demand.

Once it's on, MCP tools and non-core plugin tools are no longer listed directly into the tool array the model sees. Instead they're replaced by three bridging tools: tool_search, tool_describe, tool_call. When the model needs something, it searches for what tools exist, looks up how to use one, then calls it. It's like a library switching from "all the books spread out in front of you" to "here's a search desk."

> Model wants to do something tool_search finds available tools

→ →

> tool_describe checks usage tool_call invokes it

→

Two rules here strike me as well-measured. One is that core tools are never deferred—the source puts it bluntly: "Always load means always load. No exceptions." The batch of most-used tools that should stay visible throughout stays visible throughout, no detours. The other is a threshold gate: when the deferrable tools take up less than 10% of context, this whole search mechanism just idles and the tool array is passed through unchanged. Translation: if there aren't many tools, don't bother. The mechanism that saves context must not become a new burden itself.

The most interesting bit is a line in the source comments: this tool catalog is stateless, rebuilt every turn. Why not cache it? Because they explicitly took a lesson from OpenClaw.

| 注意 |
| --- |

> OpenClaw once stepped on a landmine: it cached the tool catalog at the session level, and the cache drifted from the live tool registry, causing tools to silently disappear. The user thought a tool was still there, but the model couldn't see it—and no error was raised. Hermes's comments name and cite this regression bug directly, and choose to rebuild every turn rather than cache, purely to dodge the same pit.

I'm especially fond of this kind of "I watched someone else trip, so I'm walking around this rock" engineering comment. It isn't abstract best practice—it's firsthand experience, learned the hard way. This progressive disclosure is essentially an open-source implementation of Anthropic's "load tools on demand" idea, solving the very real problem of context getting blown out by tool definitions once you've connected too many MCPs.

## Fully pluginized tool delivery: one file, one backend

Having covered "how to expose tools," let's look at "how the tools themselves are delivered." The biggest architectural change in Hermes over these two months is turning external capabilities entirely into plugins.

The four categories—web, browser, image_gen, video_gen—were all broken out into a one-file-one-backend structure under the plugins directory. Want to add a new image-generation provider? Add a folder, no need to fork the main tool. This is what the source calls "four-way architecture alignment": four kinds of external capability sharing the same plugin skeleton.

Image generation makes the point best. You see a single `image_generate` tool, but behind it hang 5 provider directories: fal, krea, openai, openai-codex, xai. Which one gets used is auto-routed by configuration and availability. Video generation works the same way: one `video_generate` entry point, two backends behind it (fal and xai), text-to-video if you give it plain text, image-to-video if you give it text plus an image.

The image-generation models routed in through FAL alone number 12, and it's quite a lineup: FLUX 2 Pro, Nano Banana Pro (a.k.a. Gemini 3 Pro Image), GPT Image 2, Z-Image, and Qwen Image are all in there. The source also carefully splits the size specs into three families, with each model accepting only the parameter keys it supports—rejected keys simply can't get through.

## Krea 2 and xAI: two new members the plugin model brought in

The most direct benefit of going pluginized is that new capabilities come in fast. Two members the old book had nothing on were both wired in over these two months on the back of this skeleton.

One is Krea 2. It has its own native plugin and can also be reached via the FAL path—both routes work. Krea's API is asynchronous: you submit, it returns a task ID, and the plugin polls for the result every 2 seconds, disguising the whole thing as a synchronous call to the outside. The source even ships pricing and speed metadata: Krea 2 Medium produces an image in roughly 15 to 25 seconds, with strengths in expressive styles like illustration, anime, and painting. Wrapping a third-party async API into a synchronous tool is exactly the grunt work the plugin skeleton is supposed to do.

The other is even wilder: xAI. It isn't an ordinary provider—it's a full pipeline spanning login, search, image generation, video generation, and voice.

| Capabilities xAI brings in | What it actually is |
| --- | --- |
| SuperGrok OAuth login | No API key needed—use it straight from your subscription |
| x_search | Search posts and threads on X |
| Web Search provider | A search backend that sits alongside Brave and Tavily |
| grok-imagine image generation | Hooked into the image_gen plugin |
| Grok Imagine video generation | Text-to-video, image-to-video, and reference-image guidance all supported |
| Custom Voices TTS | Speech synthesis plus voice cloning |

I think the xAI line is especially worth chewing on. It's a specimen of "how an open-source agent can wring a closed-source giant's subscription capabilities dry": you subscribe to SuperGrok, and Hermes puts that subscription's search, image generation, video generation, and voice all to use for you—no need to configure a pile of separate API keys.

That said, there's one engineering detail where I have to give Nous its due—they didn't cut corners. x_search's return value adds a `degraded` field: when you add an account or date filter but get no citation sources back, it marks degraded=true, which is its way of telling you "this answer was made up by the model, not pulled from X's index." Baking the question of "is there a real source" into the tool's return value—that kind of honesty is rare.

## What this section is really about

Back to that 64-versus-40 gap from the start. It's actually the whole section's metaphor: the growth in tools is real, but growth itself becomes a burden.

Hermes's answer is: don't equate "lots of capability" with "expose all of it to the model." Toolset grouping, check_fn gating, progressive disclosure, pluginized delivery—string these four things together and they form a single attitude: capability can grow without limit, but what's exposed to the model at any given moment is only the small handful that's genuinely useful here and now. The pit OpenClaw fell into —too many tools dragging down accuracy—Hermes sidesteps with this machinery.

In the next section we look at the other main artery connecting to the outside world: MCP. Hermes plays MCP in two directions, and it's twistier than you'd think.
