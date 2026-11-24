---
id: loop-engineering-orange-book/costs
resource: loop-engineering-orange-book
title: "The Costs: Verification Debt, Comprehension Rot, Token Blowout"
part: "Part 3 · Where It Runs, What It Costs"
order: 7
section_label: "§07"
language: en
edition: v260615
source:
  repository: alchaincyf/loop-engineering-orange-book
  revision: "829aa6084cd68680e7f389bbde9dcaebda7a43e6"
  path: Loop-Engineering-The-Complete-Guide-v260615.pdf
  pages:
    first: 25
    last: 28
extraction_status: machine-extracted
---

# The Costs: Verification Debt, Comprehension Rot, Token Blowout

*The Costs*

A loop doing your work for you sounds like all upside. But it's also quietly running up debt on your behalf. This chapter covers four tabs, and none of them clears itself.

## A loop runs itself, and makes mistakes by itself

For several chapters I've been talking about how much a loop can do for you. Here I have to put out the other half. A loop that can run itself is, at the same time, a loop that can make mistakes by itself.

This line from Addy made me stop when I read it.

> **Original:** A loop running unattended is also a loop making mistakes unattended.

A loop running unattended is also a loop making mistakes unattended. The more cheerfully it runs, the more quietly it errs.

The first tab is verification debt. You let the loop open PRs, change code, merge—every step saves you time. But the time you save doesn't come free. It turns into a pile of "not verified by anyone yet" output, sitting there waiting for you to pay it back.

The trouble with this debt is that it doesn't come for you right away. The loop changed twenty files tonight, the tests are all green, the PRs are all open—it looks gorgeous. The problem hides where the tests don't cover, in the gap between "runs" and "right." They lie there quietly, accumulating until some shipping morning when they all blow up at once. You think you saved time; really you just pushed the day of reckoning back.

Why does this debt build up? Because adding an agent is easy, and adding something that can stop an agent is hard. Addy puts this in strong terms.

> **Original:** The hard part of a loop is not the loop. It is putting something inside it that can say no.

The hard part of a loop isn't the loop itself. It's putting something inside that can say "no." A loop without a real check is just an agent nodding at itself over and over.

How do you guard against it? Give the loop an independent evaluator—and that evaluator has to be a different one from the agent doing the work. A second agent, different instructions, ideally a different model, whose job is to pick faults. Letting the code-writing agent grade itself is letting it praise itself. This layer was already laid out earlier in generator and evaluator; verification debt is the bill when it isn't installed right.

## You think you understand this repo—you don't anymore

The second tab is more hidden. Call it comprehension rot.

Every day the loop writes a pile of code you never wrote. The code runs, the tests pass, the PRs merge. On the surface, all normal. But something is slowly going off behind the scenes: your understanding of the project.

> **Original:** The faster the loop ships code you did not write, the bigger the gap between what exists and what you actually get.

The faster the loop ships code you didn't write, the bigger the gap between "what actually exists" and "what you actually understand." Addy adds a line: whether your understanding rots depends on whether you let it rot.

Why does it happen? Because reading code is more boring than writing it, and the loop has taken over all the writing. You're no longer forced to read line by line, so naturally you stop. The codebase grows, but the map in your head is stuck three months ago. The day something goes wrong, you open the file and feel like you're looking at someone else's project.

The most treacherous thing about this gap is that it sounds no alarm in normal times. The project runs fine, and you feel like you understand it well enough. Until a bug burrows into a corner you've never read, the loop can't fix it, and you have to go in yourself. That's when you find out you've become a stranger to your own project. Comprehension rot makes no sound. It only lets you discover, at the exact moment you most need to understand, that the understanding is already gone.

How do you guard against it? Force yourself to read the loop's output regularly; don't just see "tests passed" and merge. Pick a few changes and explain to yourself what they did and why they did it that way. Can't explain it? That's your map needing an update.

## When the loop runs smoothly, you stop bothering to have an opinion

The third tab is the psychological version of the first two. Call it cognitive surrender.

> **Original:** When the loop runs itself its very tempting to stop having an opinion and just take whatever it gives back.

When the loop runs itself, it's very tempting to stop having an opinion and just take whatever it hands back. What this line hits is a state that's especially comfortable and especially dangerous.

Verification debt and comprehension rot are still technical problems. Cognitive surrender is an attitude problem. The first two are "you don't have time for it"; this one is "you don't want to bother anymore." The more reliable the loop, the easier it is to outsource the whole job of judgment.

Why does it happen? Because having an opinion continuously is tiring. Thinking through whether every PR is right is far more tiring than just clicking "merge." The more steadily the loop runs, the more you tend to trust it; the more you trust it, the less you look; the less you look, the less able you are to judge. It's a self-accelerating slope.

How do you guard against it? Hold one line. The loop can execute for you; it can't decide for you. Whatever it hands back, you at least have to be capable of saying "this is wrong." You don't have to change it every time, but the capability has to be there. The day you can't say it, it's not that the loop got smart—it's that you quietly left, and no one's told you yet.

## The bill may be a lot thicker than you think

The last tab is a cold-cash one. Call it token blowout.

The first three are implicit debt; this one is money hitting the bill directly. How much an autonomous loop consumes is hard to estimate accurately in advance.

> **Original:** You absolutely have to be careful about token costs.

You absolutely have to be careful about token costs. Addy flags one key thing: usage swings wildly, depending on whether you're a token-rich person or a token-poor one. The same loop—the rich can afford to run it, the poor might wake up to a blown-up bill.

Why is it unpredictable? Because the loop hatches its own little helpers, retries on its own, and runs round after round on a timer. What you write is logic; what comes out is a count of runs, and the count times the unit price is the money. One bug spins it idle all night, and what you wake up to isn't fixed code —it's an unfamiliar bill.

How do you guard against it? Before you ship, set the loop a few hard caps: per-run budget, daily budget, max retries, and it stops when it hits the ceiling. These numbers aren't about saving money—they're about making sure an idle-spinning bug can't burn through an entire night's quota. Don't wait for the bill to teach you this lesson. Nail the ceiling down with a number first.

## The four tabs together

These four tabs share one trait: none of them sounds an alarm while the loop is running.

| Cost | Symptom | One line to guard against it |
| --- | --- | --- |
| verification debt | output piles up unverified, errors accumulate quietly | install an evaluator that isn't the one doing the work |
| comprehension rot | code grows, the map in your head stalls | read the output regularly; can't explain it means update it |
| cognitive surrender | take whatever the loop gives, can't be bothered to have an opinion | execution can be outsourced, deciding can't |
| token blowout | usage swings wildly, bill unpredictable | nail down budget and retry caps before shipping |

The most fascinating thing about loop engineering is that it lets one person do a team's work. The most dangerous thing is the same spot—a team reviews each other, reminds each other, argues with each other. One person plus a pile of loops easily turns into an echo chamber where no one argues.

These four tabs aren't trying to talk you out of loops. They're a reminder that part of the time you saved has to go toward guarding these four gates for yourself. Next chapter we talk about what guarding the gates actually relies on.
