# reddit

A Claude Code skill that lets Claude read Reddit threads, subreddit listings and "what does Reddit think about X" questions. Claude Code's WebFetch and the Claude in Chrome extension can't open reddit.com, so the skill has Claude call OpenAI's Codex CLI with live web search and report back what it read, with permalinks and `[UNVERIFIED]` markers for anything it couldn't see directly.

Needs Codex CLI installed and signed in (`codex login`; a free ChatGPT account works). If you use Claude Code's sandbox, it also needs a `sandbox.excludedCommands` entry for `codex *`.

Full setup, usage and limits are in the [repository README](../../README.md#reddit).
