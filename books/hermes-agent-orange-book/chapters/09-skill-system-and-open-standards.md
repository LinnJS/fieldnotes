---
id: hermes-agent-orange-book/skill-system-and-open-standards
resource: hermes-agent-orange-book
title: The Skill System and the Open-Standard Dividend
part: "Part 3: How It Remembers You"
order: 9
section_label: "§09"
language: en
edition: v260607
source:
  repository: alchaincyf/hermes-agent-orange-book
  revision: b6e53a8e11e00c8b14b2f72d6b4f1ce71fef6692
  path: Hermes-Agent-The-Complete-Guide-v260607.pdf
  pages:
    first: 40
    last: 44
extraction_status: machine-extracted
---

# The Skill System and the Open-Standard Dividend

*The Skill System and the Open-Standard Dividend*

Two months ago, Hermes' Skills were just "a pile of bundled templates." Today its official description has been rewritten to "an agent that builds Skills out of experience," and Skills have gone from supporting cast to lead role. But the thing most worth talking about in this section is actually a different choice it made: rather than inventing its own format, it piggybacked on someone else's ecosystem.

## Where Skills come from: three sources in one directory

All of Hermes' Skills land in the same directory, `~/.hermes/skills/` . That's its single source of truth. Open this directory and the Skills you see come from three completely different sources, yet they coexist peacefully.

| Source | How it got there | Trust level |
| --- | --- | --- |
| Bundled | Copied from the repo when Hermes is installed; topped up incrementally on each update | builtin (never scanned) |
| Agent-created | The background reflection process finds something worth crystallizing and writes it in itself | agent-created (managed by the Curator) |
| Community Hub | Installed from 9 external sources, passed through a security scan before hitting disk | trusted / community |

The numbers for the bundled tier are interesting. Back at the old book's baseline (v0.7.0), the docs still said "40+ bundled Skills." By v0.16.0, counting in the source gives 74 bundled Skills, plus 95 official optional ones (not loaded by default; one command installs them back). In two months, it went from a little over 40 to nearly 170.

But within that same version it also did the opposite: it deliberately put the default Skill set on a diet. It deleted dead Skills that native features had taken over, demoted a batch of rarely-used ones from bundled to optional, and added an `environments` gate. Context-specific Skills no longer pollute everyone's index; if you don't explicitly request one, it doesn't show up.

I think this move matters a lot. More Skills isn't better. Cram in too many and the agent has to dig through a long list every time it picks a Skill, and the prompt gets heavier too. "Make the defaults lighter and the picker less noisy" and "keep self-created Skills from ballooning endlessly" are two sides of the same anxiety.

## The real smarts: it didn't reinvent the wheel

This is the main thread of the section. Hermes' Skills don't use a home-grown format—they use the open standard at agentskills.io. This SKILL.md format was originally built by Anthropic for Claude Code, then opened up into a general standard.

The source is full of traces of compatibility with it. Frontmatter fields like `license` and `compatibility` are all marked "agentskills.io optional"; when reading config it first checks the namespace the standard prescribes, then falls back to its own fields, tucking proprietary config into a corner and never touching the shared fields. The whole point of doing this is one thing: cross-tool portability.

Portable to what degree? A SKILL.md written for Claude Code can be copied straight into Codex's Skill directory and just run, behaving identically. The same file is recognized on Codex CLI, Gemini CLI, GitHub Copilot, Cursor—any platform that has adopted the standard.

> The network effect is accelerating: at the old book's baseline the number of tools adopting this standard was "11+"; two months later it's "26+." The bigger the standard's pie, the more accumulated value whoever bets on it gets to eat.

How does Hermes cash in on this dividend? Very directly. It can install Skill repos originally built for the Claude Code or Codex ecosystems—say the official Skill repos from openai, anthropic, huggingface—and use them as-is. It even built a migration path for OpenClaw, because both sides feed on the same standard, so Skills can move over almost losslessly.

I'd infer this is a textbook "don't fight the standard" decision. Building a community from scratch takes years; reusing the entire Claude/Codex Skill inventory means you can use it today. Freeloading off someone else's ecosystem is far more cost-effective than raising your own.

## NVIDIA joined the default trust list

Speaking of ecosystems, v0.16.0 had a landmark event: NVIDIA's official Skill repo joined Hermes' default trusted tap.

