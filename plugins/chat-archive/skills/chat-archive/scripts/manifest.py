#!/usr/bin/env python3
"""Read a claude.ai export manifest and list its parts, vetting each download link.

Usage:
  manifest.py MANIFEST_JSON [--only NAME,NAME]

Large accounts get a manifest (manifest-<export id>-....json) instead of one zip. Each
entry in data_files has a filename (e.g. conversations-000.zip), a category and its own
single-use export_url. Prints JSON: [{filename, category, url, host_ok}], where host_ok
means the URL is https on claude.ai / claude.com / anthropic.com (or a subdomain).
--only limits output to the given categories or filenames (e.g. to re-fetch parts whose
links failed, from a fresh export). Exits 2 if any listed URL fails the host check.
Run with `python3 -I`.
"""
import json
import sys
from urllib.parse import urlparse

ALLOWED = ("claude.ai", "claude.com", "anthropic.com")


def host_ok(url):
    u = urlparse(url or "")
    host = (u.hostname or "").lower()
    return u.scheme == "https" and any(host == d or host.endswith("." + d) for d in ALLOWED)


def main():
    args = sys.argv[1:]
    only = None
    if "--only" in args:
        i = args.index("--only")
        only = set(args[i + 1].split(","))
        args = args[:i] + args[i + 2:]
    if len(args) != 1:
        raise SystemExit(__doc__)
    with open(args[0], encoding="utf-8") as fh:
        manifest = json.load(fh)
    parts = []
    for f in manifest.get("data_files") or []:
        if only and f.get("category") not in only and f.get("filename") not in only:
            continue
        url = f.get("export_url")
        parts.append({"filename": f.get("filename"), "category": f.get("category"),
                      "url": url, "host_ok": host_ok(url)})
    print(json.dumps(parts, indent=1))
    sys.exit(2 if any(not p["host_ok"] for p in parts) else 0)


if __name__ == "__main__":
    main()
