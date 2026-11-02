# claude-skills

Skills for [Claude Code](https://claude.com/claude-code), packaged as a plugin marketplace.

| Plugin | What it does |
|---|---|
| [`reddit`](plugins/reddit/skills/reddit/SKILL.md) | Lets Claude read Reddit threads, subreddit listings and "what does Reddit think about X" by handing the fetch to OpenAI Codex CLI |

## Install

In Claude Code:

```
/plugin marketplace add robgaunt/claude-skills
/plugin install reddit@robgaunt-skills
```

Or skip the plugin system and copy the skill by hand:

```
mkdir -p ~/.claude/skills/reddit
curl -fsSL https://raw.githubusercontent.com/robgaunt/claude-skills/main/plugins/reddit/skills/reddit/SKILL.md \
  -o ~/.claude/skills/reddit/SKILL.md
```

---

## reddit

### Why it exists

Claude can't read Reddit itself. Claude Code's WebFetch refuses reddit.com, the Claude in Chrome extension blocks the domain, and plain `curl` gets a 403 or a login redirect. Gemini (web app and CLI) couldn't open threads either when I tested it. OpenAI's browsing tool can, so this skill has Claude call [Codex CLI](https://github.com/openai/codex) with live web search and report back what it read.

### Setup

1. **Install Codex CLI:** `brew install codex` or `npm i -g @openai/codex`.
2. **Sign in:** run `codex login` and choose "Sign in with ChatGPT". A free ChatGPT account works.
3. **Only if you use Claude Code's sandbox:** Codex needs to write to `~/.codex`, so let it run outside the sandbox by adding this to `~/.claude/settings.json`, merged with what's already there:

   ```json
   {
     "sandbox": { "excludedCommands": ["codex *"] },
     "permissions": { "allow": ["Bash(codex *)"] }
   }
   ```

   ⚠️ Excluded commands run **without** sandbox restrictions. The skill always runs Codex with `-s read-only`, which uses Codex's own sandbox, but the entry above allows any `codex` command. Leave it out if you'd rather approve each run yourself.

### Usage

Paste a Reddit link or ask about Reddit and the skill triggers automatically. You can also call it directly:

```
/reddit:reddit https://www.reddit.com/r/ClaudeAI/comments/abc123/some_thread/
/reddit:reddit r/LocalLLaMA top this week
/reddit:reddit what does Reddit think about standing desks?
```

(If you installed it by hand, the command is just `/reddit`.)

### Limits

- **Public content only.** Codex browses as OpenAI, not as you, so your home feed, private subreddits and inbox aren't reachable.
- **No vote counts.** Text, authors and comment threads come through; scores usually don't.
- **Uses your Codex allowance.** OpenAI doesn't publish free-plan limits, and users report a small monthly allowance. A thread costs about 10-15k tokens, mostly fixed per-run overhead, so the skill batches URLs into one run. Check what you have left with `/status` in an interactive `codex` session.
- **Summaries come from another model.** The skill tells Codex to quote closely and mark anything it couldn't see as `[UNVERIFIED]`, but it can still make mistakes. Open the permalink for anything important.

### Terms

This skill reads Reddit through OpenAI's browsing tool, so your use is subject to [OpenAI's terms](https://openai.com/policies/terms-of-use) and [Reddit's User Agreement](https://redditinc.com/policies/user-agreement). Keep it to personal, human-paced reading. It isn't a scraper.

## License

[MIT](LICENSE)
