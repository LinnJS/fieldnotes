---
id: hermes-agent-orange-book/operating-system-boundary
resource: hermes-agent-orange-book
title: The Only Boundary Is the Operating System
part: "Part 6: Deployment, Security & Boundaries"
order: 19
section_label: "§19"
language: en
edition: v260607
source:
  repository: alchaincyf/hermes-agent-orange-book
  revision: b6e53a8e11e00c8b14b2f72d6b4f1ce71fef6692
  path: Hermes-Agent-The-Complete-Guide-v260607.pdf
  pages:
    first: 89
    last: 93
extraction_status: machine-extracted
---

# The Only Boundary Is the Operating System

*The Only Boundary Is the Operating System*

Most Agent frameworks are selling you "I have N layers of AI protection." Hermes's security docs do the opposite. They spend three hundred-plus lines making one point: those in-process protections, not a single one is a real boundary. That kind of honesty makes me trust it more than any marketing pitch could.

## Start with a counterintuitive line

The old version of Hermes from two months back had almost nothing on security. I dug through my old research notes, searched for terms like sandbox and approval, and couldn't find a single piece of real content.

By v0.16.0, it had grown a 332-line SECURITY.md. The skeleton of the whole document can be boiled down to one line straight from the official docs:

> Official quote: "The only security boundary against an adversarial LLM is the operating system."

The first time I read that line, I was a little surprised. Agent products on the market are all competing over who has more layers of protection: input filtering, output redaction, dangerous-command detection, tool allowlists, layer stacked on layer, and it all sounds reassuring. Hermes's docs come right out and say it: none of these in-process things constitute real isolation.

Its logic is actually very Feynman. Every character an LLM spits out can be influenced by an attacker through prompt injection. Any scanner you run inside the process to screen that output is, at its core, running heuristic rules over a string the attacker controls. No matter how clever the rules are, they're still heuristics, not a boundary.

## Boundary versus heuristic: you have to pull them apart

This is the single most important distinction in the chapter. Hermes lumps all the in-process security components together as "heuristics," and calls OS-level isolation the "boundary." The two words can't be mixed up.

| In-process What it does Why it isn't a boundary component |
| --- |
| Approval gate Detects common destructive shellThe shell is Turing-complete; blacklisting it commands before execution, pops up ais structurally impossible to make dialog for you to confirmexhaustive |
| OutputStrips strings that look like secrets out of theA motivated output producer can always redactiondisplay layerwork around it |
| Skills Guard Scans a skill awaiting installation forA Skill executes arbitrary Python at import injection patternstime; reading the description won't stop the code |

This distinction has a particularly honest corollary, written into the "Scope" section of the docs: bypassing these heuristics is not a vulnerability. If you figure out how to slip past the approval gate with a regex, or how to fool the redaction, Hermes welcomes you to file an issue, but it won't go through a private disclosure channel or publish a security advisory. Because it never treated these as a boundary in the first place. Getting around something that was never meant to be airtight doesn't count as "breaking through."

Conversely, what does count as a real vulnerability? Escaping declared OS isolation, unauthorized access to external interfaces, credentials leaking that should have been stripped—these touch the real boundary, and only these fall inside the security scope.

| 核 | 心 | 建议 |
| --- | --- | --- |

> I rather admire this attitude. "Out of scope doesn't mean not worth reporting." The approval gate can always catch a few more patterns, redaction can always get smarter, but admitting their ceiling is far more responsible than pretending they're impenetrable.

## So what does a real boundary look like

Since there's no boundary inside the process, the operator has to actively pick an OS-level isolation posture. Hermes offers two paths.

> Terminal backend isolation Whole-process wrapping

or

The first is terminal backend isolation. The shell commands the LLM produces get thrown into a container, remote host, or cloud sandbox to run, and the file read/write tools go through this backend too, unable to reach paths the backend hasn't exposed. It can govern what the agent does through the shell and files, but it can't govern anything the agent does inside its own Python process: the code execution tool, MCP sub-processes, plugin loading, Skill loading—these are all imported into the same interpreter.

So the docs throw in a warning about one specific misunderstanding: "Sandboxing the terminal backend while expecting it to govern non-shell code paths is operating outside the supported security posture." A lot of people fire up Docker and feel safe; this line punctures exactly that illusion.

The second is whole-process wrapping. The entire agent process tree gets thrown into a sandbox, and the shell, code execution, MCP, file tools, plugins, hooks, and Skill loading all fall under the same filesystem and network policy. Hermes ships a Docker image that can do this, and the more hardcore option is wiring up NVIDIA's OpenShell: one sandbox per session, with the filesystem, network egress, syscalls, and inference routing all declaratively controlled, and credentials injected from an external store that never land on the sandbox's filesystem.

By v0.16.0, the sandbox backends had grown from the old version's single local to seven.

