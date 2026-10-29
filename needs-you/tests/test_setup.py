"""Tests for skills/setup/scripts/setup.sh. Run: python3 -m unittest discover needs-you/tests

Fake open, pgrep, killall, brew and sleep on PATH; HAMMERSPOON_DIR points at a temp folder.
"""

import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SETUP = ROOT / "skills" / "setup" / "scripts" / "setup.sh"
LOAD = 'hs.loadSpoon("NeedsYou"):start()'


class SetupTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        self.bin = self.tmp / "bin"
        self.bin.mkdir()
        self.log = self.tmp / "calls.log"
        self.hs = self.tmp / "hammerspoon"
        for name in ("open", "killall", "brew", "sleep"):
            self.fake(name, f'echo "{name} $*" >> "$LOG"')
        self.fake("pgrep", "exit 0")
        self.env = {"PATH": f"{self.bin}:/usr/bin:/bin", "HOME": str(self.tmp), "LOG": str(self.log),
                    "HAMMERSPOON_DIR": str(self.hs)}

    def fake(self, name, body):
        p = self.bin / name
        p.write_text(f"#!/bin/bash\n{body}\n")
        p.chmod(0o755)

    def run_setup(self, *args):
        r = subprocess.run(["bash", str(SETUP), *args], capture_output=True, text=True, env=self.env)
        return r, (json.loads(r.stdout) if r.stdout.strip().startswith("{") else None)

    def test_check_on_empty_dir_lists_missing_and_changes_nothing(self):
        r, state = self.run_setup("--check")
        self.assertEqual(r.returncode, 1, r.stderr)
        self.assertEqual(state["missing"], ["spoon", "load_line"])
        self.assertFalse(self.hs.exists())

    def test_install_twice_is_idempotent_and_follows_symlink(self):
        real = self.tmp / "dotfiles" / "init.lua"
        real.parent.mkdir()
        real.write_text("hs.autoLaunch(true)")  # no trailing newline
        self.hs.mkdir()
        (self.hs / "init.lua").symlink_to(real)
        for _ in range(2):
            r, state = self.run_setup("--install")
            self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(state["missing"], [])
        self.assertEqual(state["spoon_installed_version"], state["spoon_plugin_version"])
        self.assertEqual(state["init_lua_symlink_to"], str(real))
        self.assertTrue((self.hs / "init.lua").is_symlink())
        self.assertEqual(real.read_text(), f"hs.autoLaunch(true)\n{LOAD}\n")
        self.assertTrue((self.hs / "Spoons" / "NeedsYou.spoon" / "init.lua").is_file())
        self.assertIn("hammerspoon://needs-you?session=needs-you-setup-test", self.log.read_text())

    def test_commented_load_line_does_not_count(self):
        self.hs.mkdir()
        (self.hs / "init.lua").write_text(f"-- {LOAD}\n")
        _, state = self.run_setup("--check")
        self.assertIn("load_line", state["missing"])

    def test_single_quoted_load_line_counts_and_is_not_duplicated(self):
        self.hs.mkdir()
        (self.hs / "init.lua").write_text("hs.loadSpoon('NeedsYou'):start()\n")
        r, state = self.run_setup("--install")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual((self.hs / "init.lua").read_text().count("loadSpoon"), 1)

    def test_old_binding_is_reported(self):
        self.hs.mkdir()
        (self.hs / "init.lua").write_text(f'{LOAD}\nhs.urlevent.bind("needs-you", function() end)\n')
        _, state = self.run_setup("--check")
        self.assertIn("remove_old_binding", state["missing"])

    def test_bad_argument_exits_64(self):
        r, _ = self.run_setup("--nope")
        self.assertEqual(r.returncode, 64)


if __name__ == "__main__":
    unittest.main()
