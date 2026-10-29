"""Tests for scripts/needs-you.sh. Run: python3 -m unittest discover needs-you/tests

Fake open, herdr, uname and jq on PATH log their arguments; jq passes through to the real /usr/bin/jq.
"""

import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

ROOT = Path(__file__).resolve().parents[1]
HOOK = ROOT / "scripts" / "needs-you.sh"
SID = "1e8e1bab-50e2-40d3-b802-9e5976db61f5"
REAL_JQ = shutil.which("jq") or "/usr/bin/jq"


class HookTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        self.bin = self.tmp / "bin"
        self.bin.mkdir()
        self.log = self.tmp / "calls.log"
        self.home = self.tmp / "home"
        self.home.mkdir()
        self.tmpdir = self.tmp / "t"
        self.tmpdir.mkdir()
        self.fake("open", 'echo "open $*" >> "$LOG"')
        self.fake("uname", 'echo "${FAKE_UNAME:-Darwin}"')
        self.fake("jq", f'echo "jq" >> "$LOG"; exec {REAL_JQ} "$@"')
        self.fake("herdr", 'echo "herdr $*" >> "$LOG"; printf "%s" "${FAKE_HERDR_OUT:-}"')
        self.env = {
            "PATH": f"{self.bin}:/usr/bin:/bin",
            "HOME": str(self.home),
            "TMPDIR": str(self.tmpdir),
            "LOG": str(self.log),
            "CLAUDE_PLUGIN_ROOT": str(ROOT),
            "__CFBundleIdentifier": "com.github.wez.wezterm",
        }

    def fake(self, name, body):
        p = self.bin / name
        p.write_text(f"#!/bin/bash\n{body}\n")
        p.chmod(0o755)

    def run_hook(self, event, *args, env=None, **fields):
        payload = {"session_id": SID, "hook_event_name": event, "cwd": "/work/my-repo", **fields}
        return subprocess.run(
            ["bash", str(HOOK), *args], input=json.dumps(payload), capture_output=True, text=True,
            env={**self.env, **(env or {})},
        )

    def calls(self):
        return self.log.read_text().splitlines() if self.log.exists() else []

    def opens(self):
        return [c.removeprefix("open -g ") for c in self.calls() if c.startswith("open ")]

    def shown(self):
        """Query params of the show URLs, in order."""
        out = []
        for url in self.opens():
            parts = urlsplit(url)
            if parts.netloc == "needs-you":
                out.append({k: v[0] for k, v in parse_qs(parts.query, keep_blank_values=True).items()})
        return out

    def cleared(self):
        return [u for u in self.opens() if u.startswith("hammerspoon://needs-you-clear")]

    def state(self):
        return self.tmpdir / "needs-you" / SID

    # --- show ---

    def test_permission_prompt_shows_with_encoded_reason(self):
        r = self.run_hook("Notification", notification_type="permission_prompt",
                          message='Claude needs your permission to use Bash: "rm -rf x" & more')
        self.assertEqual(r.returncode, 0, r.stderr)
        [p] = self.shown()
        self.assertEqual(p["kind"], "permission")
        self.assertEqual(p["reason"], 'Claude needs your permission to use Bash: "rm -rf x" & more')
        self.assertEqual(p["session"], SID)
        self.assertEqual(p["title"], "my-repo")
        self.assertEqual(p["terminal"], "com.github.wez.wezterm")
        self.assertEqual(p["focused"], "0")
        self.assertEqual(p["pane"], "")
        self.assertNotIn(" ", self.opens()[0])
        self.assertTrue(self.state().exists())

    def test_elicitation_shows(self):
        self.run_hook("Notification", notification_type="elicitation_url_dialog", message="Open a URL")
        [p] = self.shown()
        self.assertEqual(p["kind"], "elicitation")

    def test_other_notification_types_do_nothing(self):
        self.run_hook("Notification", notification_type="idle_prompt", message="idle")
        self.assertEqual(self.opens(), [])

    def test_herdr_title_and_focus(self):
        out = json.dumps({"result": {"pane": {"terminal_title_stripped": "Kesh: check-in", "focused": True}}})
        self.run_hook("Notification", notification_type="permission_prompt", message="m",
                      env={"HERDR_PANE_ID": "w2G:p1", "FAKE_HERDR_OUT": out})
        [p] = self.shown()
        self.assertEqual(p["title"], "Kesh: check-in")
        self.assertEqual(p["focused"], "1")
        self.assertEqual(p["pane"], "w2G:p1")
        self.assertIn("herdr pane get w2G:p1", self.calls())

    def test_herdr_missing_falls_back_to_folder(self):
        (self.bin / "herdr").unlink()
        r = self.run_hook("Notification", notification_type="permission_prompt", message="m",
                          env={"HERDR_PANE_ID": "w2G:p1"})
        self.assertEqual(r.returncode, 0, r.stderr)
        [p] = self.shown()
        self.assertEqual(p["title"], "my-repo")
        self.assertEqual(p["focused"], "0")

    # --- Stop and the marker ---

    def test_marker_on_last_line_shows_gate(self):
        msg = "Here is the draft.\n\n> text\n\n[needs-you: approve Jira comment on X-1: 'quoted']\n\n  \n"
        self.run_hook("Stop", last_assistant_message=msg)
        [p] = self.shown()
        self.assertEqual(p["kind"], "gate")
        self.assertEqual(p["reason"], "approve Jira comment on X-1: 'quoted'")

    def test_marker_wrapped_in_formatting_or_crlf_shows(self):
        for line in ("`[needs-you: approve it_now]`", "**[needs-you: approve it_now]**", "[needs-you: approve it_now]\r"):
            self.log.unlink(missing_ok=True)
            self.run_hook("Stop", last_assistant_message=f"Draft.\r\n{line}\r\n")
            self.assertEqual([p["reason"] for p in self.shown()], ["approve it_now"], repr(line))

    def test_shell_metacharacters_are_not_executed(self):
        evil = "it's $(touch PWNED) `touch PWNED2` \"q\" ; touch PWNED3"
        out = json.dumps({"result": {"pane": {"terminal_title_stripped": evil, "focused": False}}})
        self.run_hook("Notification", notification_type="permission_prompt", message=evil,
                      env={"HERDR_PANE_ID": "w2G:p1", "FAKE_HERDR_OUT": out})
        self.run_hook("Stop", last_assistant_message=f"[needs-you: {evil}]")
        self.assertEqual(list(self.tmp.rglob("PWNED*")), [])
        self.assertFalse(any(Path.cwd().glob("PWNED*")))
        self.assertEqual([p["reason"] for p in self.shown()], [evil, evil])
        self.assertEqual(self.shown()[0]["title"], evil)

    def test_marker_not_on_last_line_is_ignored(self):
        self.run_hook("Stop", last_assistant_message="[needs-you: approve]\nDone.")
        self.assertEqual(self.shown(), [])

    def test_stop_without_marker_clears_open_popup(self):
        self.run_hook("Notification", notification_type="permission_prompt", message="m")
        self.run_hook("Stop", last_assistant_message="All done.")
        self.assertEqual(self.cleared(), [f"hammerspoon://needs-you-clear?session={SID}"])
        self.assertFalse(self.state().exists())

    def test_stop_without_marker_and_no_popup_opens_nothing(self):
        self.run_hook("Stop", last_assistant_message="All done.")
        self.assertEqual(self.opens(), [])

    # --- clears ---

    def test_user_prompt_and_session_end_clear(self):
        for event in ("UserPromptSubmit", "SessionEnd"):
            self.log.unlink(missing_ok=True)
            self.run_hook("Stop", last_assistant_message="[needs-you: ok?]")
            self.run_hook(event)
            self.assertEqual(len(self.cleared()), 1, event)

    def test_tool_event_without_state_runs_no_jq_and_no_open(self):
        r = self.run_hook("PreToolUse", "--if-pending", tool_name="Bash")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.calls(), [])

    def test_main_agent_tool_event_clears(self):
        self.run_hook("Notification", notification_type="permission_prompt", message="m")
        self.run_hook("PostToolUse", "--if-pending", tool_name="Bash")
        self.assertEqual(len(self.cleared()), 1)

    def test_subagent_tool_event_does_not_clear_main_popup(self):
        self.run_hook("Notification", notification_type="permission_prompt", message="m")
        self.run_hook("PreToolUse", "--if-pending", tool_name="Read", agent_id="agent-abc")
        self.assertEqual(self.cleared(), [])
        self.assertTrue(self.state().exists())

    def test_subagent_popup_cleared_by_same_subagent(self):
        self.run_hook("Notification", notification_type="permission_prompt", message="m", agent_id="agent-abc")
        self.run_hook("PostToolUse", "--if-pending", tool_name="Read")
        self.assertEqual(self.cleared(), [])
        self.run_hook("PostToolUseFailure", "--if-pending", tool_name="Read", agent_id="agent-abc")
        self.assertEqual(len(self.cleared()), 1)

    def test_other_session_state_does_not_clear_this_one(self):
        (self.tmpdir / "needs-you").mkdir()
        (self.tmpdir / "needs-you" / "other-session").write_text("")
        self.run_hook("PostToolUse", "--if-pending", tool_name="Bash")
        self.assertEqual(self.cleared(), [])

    def test_bad_session_id_is_ignored(self):
        for sid in ("../../etc", "..", ".", ""):
            self.run_hook("Notification", session_id=sid, notification_type="permission_prompt", message="m")
        self.assertEqual(self.opens(), [])

    def test_elicitation_response_clears(self):
        self.run_hook("Notification", notification_type="elicitation_dialog", message="m")
        self.run_hook("Notification", notification_type="elicitation_response", message="")
        self.assertEqual(len(self.cleared()), 1)

    def test_stale_state_is_dropped_and_fast_path_restored(self):
        d = self.tmpdir / "needs-you"
        d.mkdir()
        old = d / "crashed-session"
        old.write_text("")
        os.utime(old, (0, 0))
        self.run_hook("PostToolUse", "--if-pending", tool_name="Bash")
        self.assertFalse(old.exists())
        self.assertEqual(self.calls(), [])

    # --- SessionStart ---

    def test_session_start_prints_rule_and_setup_hint(self):
        r = self.run_hook("SessionStart", source="startup")
        self.assertIn("[needs-you: <short reason>]", r.stdout)
        self.assertIn("AskUserQuestion", r.stdout)
        self.assertIn("/needs-you:setup", r.stdout)
        self.assertEqual(self.opens(), [])

    def test_session_start_hint_on_version_mismatch_only(self):
        spoon = self.home / ".hammerspoon" / "Spoons" / "NeedsYou.spoon"
        spoon.mkdir(parents=True)
        spoon.joinpath("init.lua").write_text((ROOT / "NeedsYou.spoon" / "init.lua").read_text())
        self.assertNotIn("/needs-you:setup", self.run_hook("SessionStart").stdout)
        spoon.joinpath("init.lua").write_text('obj.version = "0.9.0"\n')
        out = self.run_hook("SessionStart").stdout
        self.assertIn("version 0.9.0", out)
        self.assertIn("/needs-you:setup", out)

    # --- platform ---

    def test_non_macos_is_silent(self):
        env = {"FAKE_UNAME": "Linux"}
        self.assertEqual(self.run_hook("SessionStart", env=env).stdout, "")
        self.run_hook("Notification", notification_type="permission_prompt", message="m", env=env)
        self.assertEqual(self.calls(), [])


if __name__ == "__main__":
    unittest.main()