| Backend | Isolation | Notes |
| --- | --- | --- |
| local (default) | None, runs directly on the host | But credential stripping as a fallback |
| docker | Container | Ships an image, non-root user |
| singularity | Persistent container | Capability dropping, resource-limit hardening |
| daytona / modal | Cloud sandbox | Resyncs files before each command |
| ssh | Remote host | Credential files synced in on demand |

## The approval gate: 1701 lines of "the single source of truth for dangerous commands"

Even if you've chosen an OS boundary, the most concrete piece of code in the constraint layer is still worth reading line by line. The approval gate is a 1701-line file that, in its comments, calls itself "the single source of truth for the dangerous-command system."

Its order of execution hides the whole design philosophy.

`1` Sandbox backend: pass straight through If you're already inside an OS sandbox like Docker or modal, in-process approval is unnecessary, so it passes straight through. This is fully consistent with the "the only boundary is the OS" stance: once you have a real boundary, the heuristics can step aside.

`2` Hard floor: block unconditionally There's a class of commands with no recovery path: `rm -rf /` , `mkfs` , `dd` writing to a raw device, shutdown/reboot, fork bombs. These get blocked unconditionally, before YOLO mode even takes effect. The comment puts it bluntly: "Turning on YOLO means trusting the agent to touch your files and services, not trusting it to wipe your disk or shut down your machine."

`3` YOLO bypass + pattern detection Once past the hard floor, it's YOLO's turn to let everything through, or else pattern-match command by command with a session approval cache. Roughly 50 regexes, covering disk destruction, privilege abuse, SQL drop-database, remote code execution, sudo escalation, git force-push, and so on.

There's one detail that really shows how "in-process components are untrusted" gets carried down into the implementation. YOLO mode is frozen at module import time, rather than reading the environment variable on every call. The comment explains why: if it read os.environ every time, any Skill inside the process could quietly set this variable and instantly bypass all approvals—a ready-made prompt-injection privilege-escalation path. Freezing it dead at the moment of import shuts that path down.

The approval gate also has a layer of "self-protection" that's specific to agents: it forbids the agent from killing its own gateway process, forbids `docker compose down` , and forbids it from shutting itself off. An agent that can run autonomously has to be guarded against chopping off the hand that manages it.

Going further, a command flagged by a pattern can also be handed to an auxiliary LLM acting as a "security reviewer," which returns allow, deny, or escalate-to-human. There's actually a tension here worth chewing on: using one LLM to judge whether another LLM's output is safe is, internally, a little at odds with the stance that "an LLM's output is a string influenced by the attacker." So when it fails, it always escalates conservatively to a human—it doesn't gamble.

## Credential stripping: hard proof of a real vulnerability

When it comes to the difference between a "real boundary" and a "fake boundary," there's a GHSA security advisory that's the best hard proof.

When Hermes passes environment variables to low-trust in-process components—shell sub-processes, MCP sub-processes, code execution sub-processes—it strips the provider's API key and gateway token by default, letting through only the variables the operator or an already-loaded Skill has explicitly declared. This stripping isn't a hardcoded blacklist; it's dynamically derived by walking through all provider configs.

Why do this? Because there was a real attack path. The source comments record a class of now-fixed vulnerability: a malicious Skill registered `ANTHROPIC_TOKEN` and `OPENAI_API_KEY` as passthrough variables, grabbed those credentials inside the code execution sub-process, and thereby broke through the sandbox's credential wiping. The fix was decisive: provider credentials go on the blacklist, and a Skill cannot override them.

| 注意 |
| --- |

> But the docs honestly note at the same time: credential stripping itself isn't containment either. Any component running inside the agent process can read everything the agent itself can read, including credentials in memory. The only real mitigation is one thing: the operator reviewing the code before installing it. The boundary for third-party Skills and plugins is always "read its Python before you install it," not reading its description file.

## What this approach means

Stringing the above together, Hermes's overall attitude toward security really comes down to one line: don't build a moat inside the process; throw the whole process into an OS sandbox, then expose all behavior to an observability contract so people and tools can audit it after the fact.

This is the opposite road from "constrain the agent with a smarter prompt." The latter sounds more sophisticated, more AI, but it's built on an untrustworthy foundation: you can't use a thing that can be hijacked to constrain itself.

One thing worth mentioning in passing: the approval gate's comments repeatedly cite the names Claude Code and OpenAI Codex, with many dangerous patterns flagging their source directly. The constraint layers of mainstream Agents are converging, and dangerous-command detection is slowly becoming shared industry knowledge. That itself is a signal: everyone's in the same reality, an LLM's output can't be trusted, and real security can only sink down to the OS layer.

In the next chapter we follow this thread deeper: when an agent starts self-improving and running autonomously, does this "the only boundary is the OS" philosophy still hold up, and just how far can it actually go.
