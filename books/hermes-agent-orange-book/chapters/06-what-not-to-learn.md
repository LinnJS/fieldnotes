---
id: hermes-agent-orange-book/what-not-to-learn
resource: hermes-agent-orange-book
title: The Most Important Lesson Is What Not to Learn
part: "Part 2: The Reins Grow Themselves"
order: 6
section_label: "§06"
language: en
edition: v260607
source:
  repository: alchaincyf/hermes-agent-orange-book
  revision: b6e53a8e11e00c8b14b2f72d6b4f1ce71fef6692
  path: Hermes-Agent-The-Complete-Guide-v260607.pdf
  pages:
    first: 27
    last: 30
extraction_status: machine-extracted
---

# The Most Important Lesson Is What Not to Learn

*The Most Important Lesson Is What Not to Learn*

For an agent that evolves on its own, the real danger was never that it fails to learn. It's that once it learns the wrong thing, it'll keep citing a broken rule and refusing itself for months on end. Hermes' review prompt has a dedicated blacklist built precisely to prevent this.

## First, a bug that bites back for months

Picture this scenario. One day you ask Hermes to scrape a web page, and at that exact moment the browser tool throws an error because the environment wasn't set up right. The agent gives it a shot, and fails.

So far, nothing's wrong. The catch is that it has a learning loop (see §04): after each conversation it forks a background sub-agent to do a retrospective, asking itself one question: what did I learn this time, and should it go into a skill?

With no constraint in place, it'll very likely reach a conclusion that looks perfectly reasonable: "The browser tool doesn't work." And then it solemnly writes that line into one of its own skill files.

The trouble starts right there. The environment gets fixed soon enough, the browser tool works fine again, but that rule is still sitting in the skill. So for the next several months, every time you ask it to go online, it cites the line it wrote itself and tells you: the browser tool doesn't work, can't do it.

The comment in the Hermes source code nails this phenomenon, so let me quote it directly (from `agent/background_review.py` ):

> Original: Negative claims about tools or features ('browser tools do not work', 'X tool is broken'). These harden into refusals the agent cites against itself for months after the actual problem was fixed.

"Harden into refusals the agent cites against itself." I find that phrasing remarkably clear-eyed. A system that's supposed to get smarter the more it's used ends up digging itself a long-term pit, precisely because of its ability to learn.

## Why self-improving agents are especially prone to this trap

You have to read this together with what came before. §04 covered how that background-retrospective prompt takes a pretty aggressive stance: by default it should write more rules — "doing nothing is not a neutral outcome, it's a missed learning opportunity."

In other words, Hermes defaults to learning, biased toward writing more rules rather than fewer. That bias is the right one in itself; it maps onto Mitchell Hashimoto's famous habit: every time the agent makes a mistake, add a rule to CLAUDE.md. But once you automate "add a rule on every mistake," a new problem comes to light.

A human mistake and an environment failure look almost identical. Both are "I tried, it failed." Yet the correct response to each is worlds apart.

| 推 | 荐 | 不推 | 荐 |
| --- | --- | --- | --- |
| I got the command arguments wrong fault, worth learning, don't mess it up next time | → that's my | this machine just happens to not have that binary installed environment, not something to learn as a permanent rule | → that's a temporary state of the |

An agent that only knows how to "learn from failure" can't tell these two apart. It treats the second kind as the first, dutifully learning a temporary environment glitch as a permanent self-imposed limit. This is the real second-order risk of self-improvement: it doesn't lie in the ability to learn itself, but in the lack of judgment about whether a given failure even deserves to be remembered.

## The blacklist: spelling out exactly what's off-limits to learn

Hermes' countermeasure isn't complicated, but it's solid: that review prompt includes a dedicated "do not learn" list (again from `background_review.py` ). Before the retrospective sub-agent decides whether to write a skill, it has to run through this blacklist first.

