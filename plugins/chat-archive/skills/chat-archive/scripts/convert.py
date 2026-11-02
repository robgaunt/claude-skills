#!/usr/bin/env python3
"""Unpack a claude.ai data export and merge its conversations into a Markdown archive.

Usage:
  convert.py [--trash-sources] SOURCE [SOURCE ...] ARCHIVE_DIR

--trash-sources: after every zip has been extracted and size-verified and the merge has
  finished, move the source zips/manifest to ~/.Trash (recoverable; never deleted).

- SOURCE: export zips from claude.ai (conversations-000.zip, frames-000.zip, ...), the
  manifest .json, or a folder. A single folder already under ARCHIVE_DIR/exports/ is
  used in place (handy for re-converting without another copy).
- ARCHIVE_DIR: e.g. ~/claude-ai-archive (always last)

Result:
  ARCHIVE_DIR/exports/<YYYY-MM-DD_HHMMSS>/  raw export (one subfolder per source if several)
  ARCHIVE_DIR/markdown/<date>_<slug>_<id8>.md  one file per conversation, with YAML
                                              frontmatter (qmd.metadata) for filtering
  ARCHIVE_DIR/markdown/INDEX.md             all conversations, newest first
  ARCHIVE_DIR/catalog.json                  uuid -> file/title/dates/deleted_upstream

Merging, not rebuilding: each export contains your full current history, so a file is
rewritten only when its content changes (search indexers then re-embed only those),
renamed when the title changes, and conversations that have disappeared from claude.ai
are kept and marked `deleted_upstream: true`.

Edited/regenerated messages: rendered along the branch claude.ai shows (most recent
child at each fork); alternates go in collapsed <details>. Tool results are trimmed to
a short preview (they're ~75% of the text and drown search); the raw export keeps them.

Run with `python3 -I` so nothing in the working directory is imported.
"""
import datetime as dt
import json
import os
import re
import shutil
import sys
import zipfile

TOOL_PREVIEW_CHARS = 300


def safe_extract(zip_path, dest):
    """Extract a zip, refusing entries that would escape dest."""
    dest_real = os.path.realpath(dest)
    with zipfile.ZipFile(zip_path) as zf:
        for member in zf.infolist():
            target = os.path.realpath(os.path.join(dest, member.filename))
            if not (target == dest_real or target.startswith(dest_real + os.sep)):
                raise SystemExit(f"Refusing unsafe zip entry: {member.filename}")
        zf.extractall(dest)


def find_file(root, name):
    for dirpath, _, files in os.walk(root):
        if name in files:
            return os.path.join(dirpath, name)
    return None


def slugify(text, maxlen=60):
    text = re.sub(r"[^\w\s-]", "", text or "").strip().lower()
    text = re.sub(r"[\s_-]+", "-", text)
    return text[:maxlen].strip("-") or "untitled"


def ymd(stamp):
    digits = re.sub(r"\D", "", (stamp or "")[:10])
    return int(digits) if len(digits) == 8 else 0


