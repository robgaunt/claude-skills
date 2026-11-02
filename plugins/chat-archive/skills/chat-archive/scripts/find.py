#!/usr/bin/env python3
"""Search the claude.ai archive with qmd and print clean, filterable results.

Usage:
  find.py QUERY [--mode query|search|vsearch] [--since YYYY-MM-DD] [--days N]
          [--include-deleted] [-n N] [--archive DIR] [--json]

- --mode query (default): qmd hybrid search (BM25 + vectors + rerank). QUERY should be
  a structured query document you write yourself, one field per line:
    intent: what to find, and what to avoid
    lex: exact terms, names, aliases, rare words
    vec: the idea paraphrased in natural language
    hyde: a description of the conversation that would match
  (In bash: $'intent: ...\\nlex: ...\\nvec: ...\\nhyde: ...'.) A bare sentence falls back
  to qmd's small built-in query expander, which ranks noticeably worse.
- search = keywords only (instant, no models). vsearch = vectors only.
- --since / --days: keep conversations *updated* on/after that date (e.g. --days 60
  for "recent"). Filtering happens here, by joining qmd's hits to catalog.json, because
  qmd 2.8.3 has no metadata filter.
- Conversations deleted on claude.ai are hidden unless --include-deleted.

Runs qmd from the archive dir so its project-local index (.qmd/) is used.
Run with `python3 -I`.
"""
import argparse
import datetime as dt
import json
import os
import re
import subprocess
import sys


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("query")
    ap.add_argument("--mode", choices=["query", "search", "vsearch"], default="query")
    ap.add_argument("--since")
    ap.add_argument("--days", type=int)
    ap.add_argument("--include-deleted", action="store_true")
    ap.add_argument("-n", type=int, default=5)
    ap.add_argument("--archive", default=os.environ.get("CLAUDE_AI_ARCHIVE") or "~/claude-ai-archive",
                    help="archive dir (default: $CLAUDE_AI_ARCHIVE, else ~/claude-ai-archive)")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    archive = os.path.expanduser(a.archive)
    with open(os.path.join(archive, "catalog.json"), encoding="utf-8") as fh:
        by_file = {e["file"]: dict(e, uuid=uid) for uid, e in json.load(fh).items()}
    since = a.since
    if a.days is not None:
        since = (dt.date.today() - dt.timedelta(days=a.days)).isoformat()

    # Over-fetch so filtering still leaves n results.
    fetch = max(a.n * 6, 40) if (since or not a.include_deleted) else a.n
    cmd = ["qmd", a.mode, a.query, "-c", "claude-ai", "--format", "json", "-n", str(fetch)]
    proc = subprocess.run(cmd, cwd=archive, capture_output=True, text=True)
    if proc.returncode != 0:
        sys.exit(f"qmd failed ({proc.returncode}): {proc.stderr.strip()[-500:]}")
    start = proc.stdout.find("[")
    hits = json.loads(proc.stdout[start:]) if start >= 0 else []

    results, seen = [], set()
    for h in hits:
        fname = h.get("file", "").rsplit("/", 1)[-1]
        e = by_file.get(fname)
        if not e or fname in seen:
            continue
        if since and (e.get("updated_at") or "")[:10] < since:
            continue
        if e.get("deleted_upstream") and not a.include_deleted:
            continue
        seen.add(fname)
        snippet = re.sub(r"@@[^@]*@@\s*(\([^)]*\))?", "", h.get("snippet") or "")
        snippet = re.sub(r"(^|\n)\s*(>\s*)+", r"\1", snippet)  # blockquote markers (summaries, thinking)
        if "conversation_id:" in snippet:  # hit landed in the frontmatter
            snippet = ""
        results.append({
            "title": e["title"],
            "updated": (e.get("updated_at") or "")[:10],
            "created": (e.get("created_at") or "")[:10],
            "score": h.get("score"),
            "deleted_upstream": bool(e.get("deleted_upstream")),
            "path": os.path.join(archive, "markdown", fname),
            "link": f"https://claude.ai/chat/{e['uuid']}",
            "snippet": " ".join(snippet.split())[:240],
        })
        if len(results) >= a.n:
            break

    if a.json:
        print(json.dumps(results, indent=1, ensure_ascii=False))
        return
    if not results:
        print("No matches." + (f" (filtered to updated ≥ {since})" if since else ""))
        return
    for r in results:
        flag = "  [deleted on claude.ai]" if r["deleted_upstream"] else ""
        print(f"{r['updated']}  {r['title']}  (score {r['score']}){flag}")
        print(f"    {r['snippet']}")
        print(f"    {r['path']}")
        print(f"    {r['link']}")


if __name__ == "__main__":
    main()