| Blacklist category | Typical examples | Why it can't be learned |
| --- | --- | --- |
| Environment-dependent failures | Missing binary, command not found, credentials not configured | It's the state of this machine right now, not a general rule of the task |
| Negative claims about tools | "The browser tool doesn't work," "X tool is broken" | It hardens into an excuse the agent keeps citing to refuse itself long-term |
| One-off task debris | A specific PR number, a particular error string, today's temporary codename | It only matters for this one thing today; tomorrow it's just noise |

Behind this blacklist sits a plain criterion, which I'll put in everyday terms: if a rule only holds in today's specific context, it shouldn't be written as a permanent rule.

Telling "real knowledge" apart from "temporary state" comes down to exactly this. Getting command arguments wrong is a general rule, worth learning; one particular machine not having a package installed is a temporary state, not worth learning. Before the agent puts pen to paper on a skill, it first has to ask itself: would this rule still hold on a different environment, a different machine? If not, the blacklist stops it cold.

| 注意 |
| --- |

> This insight is something the old book didn't have at all. Two months ago Hermes was still just the idea of "writes memory, builds skills," and back then nobody realized that the real hard part of self-improvement isn't "how to make it learn," but "how to stop it from learning the wrong things." The blacklist is the most mature thing to grow out of these two months.

## If it learns wrong anyway, provenance locks the blast radius

The blacklist is prevention up front. But no rule, however clear-eyed, can stop every misjudgment; some bad skill always slips through and gets written. Beyond this layer, Hermes has a fallback after the fact: lock down, from the very start, how far the damage from any single bad skill can spread.

It relies on the provenance (origin tracking) covered in §05: every skill carries a tag for "who made it" — factory-shipped, community-installed, hand-written by you, or forked and created by the agent itself. Here you only need to remember what that ownership line means for the "what not to learn" question: only skills the agent created itself can be reclaimed by the agent itself.

So even if the blacklist has a slip and some bad rule slips through into an agent-created skill, all it can contaminate is the agent's own little plot of land. Whatever came factory-shipped, whatever you installed from the community Hub, whatever you wrote by hand — all of it stays safe. The source comment puts it bluntly: a skill the user had the foreground agent write belongs to the user, and the Curator is never allowed to touch it.

> Blast radius: a skill the agent writes badly while self-learning will, at worst, contaminate its own little plot. It can't reach the configuration you carefully maintain, can't reach the trusted, security-scanned skills from the community. The cost of self-improvement is strictly fenced into a small, controllable circle.

This layer of design is, I think, where the real craft shows. §05 covered how the Curator never deletes, only archives, and takes a tar.gz snapshot before each run so a whole round can be rolled back. Provenance adds one more layer on top: it simply doesn't let self-improvement's effects spill beyond the agent's own plot. A blacklist up front to stop it from learning the wrong things, provenance after the fact to fence in the blast radius — one before, one after, putting this slightly dangerous-sounding thing called "self-evolution" into a cage that won't spin out of control.

## A self-learning system most needs to learn restraint

Back to the title of this section. We're always hoping the agent learns more, edits more diligently, evolves faster. But this mechanism of Hermes' tells me something counterintuitive: for a system that can modify itself, the boundary of "what it shouldn't learn" determines its floor more than "how much it can learn" does.

The faster a system learns, the deeper the bite-back when it errs. A tool that can't learn fails at most this once; a tool that learns but lacks restraint will harden this one failure into a rule and make itself fail every single time after. Capability and risk are two sides of the same coin.

So Hermes puts a lot of effort into "making it learn," and just as seriously sets three gates to "stop it from learning the wrong things": the blacklist handles before, provenance handles boundaries, the Curator handles reclamation. This kind of clear-headedness earns my trust more than any "gets smarter the more you use it" marketing ever could. Only an agent willing to tell itself plainly "these things are off-limits to learn" is worthy of talking about true self-evolution.

In the next chapter we dig down one more layer, to the foundation that holds all of this up: the three-tier memory system. If the learning loop is the engine, memory is its fuel and its tank.
