# chat-archive

A Claude Code skill that backs up your claude.ai chat history and makes it searchable. It drives claude.ai's official **Export data** feature in Chrome and waits for the emailed link. Then it downloads every part of the export and merges your conversations into a local Markdown archive, keeping chats you've since deleted on claude.ai. Finally it indexes the archive with [qmd](https://github.com/tobi/qmd) for local keyword and semantic search.

Needs the Claude in Chrome extension (signed in to claude.ai), Python 3, and Chrome's "Ask where to save each file" setting turned off. A Gmail connector lets it pick up the download email by itself, and qmd is needed for search; both are optional.

Full setup, usage and limits are in the [repository README](../../README.md#chat-archive). Tests: `python3 -m unittest discover -s tests -v` from this directory.
