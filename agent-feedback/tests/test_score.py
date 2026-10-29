"""Tests for the scoring in evals/run_evals.py."""

import importlib.util
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "run_evals", Path(__file__).resolve().parents[1] / "evals" / "run_evals.py")
run_evals = importlib.util.module_from_spec(spec)
spec.loader.exec_module(run_evals)
score = run_evals.score


class ScoreTest(unittest.TestCase):
    POSITIVE = {"capture": True, "source": ["agent"], "kind": ["docs", "instruction"]}

    def test_positive_passes_with_matching_entry(self):
        r = score(self.POSITIVE, [{"source": "agent", "kind": "docs"}], denials=[])
        self.assertTrue(r["passed"], r)

    def test_positive_fails_without_entry(self):
        r = score(self.POSITIVE, [], denials=[])
        self.assertFalse(r["passed"])
        self.assertIn("no entry", r["reasons"][0])

    def test_any_matching_entry_is_enough(self):
        entries = [{"source": "agent", "kind": "access"}, {"source": "agent", "kind": "instruction"}]
        self.assertTrue(score(self.POSITIVE, entries, denials=[])["passed"])

    def test_wrong_source_or_kind_fails(self):
        self.assertFalse(score(self.POSITIVE, [{"source": "user", "kind": "docs"}], denials=[])["passed"])
        self.assertFalse(score(self.POSITIVE, [{"source": "agent", "kind": "infra"}], denials=[])["passed"])

    def test_blank_kind_fails_when_kinds_expected(self):
        self.assertFalse(score(self.POSITIVE, [{"source": "agent", "kind": ""}], denials=[])["passed"])

    def test_negative_passes_only_when_empty(self):
        neg = {"capture": False}
        self.assertTrue(score(neg, [], denials=[])["passed"])
        self.assertFalse(score(neg, [{"source": "agent", "kind": "docs"}], denials=[])["passed"])

    def test_capture_script_denial_fails(self):
        r = score(self.POSITIVE, [{"source": "agent", "kind": "docs"}],
                  denials=[{"tool_name": "Bash", "tool_input": {"command": "/x/scripts/capture.py add"}}])
        self.assertFalse(r["passed"])
        self.assertIn("denied", r["reasons"][0])

    def test_skill_denial_fails(self):
        r = score(self.POSITIVE, [],
                  denials=[{"tool_name": "Skill", "tool_input": {"skill": "agent-feedback:capture"}}])
        self.assertIn("denied", r["reasons"][0])

    def test_failed_run_fails_even_negative(self):
        r = score({"capture": False}, [], denials=[], error="exit 1: auth failed")
        self.assertFalse(r["passed"])
        self.assertIn("run failed", r["reasons"][0])

    def test_other_denials_are_ignored(self):
        r = score(self.POSITIVE, [{"source": "agent", "kind": "docs"}],
                  denials=[{"tool_name": "WebFetch", "tool_input": {"url": "https://example.com"}}])
        self.assertTrue(r["passed"])


if __name__ == "__main__":
    unittest.main()