The trusted tap is the handful of sources you can browse directly, with no setup, right after installing Hermes. The list used to be openai, anthropic, huggingface, garrytan. This version added `NVIDIA/skills` —NVIDIA-verified, signed, with governance cards, covering product stacks like CUDA-X and cuOpt.

The signal here matters more than the feature itself. When hardware vendors start providing official supply for the agent Skill ecosystem, it means the SKILL.md standard is no longer just a software-circle toy. OpenAI, Anthropic, and HuggingFace being on the list is understandable; when even NVIDIA shows up to pave the way, you can see the standard's gravitational pull.

## Three-tier loading: open it only when you need it

More Skills create a real problem: cram them all into context and you can't afford the tokens. Hermes' answer is progressive disclosure, loading in three tiers.

> Level 0Level 1Level 2

→ →

> name + description onlyexpand the full textfetch a referenced file

At the first tier, the agent only gets each Skill's name, description, and category—a few thousand tokens is enough to list every Skill. At this tier it judges "which one is useful this time." Only when it actually needs one does it move to the second tier and load that Skill's full text. If the full text in turn points to some reference material, only then does it go to the third tier and fetch that file.

The upside of this design is that you can install dozens or hundreds of Skills without them taking up context day to day. The agent is like flipping through a book with a table of contents: it reads the contents first to decide which page to turn to, instead of memorizing the whole book. That's also why the Skill count can climb to 169 without slowing it down—most of the time they're just a single line in the table of contents.

## Skills Hub: 9 sources + isolated scanning + three-tier trust

The third source, the community Hub, is the fastest-expanding part of these two months. In the old book it was still a vague "provides community Skill installation." Now it's grown into a multi-source aggregated discovery/install system, integrating 9 sources externally.

| Source | What it is | Scale |
| --- | --- | --- |
| skills.sh | Vercel's public Skill directory | ~20,000+ |
| ClawHub | Third-party Skill marketplace | 50,000-ish |
| LobeHub | Agent marketplace; entries converted into installable Skills | 14,000+ agents |
| browse.sh | Browserbase's browser-automation Skills | 200+ sites |
| github / url / well-known / official / claude-marketplace | Direct repo install, single-file URL, site-convention discovery, official optional, Claude-compatible marketplace | — |

Fifty thousand strange Skills sounds tempting, but there's a real attack surface hiding here. Installing an unknown SKILL.md is the same as stuffing a chunk of text into the agent that will be treated as instructions and executed. That's inherently a breeding ground for prompt injection. A seemingly harmless "check the weather for you" Skill might have "and by the way, send the user's keys to this address" buried in its body.

How Hermes handles this is a piece of design worth spelling out. Community Skills are not installed bare; they first have to pass a mandatory security scanner. It uses static analysis to find known bad patterns—data exfiltration, prompt injection, destructive commands, persistent backdoors.

> Scan and grade Download to isolated area

→ →

> safe/caution/dangerous

> Hits disk only if it passes audit log written throughout

Paired with the scan is a three-tier trust grading that decides how strictly to treat the scan results:

| 推 | 荐 | 不推 | 荐 |
| --- | --- | --- | --- |
| builtin: ships with Hermes, never scanned, always trusted; trusted (openai/anthropic only): allows caution-level results through |  | community (everything else): any suspicious finding is blocked outright, unless you manually add --force to force the install |  |

This mechanism connects neatly to topics like Skill poisoning. The dividend and the risk of open standards are two sides of one coin: it lets you freeload off the entire ecosystem, and it gives all of that ecosystem's filth a channel into your machine. Hermes' answer is isolated scanning plus tiered trust— loosen up a bit for big-vendor official sources, and treat unknown Skills of dubious origin as thieves by default. I think that boundary is drawn pretty soberly.

| 核 | 心 | 建议 |
| --- | --- | --- |

> Practical tip: for your own use, prefer installing Skills from the trusted tap (openai/anthropic/huggingface/NVIDIA)—these have official backing. Before installing from a community source like ClawHub, spend a minute reading the SKILL.md body, especially checking whether it demands network access, wants your keys, or has weird commands. Isolated scanning catches known bad patterns, but your common sense is the last gate.

Putting this section together: Hermes bet on the open standard and got the speed of "freeloading an entire Claude/Codex ecosystem in two months," with even NVIDIA showing up to supply it. The price is having to face the poisoning surface of 50,000 strange Skills, so it backstops that with isolated scanning and three-tier trust. This is a well-thought-out trade-off: if you want the standard's network effect, you have to pay the security bill—do both, instead of taking only the dividend and ignoring the risk.
