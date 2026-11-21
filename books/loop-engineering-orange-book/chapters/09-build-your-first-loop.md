---
id: loop-engineering-orange-book/build-your-first-loop
resource: loop-engineering-orange-book
title: Build Your First Loop Today
part: "Part 4 · How You Start"
order: 9
section_label: "§09"
language: en
edition: v260615
source:
  repository: alchaincyf/loop-engineering-orange-book
  revision: "829aa6084cd68680e7f389bbde9dcaebda7a43e6"
  path: Loop-Engineering-The-Complete-Guide-v260615.pdf
  pages:
    first: 32
    last: 35
extraction_status: machine-extracted
---

# Build Your First Loop Today

*Build Your First Loop Today*

After all that theory, this chapter does just one thing: walks you from a single command, layer by layer, to a loop that really runs on its own.

## Don't aim for the finished product

A lot of people hear "loop engineering" and immediately picture Stripe's thousand-plus-PR-a-week pipeline, decide it's way out of reach, and give up.

That's a misunderstanding. Stripe's setup is the endpoint, not the starting point. Your first loop should be so small it barely looks like a system—just a little thing that checks something for you on a timer.

My suggestion is to start with a `/loop` scheduled task. It's a built-in Claude Code command, the lowest barrier there is, and the moment it runs you'll feel "oh, so that's what this is."

## Step one: run a /loop

`/loop` is available after Claude Code v2.1.72, and it does one thing: on a time interval, rerun the same task. It has three forms—pick by need.

> **Three forms:**
>
> `/loop 5m check the deploy`: fixed, once every 5 minutes
>
> `/loop check the deploy`: Claude sets its own pace (between 1 minute and 1 hour)
>
> `/loop`: bare run, executing the built-in maintenance task or whatever you wrote in `.claude/loop.md`

The time units are s/m/h/d, and the minimum cron interval is 1 minute. Two details to keep in mind so you don't trip up.

First, it's session-scoped, and recurring tasks expire after 7 days—not 3, as some tutorials say. Second, it runs on your machine; turn the machine off and it stops. To really run while you sleep, with the machine off, you switch to Cloud Routines or GitHub Actions—more on that later.

## Step two: have it read CI and issues, do triage first

Rerunning one line isn't a loop. You need it to read something and make a judgment. The most basic starting point is a triage task.

You give it a prompt to look at three things every morning: did yesterday's CI fail, what new issues were opened, what did recent commits change. Then it picks out what's worth handling and makes a list.

At this point you already have the two core parts of a loop: a timer-triggered discovery mechanism, plus a triage brain that runs through the information for you. Addy calls this kind of auto-discovery automation.

Addy says it's automation that makes a loop a real loop, rather than just the one time you ran it (his words are in §03). That line names the threshold: scheduled plus auto-discovery is what gets you to loop entry level.

## Step three: add a state file so it has memory

The triage runs—where do the results go? Don't leave them in the chat window; close it and they're gone. Open a markdown file and write every finding, and how far each has been handled, into it.

That file is the loop's memory. Addy puts it vividly: the agent forgets, the repo doesn't. Memory has to land on disk, not just live in the context. With it, work you didn't finish today, the loop can pick back up when it wakes tomorrow.

Don't want bare markdown? A Linear board or an issue list works too—same idea: state has to live outside any single conversation.

## Step four: add an evaluator so it can say no

This step is the most critical in the whole loop, and the easiest to skip.

A loop nobody's watching makes mistakes nobody's watching too. You need to put something inside the loop that can say "no" to it, or it's just nodding at itself over and over.

Claude Code has a ready-made tool for exactly this called `/goal` (available after v2.1.139). It runs until some condition is met, and the one judging whether the condition holds is another model.

§05 broke down this mechanism: the one judging completion is another fresh model, not the one doing the work.

Why must it be a different model? Because the one doing the work is far too quick to praise itself. Finish the code, ask it to rate its own work, and it'll mostly say "looks good" with confidence. Only an evaluator with different instructions, even a different model, can catch the spots where it talked itself into glossing over. The usage is direct, for example:

```text
/goal all tests in test/auth pass and the lint step is clean
```

## Step five: add worktrees so it runs in parallel

With the first four steps built, you already have a single-threaded loop that runs on its own. The last step is letting it do several things at once.

The way is git worktree. Claude Code uses `--worktree` (or `-w`) to open an independent worktree for each background agent, so they don't step on each other.

Two agents writing the same file is as much of a headache as two engineers editing the same line (this is in §04). Isolate them and they can run in parallel without fighting. At this point, your loop has all its vital organs.

## Tool status at a glance (June 2026)

The commands above are all Claude Code's. Codex can do the same things—just different entry points and names. Don't pin the command names on the wrong house. `/loop` and `/goal` are Claude Code's, not Codex's.

| Capability | Claude Code | Codex |
| --- | --- | --- |
| scheduling | `/loop` (background timer worker) | Automations tab (daily/weekly + custom cron) |
| run until condition met | `/goal` | — (via automation rerun + judgment) |
| parallel isolation | `--worktree` / `-w` | dedicated background worktree, results to Triage inbox |
| sub-agents | Subagents / Agent Teams (`.claude/agents/`) | `.codex/agents/` TOML definitions |
| external connections | MCP + Plugins (one-click install) | MCP connector |
| explicit skill invocation | Skills (SKILL.md) | `$skill-name` |
| runs with machine off | Cloud Routines (runs in the cloud) | cloud (planned Codex Jobs) |

The MCP row is worth a word more: it's compatible across both sides. A connector you write on one side can often be moved to the other and used directly. As for Cursor's setup (Background Agents, subagents, Cloud Agents), the capability path is similar, but my details on it are secondhand, so I won't go into it here—if you're going to use it, check its latest changelog yourself.

## First-loop checklist

Before you start, run through these six. Whichever one you're missing, that's where your loop is at risk.

| Element | Ask yourself |
| --- | --- |
| discovery source | what does it read on a timer? (CI / issues / commits / inbox) |
| state file | which disk file holds the cross-round memory? |
| evaluator | is there an independent check that can say "no"? |
| isolation | does each parallel agent get its own worktree? |
| token cap | did you set a spending ceiling? who stops it if it runs off? |
| human review point | which step pauses for you to look, rather than auto-ing all the way through? |

Of these six, the first two decide whether your loop can run; the last four decide whether it gets into trouble once it does. Beginners most often ship with just the first two built, and the result is a loop nobody's watching and nobody can stop, sitting there nodding at itself.

So my closing advice is simple: your first loop—better small, but with that "no"-saying check and the human review point fully installed. As for how to keep it from hollowing you out once it's built, §08 already covered that—go back and flip through it.

This book ends here. Principles, parts, cases, costs—I've said everything there is to say. The rest isn't in the book; it's in your terminal. Go build your first loop now.
