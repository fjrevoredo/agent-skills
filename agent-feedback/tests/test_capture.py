"""Tests for skills/capture/scripts/capture.py. Run: python3 -m unittest discover agent-feedback/tests"""

import gzip
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "skills" / "capture" / "scripts" / "capture.py"
SID = "1e8e1bab-50e2-40d3-b802-9e5976db61f5"


class CaptureTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.state = self.tmp / "state"
        self.config = self.tmp / "claude"
        self.cwd = self.tmp / "work"
        self.cwd.mkdir()
        self.env = {
            "PATH": os.environ["PATH"],
            "HOME": str(self.tmp / "home"),
            "AGENT_FEEDBACK_DIR": str(self.state),
            "CLAUDE_CONFIG_DIR": str(self.config),
        }

    def run_script(self, *args, stdin=None, env=None, cwd=None):
        return subprocess.run(
            [sys.executable, str(SCRIPT), *args],
            input=stdin, capture_output=True, text=True,
            env={**self.env, **(env or {})}, cwd=cwd or self.cwd,
        )

    def entries(self, state="inbox"):
        d = self.state / state
        return sorted(d.glob("*.md")) if d.is_dir() else []

    def fields(self, path):
        head, _, body = path.read_text().partition("\n---\n")
        meta = {}
        for line in head.splitlines()[1:]:
            key, _, value = line.partition(":")
            meta[key] = json.loads(value) if value.strip() else ""
        return meta, body.strip()

    def make_transcript(self, model="claude-haiku-5-5"):
        p = self.config / "projects" / "-some-slug" / f"{SID}.jsonl"
        p.parent.mkdir(parents=True)
        p.write_text(
            json.dumps({"type": "user", "message": {"role": "user", "content": "hi"}}) + "\n"
            + json.dumps({"type": "assistant", "message": {"model": model, "content": []}}) + "\n"
        )
        return p

    # --- add ---

    def test_add_writes_entry_with_fields_and_prints_json(self):
        r = self.run_script("add", "--kind", "docs", "--severity", "medium",
                            "--suggestion", "Fix the path", "--text", "README names a missing script.")
        self.assertEqual(r.returncode, 0, r.stderr)
        out = json.loads(r.stdout)
        [entry] = self.entries()
        self.assertEqual(out["id"], entry.stem)
        self.assertEqual(Path(out["path"]), entry)
        meta, body = self.fields(entry)
        self.assertEqual(meta["id"], entry.stem)
        self.assertEqual(meta["source"], "agent")
        self.assertEqual(meta["kind"], "docs")
        self.assertEqual(meta["severity"], "medium")
        self.assertEqual(meta["suggestion"], "Fix the path")
        self.assertTrue(meta["time"])
        self.assertEqual(body, "README names a missing script.")

    def test_add_reads_text_from_stdin(self):
        r = self.run_script("add", "--source", "user", stdin="Line one.\nLine two.\n")
        self.assertEqual(r.returncode, 0, r.stderr)
        meta, body = self.fields(self.entries()[0])
        self.assertEqual(meta["source"], "user")
        self.assertEqual(body, "Line one.\nLine two.")

    def test_add_rejects_unknown_kind_without_writing(self):
        r = self.run_script("add", "--kind", "bogus", "--text", "x")
        self.assertEqual(r.returncode, 64)
        self.assertIn("instruction", r.stderr)
        self.assertEqual(self.entries(), [])

    def test_add_rejects_empty_text(self):
        r = self.run_script("add", stdin="  \n")
        self.assertEqual(r.returncode, 64)
        self.assertEqual(self.entries(), [])

    def test_single_line_fields_drop_newlines(self):
        self.run_script("add", "--suggestion", "a\nb", "--text", "x")
        meta, _ = self.fields(self.entries()[0])
        self.assertEqual(meta["suggestion"], "a b")

    def test_header_values_are_quoted(self):
        self.run_script("add", "--suggestion", "Use `x`: y \"z\"", "--text", "x")
        entry = self.entries()[0]
        self.assertIn('suggestion: "Use `x`: y \\"z\\""', entry.read_text())
        meta, _ = self.fields(entry)
        self.assertEqual(meta["suggestion"], 'Use `x`: y "z"')

    def test_unwritable_inbox_exits_73(self):
        (self.state / "inbox").mkdir(parents=True)
        (self.state / "inbox").chmod(0o500)
        self.addCleanup((self.state / "inbox").chmod, 0o700)
        r = self.run_script("add", "--text", "x")
        self.assertEqual(r.returncode, 73)
        self.assertNotIn("Traceback", r.stderr)

    def test_invalid_utf8_on_stdin_is_replaced(self):
        r = subprocess.run([sys.executable, str(SCRIPT), "add"], input=b"caf\xe9 broken",
                           capture_output=True, env=self.env, cwd=self.cwd)
        self.assertEqual(r.returncode, 0, r.stderr)
        _, body = self.fields(self.entries()[0])
        self.assertTrue(body.startswith("caf"))

    def test_default_state_dir_is_xdg(self):
        env = {"AGENT_FEEDBACK_DIR": "", "XDG_STATE_HOME": str(self.tmp / "xdg")}
        r = self.run_script("add", "--text", "x", env=env)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(len(list((self.tmp / "xdg" / "agent-feedback" / "inbox").glob("*.md"))), 1)
        for d in ("proposed", "done", "wontfix", "transcripts", "briefs"):
            self.assertTrue((self.tmp / "xdg" / "agent-feedback" / d).is_dir())

    def test_ids_are_unique(self):
        for _ in range(3):
            self.run_script("add", "--text", "x")
        self.assertEqual(len(self.entries()), 3)

    # --- metadata ---

    def test_outside_claude_code_fields_are_blank_and_no_transcript(self):
        r = self.run_script("add", "--text", "x")
        self.assertEqual(r.returncode, 0, r.stderr)
        meta, _ = self.fields(self.entries()[0])
        for f in ("session", "agent", "model", "repo", "path", "branch"):
            self.assertEqual(meta[f], "", f)
        self.assertEqual(list((self.state / "transcripts").iterdir()), [])

    def test_session_copies_transcript_and_reads_model(self):
        self.make_transcript()
        env = {"CLAUDE_CODE_SESSION_ID": SID, "AI_AGENT": "claude-code_2-1-312_harness"}
        r = self.run_script("add", "--text", "x", env=env)
        self.assertEqual(r.returncode, 0, r.stderr)
        meta, _ = self.fields(self.entries()[0])
        self.assertEqual(meta["session"], SID)
        self.assertEqual(meta["agent"], "claude-code_2-1-312_harness")
        self.assertEqual(meta["model"], "claude-haiku-5-5")
        copy = self.state / "transcripts" / f"{SID}.jsonl.gz"
        with gzip.open(copy, "rt") as f:
            self.assertIn("claude-haiku-5-5", f.read())

    def test_session_without_transcript_still_succeeds(self):
        r = self.run_script("add", "--text", "x", env={"CLAUDE_CODE_SESSION_ID": SID})
        self.assertEqual(r.returncode, 0, r.stderr)
        meta, _ = self.fields(self.entries()[0])
        self.assertEqual(meta["session"], SID)

    def test_git_repo_fields_use_remote_and_relative_path(self):
        def git(*a):
            subprocess.run(["git", *a], cwd=self.cwd, check=True, capture_output=True)
        git("init", "-q", "-b", "feature-x")
        git("remote", "add", "origin", "https://user:secret@gitlab.example.com/group/repo.git")
        sub = self.cwd / "a" / "b"
        sub.mkdir(parents=True)
        r = self.run_script("add", "--text", "x", cwd=sub)
        self.assertEqual(r.returncode, 0, r.stderr)
        meta, _ = self.fields(self.entries()[0])
        self.assertEqual(meta["repo"], "https://gitlab.example.com/group/repo.git")
        self.assertEqual(meta["path"], "a/b")
        self.assertEqual(meta["branch"], "feature-x")

    def test_local_path_remote_is_blank(self):
        subprocess.run(["git", "init", "-q"], cwd=self.cwd, check=True)
        for remote in ("/Users/someone/repos/x.git", "file:///Users/someone/repos/x.git"):
            subprocess.run(["git", "remote", "remove", "origin"], cwd=self.cwd, capture_output=True)
            subprocess.run(["git", "remote", "add", "origin", remote], cwd=self.cwd, check=True)
            self.run_script("add", "--text", "x")
        for entry in self.entries():
            self.assertEqual(self.fields(entry)[0]["repo"], "")

    def test_ssh_remote_is_kept(self):
        subprocess.run(["git", "init", "-q"], cwd=self.cwd, check=True)
        subprocess.run(["git", "remote", "add", "origin", "git@gitlab.example.com:g/r.git"], cwd=self.cwd, check=True)
        self.run_script("add", "--text", "x")
        self.assertEqual(self.fields(self.entries()[0])[0]["repo"], "git@gitlab.example.com:g/r.git")

    # --- session-end ---

    def hook_input(self, transcript):
        return json.dumps({"session_id": SID, "transcript_path": str(transcript),
                           "cwd": str(self.cwd), "hook_event_name": "SessionEnd", "reason": "other"})

    def test_session_end_refreshes_copy_for_session_with_open_entry(self):
        t = self.make_transcript()
        self.run_script("add", "--text", "x", env={"CLAUDE_CODE_SESSION_ID": SID})
        with open(t, "a") as f:
            f.write(json.dumps({"type": "user", "marker": "late"}) + "\n")
        r = self.run_script("session-end", stdin=self.hook_input(t))
        self.assertEqual(r.returncode, 0, r.stderr)
        with gzip.open(self.state / "transcripts" / f"{SID}.jsonl.gz", "rt") as f:
            self.assertIn('"late"', f.read())

    def test_session_end_skips_session_without_entries(self):
        t = self.make_transcript()
        r = self.run_script("session-end", stdin=self.hook_input(t))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertFalse((self.state / "transcripts" / f"{SID}.jsonl.gz").exists())

    def test_session_end_with_missing_transcript_exits_0(self):
        self.run_script("add", "--text", "x", env={"CLAUDE_CODE_SESSION_ID": SID})
        r = self.run_script("session-end", stdin=self.hook_input(self.tmp / "gone.jsonl"))
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_session_end_ignores_bad_input(self):
        r = self.run_script("session-end", stdin="not json")
        self.assertEqual(r.returncode, 0)


if __name__ == "__main__":
    unittest.main()
