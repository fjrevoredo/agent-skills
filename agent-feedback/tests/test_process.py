"""Tests for skills/process/scripts/process.py. Run: python3 -m unittest discover agent-feedback/tests"""

import gzip
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PLUGIN = Path(__file__).resolve().parents[1]
SCRIPT = PLUGIN / "skills" / "process" / "scripts" / "process.py"
SID_A = "aaaaaaaa-0000-4000-8000-000000000001"
SID_B = "bbbbbbbb-0000-4000-8000-000000000002"


def entry(entry_id, session=SID_A, kind="docs", severity="low", text="Some text.", **extra):
    fields = {"id": entry_id, "time": "2026-11-10T10:00:00+01:00", "source": "agent", "kind": kind,
              "severity": severity, "session": session, "agent": "claude-code", "model": "",
              "repo": "https://gitlab.example.com/group/some-repo.git", "path": "docs", "branch": "main",
              "suggestion": "Fix the doc", **extra}
    head = "\n".join(f"{k}: {json.dumps(v)}" if v else f"{k}:" for k, v in fields.items())
    return f"---\n{head}\n---\n\n{text}\n"


class ProcessTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.state = self.tmp / "state"
        for d in ("inbox", "proposed", "done", "wontfix", "transcripts", "briefs"):
            (self.state / d).mkdir(parents=True)
        self.env = {"PATH": os.environ["PATH"], "HOME": str(self.tmp / "home"),
                    "AGENT_FEEDBACK_DIR": str(self.state)}

    def add(self, entry_id, state="inbox", **kw):
        (self.state / state / f"{entry_id}.md").write_text(entry(entry_id, **kw))

    def run_script(self, *args, env=None):
        return subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True, text=True,
                              env={**self.env, **(env or {})})

    def meta(self, path):
        head = path.read_text().split("\n---\n", 1)[0]
        out = {}
        for line in head.splitlines()[1:]:
            k, _, v = line.partition(":")
            out[k] = json.loads(v) if v.strip() else ""
        return out

    # list

    def test_list_shows_each_inbox_entry_compactly_with_text_and_suggestion(self):
        self.add("20261110-100000-aaaa", text="The README names scripts/test.sh, which is gone.")
        self.add("20261110-110000-bbbb", kind="access", severity="high", session=SID_B)
        r = self.run_script("list")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("20261110-100000-aaaa agent docs low some-repo docs", r.stdout)
        self.assertIn("The README names scripts/test.sh, which is gone.", r.stdout)
        self.assertIn("suggestion: Fix the doc", r.stdout)
        self.assertIn("20261110-110000-bbbb agent access high", r.stdout)
        self.assertNotIn("claude-code", r.stdout)  # metadata noise stays out
        self.assertLess(r.stdout.index("aaaa"), r.stdout.index("bbbb"))

    def test_list_other_state(self):
        self.add("20261110-100000-aaaa")
        self.add("20261110-110000-bbbb", state="proposed", outcome="Brief written", link="briefs/x.md")
        r = self.run_script("list", "--state", "proposed")
        self.assertNotIn("aaaa", r.stdout)
        self.assertIn("20261110-110000-bbbb", r.stdout)
        self.assertIn("outcome: Brief written", r.stdout)
        self.assertIn("link: briefs/x.md", r.stdout)

    def test_list_empty_inbox_says_so(self):
        r = self.run_script("list")
        self.assertEqual(r.returncode, 0)
        self.assertIn("no entries in inbox", r.stdout)

    # move

    def test_move_to_proposed_records_outcome_link_and_time(self):
        self.add("20261110-100000-aaaa")
        self.add("20261110-110000-bbbb")
        r = self.run_script("move", "20261110-100000-aaaa", "20261110-110000-bbbb", "--to", "proposed",
                            "--outcome", "Brief for some-repo", "--link", "briefs/some-repo-docs.md")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(list((self.state / "inbox").glob("*.md")), [])
        moved = self.state / "proposed" / "20261110-100000-aaaa.md"
        m = self.meta(moved)
        self.assertEqual(m["outcome"], "Brief for some-repo")
        self.assertEqual(m["link"], "briefs/some-repo-docs.md")
        self.assertRegex(m["moved"], r"^\d{4}-\d\d-\d\dT")
        self.assertEqual(m["kind"], "docs")  # capture fields kept
        self.assertIn("Some text.", moved.read_text())
        self.assertEqual(json.loads(r.stdout)["moved"], ["20261110-100000-aaaa", "20261110-110000-bbbb"])

    def test_move_again_replaces_outcome(self):
        self.add("20261110-100000-aaaa", state="proposed", outcome="Brief", link="briefs/x.md")
        r = self.run_script("move", "20261110-100000-aaaa", "--to", "done", "--outcome", "Merged")
        self.assertEqual(r.returncode, 0, r.stderr)
        text = (self.state / "done" / "20261110-100000-aaaa.md").read_text()
        self.assertEqual(text.count("outcome:"), 1)
        m = self.meta(self.state / "done" / "20261110-100000-aaaa.md")
        self.assertEqual((m["outcome"], m["link"]), ("Merged", "briefs/x.md"))

    def test_move_to_proposed_needs_a_link(self):
        self.add("20261110-100000-aaaa")
        r = self.run_script("move", "20261110-100000-aaaa", "--to", "proposed", "--outcome", "x")
        self.assertEqual(r.returncode, 64)
        self.assertIn("--link", r.stderr)
        self.assertTrue((self.state / "inbox" / "20261110-100000-aaaa.md").exists())

    def test_move_with_unknown_id_moves_nothing(self):
        self.add("20261110-100000-aaaa")
        r = self.run_script("move", "20261110-100000-aaaa", "20261110-999999-zzzz", "--to", "wontfix",
                            "--outcome", "Obsolete")
        self.assertEqual(r.returncode, 64)
        self.assertIn("20261110-999999-zzzz", r.stderr)
        self.assertTrue((self.state / "inbox" / "20261110-100000-aaaa.md").exists())

    def test_closing_the_last_open_entry_of_a_session_deletes_its_transcript_copy(self):
        for sid in (SID_A, SID_B):
            (self.state / "transcripts" / f"{sid}.jsonl.gz").write_bytes(gzip.compress(b"{}\n"))
        self.add("20261110-100000-aaaa", session=SID_A)
        self.add("20261110-110000-bbbb", session=SID_B)
        self.add("20261110-120000-cccc", session=SID_B, state="proposed", link="briefs/x.md")
        r = self.run_script("move", "20261110-100000-aaaa", "20261110-110000-bbbb", "--to", "done",
                            "--outcome", "Fixed")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertFalse((self.state / "transcripts" / f"{SID_A}.jsonl.gz").exists())
        self.assertTrue((self.state / "transcripts" / f"{SID_B}.jsonl.gz").exists())  # cccc still open
        self.assertEqual(json.loads(r.stdout)["transcripts_deleted"], [SID_A])

    def test_moving_to_proposed_keeps_the_transcript_copy(self):
        (self.state / "transcripts" / f"{SID_A}.jsonl.gz").write_bytes(gzip.compress(b"{}\n"))
        self.add("20261110-100000-aaaa", session=SID_A)
        self.run_script("move", "20261110-100000-aaaa", "--to", "proposed", "--outcome", "x", "--link", "y")
        self.assertTrue((self.state / "transcripts" / f"{SID_A}.jsonl.gz").exists())

    # paths

    def test_paths_default_routing_lives_in_the_state_dir(self):
        r = self.run_script("paths")
        self.assertEqual(r.returncode, 0, r.stderr)
        p = json.loads(r.stdout)
        self.assertEqual(p["state"], str(self.state))
        self.assertEqual(p["briefs"], str(self.state / "briefs"))
        self.assertEqual(p["routing"], str(self.state / "routing.md"))
        self.assertFalse(p["routing_exists"])
        self.assertTrue(Path(p["routing_template"]).is_file())

    def test_paths_routing_from_env(self):
        routing = self.tmp / "my-routing.md"
        routing.write_text("# routing\n")
        p = json.loads(self.run_script("paths", env={"AGENT_FEEDBACK_ROUTING": str(routing)}).stdout)
        self.assertEqual(p["routing"], str(routing))
        self.assertTrue(p["routing_exists"])

    def test_move_rejects_ids_that_are_not_entry_ids(self):
        outside = self.tmp / "outside"
        outside.mkdir()
        (outside / "victim.md").write_text("keep me")
        self.add("20261110-100000-aaaa")
        r = self.run_script("move", "20261110-100000-aaaa", "../../outside/victim", "--to", "wontfix",
                            "--outcome", "x")
        self.assertEqual(r.returncode, 64)
        self.assertEqual((outside / "victim.md").read_text(), "keep me")
        self.assertTrue((self.state / "inbox" / "20261110-100000-aaaa.md").exists())

    def test_move_within_the_same_state_updates_in_place(self):
        self.add("20261110-100000-aaaa", state="proposed", link="briefs/x.md")
        r = self.run_script("move", "20261110-100000-aaaa", "--to", "proposed", "--outcome", "Still waiting",
                            "--link", "briefs/x.md")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.meta(self.state / "proposed" / "20261110-100000-aaaa.md")["outcome"], "Still waiting")
        self.assertIn("Some text.", (self.state / "proposed" / "20261110-100000-aaaa.md").read_text())

    def test_move_of_an_entry_without_session_works(self):
        self.add("20261110-100000-aaaa", session="")
        r = self.run_script("move", "20261110-100000-aaaa", "--to", "done", "--outcome", "x")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(json.loads(r.stdout)["transcripts_deleted"], [])

    def test_move_round_trips_a_real_capture_entry(self):
        capture = PLUGIN / "skills" / "capture" / "scripts" / "capture.py"
        text = 'Quotes "x" and \'y\', unicode é, and a line:\n---\nafter it.'
        r = subprocess.run([sys.executable, str(capture), "add", "--kind", "docs", "--suggestion", 'Use "z"'],
                           input=text, capture_output=True, text=True, env=self.env, cwd=self.tmp)
        entry_id = json.loads(r.stdout)["id"]
        r = self.run_script("move", entry_id, "--to", "proposed", "--outcome", "Brief", "--link", "b.md")
        self.assertEqual(r.returncode, 0, r.stderr)
        moved = (self.state / "proposed" / f"{entry_id}.md").read_text()
        self.assertIn(text, moved)
        self.assertEqual(self.meta(self.state / "proposed" / f"{entry_id}.md")["suggestion"], 'Use "z"')

    # transcript

    def write_transcript(self, session, lines):
        data = "".join(json.dumps(l) + "\n" for l in lines).encode()
        (self.state / "transcripts" / f"{session}.jsonl.gz").write_bytes(gzip.compress(data))

    def test_transcript_shows_the_conversation_before_the_entry(self):
        # entry time is 2026-11-10T10:00:00+01:00 = 09:00Z
        self.write_transcript(SID_A, [
            {"type": "user", "timestamp": "2026-11-10T08:30:00Z", "message": {"content": "too early"}},
            {"type": "user", "timestamp": "2026-11-10T08:52:00Z", "message": {"content": "run the tests"}},
            {"type": "user", "timestamp": "2026-11-10T08:52:01Z", "isMeta": True,
             "message": {"content": "<system-reminder>noise</system-reminder>"}},
            {"type": "assistant", "timestamp": "2026-11-10T08:53:00Z", "message": {"content": [
                {"type": "thinking", "thinking": "secret thoughts"},
                {"type": "text", "text": "Running them now."},
                {"type": "tool_use", "name": "Bash", "input": {"command": "./scripts/test.sh"}}]}},
            {"type": "user", "timestamp": "2026-11-10T08:53:05Z", "message": {"content": [
                {"type": "tool_result", "is_error": True, "content": "No such file: ./scripts/test.sh"}]}},
            {"type": "user", "timestamp": "2026-11-10T08:53:06Z", "message": {"content": [
                {"type": "tool_result", "content": "ok output"}]}},
            {"type": "api-request", "timestamp": "2026-11-10T08:54:00Z"},
            {"type": "user", "timestamp": "2026-11-10T09:30:00Z", "message": {"content": "too late"}},
        ])
        self.add("20261110-100000-aaaa", session=SID_A)
        r = self.run_script("transcript", "20261110-100000-aaaa", "--minutes", "10")
        self.assertEqual(r.returncode, 0, r.stderr)
        out = r.stdout
        for wanted in ("user: run the tests", "assistant: Running them now.", "tool: Bash ./scripts/test.sh",
                       "tool error: No such file: ./scripts/test.sh"):
            self.assertIn(wanted, out)
        for unwanted in ("too early", "too late", "noise", "secret thoughts", "ok output", "api-request"):
            self.assertNotIn(unwanted, out)
        self.assertLess(out.index("run the tests"), out.index("Running them now."))

    def test_transcript_truncates_long_messages(self):
        self.write_transcript(SID_A, [{"type": "user", "timestamp": "2026-11-10T08:59:00Z",
                                       "message": {"content": "x" * 5000}}])
        self.add("20261110-100000-aaaa", session=SID_A)
        r = self.run_script("transcript", "20261110-100000-aaaa")
        self.assertLess(len(r.stdout), 1000)

    def test_transcript_skips_records_without_timezone(self):
        self.write_transcript(SID_A, [
            {"type": "user", "timestamp": "2026-11-10T08:59:00", "message": {"content": "naive"}},
            {"type": "user", "timestamp": "2026-11-10T08:59:30Z", "message": {"content": "aware"}}])
        self.add("20261110-100000-aaaa", session=SID_A)
        r = self.run_script("transcript", "20261110-100000-aaaa")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("aware", r.stdout)
        self.assertNotIn("naive", r.stdout)

    def test_transcript_rejects_negative_minutes(self):
        self.add("20261110-100000-aaaa", session=SID_A)
        self.assertEqual(self.run_script("transcript", "20261110-100000-aaaa", "--minutes", "-5").returncode, 64)

    def test_transcript_missing_copy_says_so(self):
        self.add("20261110-100000-aaaa", session=SID_A)
        r = self.run_script("transcript", "20261110-100000-aaaa")
        self.assertEqual(r.returncode, 66)
        self.assertIn("no transcript copy", r.stderr)

    def test_transcript_of_an_entry_without_a_valid_time_says_so(self):
        self.write_transcript(SID_A, [{"type": "user", "timestamp": "2026-11-10T08:59:00Z",
                                       "message": {"content": "hi"}}])
        for bad in ("", "yesterday"):
            self.add("20261110-100000-aaaa", session=SID_A, time=bad)
            r = self.run_script("transcript", "20261110-100000-aaaa")
            self.assertEqual(r.returncode, 65, r.stderr)
            self.assertIn("no valid time", r.stderr)
            self.assertNotIn("Traceback", r.stderr)

    def test_move_with_an_unreadable_entry_moves_nothing(self):
        self.add("20261110-100000-aaaa")
        self.add("20261110-100000-bbbb")
        bad = self.state / "inbox" / "20261110-100000-bbbb.md"
        bad.chmod(0)
        self.addCleanup(bad.chmod, 0o644)
        r = self.run_script("move", "20261110-100000-aaaa", "20261110-100000-bbbb", "--to", "done",
                            "--outcome", "x")
        self.assertEqual(r.returncode, 73, r.stderr)
        self.assertTrue((self.state / "inbox" / "20261110-100000-aaaa.md").exists())
        self.assertEqual(list((self.state / "done").iterdir()), [])


if __name__ == "__main__":
    unittest.main()
