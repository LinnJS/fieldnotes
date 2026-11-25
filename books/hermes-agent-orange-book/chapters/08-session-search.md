---
id: hermes-agent-orange-book/session-search
resource: hermes-agent-orange-book
title: "Session Search: Taking Back the Work LLMs Should Not Do"
part: "Part 3: How It Remembers You"
order: 8
section_label: "§08"
language: en
edition: v260607
source:
  repository: alchaincyf/hermes-agent-orange-book
  revision: b6e53a8e11e00c8b14b2f72d6b4f1ce71fef6692
  path: Hermes-Agent-The-Complete-Guide-v260607.pdf
  pages:
    first: 36
    last: 39
extraction_status: machine-extracted
---

# Session Search: Taking Back the Work LLMs Should Not Do

*Session Search: Taking Back the Work LLMs Should Not Do*

Over two months, the biggest change to this memory system wasn't that retrieval got faster. It was that someone yanked out an LLM that never belonged there in the first place. The result: the same job, now free, instant, and incapable of making things up.

## Start with one line from the official notes

There's a line in the v0.15.0 release notes that made me pause when I read it. It said session_search had been rewritten: no LLM, no cost, 4500× faster.

Forty-five hundred times. The moment a number like that shows up, my first instinct is suspicion. In the AI world, most "X times faster" claims are marketing — swap the benchmark and they fall apart. So I went and dug through the source code to see where this 4500× actually came from.

After reading it, I have to admit: this time it's real. But the truth is far more interesting than "4500 times faster."

## Where exactly the old version was slow and expensive

Here's how the old session search worked. You want to find "that conversation last week about the database migration." First it uses SQLite's FTS5 full-text index to pull back a few candidate sessions — that step is plenty fast. Then it did something unnecessary: it called an auxiliary LLM to "summarize" the matched sessions and show them to you.

The whole problem lives in that auxiliary LLM. Every three sessions it summarized took roughly 30 seconds and cost roughly $0.30. Worse: when FTS5 didn't actually pull back the right session, this LLM wouldn't say "not found." It would earnestly invent a passage you never said and hand it to you.

Sit with how twisted this design is. Retrieval already has an exact answer — FTS5 gave it. Which messages matched is sitting right there in the database, crystal clear. And yet it insisted on spending money again, waiting 30 seconds, and having a model that hallucinates "paraphrase" those real messages back to you. You're holding the original text, but you insist on getting someone to recite it for you — and the reciter might misremember.

## What the new version did: it deleted that LLM

The new fix is so plain it's almost boring — return the real messages straight from the database, never touching an LLM at any point.

| 不推 | 荐 | 推 | 荐 |
| --- | --- | --- | --- |
| Old: FTS5 recall three sessions return the "paraphrased version" | → call auxiliary LLM to summarize → ~30s, ~$0.30, can fabricate → | New: FTS5 recall straight from the DB to fabricate | → pull the matched real messages → ~20ms, zero cost, impossible → return the original text |

The source code says it bluntly. The comment block at the top of the session_search tool file spells it out: every mode goes through SQLite's FTS5 index, "No LLM calls anywhere," and every return is a real message from the database.

For a discovery-style query with search, latency dropped from about 90 seconds to about 20 milliseconds; pure paging (scroll) is even faster, around 1 millisecond. The famous 4500× is simply 90 seconds divided by 20 milliseconds — it's the end-to-end latency comparison of this whole tool, not the FTS5 engine itself getting 4500 times faster.

I owe readers an extra word here so the number doesn't mislead you. The retrieval engine is FTS5 from start to finish — not a single line was swapped. The only thing that changed was deleting the slowest, most expensive, most fabrication-prone link in the chain. In essence, this is taking back a job that never should have used an LLM, out of the LLM's hands.

> **A counterintuitive judgment:** a lot of people reflexively assume "add an LLM = smarter = better." But retrieval is a task with a correct answer: a match is a match, a miss is a miss. Wrap a deterministic task in a probabilistic model and you don't get intelligence — you get cost, latency, and hallucination. The most disciplined engineering progress is sometimes subtraction.

## Without LLM summaries, why is this good enough

This was my initial doubt: at least an LLM summary gives you an overview of "what this session was about." Return the raw text and won't a pile of messages just dump in your face?

