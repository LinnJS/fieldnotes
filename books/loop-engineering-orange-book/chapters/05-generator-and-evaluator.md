---
id: loop-engineering-orange-book/generator-and-evaluator
resource: loop-engineering-orange-book
title: "Generator and Evaluator: Why an AI Can't Grade Its Own Code"
part: "Part 2 · How It Turns"
order: 5
section_label: "§05"
language: en
edition: v260615
source:
  repository: alchaincyf/loop-engineering-orange-book
  revision: "829aa6084cd68680e7f389bbde9dcaebda7a43e6"
  path: Loop-Engineering-The-Complete-Guide-v260615.pdf
  pages:
    first: 17
    last: 20
extraction_status: machine-extracted
---

# Generator and Evaluator: Why an AI Can't Grade Its Own Code

*Generator and Evaluator*

The hardest part of a loop isn't getting the agent to run. It's putting something inside that can say "no." And the agent writing the code is exactly the one least likely to say it.

## It always praises itself

You have an agent finish a chunk of code, then ask it to grade its own work. What does it say?

Anthropic engineer Prithvi Rajasekaran answered this in an official blog post. Building long-running applications, he kept seeing the same thing.

> **Original:** when asked to evaluate work they've produced, agents tend to respond by confidently praising the work—even when, to a human observer, the quality is obviously mediocre.

Ask an agent to evaluate what it produced and it tends to praise it confidently, even when a human can plainly see the quality is mediocre.

This isn't a smarts problem. It's an agent grading its own homework. The context where the code got written is already stuffed with all the reasons it was written that way. When the agent looks at its own code, it doesn't see the result—it sees the chain of self-persuasion that led there.

You and I do this too. You write something, read it back, and it reads smoother every pass. The problem isn't that the writing is good. It's that you already have a version of what it's supposed to be in your head. When you read, you're not seeing the words on the page—you're seeing that version in your head.

Inside a loop, this flaw gets amplified. A loop is valuable because it can run unattended for many rounds. But if every "is this version good enough" gets decided by the agent that just wrote it, then every round it's nodding at itself. The longer it runs, the more self-praise it piles up, and the further it drifts from real quality. A loop without a real check is, at bottom, an agent repeatedly reaching consensus with itself.

## Tuning a skeptic is easier than fixing a modest author

Rajasekaran tried making the generator agent more critical of itself. It didn't work well.

> **Original:** tuning a standalone evaluator to be skeptical turns out to be far more tractable than making a generator critical of its own work.

Tuning a separate evaluator to be skeptical is far easier than getting a generator to critique its own work.

The difference is structural, not a matter of wording. You can't get an author to step outside its own perspective with a "please be stricter." But you can swap in another agent, hand it a completely different set of instructions, and have it look at the code from scratch. It didn't write any of it, so it carries none of the self-persuasion.

This is a counterintuitive result. Our instinct is to fix the prompt: write it meaner, push the generator to find its own faults. But Rajasekaran's experience is that this road gets harder the further you go, and it's far less cost-effective than just spinning up another agent. Self-critique is hard because the thing being critiqued and the critic share one context. Swapping agents is easy because you've used structure to manufacture an outsider.

Rajasekaran is blunt about where the idea comes from. He borrowed it from GANs.

> **Original:** I designed a multi-agent structure with a generator and evaluator agent.

In a generative adversarial network (GAN), one network builds and one network picks faults. The two work against each other, and the builder gets better and better at looking real. Ported to agents, it's a generator that writes and an evaluator that reviews—structurally separating "writing" from "judging whether the writing is good."

This is exactly what the sub-agent cell in Addy's framework from the last chapter was about. Addy puts it less gently (his words are in §04, part five): the model writing code is too easygoing when grading its own homework. Swap in a second agent, a different set of instructions, sometimes even a different model, and it can catch the holes the first agent talked itself into.

## The evaluator should act, not just read