def message_text(msg):
    """Render one chat message to Markdown."""
    parts = []
    content = msg.get("content")
    if isinstance(content, list) and content:
        for block in content:
            if not isinstance(block, dict):
                continue
            kind = block.get("type")
            if kind == "text" and block.get("text"):
                parts.append(block["text"])
            elif kind == "thinking" and block.get("thinking"):
                quoted = "\n".join("> " + line for line in block["thinking"].splitlines())
                parts.append("> **Thinking**\n>\n" + quoted)
            elif kind == "tool_use":
                name = block.get("name", "tool")
                payload = block.get("input")
                body = json.dumps(payload, indent=2, ensure_ascii=False) if payload else ""
                parts.append(f"**Tool call: `{name}`**\n\n```json\n{body}\n```" if body else f"**Tool call: `{name}`**")
            elif kind == "tool_result":
                inner = block.get("content")
                if isinstance(inner, list):
                    inner = "\n".join(c.get("text", "") for c in inner if isinstance(c, dict))
                if inner:
                    preview = inner[:TOOL_PREVIEW_CHARS].rstrip()
                    more = f"\n… ({len(inner):,} chars; full text in the raw export)" if len(inner) > TOOL_PREVIEW_CHARS else ""
                    parts.append(f"<details><summary>Tool result</summary>\n\n```\n{preview}{more}\n```\n</details>")
    if not parts and msg.get("text"):
        parts.append(msg["text"])

    for att in msg.get("attachments") or []:
        fname = att.get("file_name") or "attachment"
        extracted = att.get("extracted_content")
        if extracted:
            parts.append(f"<details><summary>Attachment: {fname}</summary>\n\n```\n{extracted}\n```\n</details>")
        else:
            parts.append(f"*Attachment: {fname}*")
    for f in msg.get("files") or []:
        parts.append(f"*File: {f.get('file_name') or 'file'}*")
    return "\n\n".join(parts).strip()


def thread(conv):
    """Return [(message, [alternate messages])] along the branch claude.ai shows."""
    msgs = conv.get("chat_messages") or []
    if not msgs or not any(m.get("parent_message_uuid") for m in msgs):
        return [(m, []) for m in msgs]
    uuids = {m.get("uuid") for m in msgs}
    kids = {}
    for m in msgs:
        parent = m.get("parent_message_uuid")
        kids.setdefault(parent if parent in uuids else None, []).append(m)
    for v in kids.values():
        v.sort(key=lambda m: m.get("created_at") or "")
    out, parent, seen = [], None, set()
    while kids.get(parent):
        siblings = kids[parent]
        chosen = siblings[-1]  # the most recent edit/regeneration is what the UI shows
        if chosen.get("uuid") in seen:
            break
        seen.add(chosen.get("uuid"))
        out.append((chosen, siblings[:-1]))
        parent = chosen.get("uuid")
    return out or [(m, []) for m in msgs]


def who(msg):
    return {"human": "You", "assistant": "Claude"}.get(msg.get("sender"), msg.get("sender") or "?")


def frontmatter(conv, deleted):
    uid = conv.get("uuid") or ""
    return "\n".join([
        "---",
        f"title: {json.dumps(conv.get('name') or 'Untitled', ensure_ascii=False)}",  # JSON string = valid YAML
        f"conversation_id: {uid}",
        f"link: https://claude.ai/chat/{uid}",
        "qmd:",
        "  metadata:",
        f"    created: {ymd(conv.get('created_at'))}",
        f"    updated: {ymd(conv.get('updated_at') or conv.get('created_at'))}",
        f"    messages: {len(conv.get('chat_messages') or [])}",
        f"    deleted_upstream: {'true' if deleted else 'false'}",
        "---",
        "",
    ])


def render_conversation(conv, deleted=False):
    title = conv.get("name") or "Untitled"
    lines = [frontmatter(conv, deleted), f"# {title}", ""]
    meta = [("Created", conv.get("created_at")), ("Updated", conv.get("updated_at")), ("ID", conv.get("uuid"))]
    if conv.get("uuid"):
        meta.append(("Link", f"https://claude.ai/chat/{conv['uuid']}"))
    lines += [f"- **{k}:** {v}" for k, v in meta if v]
    if conv.get("summary"):
        lines += [""] + ["> " + line for line in conv["summary"].splitlines()]
    lines.append("")
    for msg, alternates in thread(conv):
        for alt in alternates:
            lines += ["<details><summary>Alternate version (edited or regenerated)</summary>", "",
                      f"**{who(alt)}**", "", message_text(alt) or "*(empty)*", "", "</details>", ""]
        stamp = msg.get("created_at") or ""
        lines += ["---", "", f"## {who(msg)}" + (f"  \n<sub>{stamp}</sub>" if stamp else ""), ""]
        lines += [message_text(msg) or "*(empty)*", ""]
    return "\n".join(lines)


