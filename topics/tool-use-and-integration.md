---
id: tool-use-and-integration
title: Tool Use and Integration
references:
  - resource: loop-engineering-orange-book
    chapter: loop-engineering-orange-book/six-parts-of-a-loop
    note: Describes connectors built on MCP as the interface between a loop and outside systems, and skills as reusable project knowledge.
  - resource: loop-engineering-orange-book
    chapter: loop-engineering-orange-book/generator-and-evaluator
    note: Gives the example of an evaluator connected to Playwright MCP so that it can use a page and not only read its code.
  - resource: hermes-agent-orange-book
    chapter: hermes-agent-orange-book/tools-and-exposure-on-demand
    note: Describes how Hermes Agent keeps a large tool set from crowding the model's context, through toolsets, conditional tool exposure, on-demand tool discovery, and plugin-based providers.
  - resource: hermes-agent-orange-book
    chapter: hermes-agent-orange-book/mcp-in-two-directions
    note: Describes Hermes Agent as both an MCP client, with its transports, OAuth, and a reviewed catalog, and an MCP server that other agents call, and when to choose MCP over a native tool.
  - resource: codex-orange-book
    note: Its README lists a chapter on Skills, MCP, Automations, and /goal as the extension layers of Codex.
  - resource: claude-code-orange-book
    note: Its README lists Skills, Hooks, and MCP among its advanced practice chapters.
  - resource: deepseek-harness-orange-book
    note: Its README lists a section on how skills, MCP, and plugins relate in DeepSeek Harness, and a record of the agent building a tool for itself. The book is in Chinese.
  - resource: agent-skills-orange-book
    note: Its README calls it a complete guide to Agent Skills, from installing and using skills to creating them.
  - resource: openclaw-orange-book
    note: Its README lists parts on channel integration with messaging platforms and on the skills system of OpenClaw.
  - resource: claude-code-source-analysis-orange-book
    note: Its README lists a chapter on the tool system of Claude Code.
---

# Tool Use and Integration

**Scope (editorial).** Tool use and integration cover how an agent reaches beyond the model: the tools it can call, the connectors that link it to outside systems, and the packaged extensions that add to what it can do. This topic gathers reading on tool systems, the Model Context Protocol, skills, and plugins.

§04 defines a connector as the interface that hooks a loop to the outside world, such as an issue tracker, a database, a staging API, or Slack, and names MCP as the technical foundation. It quotes the line "A loop that can only see the filesystem is a tiny loop." [cite:loop-engineering-orange-book/six-parts-of-a-loop@v260615]

§04 adds that MCP connectors carry across tools, so that one written on the Codex side can often be used on the Claude Code side as it is. [cite:loop-engineering-orange-book/six-parts-of-a-loop@v260615]

§04 describes a skill as project knowledge made permanent in a SKILL.md file. It says an automation should trigger a named skill and not a pasted block of instructions, because the skill can be updated when the logic changes. [cite:loop-engineering-orange-book/six-parts-of-a-loop@v260615]

§05 gives an evaluator tools of its own. In its example the evaluator is connected to Playwright MCP, so it can open the page, click buttons, take screenshots, and inspect the DOM. [cite:loop-engineering-orange-book/generator-and-evaluator@v260615]

## Where to read

- [§04 Six Parts: What a Loop Is Built From](../books/loop-engineering-orange-book/chapters/04-six-parts-of-a-loop.md)
- [§05 Generator and Evaluator: Why an AI Can't Grade Its Own Code](../books/loop-engineering-orange-book/chapters/05-generator-and-evaluator.md)
- [§11 64 Tools and Exposure on Demand](../books/hermes-agent-orange-book/chapters/11-tools-and-exposure-on-demand.md)
- [§12 MCP in Two Directions](../books/hermes-agent-orange-book/chapters/12-mcp-in-two-directions.md)
- `codex-orange-book`. Run `python3 scripts/resolve.py codex-orange-book` for its official URL.
- `claude-code-orange-book`. Run `python3 scripts/resolve.py claude-code-orange-book` for its official URL.
- `deepseek-harness-orange-book`. Run `python3 scripts/resolve.py deepseek-harness-orange-book` for its official URL.
- `agent-skills-orange-book`. Run `python3 scripts/resolve.py agent-skills-orange-book` for its official URL.
- `openclaw-orange-book`. Run `python3 scripts/resolve.py openclaw-orange-book` for its official URL.
- `claude-code-source-analysis-orange-book`. Run `python3 scripts/resolve.py claude-code-source-analysis-orange-book` for its official URL.
