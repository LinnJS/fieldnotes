---
id: hermes-agent-orange-book/limits-of-self-improvement
resource: hermes-agent-orange-book
title: How Far Can a Self-Improving Agent Go
part: "Part 6: Deployment, Security & Boundaries"
order: 21
section_label: "§21"
language: en
edition: v260607
source:
  repository: alchaincyf/hermes-agent-orange-book
  revision: b6e53a8e11e00c8b14b2f72d6b4f1ce71fef6692
  path: Hermes-Agent-The-Complete-Guide-v260607.pdf
  pages:
    first: 99
    last: 103
extraction_status: machine-extracted
---

# How Far Can a Self-Improving Agent Go

*How Far Can a Self-Improving Agent Go*

Writing this far, the whole book has come full circle, back to the question we started with: an Agent that rewrites itself, exactly how much should it be trusted. Two months ago that was an abstract worry. Now I can point at specific lines in the source code and make the case.

## Let's pull out that old yardstick first

Years ago, when Martin Fowler talked about working with AI, he gave us a yardstick with three notches: human in the loop, human on the loop, human out the loop.

In the loop means every step needs your nod, the AI writes a line and you read a line. On the loop means the AI runs on its own while you stand beside it watching the dashboard, ready to pull the plug the moment something looks wrong. Out the loop means you hand off the work, sleep on it, and check the result in the morning, with no idea and no care about what happened in between.

The nice thing about this yardstick is that it doesn't talk about feelings, only position. The question shifts from "should I trust the AI" to "for this specific task, which notch of the loop am I standing on."

In the old book I used this yardstick to talk about Hermes's learning loop, but back then I could only stay at the level of ideas. An Agent that writes its own Skills and rewrites its own Skills, exactly which notch of the loop does it put the human in, that I couldn't quite answer. All I could say was "it should be on the loop."

Two months later, rereading the source, that "should" can come out.

## Three source-level proofs from the Curator

v0.16.0 ships with a thing called the Curator, a real maintainer running in the background that periodically merges, archives, and packages the Skill library the Agent built for itself. This is exactly where "self-improving" most easily sends a chill down your spine: a program rewriting itself while you're not watching.

But go dig into `agent/curator.py` and you'll find every one of its actions is gated by three locks, and those three locks happen to be the engineering definition of "on the loop."

dry-run, report first → never delete, only archive → snapshot before acting, rollback ready

First lock, dry-run preview. `hermes curator run --dry-run` does a pass that only produces a report and touches nothing in the library. Whatever the Agent wants to merge, whatever it wants to archive, it lists for you first, and you decide whether to actually run it after reviewing. The human isn't kicked out of the loop, the human stands on the loop reading the report.

Second lock, never delete, only archive. The file header carries an invariant in plain words: "never auto-delete, only archive; archives are recoverable." Archiving just moves a Skill directory into an `.archive/` folder, restorable at any time. The Agent has no delete permission. The worst it can do is shove things off to the side.

Third lock, snapshot before acting. Every time the Curator is about to actually change the library, it first tars the whole Skill directory into a timestamped tar.gz, including anything previously archived. If it breaks something, one rollback command brings everything back.

And there's a more subtle boundary, which I think is the cleverest stroke in the whole design: provenance. Hermes records "who made you" for every Skill. Hand-written ones, ones installed from the community, ones shipped out of the box, all get a protected mark, and the Curator may not touch a single one of them. The only thing it can move is the part the Agent forked and grew itself.

> **What this means:** the "blast radius" of self-improvement is locked inside the Agent's own backyard. It can mess with the things it grew itself, but it can't touch the ones you wrote by hand and trust. If something goes wrong, the only patch that gets ruined is its own.

Lay all four of these side by side, dry-run, the no-delete blacklist, snapshots, and provenance, and Fowler's abstract yardstick finally gets source-level markings. Hermes clearly picked "on the loop": the Agent runs on its own, but you can watch, intercept, roll back, and draw the boundary of its activity at any time.

## Don't build a wall inside the house, move the whole house into the vault

The learning-loop part covers boundaries. The security chapters are really talking about the other side of the same thing, just with a different object, going from "how the Agent changes itself" to "how the Agent touches the outside world."

There's a line in Hermes's security docs whose attitude runs opposite to most products on the market:

"Against an adversarial LLM, the only security boundary is the operating system."

That line stings. It's essentially saying: all those things inside my process, the approval gate, output redaction, injection scanning, tool allowlists, none of them is a real boundary. They're just heuristics, "guesses running on a string an attacker may have influenced." Counting on them to stop a model dead set on doing damage is structurally impossible.

Most products tell the marketing story the other way around: I've got N layers of AI protection, each one makes you safer. Hermes goes and labels every single one of its own in-process defenses as "not a boundary," then throws the real trust anchor over to the operating system.