def write_if_changed(path, text):
    # newline="" on both sides: messages can contain \r\n, and universal-newline
    # translation would make every comparison fail (rewriting the file each run).
    try:
        with open(path, encoding="utf-8", newline="") as fh:
            if fh.read() == text:
                return False
    except FileNotFoundError:
        pass
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="") as fh:
        fh.write(text)
    os.replace(tmp, path)
    return True


def verify_extract(zip_path, dest):
    """Return the zip entries missing from dest or with a different size."""
    bad = []
    with zipfile.ZipFile(zip_path) as zf:
        for i in zf.infolist():
            if i.is_dir():
                continue
            p = os.path.join(dest, i.filename)
            if not os.path.isfile(p) or os.path.getsize(p) != i.file_size:
                bad.append(i.filename)
    return bad


def trash(paths):
    """Move files to the macOS Trash (never delete). Returns the list moved."""
    bin_dir = os.path.expanduser("~/.Trash")
    if not os.path.isdir(bin_dir):
        print(f"No {bin_dir}; leaving sources in place.", file=sys.stderr)
        return []
    moved = []
    for p in paths:
        if not os.path.isfile(p):
            continue
        base, ext = os.path.splitext(os.path.basename(p))
        dest = os.path.join(bin_dir, base + ext)
        if os.path.exists(dest):
            dest = os.path.join(bin_dir, f"{base} {dt.datetime.now():%H%M%S}{ext}")
        shutil.move(p, dest)
        moved.append(p)
    return moved


def unpack(srcs, archive):
    exports = os.path.realpath(os.path.join(archive, "exports"))
    if len(srcs) == 1 and os.path.isdir(srcs[0]) and os.path.realpath(srcs[0]).startswith(exports + os.sep):
        return srcs[0]
    raw_dir = os.path.join(archive, "exports", dt.datetime.now().strftime("%Y-%m-%d_%H%M%S"))
    os.makedirs(raw_dir, exist_ok=True)
    # Large accounts get several batch zips; with more than one source, each goes in
    # its own subfolder named after the file.
    for src in srcs:
        dest = raw_dir
        if len(srcs) > 1:
            dest = os.path.join(raw_dir, re.sub(r"\.(zip|json)$", "", os.path.basename(src.rstrip("/"))))
            os.makedirs(dest, exist_ok=True)
        if os.path.isdir(src):
            shutil.copytree(src, dest, dirs_exist_ok=True)
        elif zipfile.is_zipfile(src):
            safe_extract(src, dest)
            bad = verify_extract(src, dest)
            if bad:
                raise SystemExit(f"Extraction of {src} incomplete ({len(bad)} entries, e.g. {bad[:3]}); sources left in place.")
        elif src.endswith(".json"):
            shutil.copy2(src, dest)  # e.g. the manifest
        else:
            raise SystemExit(f"Not a zip, directory or json: {src}")
    return raw_dir


