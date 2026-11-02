#!/usr/bin/env python3
"""Wait until Chrome has finished downloading files into ~/Downloads.

Usage:
  wait_downloads.py [--timeout SECONDS] [--dir DIR] NAME [NAME ...]
  wait_downloads.py [--timeout SECONDS] [--dir DIR] --since 'YYYY-MM-DD HH:MM:SS' --pattern GLOB

First form: wait for each exact filename (e.g. conversations-000.zip).
Second form: wait for any file matching GLOB modified after --since (e.g. the first
download from the email link, whose name you don't know yet: 'manifest-*.json' or '*.zip').

"Finished" means the file exists and no *.crdownload is left in the folder. Prints one
JSON line {"done": [...], "missing": [...], "in_progress": N} and exits 0 when everything
arrived, 1 on timeout (default 300s). A download Chrome blocked never shows up at all, so
a timeout usually means a blocked download, not a slow one.
Run with `python3 -I`.
"""
import datetime as dt
import fnmatch
import json
import os
import sys
import time


def main():
    args = sys.argv[1:]
    opts = {"--timeout": "300", "--dir": "~/Downloads", "--since": None, "--pattern": None}
    names = []
    while args:
        a = args.pop(0)
        if a in opts:
            opts[a] = args.pop(0)
        else:
            names.append(a)
    folder = os.path.expanduser(opts["--dir"])
    deadline = time.time() + float(opts["--timeout"])
    since = dt.datetime.strptime(opts["--since"], "%Y-%m-%d %H:%M:%S").timestamp() if opts["--since"] else None
    if not names and not opts["--pattern"]:
        raise SystemExit(__doc__)

    while True:
        entries = os.listdir(folder)
        in_progress = sum(1 for e in entries if e.endswith(".crdownload"))
        if opts["--pattern"]:
            done = [e for e in entries if fnmatch.fnmatch(e, opts["--pattern"]) and not e.endswith(".crdownload")
                    and (since is None or os.path.getmtime(os.path.join(folder, e)) >= since)]
            missing = [] if done else [opts["--pattern"]]
        else:
            done = [n for n in names if os.path.isfile(os.path.join(folder, n))]
            missing = [n for n in names if n not in done]
        if not missing and in_progress == 0:
            print(json.dumps({"done": sorted(done), "missing": [], "in_progress": 0}))
            return
        if time.time() > deadline:
            print(json.dumps({"done": sorted(done), "missing": missing, "in_progress": in_progress}))
            sys.exit(1)
        time.sleep(2)


if __name__ == "__main__":
    main()