| 推荐 | 不推荐 |
| --- | --- |
| Drop the whole Agent process into an OS sandbox (Docker / OpenShell / a remote host) so the filesystem, network, and processes are all constrained by the OS. This is a real boundary. | Pile up approval regexes, redaction rules, and pattern scans inside the Agent process and count on them to block adversarial output. This is just a heuristic, not a wall. |

This kind of honesty comes at a cost. Admitting "the protection inside my process is not a boundary" means voluntarily giving up a very sellable pitch. But it buys something sturdier: you know exactly what's protecting you. Not a pile of regexes that might be bypassed, but a layer of OS-level isolation.

The matching half is the other one: fully auditable end to end. Hermes has a read-only observer contract, and everything the Agent does, every model call, every tool execution, every approval, every sub-agent spawn, comes out as an event stream carrying correlation IDs. Autonomy doesn't mean black box. It runs where you can't see, but every step it ran leaves a trace, and you can fully reconstruct it afterward.

Put these two together and you get Hermes's engineering answer to "how far should you trust a self-improving Agent": don't dig a moat inside the Agent's head, instead drop the whole thing into a transparent box, with walls built by the operating system and glass that lets you see every single move inside.

## Are they growing more alike, or drifting further apart

What's interesting is that the specific practices of this constraint layer are becoming the industry's common knowledge.

Flip through Hermes's 1701-line approval-gate source and the comments openly credit inspiration from Claude Code's dangerous-command rules and from OpenAI Codex's command-detection work. Which shell commands to block, guarding against \`sudo\` reading a password from stdin, the Agent not being allowed to kill its own process, this knowledge of "what to block" is being copied and patched back and forth among the mainstream Agents. The constraint layer is converging.

But the positioning layer is diverging. Over that same stretch, Hermes itself went from twenty thousand stars to over a hundred and eighty thousand, grew a desktop App, grew a Simplified Chinese interface, and started shifting from a geek's command-line toy toward a product you can "send an installer to a friend." Its biggest rival OpenClaw is still ahead in size, but the founder went elsewhere and the project moved into foundation stewardship. The ecosystem has also sprouted a hardcore fork aimed specifically at risk-averse enterprises.

So you see a rather subtle picture: the lower layer, "how to lock the Agent up," is getting more alike, while the upper layer, "who this Agent is for, what it looks like, and how it makes money," is getting more unlike. What converges is engineering common sense, what diverges is product ambition. This is probably what any technology looks like as it moves from its early days toward maturity: the foundation's methods converge, while what gets built on top is up to each builder's own skill.

## The question you can't dodge: open source, therefore trustworthy?

Having gotten this far, there's one question I've kept dodging head-on, and now I can't.

Hermes is MIT open source. Open source often gets treated as a synonym for trust, the code is all right there, anyone can read it, how could you not trust it.

But go look at what's actually behind those hundred and eighty thousand stars and you'll hesitate a bit. A single release is hundreds of commits, with over a hundred people involved, and the PR numbers have already shot past thirty-nine thousand. For a project this big, moving this fast, there's a sizable gap between "the code is public" and "someone has actually read it line by line."

Worse still is the one thing Hermes's own trust model admits out loud: third-party Skills and plugins run arbitrary Python the moment they're imported. They run with full Agent privileges, can read your credentials, can call your tools. The docs spell out the mitigation very clearly, in four words: "review before installing." Translated, that means: before you install, you have to read that Python yourself, don't just go by the self-introduction in its SKILL.md.

This is very honest, honest to the point of being cold. It's essentially saying: open source gives you the right to review, but it doesn't review for you. I built the wall for you, the key to the door is in your hand, you decide who you let in.

I think this is exactly the attitude that deserves to be remembered most about this whole thing. It doesn't fob you off with "we're open source so just trust us." Instead it marks the limits of every defense crystal clear: the approval gate can't catch adversarial output, redaction can be bypassed, injection scanning has misses and false positives. A system willing to point out the holes in its own defenses, of its own accord, is actually a bit more worthy of your trust than one that claims "N layers of protection, absolutely secure."

## Back to the original question

How far can a self-improving Agent go.

After reading two months of source code, my answer isn't a distance, it's a posture.

How far it can go depends on which notch of the loop you're willing to stand on. Hermes has the tools all laid out: want to watch every step, it has dry-run; want to let it run loose, it has snapshots and archiving as a safety net; want to fully let go, it has the OS sandbox and end-to-end auditing holding the line for you. It doesn't pick your position for you, it just makes sure that wherever you stand, the reins are still in your hand.

The reins grow on their own, that was a line from the old book. Two months later I want to add one more: no matter how cleverly the reins grow, the hand holding them had better still be yours.

This is where the book ends. Hermes is still shipping a release every week, and by the time you read this page, it has probably grown some things this book doesn't have. That's fine. A system that evolves on its own is bound to run ahead of any book written about it. What you can do, and what I wrote this book to help you do, isn't to memorize what it looks like today, but to understand the few rules it follows as it evolves, which boundaries it never crosses, which brakes it always keeps.

The rest, I leave to you to raise.
