"""Tests for the chat-archive scripts. Run: python3 -m unittest discover -s tests -v
(from plugins/chat-archive). Uses only the standard library; no network, no qmd."""
import importlib.util
import json
import os
import stat
import subprocess
import sys
import tempfile
import time
import unittest
import zipfile

SCRIPTS = os.path.join(os.path.dirname(__file__), "..", "skills", "chat-archive", "scripts")


def script(name):
    return os.path.join(SCRIPTS, name)


def load(name):
    spec = importlib.util.spec_from_file_location(name, script(name + ".py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def run(args, env=None, cwd=None):
    return subprocess.run([sys.executable, "-I", *args], capture_output=True, text=True,
                          env={**os.environ, **(env or {})}, cwd=cwd)


def conv(uid, name, updated="2026-10-01", messages=None):
    return {
        "uuid": f"{uid}-0000-4000-8000-000000000000", "name": name, "summary": "",
        "created_at": "2026-10-01T00:00:00Z", "updated_at": f"{updated}T00:00:00Z",
        "chat_messages": messages if messages is not None else [
            {"uuid": f"{uid}-m1", "parent_message_uuid": "00000000-root", "sender": "human",
             "created_at": "2026-10-01T00:00:01Z", "text": f"hi {name}",
             "content": [{"type": "text", "text": f"hi {name}"}]},
        ],
    }


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = self.tmp.name
        self.archive = os.path.join(self.dir, "archive")

    def tearDown(self):
        self.tmp.cleanup()

    def export(self, name, conversations):
        d = os.path.join(self.dir, name)
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, "conversations.json"), "w", newline="") as fh:
            json.dump(conversations, fh)
        return d

    def convert(self, *sources, env=None):
        p = run([script("convert.py"), *sources, self.archive], env=env)
        self.assertEqual(p.returncode, 0, p.stderr)
        return json.loads(p.stdout)


