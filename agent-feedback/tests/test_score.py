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


class ScoreProcessTest(unittest.TestCase):
    A, B, C = "20261110-100000-aaaa", "20261110-110000-bbbb", "20261110-120000-cccc"

    def snap(self, states, links=None, briefs=(), repo_changed=False):
        entries = {i: {"state": s, "link": (links or {}).get(i, "")} for i, s in states.items()}
        return {"entries": entries, "briefs": list(briefs), "repo_changed": repo_changed}

    def score(self, expect, snap, final="", denials=(), error=None):
        return run_evals.score_process(expect, snap, final, list(denials), error)

    def test_states_must_match(self):
        expect = {"states": {self.A: ["inbox"], self.C: ["wontfix", "done"]}}
        self.assertTrue(self.score(expect, self.snap({self.A: "inbox", self.C: "done"}))["passed"])
        r = self.score(expect, self.snap({self.A: "proposed", self.C: "done"}))
        self.assertFalse(r["passed"])
        self.assertIn(self.A, r["reasons"][0])

    def test_same_row_needs_both_ids_on_one_line_by_suffix(self):
        expect = {"same_row": [self.A, self.B]}
        snap = self.snap({})
        self.assertTrue(self.score(expect, snap, final="| README path | aaaa, bbbb | 2 |")["passed"])
        self.assertFalse(self.score(expect, snap, final="| x | aaaa |\n| y | bbbb |")["passed"])

    def test_same_link_must_be_one_existing_brief(self):
        expect = {"same_link": [self.A, self.B]}
        ok = self.snap({self.A: "proposed", self.B: "proposed"},
                       links={self.A: "/s/briefs/readme.md", self.B: "/s/briefs/readme.md"}, briefs=["readme.md"])
        self.assertTrue(self.score(expect, ok)["passed"])
        split = self.snap({self.A: "proposed", self.B: "proposed"},
                          links={self.A: "briefs/a.md", self.B: "briefs/b.md"}, briefs=["a.md", "b.md"])
        self.assertFalse(self.score(expect, split)["passed"])
        missing = self.snap({self.A: "proposed", self.B: "proposed"},
                            links={self.A: "briefs/x.md", self.B: "briefs/x.md"}, briefs=[])
        self.assertFalse(self.score(expect, missing)["passed"])

    def test_no_briefs_and_repo_unchanged(self):
        expect = {"no_briefs": True, "repo_unchanged": True}
        self.assertTrue(self.score(expect, self.snap({}))["passed"])
        self.assertFalse(self.score(expect, self.snap({}, briefs=["x.md"]))["passed"])
        self.assertFalse(self.score(expect, self.snap({}, repo_changed=True))["passed"])

    def test_process_script_denial_and_errors_fail(self):
        d = [{"tool_name": "Bash", "tool_input": {"command": "/p/scripts/process.py list"}}]
        self.assertFalse(self.score({}, self.snap({}), denials=d)["passed"])
        self.assertFalse(self.score({}, self.snap({}), error="exit 1")["passed"])


if __name__ == "__main__":
    unittest.main()