The clever bit of the new version lives in the discovery shape. In a single call it gives you three things at once: the first few messages of the session (so you know what the thing was originally for), a window of messages around the match point (so you see the key passage), and the last few messages of the session (so you know what conclusion it ended on).

This "bookend" style of grabbing the head and the tail, plus the context window around the match, lets the main model piece together "what this session was about" on its own. The overview the LLM summary was meant to give you can be reconstructed by the main model from a structured head, tail, and match window — no separate LLM bill required. Goal, match, conclusion, all in one grab.

## Four retrieval postures, all inferred from parameters

The release notes mention three modes (discovery/scroll/browse), but digging through the source I found there are actually four. And there's no mode parameter for you to pick. Whatever parameters you pass, it infers what you're trying to do.

| Shape | What you pass | What it gives you | Uses an LLM? |
| --- | --- | --- | --- |
| DISCOVERY (search) | keyword query | FTS5 matches deduped by session, each with an excerpt snippet, a context window around the match, and head/tail bookends | No |
| SCROLL (page) | session id + anchor message id | some messages above and below the anchor (default 5, max 20), no search, no bookends | No |
| READ (read) | only the session id | the whole session (if too long, the first 20 + last 10) | No |
| BROWSE (browse) | nothing | titles, previews, and timestamps of the most recent sessions | No |

This "no mode switch, act on the parameters" design is something I quite admire. One tool carrying four jobs means the least cognitive load for the Agent calling it — no need to figure out which mode you're in first; just pass whatever you happen to have. The READ shape does one extra practical thing: paste a session link into the chat and it can read-only fetch that session across profiles and show it to you. That's the entry point to "cross-identity memory interoperability."

## An Easter egg for Chinese users: dual FTS5 tables

The old book didn't mention this at all, but for Chinese readers it's worth a lot.

FTS5's default tokenizer (unicode61) has a long-standing flaw: it splits Chinese character by character. Search for "大别山项目" and internally it becomes "大 AND 别 AND 山 AND 项 AND 目" — easy to false-match, and unable to hit the exact phrase. Japanese, Korean, and Thai fall into the same pit.

The new version built two FTS5 virtual tables to solve this. One is the default unicode61, serving English; the other is dedicated to CJK, using trigram (three-character overlapping) tokenization, which makes substring matching naturally work for any script.

Non-Chinese query → main table unicode61 · Chinese, each term ≥ 3 chars → trigram table · Chinese, each term \<3 chars → LIKE fallback

The routing logic is confirmed in the source: English goes to the main table, with BM25 ranking and highlighting; Chinese where every term is at least three characters goes to the trigram table; Chinese but with terms too short (like "桂林 OR 漓江" — two-character terms, while trigram needs three characters to match) falls back to LIKE, ordered by time descending. This whole setup runs locally at zero cost, and that's the real answer to "why Hermes's session search works well for Chinese too."

## This last Easter egg is a methodology for everyone

De-LLM-ing really did delete code. But while digging through it, I found the surrounding docs and config hadn't fully caught up, leaving two self-contradictions.

One is in the config example file. The old block of LLM config for "session summarization" is still sitting there untouched — provider, model, timeout, concurrency, all of it. But the new code doesn't read any of it. It's a dead piece of config.

The other is more direct. The feature table in the README still says "FTS5 session search with LLM summarization," while the source comment plainly states "No LLM calls anywhere." One file says it uses an LLM, the other says it never touches one — fighting each other in the same repo.

> **注意**
>
> The README says "with LLM summarization," the source says "zero LLM throughout" — which do you trust? Trust the source. Code is fact that runs; docs are claims that may be stale. This contradiction is itself the best teaching case for "don't trust secondhand interpretations, go read the source."

I pulled this Easter egg out on its own because it points at something more important than session_search itself. AI tools iterate too fast, and documentation forever lags behind the code. The tutorial you read, the "what features it has" someone else relayed — it might be describing how things looked three versions ago. If you really want to know how a tool actually works right now, the only reliable source is the very source code it's currently running.

I'd happily read this section as the book's model of "engineering discipline." It added nothing new — instead it took away a seemingly sophisticated LLM. What it bought was free, instant, hallucination-free, plus native friendliness to Chinese. In the next section we leave memory behind and look at how Hermes splits a whole set of abilities into loadable, shareable Skills.