class TestConvert(Base):
    def test_merge_new_rename_delete_and_idempotent(self):
        r1 = self.convert(self.export("e1", [conv("aaaaaaaa", "Alpha"), conv("bbbbbbbb", "Beta"), conv("cccccccc", "Gamma")]))
        self.assertEqual(r1["new"], 3)
        r2 = self.convert(self.export("e2", [conv("aaaaaaaa", "Alpha"), conv("bbbbbbbb", "Beta renamed", "2026-10-05"),
                                             conv("dddddddd", "Delta")]))
        self.assertEqual((r2["new"], r2["updated"], r2["unchanged"], r2["renamed"], r2["newly_deleted_upstream"]),
                         (1, 1, 1, 1, 1))
        md = os.listdir(os.path.join(self.archive, "markdown"))
        self.assertIn("2026-10-01_beta-renamed_bbbbbbbb.md", md)
        self.assertNotIn("2026-10-01_beta_bbbbbbbb.md", md)
        with open(os.path.join(self.archive, "markdown", "2026-10-01_gamma_cccccccc.md")) as fh:
            self.assertIn("deleted_upstream: true", fh.read())  # kept, flagged
        r3 = self.convert(os.path.join(self.dir, "e2"))
        self.assertEqual((r3["new"], r3["updated"], r3["unchanged"]), (0, 0, 3))

    def test_crlf_content_is_idempotent(self):
        c = conv("eeeeeeee", "Windows", messages=[{"uuid": "m1", "parent_message_uuid": None, "sender": "human",
                                                  "text": "line1\r\nline2", "content": [{"type": "text", "text": "line1\r\nline2"}]}])
        src = self.export("e", [c])
        self.convert(src)
        self.assertEqual(self.convert(src)["updated"], 0)

    def test_branches_render_latest_and_collapse_alternates(self):
        msgs = [
            {"uuid": "q", "parent_message_uuid": "root", "sender": "human", "created_at": "2026-10-01T00:00:00Z",
             "content": [{"type": "text", "text": "question"}]},
            {"uuid": "a1", "parent_message_uuid": "q", "sender": "assistant", "created_at": "2026-10-01T00:00:01Z",
             "content": [{"type": "text", "text": "OLD ANSWER"}]},
            {"uuid": "a2", "parent_message_uuid": "q", "sender": "assistant", "created_at": "2026-10-01T00:00:02Z",
             "content": [{"type": "text", "text": "NEW ANSWER"}]},
        ]
        cv = load("convert")
        out = cv.render_conversation(conv("ffffffff", "Branchy", messages=msgs))
        self.assertIn("Alternate version", out)
        self.assertLess(out.index("OLD ANSWER"), out.index("## Claude"))  # alternate sits before the chosen reply
        self.assertGreater(out.index("NEW ANSWER"), out.index("## Claude"))

    def test_tool_results_are_trimmed(self):
        cv = load("convert")
        big = "x" * 5000
        text = cv.message_text({"content": [{"type": "tool_result", "content": [{"type": "text", "text": big}]}]})
        self.assertLess(len(text), 1000)
        self.assertIn("5,000 chars", text)

    def test_frontmatter_metadata(self):
        self.convert(self.export("e", [conv("abcdef12", "Meta", "2026-10-09")]))
        with open(os.path.join(self.archive, "markdown", "2026-10-01_meta_abcdef12.md")) as fh:
            head = fh.read(400)
        self.assertIn("    updated: 20261009", head)
        self.assertIn("    created: 20261001", head)

    def test_refuses_empty_export(self):
        self.convert(self.export("e1", [conv("aaaaaaaa", "Alpha")]))
        p = run([script("convert.py"), self.export("e2", []), self.archive])
        self.assertNotEqual(p.returncode, 0)
        with open(os.path.join(self.archive, "catalog.json")) as fh:
            self.assertFalse(any(e["deleted_upstream"] for e in json.load(fh).values()))

    def test_zip_slip_refused(self):
        z = os.path.join(self.dir, "evil.zip")
        with zipfile.ZipFile(z, "w") as zf:
            zf.writestr("../../escape.txt", "nope")
            zf.writestr("conversations.json", "[]")
        p = run([script("convert.py"), z, os.path.join(self.dir, "x.json"), self.archive])
        self.assertNotEqual(p.returncode, 0)
        self.assertIn("unsafe", p.stdout + p.stderr)

    def test_trash_sources_only_after_success(self):
        home = os.path.join(self.dir, "home")
        os.makedirs(os.path.join(home, ".Trash"))
        dl = os.path.join(self.dir, "dl")
        os.makedirs(dl)
        z = os.path.join(dl, "conversations-000.zip")
        with zipfile.ZipFile(z, "w") as zf:
            zf.writestr("conversations.json", json.dumps([conv("aaaaaaaa", "Alpha")]))
        m = os.path.join(dl, "manifest-x.json")
        with open(m, "w") as fh:
            fh.write('{"data_files": []}')
        p = run([script("convert.py"), "--trash-sources", z, m, self.archive], env={"HOME": home})
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(os.listdir(dl), [])
        self.assertEqual(sorted(os.listdir(os.path.join(home, ".Trash"))), ["conversations-000.zip", "manifest-x.json"])
        # A failing run (no conversations.json) leaves its sources alone.
        bad = os.path.join(dl, "projects-000.zip")
        with zipfile.ZipFile(bad, "w") as zf:
            zf.writestr("projects/p.json", "{}")
        p = run([script("convert.py"), "--trash-sources", bad, m + ".missing.json", self.archive], env={"HOME": home})
        self.assertNotEqual(p.returncode, 0)
        self.assertTrue(os.path.exists(bad))


