---
id: evaluation-and-testing
title: Evaluation and Testing
references:
  - resource: loop-engineering-orange-book
    chapter: loop-engineering-orange-book/five-moves-of-one-loop
    note: Presents verification as one of five moves, done by a second sub-agent that reviews the first one's fix against the project's skills and tests.
  - resource: loop-engineering-orange-book
    chapter: loop-engineering-orange-book/generator-and-evaluator
    note: Explains why an agent overrates its own work, and why judging should go to a separate evaluator that tests the result by acting on it.
  - resource: loop-engineering-orange-book
    chapter: loop-engineering-orange-book/costs
    note: Describes verification debt, the pile of output nobody has verified, and names an independent evaluator as the guard.
  - resource: loop-engineering-orange-book
    chapter: loop-engineering-orange-book/build-your-first-loop
    note: Shows how to add an evaluator to a first loop with Claude Code's /goal command.
---

# Evaluation and Testing

**Scope (editorial).** Evaluation and testing cover how the output of an agent is judged: who or what does the judging, against which evidence, and what happens when the answer is no. This topic gathers reading on evaluators, verification steps, and the tests an agent's work has to pass.

§05 reports that agents asked to grade their own work tend to praise it. It quotes Anthropic engineer Prithvi Rajasekaran on the remedy: "tuning a standalone evaluator to be skeptical turns out to be far more tractable than making a generator critical of its own work." [cite:loop-engineering-orange-book/generator-and-evaluator@v260615]

§05 says an evaluator should act and not only read. Its example connects the evaluator to Playwright MCP so that it opens the page, clicks buttons, takes screenshots, and inspects the DOM. [cite:loop-engineering-orange-book/generator-and-evaluator@v260615]

§05 closes with four steps: separate generation from judgment, tune the evaluator into a skeptic, make it verify by acting, and give the final say to a fresh model that took no part in the work. [cite:loop-engineering-orange-book/generator-and-evaluator@v260615]

§03 calls verification the step that is easiest to cut corners on. In its example a second sub-agent checks the first one's fix against the project's skills and tests, with different instructions and sometimes a different model. [cite:loop-engineering-orange-book/five-moves-of-one-loop@v260615]

§07 names verification debt, which is the output of a loop that no one has verified yet. It says the problems hide where the tests do not cover, and that the guard is an independent evaluator that is not the agent doing the work. [cite:loop-engineering-orange-book/costs@v260615]

§09 makes the evaluator the fourth step of a first loop. It uses Claude Code's `/goal`, which runs until a condition is met while another model judges whether the condition holds. [cite:loop-engineering-orange-book/build-your-first-loop@v260615]

## Where to read

- [§03 The Five Moves of One Loop](../books/loop-engineering-orange-book/chapters/03-five-moves-of-one-loop.md)
- [§05 Generator and Evaluator: Why an AI Can't Grade Its Own Code](../books/loop-engineering-orange-book/chapters/05-generator-and-evaluator.md)
- [§07 The Costs: Verification Debt, Comprehension Rot, Token Blowout](../books/loop-engineering-orange-book/chapters/07-costs.md)
- [§09 Build Your First Loop Today](../books/loop-engineering-orange-book/chapters/09-build-your-first-loop.md)