def main():
    args = sys.argv[1:]
    trash_sources = "--trash-sources" in args
    args = [a for a in args if a != "--trash-sources"]
    if len(args) < 2:
        raise SystemExit(__doc__)
    srcs = [os.path.expanduser(s) for s in args[:-1]]
    archive = os.path.expanduser(args[-1])
    os.makedirs(archive, exist_ok=True)
    raw_dir = unpack(srcs, archive)

    conv_path = find_file(raw_dir, "conversations.json")
    if not conv_path:
        raise SystemExit(f"No conversations.json found in {raw_dir}. Contents: {os.listdir(raw_dir)}")
    with open(conv_path, encoding="utf-8") as fh:
        conversations = json.load(fh)
    if isinstance(conversations, dict):  # tolerate {"conversations": [...]}
        conversations = conversations.get("conversations", [])
    if not conversations:
        raise SystemExit("conversations.json is empty; refusing to mark the whole archive as deleted.")

    md_dir = os.path.join(archive, "markdown")
    catalog_path = os.path.join(archive, "catalog.json")
    catalog = {}
    if os.path.exists(catalog_path):
        with open(catalog_path, encoding="utf-8") as fh:
            catalog = json.load(fh)
    elif os.path.isdir(md_dir):
        # Pre-catalog markdown (older converter, no frontmatter): regenerate from scratch.
        shutil.rmtree(md_dir)
    os.makedirs(md_dir, exist_ok=True)

    counts = dict(new=0, updated=0, unchanged=0, renamed=0, newly_deleted_upstream=0)
    seen = set()
    taken = {v["file"] for v in catalog.values()}
    for conv in conversations:
        uid = conv.get("uuid")
        if not uid:
            continue
        seen.add(uid)
        prev = catalog.get(uid)
        created = (conv.get("created_at") or "")[:10] or "unknown-date"
        fname = f"{created}_{slugify(conv.get('name'))}_{uid[:8]}.md"
        if prev and prev["file"] != fname:
            if fname in taken:  # extremely unlikely: same date+slug+id8
                fname = fname[:-3] + f"_{uid[8:13]}.md"
            old = os.path.join(md_dir, prev["file"])
            if os.path.exists(old):
                os.replace(old, os.path.join(md_dir, fname))
            taken.discard(prev["file"])
            counts["renamed"] += 1
        taken.add(fname)
        changed = write_if_changed(os.path.join(md_dir, fname), render_conversation(conv))
        counts["new" if not prev else ("updated" if changed else "unchanged")] += 1
        catalog[uid] = {
            "file": fname,
            "title": conv.get("name") or "Untitled",
            "created_at": conv.get("created_at"),
            "updated_at": conv.get("updated_at") or conv.get("created_at"),
            "messages": len(conv.get("chat_messages") or []),
            "deleted_upstream": False,
        }

    # Conversations no longer in the export were deleted on claude.ai: keep, but mark.
    for uid, entry in catalog.items():
        if uid in seen or entry.get("deleted_upstream"):
            continue
        entry["deleted_upstream"] = True
        counts["newly_deleted_upstream"] += 1
        path = os.path.join(md_dir, entry["file"])
        if os.path.exists(path):
            with open(path, encoding="utf-8", newline="") as fh:
                text = fh.read()
            write_if_changed(path, text.replace("    deleted_upstream: false", "    deleted_upstream: true", 1))

    rows = sorted(catalog.values(), key=lambda e: e.get("updated_at") or "", reverse=True)
    live = sum(1 for e in rows if not e.get("deleted_upstream"))
    index = ["# claude.ai conversations", "",
             f"Last merged {dt.datetime.now():%Y-%m-%d %H:%M} — {live} on claude.ai, "
             f"{len(rows) - live} kept after deletion there", "",
             "| Updated | Title | Messages |", "|---|---|---|"]
    for e in rows:
        name = e["title"].replace("|", "\\|") + (" *(deleted on claude.ai)*" if e.get("deleted_upstream") else "")
        index.append(f"| {(e.get('updated_at') or '')[:10]} | [{name}]({e['file']}) | {e['messages']} |")
    write_if_changed(os.path.join(md_dir, "INDEX.md"), "\n".join(index) + "\n")

    tmp = catalog_path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(catalog, fh, indent=1, ensure_ascii=False)
    os.replace(tmp, catalog_path)

    # Only now (every zip verified, archive merged) are the downloads redundant.
    trashed = []
    if trash_sources and os.path.realpath(raw_dir) != os.path.realpath(srcs[0]):
        trashed = trash([s for s in srcs if os.path.isfile(s)])

    print(json.dumps({
        "trashed_sources": [os.path.basename(t) for t in trashed],
        "conversations_in_export": len(seen),
        "archive_total": len(catalog),
        **counts,
        "raw_dir": raw_dir,
        "markdown_dir": md_dir,
        "parts": sorted(os.listdir(raw_dir)),
    }, indent=2))


if __name__ == "__main__":
    main()