Swapping agents isn't enough on its own. If the evaluator only reads the code, it's still judging "does this code look right," not "does it run right."

Rajasekaran's approach on frontend tasks is worth copying. He hooked the evaluator up to Playwright MCP so it could open the page itself, click buttons, take screenshots, inspect the DOM—use the thing like a real QA person would.

That single move shifts the basis for judgment from "this JSX looks fine to me" to "I clicked the login button, the page navigated, here's the screenshot." An evaluator that acts looks at behavior, not intent.

One nice detail: Addy mentions that when he swaps agents, he sometimes swaps the model too (sometimes a different model). The same model, even with new instructions, often keeps its blind spots right where they were. Swap the base and even the holes it habitually steps around may change. For judgment, the bigger the difference, the more it's worth.

When writing evaluator instructions, practitioners often calibrate toward the worst case. A common phrasing tells the evaluator to assume "this code is broken until proven otherwise." That line isn't an official Anthropic statement—it's something the community figured out by feel. But the direction is right: the evaluator's default stance should be doubt, not trust. The generator already trusts itself plenty. If the evaluator is polite too, the loop is just an agent nodding at itself.

## In a product: /goal puts the evaluator on the stop condition

By now you might feel that generator and evaluator sound like two boxes on an architecture diagram, a little far from your hands. In fact Claude Code already has a command that turns this structure into a product primitive: /goal.

You use /goal by giving an agent a condition and letting it run until the condition is met. For example:

```text
/goal all tests in test/auth pass and the lint step is clean
```

The key is who decides whether it's met. Not the agent doing the work saying "I think that's good enough."

> **Official docs:** After each turn, a small fast model checks whether the condition holds. If not, Claude starts another turn instead of returning control to you. completion is decided by a fresh model rather than the one doing the work.

After each turn, a small fast model checks whether the condition holds. If it doesn't, Claude runs another turn instead of handing control back to you. Whether it's done is decided by a fresh model, not by the one doing the work.

This is the maker-checker principle applied to the stop condition. The agent doing the work is the maker; that fresh model is the checker. It didn't take part in this round, carries no baggage of self-persuasion, and when you ask it "did the tests really pass," all it can do is go look at the test results. Underneath, it's a prompt-based Stop hook that intercepts each turn and refuses to let it through if the check fails.

Maker-checker wasn't invented by AI. When a bank moves a large sum, the person entering it and the person reviewing it have to be two different people. That rule has been around for decades, for exactly the same reason as here: the person who handled it will trust their own work, so the review only means something if someone else does it. What /goal does is, at bottom, stuff that old rule into the agent's loop. Every "I'm done" has to clear a check that isn't its own.

|  | Who decides "done" | Problem / advantage |
| --- | --- | --- |
| agent self-grades | the agent doing the work | carries self-persuasion, tends to praise itself |
| /goal | a fresh small model each turn | no baggage, can only look at objective conditions |

One thing to keep straight. /goal is a Claude Code command name. Codex doesn't have this command; it reaches the same kind of capability through Automations plus agent configuration—same structure, different name. When you write them side by side, don't pin the command name on the wrong door.

And one that's even easier to confuse: don't mistake /loop for this. /loop reruns on a time interval—it's scheduling, a different thing from "run until the condition is met." The next chapter is all about it.

## A loop's floor is its evaluator

Let me wrap this chapter. Building a loop that runs isn't hard. The hard part is giving it a reliable evaluator.

The generator's level decides what a loop can produce. The evaluator's level decides what a loop won't produce. Without the latter, the more cheerfully a loop runs, the more bad code it stacks up, because no one is calling stop.

Separate generation from judgment structurally, tune the evaluator into a skeptic, make it verify by acting rather than just reading, then hand the final say to a fresh model that didn't take part in the work. Those four steps are everything it takes to grow a loop's ability to say "no."

Next chapter we look at three loops that are actually running, and see how this whole thing works while everyone else is asleep.