class TestManifest(Base):
    def test_host_vetting_and_only(self):
        m = os.path.join(self.dir, "manifest.json")
        with open(m, "w") as fh:
            json.dump({"data_files": [
                {"filename": "conversations-000.zip", "category": "conversations", "export_url": "https://claude.ai/export/a/download/b"},
                {"filename": "projects-000.zip", "category": "projects", "export_url": "https://claude.ai.evil.example/x"},
                {"filename": "memories-000.zip", "category": "memories", "export_url": "http://claude.ai/x"},
            ]}, fh)
        p = run([script("manifest.py"), m])
        self.assertEqual(p.returncode, 2)
        self.assertEqual([x["host_ok"] for x in json.loads(p.stdout)], [True, False, False])
        p = run([script("manifest.py"), m, "--only", "conversations"])
        self.assertEqual(p.returncode, 0)
        self.assertEqual([x["filename"] for x in json.loads(p.stdout)], ["conversations-000.zip"])


class TestWaitDownloads(Base):
    def test_waits_for_names_and_crdownload(self):
        open(os.path.join(self.dir, "a.zip"), "w").close()
        p = run([script("wait_downloads.py"), "--dir", self.dir, "--timeout", "2", "a.zip", "b.zip"])
        self.assertEqual(p.returncode, 1)
        self.assertEqual(json.loads(p.stdout)["missing"], ["b.zip"])
        open(os.path.join(self.dir, "b.zip.crdownload"), "w").close()
        proc = subprocess.Popen([sys.executable, "-I", script("wait_downloads.py"), "--dir", self.dir,
                                 "--timeout", "15", "a.zip", "b.zip"], stdout=subprocess.PIPE, text=True)
        time.sleep(2.5)
        os.rename(os.path.join(self.dir, "b.zip.crdownload"), os.path.join(self.dir, "b.zip"))
        out, _ = proc.communicate(timeout=20)
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(json.loads(out)["done"], ["a.zip", "b.zip"])

    def test_pattern_since(self):
        since = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(time.time() - 60))
        open(os.path.join(self.dir, "manifest-1.json"), "w").close()
        p = run([script("wait_downloads.py"), "--dir", self.dir, "--timeout", "2", "--since", since, "--pattern", "manifest-*.json"])
        self.assertEqual(p.returncode, 0)


class TestFind(Base):
    def test_filters_with_fake_qmd(self):
        self.convert(self.export("e", [conv("aaaaaaaa", "Recent", "2099-01-01"), conv("bbbbbbbb", "Old", "2020-01-01")]))
        # Mark one conversation as deleted upstream.
        cat_path = os.path.join(self.archive, "catalog.json")
        with open(cat_path) as fh:
            cat = json.load(fh)
        cat["aaaaaaaa-0000-4000-8000-000000000000"]["deleted_upstream"] = True
        with open(cat_path, "w") as fh:
            json.dump(cat, fh)
        bindir = os.path.join(self.dir, "bin")
        os.makedirs(bindir)
        fake = os.path.join(bindir, "qmd")
        hits = [{"file": f"qmd://claude-ai/{e['file']}", "score": 0.9, "title": e["title"], "snippet": "> hello"}
                for e in cat.values()]
        with open(fake, "w") as fh:
            fh.write("#!/bin/sh\ncat <<'EOF'\n" + json.dumps(hits) + "\nEOF\n")
        os.chmod(fake, os.stat(fake).st_mode | stat.S_IEXEC)
        env = {"PATH": bindir + os.pathsep + os.environ["PATH"]}

        def titles(*extra):
            p = run([script("find.py"), "x", "--archive", self.archive, "--json", *extra], env=env)
            self.assertEqual(p.returncode, 0, p.stderr)
            return [r["title"] for r in json.loads(p.stdout)]

        self.assertEqual(titles(), ["Old"])  # deleted hidden by default
        self.assertEqual(sorted(titles("--include-deleted")), ["Old", "Recent"])
        self.assertEqual(titles("--include-deleted", "--days", "30"), ["Recent"])
        self.assertEqual(titles("--since", "2030-01-01"), [])


if __name__ == "__main__":
    unittest.main()
