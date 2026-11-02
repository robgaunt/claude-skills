# claude-skills

Skills for [Claude Code](https://claude.com/claude-code), packaged as a plugin marketplace.

| Plugin | What it does |
|---|---|
| [`reddit`](plugins/reddit/skills/reddit/SKILL.md) | Lets Claude read Reddit threads, subreddit listings and "what does Reddit think about X" by handing the fetch to OpenAI Codex CLI |
| [`chat-archive`](plugins/chat-archive/skills/chat-archive/SKILL.md) | Backs up your claude.ai chat history with the official export, keeps a local Markdown archive that merges each new export, and searches it with local keyword + semantic search |

## Install

In Claude Code:

```
/plugin marketplace add robgaunt/claude-skills
/plugin install reddit@robgaunt-skills
/plugin install chat-archive@robgaunt-skills
```

Or skip the plugin system and copy a skill by hand:

```
mkdir -p ~/.claude/skills/reddit
curl -fsSL https://raw.githubusercontent.com/robgaunt/claude-skills/main/plugins/reddit/skills/reddit/SKILL.md \
  -o ~/.claude/skills/reddit/SKILL.md

# chat-archive has helper scripts, so copy the whole folder
git clone https://github.com/robgaunt/claude-skills.git /tmp/claude-skills
cp -R /tmp/claude-skills/plugins/chat-archive/skills/chat-archive ~/.claude/skills/
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

## chat-archive

### Why it exists

claude.ai has no API for your own chat history. The official export works, but it's awkward to do by hand:

- You click Export data and wait for an email.
- On a large account the email link downloads a manifest that points to eight separate zips, each with its own link.
- Every link works exactly once.
- Chrome quietly blocks most of those downloads if they come from one tab, and the link is still used up.
- `curl` gets a Cloudflare challenge.

Existing tools pick up only after you have the file, or fetch one conversation at a time through claude.ai's internal API (see [Alternatives](#alternatives)). This skill automates the official route from end to end and keeps the result as an archive you can search. It doesn't build its own search engine; it uses [qmd](https://github.com/tobi/qmd).

### What you get

```
~/claude-ai-archive/
  markdown/            one .md per conversation, plus INDEX.md (newest first)
  catalog.json         id → file, title, dates, deleted_upstream
  exports/<timestamp>/ every part of each raw export, unzipped
  .qmd/                the search index (if you use qmd)
```

- **Each new export is merged in, not used to rebuild the archive:**
  - Only conversations that changed are rewritten.
  - Renamed chats are renamed on disk.
  - Chats you've deleted on claude.ai are kept and flagged `deleted_upstream`.
  - The search index therefore only re-embeds what changed.
- **Edited and regenerated replies** follow the branch claude.ai shows, and the
  alternates sit in collapsed sections.
- **Tool output** (web searches and so on) is cut to a short preview in the Markdown.
  It was three quarters of the text in testing and buried real matches. The full text
  stays in `exports/`.

### Setup

1. **Claude in Chrome**, signed in to claude.ai.
2. **Turn off "Ask where to save each file before downloading"** in `chrome://settings/downloads`. With it on, every download waits on a dialog that Claude can't see.
3. **Optional: a Gmail connector.** With one, Claude can find the download email itself, and keep checking for it every 15 minutes while the session is open. Without one, you paste the link.
4. **Optional, for search: [qmd](https://github.com/tobi/qmd)** (MIT, by Tobi Lütke). Install it with `npm install -g @tobilu/qmd@2.8.3`. It needs Node 22+ and, on macOS, `brew install sqlite`.
   - The first index downloads about 2.3 GB of models from Hugging Face into `~/.cache/qmd/models`.
   - About 9k chunks took around 3 minutes to embed on Apple Silicon.
   - npm 11+ skips the dependencies' install scripts by default, and it works fine that way.
5. **Optional: archive location.** The default is `~/claude-ai-archive`. To use another folder, set `CLAUDE_AI_ARCHIVE` in `~/.claude/settings.json`:
   ```json
   { "env": { "CLAUDE_AI_ARCHIVE": "/Users/you/somewhere/claude-ai-archive" } }
   ```
6. **Only if you use Claude Code's sandbox:**
   - The archive folder must be somewhere the sandbox can write.
   - Two steps run outside the sandbox, so you'll approve them each time: moving the finished downloads to the Trash, and anything in qmd that uses the GPU (`embed`, semantic search). The sandbox blocks Metal, and qmd 2.8.3 has no CPU-only fallback.
   - Keyword search works inside the sandbox.

### Usage

Ask in plain language ("back up my claude.ai chats", "find the conversation where I compared espresso grinders"), or call it directly:

```
/chat-archive:chat-archive request      # ask claude.ai for an export
/chat-archive:chat-archive fetch        # download, merge and index a finished one
/chat-archive:chat-archive search <what you're looking for>
/chat-archive:chat-archive              # does whichever step is due
```

(If you installed it by hand, the command is just `/chat-archive`.)

- **Approval:** before downloading, Claude asks once whether it should download automatically when the email arrives.
- **Cleanup:** after every file is extracted and size-checked, the zips are moved to the Trash, not deleted.
- **Search:** Claude writes the search query itself (intent, keywords, a paraphrase, a description of the ideal match), as qmd's agent guidance recommends. That gave much better results in testing than passing your sentence straight through.
- **Results:** you get the title, date, local file and claude.ai link for each match.

### Limits

- **It depends on claude.ai's current settings page and export format.** Neither is documented; both were tested in November 2026, and either may change. The skill stops and describes what it sees rather than clicking around. If `conversations.json` changes shape, `tests/` shows what the converter expects.
- **Downloads have to go through Chrome,** and automatic checking for the email only runs while the Claude Code session stays open.
- **macOS is the tested platform.** Elsewhere the downloads aren't moved to the Trash.
- **qmd 2.8.3 has no metadata filters,** so the date and deleted-chat filters live in the skill's `find.py` wrapper.
- **The archive holds everything you've said to Claude.** It stays on your machine, and qmd runs locally; the only network traffic it documents is the model download. Keep the folder out of anything synced or shared.

### Alternatives

| Tool | What it covers | What it doesn't |
|---|---|---|
| [daymade/read-claude-web-conversation](https://github.com/daymade/claude-code-skills) | One conversation at a time, read through claude.ai's internal API inside your logged-in Chrome | Bulk export, search, sync; relies on an undocumented API |
| [claude-vault](https://pypi.org/project/claude-vault/) | Converts a downloaded `conversations.json` to Markdown, with sync and Ollama-based semantic search | You download and unzip the export yourself. AGPL license |
| [claude-chroma](https://pypi.org/project/claude-chroma/) | Loads a downloaded `conversations.json` into ChromaDB for semantic search | Same: the export is up to you |

If you'd rather fetch the export yourself, `convert.py` works on its own: pass it the downloaded zips and an archive folder.

## License

[MIT](LICENSE)
