#!/usr/bin/env python3
"""Measure what a plan (or any subject) cost, from local coding-agent transcripts.

Reads Claude Code session files and the OpenCode SQLite database (v1 and v2
shapes), selects the sessions that mention the subject's keys, and reports
attended time, agent-busy time, human touches, why the agent stopped, what
filled its context, and which tasks dominated, with a short list of findings.

    telemetry.py report <plan-file> [--repo DIR] [--key K ...] [--json] [--sessions]
    telemetry.py close <plan-file> [--repo DIR]
    telemetry.py baseline [--format 2.1] [--json]
    telemetry.py sources [--repo DIR]

Read-only on every source. Never prints or stores transcript text, prompts or
session titles: only ids, timestamps, categories, counts, byte sizes and stop
reasons.

Paths (first match wins):
  storage   --home, $SESSION_TELEMETRY_HOME, $XDG_DATA_HOME/session-telemetry,
            ~/.local/share/session-telemetry
  Claude    $CLAUDE_CONFIG_DIR/projects, ~/.claude/projects
  OpenCode  $OPENCODE_DB, ~/.local/share/opencode/opencode.db (opened mode=ro)

A missing source is reported under "coverage", never an error.

Exit codes:
  0  ok
  1  no sessions matched the subject (report/close), or no ledger rows (baseline)
 64  usage error
 66  plan file not readable
"""

import argparse
import collections
import datetime
import glob
import json
import os
import pathlib
import re
import sqlite3
import statistics
import subprocess
import sys

VERSION = "1.0.0"
IDLE = 600  # s; a step longer than this is capped: the agent was stalled, not working
TOOL_CAP = 3 * 3600  # s; a single tool call longer than this is not work
LONG_CALL = 600  # s; a ceremony-classified call this long is a wait (CI inside a plan command)
AWAY = 3600  # s; a human gap this long means the person left

# ------------------------------------------------------------ classification

READ_TOOLS = {"Read", "read", "Grep", "grep", "Glob", "glob", "list"}
EDIT_TOOLS = {"Edit", "Write", "MultiEdit", "patch", "edit", "write", "apply_patch", "NotebookEdit"}
SHELL_TOOLS = {"Bash", "PowerShell", "shell", "bash"}
ASK_TOOLS = {"AskUserQuestion", "question"}
VERIFY_RE = re.compile(
    r"\b(pnpm|npm|npx|yarn|cargo|uv run|pytest|ruff|tsc|vitest|jest|playwright|eslint|golden:|"
    r"check:bundle|docs-check|bun|make|go test|dotnet)\b"
)
WAIT_RE = re.compile(r"Start-Sleep|\bsleep\b|Wait-Process|Wait-Job")
SHELL_READ_RE = re.compile(
    r"Get-Content|Select-String|\bcat\b|sed -n|\bhead\b|\btail\b|\brg\b|\bgrep\b|Get-ChildItem|"
    r"\bls\b|\bawk\b|\bwc\b"
)
SHELL_WRITE_RE = re.compile(
    r"write_text|writeFileSync|Set-Content|WriteAllText|Out-File|sed -i|cat >>|cat >|\.write\(|"
    r"Add-Content"
)
ORIENT_RE = re.compile(
    r"AGENTS\.md|CLAUDE\.md|README\.md|docs[\\/]+explorations|requirements|architecture\.md|SKILL\.md"
)
PLANDIR_RE = re.compile(r"docs[\\/]+plans")


def classify(tool, inp):
    """Category of one tool call. Rule order matters: a shell command that
    writes to the plan and then runs the checker is a plan write."""
    s = json.dumps(inp, ensure_ascii=False)
    if tool in SHELL_TOOLS and PLANDIR_RE.search(s) and SHELL_WRITE_RE.search(s):
        return "plan_write_script"
    if "check-plan" in s:
        return "plan_check"
    if "plan-status" in s:
        return "plan_status_set" if re.search(r"\b(set|set-plan|resume|decision|note)\b", s) else "plan_read"
    if tool in ("Skill", "skill"):
        return "plan_read" if "manual-planning" in s else "orientation"
    if tool in ASK_TOOLS:
        return "ask_user"
    if tool in ("Agent", "Task", "task"):
        return "delegate"
    if tool in ("TodoWrite", "todowrite", "TaskCreate", "TaskUpdate"):
        return "todo_list"
    plan = bool(PLANDIR_RE.search(s))
    if tool in EDIT_TOOLS:
        return "plan_write" if plan else ("docs_edit" if re.search(r"\.md\b", s) else "code_edit")
    if tool in READ_TOOLS:
        return "plan_read" if plan else ("orientation" if ORIENT_RE.search(s) else "code_read")
    if tool in SHELL_TOOLS:
        if WAIT_RE.search(s):
            return "wait_poll"
        if plan and SHELL_WRITE_RE.search(s):
            return "plan_write_script"
        if re.search(r"\bgit\b", s) and not VERIFY_RE.search(s):
            return "git"
        if VERIFY_RE.search(s):
            return "verify"
        if plan:
            return "plan_read"
        if re.search(r"agent-browser|chrome-devtools|playwright-cli", s):
            return "e2e_manual"
        if SHELL_WRITE_RE.search(s):
            return "code_edit_script"
        if SHELL_READ_RE.search(s):
            return "orientation" if ORIENT_RE.search(s) else "code_read"
        return "shell_other"
    if "chrome-devtools" in tool or "browser" in tool.lower():
        return "e2e_manual"
    return "other"


CEREMONY = {"plan_read", "plan_write", "plan_write_script", "plan_check", "plan_status_set"}
PRODUCTIVE = {"code_edit", "code_edit_script", "verify", "e2e_manual"}

STOP_REASONS = ("done", "ask", "gate", "question", "context", "limit")
STOP_LINE_RE = re.compile(
    r"^[\s>*_`]*Stop[*_`]*\s*:[*_`]*\s*[*_`]*(done|ask|gate|question|context|limit)\b[*_`]*"
    r"\s*(?:[—:-]+\s*(.*))?$",
    re.I | re.M,
)
STOP_PATTERNS = [
    ("limit", r"usage limit|rate limit|out of (credits|tokens)"),
    ("context", r"context (window|limit|is (getting )?(full|large|high))|handover|fresh session|new session"),
    (
        "asks_permission",
        r"(want me to|should I|shall I|unless you say|do you want|your call|let me know|approve|"
        r"confirm|ok to|okay to|go ahead)",
    ),
    ("blocked", r"\b(blocked|cannot proceed|can't proceed|stuck|waiting (on|for) (you|your))"),
    ("reports_done", r"\b(done|completed|complete|finished|all green|passes|passed|committed|ready)\b"),
]
FOOTER_RE = re.compile(r"\**Blocked on me\**:?\s*(.*?)(?:\n\s*\n|\**Changed|$)", re.S | re.I)
HANDOVER_RE = re.compile(
    r"hand-?over|clean session|fresh session|new session|context (is )?(too )?(big|full|large)",
    re.I,
)


def stop_reason(text, last_was_tool):
    """(reason, explicit, detail_empty). An explicit `Stop:` line wins; the
    regex classifier is the fallback for sessions without one."""
    if last_was_tool:
        return "interrupted_midwork", False, None
    text = text or ""
    lines = STOP_LINE_RE.findall(text)
    if lines:
        reason, detail = lines[-1]
        return "stop:" + reason.lower(), True, not (detail or "").strip()
    f = FOOTER_RE.search(text)
    if f:
        if not re.match(r"\W*none\b", f.group(1).strip(), re.I):
            return "blocked_on_user", False, None
        text = text[: f.start()]
    t = text[-900:]
    for name, pat in STOP_PATTERNS:
        if re.search(pat, t, re.I):
            return name, False, None
    if t.rstrip().endswith("?"):
        return "asks_permission", False, None
    return "other", False, None


# --------------------------------------------------------- normalised model


class Session:
    def __init__(self, sid, harness):
        self.sid, self.harness = sid, harness
        self.prompts = []  # (t, is_handover_request) -- the text itself is never kept
        self.steps = []  # (start, end, final text, [tool dicts]); text is used only to classify
        self.compactions = 0

    def finish(self):
        self.steps.sort(key=lambda s: s[0])
        self.prompts.sort()


def tool(name, inp, start, end, result_len):
    inp = inp or {}
    return {
        "name": name,
        "cat": classify(name, inp),
        "start": start,
        "end": end,
        "rlen": result_len,
        "set": status_sets(inp),
    }


SET_RE = re.compile(r"plan-status\.py\S*\s+\S+\s+set\s+([0-9][0-9.]*)\s+\W{0,2}([A-Z][A-Z ]+)")


def status_sets(inp):
    """(task id, status) pairs a tool call sets through `plan-status.py set`."""
    s = json.dumps(inp, ensure_ascii=False).replace('\\"', '"')
    return [(m.group(1).rstrip("."), m.group(2).strip()) for m in SET_RE.finditer(s)]


def rlen(content):
    if isinstance(content, str):
        return len(content)
    return sum(len(c.get("text", "")) for c in content or [] if isinstance(c, dict))


def human_text(c):
    return (
        isinstance(c, str)
        and not c.startswith("<local-command")
        and not c.startswith("<command-")
        and not c.startswith("Caveat:")
        and "<system-reminder>" not in c[:200]
    )


class Coverage:
    """What each adapter found and what it did not recognise."""

    def __init__(self):
        self.sources = collections.OrderedDict()
        self.sessions = collections.Counter()
        self.records = collections.Counter()
        self.unknown = collections.Counter()

    def as_dict(self):
        total = sum(self.records.values())
        unknown = sum(self.unknown.values())
        return {
            "sources": dict(self.sources),
            "sessions": dict(self.sessions),
            "records": total,
            "unrecognised": unknown,
            "unrecognised_pct": round(100.0 * unknown / total, 2) if total else 0.0,
            "unrecognised_types": dict(self.unknown.most_common(8)),
        }


CLAUDE_TYPES = {
    "user", "assistant", "system", "ai-title", "summary", "attachment", "mode", "atis-latch",
    "last-prompt", "bridge-session", "permission-mode", "file-history-delta",
    "file-history-snapshot", "queue-operation", "agent-name", "cost-state", "custom-title",
}
OC_V2_TYPES = {"user", "assistant", "compaction", "synthetic", "idle", "system", "agent-switched",
               "model-switched"}
OC_V1_PARTS = {"text", "tool", "reasoning", "step-start", "step-finish", "patch", "file",
               "compaction", "snapshot", "agent", "subtask", "retry"}


def claude_projects_dir():
    base = os.environ.get("CLAUDE_CONFIG_DIR")
    if base:
        return os.path.join(base, "projects")
    return os.path.join(os.path.expanduser("~"), ".claude", "projects")


def claude_project_dir(repo):
    """Claude Code names a project folder after its path, every non-alphanumeric
    character replaced by '-'. Matched case-insensitively (drive letters vary)."""
    root = claude_projects_dir()
    want = re.sub(r"[^A-Za-z0-9-]", "-", os.path.abspath(repo).rstrip("\\/")).lower()
    try:
        for name in os.listdir(root):
            if name.lower() == want:
                return os.path.join(root, name)
    except OSError:
        return None
    return None


def ts(value):
    return datetime.datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()


def load_claude(repo, keys, cov):
    d = claude_project_dir(repo)
    cov.sources["claude"] = d or "missing (%s)" % claude_projects_dir()
    out = []
    if not d:
        return out
    for f in sorted(glob.glob(os.path.join(d, "*.jsonl"))):
        try:
            raw = open(f, encoding="utf-8").read()
        except (OSError, UnicodeDecodeError):
            continue
        if not any(k in raw for k in keys):
            continue
        s = Session(os.path.basename(f)[:8], "claude")
        pend, msgs = {}, collections.OrderedDict()
        last_nonassist = None
        for line in raw.splitlines():
            try:
                r = json.loads(line)
            except ValueError:
                cov.records["claude"] += 1
                cov.unknown["claude:<bad json>"] += 1
                continue
            cov.records["claude"] += 1
            if r.get("type") not in CLAUDE_TYPES:
                cov.unknown["claude:%s" % r.get("type")] += 1
            if r.get("type") == "system" and r.get("subtype") == "compact_boundary":
                s.compactions += 1
            if r.get("isSidechain") or "timestamp" not in r:
                continue
            t = ts(r["timestamp"])
            if r.get("type") == "assistant":
                m = r.get("message") or {}
                e = msgs.setdefault(
                    m.get("id"), {"start": last_nonassist or t, "end": t, "text": "", "tools": []}
                )
                e["end"] = t
                for b in m.get("content") or []:
                    if not isinstance(b, dict):
                        continue
                    if b.get("type") == "text":
                        e["text"] += b.get("text", "")
                    elif b.get("type") == "tool_use":
                        tl = tool(b.get("name", "?"), b.get("input"), t, t, 0)
                        e["tools"].append(tl)
                        pend[b.get("id")] = tl
            elif r.get("type") == "user":
                c = (r.get("message") or {}).get("content")
                if isinstance(c, list):
                    for x in c:
                        if isinstance(x, dict) and x.get("type") == "tool_result" and x.get("tool_use_id") in pend:
                            tl = pend.pop(x["tool_use_id"])
                            tl["end"] = t
                            tl["rlen"] = rlen(x.get("content"))
                elif not r.get("isMeta") and human_text(c):
                    s.prompts.append((t, bool(HANDOVER_RE.search(c))))
                last_nonassist = t
        s.steps = [(e["start"], e["end"], e["text"], e["tools"]) for e in msgs.values()]
        s.finish()
        out.append(s)
        cov.sessions["claude"] += 1
    return out


def opencode_db():
    return os.environ.get("OPENCODE_DB") or os.path.join(
        os.path.expanduser("~"), ".local", "share", "opencode", "opencode.db"
    )


def open_opencode(cov):
    path = opencode_db()
    if not os.path.isfile(path):
        cov.sources["opencode"] = "missing (%s)" % path
        return None, set()
    try:
        c = sqlite3.connect(pathlib.Path(path).resolve().as_uri() + "?mode=ro", uri=True)
        tables = {r[0] for r in c.execute("select name from sqlite_master where type='table'")}
    except sqlite3.Error as exc:
        cov.sources["opencode"] = "unreadable (%s): %s" % (path, exc)
        return None, set()
    shapes = [v for v, need in (("v2", {"session_v2", "session_message"}),
                                ("v1", {"session", "message", "part"})) if need <= tables]
    cov.sources["opencode"] = "%s (%s)" % (path, "+".join(shapes) or "no known tables")
    return c, tables


def load_opencode(repo, keys, cov):
    out = []
    c, tables = open_opencode(cov)
    if c is None:
        return out
    fwd = os.path.abspath(repo).replace("\\", "/").rstrip("/").lower()
    like = " or ".join(["data like ?"] * len(keys))
    params = ["%" + k + "%" for k in keys]
    dir_sql = "replace(lower(directory), '\\', '/') = ?"
    if {"session_v2", "session_message"} <= tables:
        rows = c.execute(
            "select id from session_v2 where %s and parent_id is null" % dir_sql, (fwd,)
        ).fetchall()
        for (sid,) in rows:
            if not c.execute(
                "select 1 from session_message where session_id=? and (%s) limit 1" % like,
                [sid] + params,
            ).fetchone():
                continue
            s = Session(sid[-8:], "opencode")
            for typ, tc, d in c.execute(
                "select type,time_created,data from session_message where session_id=? order by seq",
                (sid,),
            ):
                cov.records["opencode"] += 1
                if typ not in OC_V2_TYPES:
                    cov.unknown["opencode:%s" % typ] += 1
                try:
                    j = json.loads(d)
                except ValueError:
                    cov.unknown["opencode:<bad json>"] += 1
                    continue
                if typ == "compaction":
                    s.compactions += 1
                elif typ == "user":
                    s.prompts.append((tc / 1000, bool(HANDOVER_RE.search(j.get("text", "") or ""))))
                elif typ == "assistant":
                    tm = j.get("time", {})
                    st = tm.get("created", tc) / 1000
                    en = (tm.get("completed") or tm.get("created", tc)) / 1000
                    text, tools = "", []
                    for b in j.get("content", []):
                        if b.get("type") == "text":
                            text += b.get("text", "")
                        elif b.get("type") == "tool":
                            stt = b.get("state", {})
                            tools.append(tool(b.get("name", "?"), stt.get("input"), en, en, rlen(stt.get("content"))))
                    s.steps.append((st, en, text, tools))
            # v2 has no per-tool timing: the gap to the next step is the tool time.
            for i, (st, en, text, tools) in enumerate(s.steps[:-1]):
                nxt = s.steps[i + 1][0]
                if tools and 0 < nxt - en < IDLE * 6:
                    for tl in tools:
                        tl["end"] = en + (nxt - en) / len(tools)
            s.finish()
            out.append(s)
            cov.sessions["opencode"] += 1
    if {"session", "message", "part"} <= tables:
        rows = c.execute(
            "select id from session where %s and parent_id is null" % dir_sql, (fwd,)
        ).fetchall()
        for (sid,) in rows:
            if not c.execute(
                "select 1 from part where session_id=? and (%s) limit 1" % like, [sid] + params
            ).fetchone():
                continue
            s = Session(sid[-8:], "opencode-v1")
            role = {}
            for mid, tc, d in c.execute("select id,time_created,data from message where session_id=?", (sid,)):
                j = json.loads(d)
                role[mid] = (
                    j.get("role"),
                    j.get("time", {}),
                    j.get("summary") is True or j.get("mode") == "compaction",
                )
            steps = collections.OrderedDict()
            for mid, tc, d in c.execute(
                "select message_id,time_created,data from part where session_id=? order by time_created",
                (sid,),
            ):
                cov.records["opencode-v1"] += 1
                j = json.loads(d)
                if j.get("type") not in OC_V1_PARTS:
                    cov.unknown["opencode-v1:%s" % j.get("type")] += 1
                r, tm, _ = role.get(mid, ("?", {}, False))
                if j.get("type") == "compaction":
                    s.compactions += 1
                if r == "user":
                    if j.get("type") == "text" and not j.get("synthetic"):
                        s.prompts.append(
                            (tm.get("created", tc) / 1000, bool(HANDOVER_RE.search(j.get("text", "") or "")))
                        )
                    continue
                if r != "assistant":
                    continue
                e = steps.setdefault(
                    mid,
                    {
                        "start": tm.get("created", tc) / 1000,
                        "end": (tm.get("completed") or tm.get("created", tc)) / 1000,
                        "text": "",
                        "tools": [],
                    },
                )
                if j.get("type") == "text":
                    e["text"] += j.get("text", "")
                elif j.get("type") == "tool":
                    stt = j.get("state", {})
                    tt = stt.get("time", {})
                    st = tt.get("start", tc) / 1000
                    en = tt.get("end", tt.get("start", tc)) / 1000
                    e["tools"].append(tool(j.get("tool", "?"), stt.get("input"), st, en, len(str(stt.get("output", "")))))
                    e["end"] = max(e["end"], en)
            s.compactions += sum(1 for r, tm, comp in role.values() if comp)
            s.steps = [(e["start"], e["end"], e["text"], e["tools"]) for e in steps.values()]
            s.finish()
            out.append(s)
            cov.sessions["opencode-v1"] += 1
    c.close()
    return out


# ------------------------------------------------------------------ metrics


def session_metrics(s):
    if not s.steps:
        return None
    m = {"sid": s.sid, "harness": s.harness, "prompts": len(s.prompts), "compactions": s.compactions,
         "handover_prompts": sum(1 for _, h in s.prompts if h)}
    events = [(t, "prompt", None) for t, _ in s.prompts] + [(st[0], "step", st) for st in s.steps]
    events.sort(key=lambda e: e[0])
    m["start"], m["end"] = events[0][0], max(max(st[1] for st in s.steps), events[-1][0])
    cat_time, cat_calls, cat_bytes = collections.Counter(), collections.Counter(), collections.Counter()
    ask_time = 0.0
    for st, en, txt, tl in s.steps:
        dur = min(IDLE, max(0.0, en - st))
        cats = [t["cat"] for t in tl] or ["narration"]
        for c in cats:
            cat_time[c] += dur / len(cats)
        for t in tl:
            td = max(0.0, t["end"] - t["start"])
            cat = t["cat"]
            if cat == "ask_user":
                ask_time += td
                td = 0
            elif td > TOOL_CAP:
                td = 0
            elif td > LONG_CALL and cat in CEREMONY:
                cat = "long_wait"
            cat_time[cat] += td
            cat_calls[t["cat"]] += 1
            cat_bytes[t["cat"]] += t["rlen"]
    m["span"] = m["end"] - m["start"]
    m["busy"] = sum(cat_time.values())
    m["ask_time"] = ask_time
    m["cat_time"], m["cat_calls"], m["cat_bytes"] = cat_time, cat_calls, cat_bytes
    stops, runs = [], []
    seg_busy, last_step = 0.0, None

    def close(last, wait, prefix=""):
        st, en, txt, tl = last
        reason, explicit, empty = stop_reason(txt, bool(tl) and not txt.strip())
        stops.append({"reason": prefix + reason, "wait": wait, "explicit": explicit, "detail_empty": empty})

    for t, kind, payload in events:
        if kind == "prompt":
            if last_step is not None:
                close(last_step, max(0.0, t - last_step[1]))
                runs.append(seg_busy)
            seg_busy, last_step = 0.0, None
        else:
            st, en, txt, tl = payload
            seg_busy += min(IDLE, max(0.0, en - st)) + sum(
                min(TOOL_CAP, max(0.0, x["end"] - x["start"])) for x in tl if x["cat"] != "ask_user"
            )
            last_step = payload
    if last_step is not None:
        close(last_step, 0.0, "session_end:")
        runs.append(seg_busy)
    m["stops"], m["runs"] = stops, runs
    first_prod, plan_bytes = None, 0
    for st, en, txt, tl in s.steps:
        for t in tl:
            if t["cat"] in PRODUCTIVE and first_prod is None:
                first_prod = t["start"]
            if first_prod is None and t["cat"] == "plan_read":
                plan_bytes += t["rlen"]
    t0 = s.prompts[0][0] if s.prompts else m["start"]
    m["resume_s"] = (first_prod - t0) if first_prod else None
    m["resume_plan_bytes"] = plan_bytes
    m["calls"] = [(t["start"], t["cat"], t["set"]) for st in s.steps for t in st[3]]
    return m


def local(t, fmt="%Y-%m-%d %H:%M"):
    return datetime.datetime.fromtimestamp(t).strftime(fmt)


def pctl(values, q):
    values = sorted(values)
    return values[int(q * (len(values) - 1))] if values else 0.0


def aggregate(ms):
    ms = sorted((m for m in ms if m), key=lambda m: m["start"])
    A = {"sessions": len(ms)}
    if not ms:
        return A
    A["window"] = [local(min(m["start"] for m in ms)), local(max(m["end"] for m in ms))]
    A["window_epoch"] = [min(m["start"] for m in ms), max(m["end"] for m in ms)]
    A["calendar_h"] = (max(m["end"] for m in ms) - min(m["start"] for m in ms)) / 3600
    away = sum(s["wait"] for m in ms for s in m["stops"] if s["wait"] > AWAY)
    A["attended_h"] = (sum(m["span"] for m in ms) - away) / 3600
    A["busy_h"] = sum(m["busy"] for m in ms) / 3600
    A["busy_pct_of_attended"] = 100 * A["busy_h"] / A["attended_h"] if A["attended_h"] > 0 else 0.0
    A["prompts"] = sum(m["prompts"] for m in ms)
    A["handover_prompts"] = sum(m["handover_prompts"] for m in ms)
    A["compactions"] = sum(m["compactions"] for m in ms)
    ct, cc, cb = collections.Counter(), collections.Counter(), collections.Counter()
    for m in ms:
        ct.update(m["cat_time"])
        cc.update(m["cat_calls"])
        cb.update(m["cat_bytes"])
    busy = sum(ct.values()) or 1
    A["ceremony_pct"] = 100 * sum(ct[c] for c in CEREMONY) / busy
    A["ceremony_calls_pct"] = 100 * sum(cc[c] for c in CEREMONY) / (sum(cc.values()) or 1)
    A["plan_script_writes"] = cc["plan_write_script"]
    A["plan_tool_writes"] = cc["plan_write"]
    A["cat_min"] = {k: round(v / 60, 1) for k, v in ct.most_common()}
    total_bytes = sum(cb.values()) or 1
    A["intake_kb"] = {k: round(v / 1024) for k, v in cb.most_common()}
    A["intake_pct"] = {k: round(100.0 * v / total_bytes, 1) for k, v in cb.most_common()}
    stops, wait = collections.Counter(), collections.Counter()
    explicit = ungated = 0
    runs = []
    for m in ms:
        for s in m["stops"]:
            stops[s["reason"]] += 1
            wait[s["reason"]] += min(s["wait"], AWAY)
            explicit += s["explicit"]
            ungated += bool(s["explicit"] and s["reason"].endswith("stop:ask") and s["detail_empty"])
        runs += m["runs"]
    A["stops"] = dict(stops.most_common())
    A["stop_wait_min"] = {k: round(v / 60, 1) for k, v in wait.items()}
    A["stops_total"] = sum(stops.values())
    A["stops_explicit"] = explicit
    A["stops_ungated_ask"] = ungated
    A["human_wait_h"] = sum(min(s["wait"], AWAY) for m in ms for s in m["stops"]) / 3600
    runs = [r / 60 for r in runs if r > 30]
    A["auto_run_min_median"] = statistics.median(runs) if runs else 0.0
    A["auto_run_min_p90"] = pctl(runs, 0.9)
    rs = [m["resume_s"] / 60 for m in ms if m["resume_s"] is not None]
    A["resume_min_median"] = statistics.median(rs) if rs else None
    A["resume_plan_kb_median"] = statistics.median([m["resume_plan_bytes"] / 1024 for m in ms])
    A["per_session"] = [
        {"sid": m["sid"], "harness": m["harness"], "start": local(m["start"], "%m-%d %H:%M"),
         "span_min": round(m["span"] / 60), "busy_min": round(m["busy"] / 60), "prompts": m["prompts"],
         "compactions": m["compactions"]}
        for m in ms
    ]
    return A


def per_task(ms, events):
    """Busy share per task. Task boundaries come from the manual-planning event
    log when it has status events, else from `plan-status.py set` calls found in
    the transcripts. Active time = gaps under 10 min between consecutive calls,
    attributed to the task most recently set IN PROGRESS."""
    calls = sorted(
        (t, m["sid"], cat, sets) for m in ms if m for t, cat, sets in m["calls"]
    )
    marks = []
    source = "transcripts"
    status_events = [e for e in events if e.get("event") == "status" and e.get("to") == "IN PROGRESS"]
    if status_events:
        source = "event log"
        for e in status_events:
            try:
                marks.append((ts(e["t"]), str(e.get("task"))))
            except (KeyError, ValueError, TypeError):
                continue
    else:
        for t, sid, cat, sets in calls:
            for tid, status in sets:
                if status == "IN PROGRESS":
                    marks.append((t, tid))
    if not marks:
        return {"source": None, "tasks": []}
    marks.sort()
    timeline = [(t, "mark", tid, None) for t, tid in marks] + [(t, "call", cat, sid) for t, sid, cat, _ in calls]
    timeline.sort(key=lambda x: (x[0], x[1] != "mark"))
    cur, last = "(before first task)", None
    dur, n, cer, sessions, first = (collections.Counter(), collections.Counter(), collections.Counter(),
                                    collections.defaultdict(set), {})
    for t, kind, value, sid in timeline:
        if kind == "mark":
            cur = value
            first.setdefault(value, t)
            continue
        if last is not None and t - last < IDLE:
            dur[cur] += t - last
        last = t
        n[cur] += 1
        cer[cur] += value in CEREMONY
        sessions[cur].add(sid)
    total = sum(dur.values()) or 1

    def key(tid):
        return tuple(int(x) for x in tid.split(".") if x.isdigit()) or (-1,)

    rows = [
        {"task": tid, "active_min": round(dur[tid] / 60, 1), "share_pct": round(100.0 * dur[tid] / total, 1),
         "calls": n[tid], "ceremony_calls": cer[tid], "sessions": len(sessions[tid]),
         "started": local(first[tid], "%m-%d %H:%M") if tid in first else ""}
        for tid in sorted(set(dur) | set(n), key=key)
    ]
    return {"source": source, "tasks": rows, "active_h": round(total / 3600, 2)}


# ------------------------------------------------------------------ subject


def git(args, cwd):
    try:
        out = subprocess.run(["git"] + args, cwd=cwd, capture_output=True, text=True, check=False,
                             encoding="utf-8", errors="replace")
    except OSError:
        return None
    return out.stdout if out.returncode == 0 else None


def mask(text):
    """Drop fenced blocks and HTML comments: examples are not the plan's own links."""
    text = re.sub(r"<!--.*?-->", "", text, flags=re.S)
    return re.sub(r"^(```|~~~).*?^\1[^\n]*$", "", text, flags=re.S | re.M)


def section(text, title):
    m = re.search(r"^##\s+%s\s*$(.*?)(?=^#{1,2}\s|\Z)" % re.escape(title), text, re.M | re.S)
    return m.group(1) if m else ""


# Markdown links from Context to dated explorations, proposals and reviews: the
# feature's earlier documents. Backticked paths are evidence citations, not scope.
LINKED_DOC_RE = re.compile(
    r"\]\(([^)\s]*?(?:exploration|proposal|review)[^)\s]*?\.md)(?:#[^)\s]*)?\)", re.I
)
DATED_RE = re.compile(r"^\d{4}-\d{2}-\d{2}-")


def derive_subject(plan_path, text, repo):
    stem = os.path.splitext(os.path.basename(plan_path))[0]
    base = stem[: -len("-plan")] if stem.endswith("-plan") else stem
    slug = re.sub(r"^\d{4}-\d{2}-\d{2}-", "", base)
    # The undated slug also matches the dated filename; use it unless it is too generic.
    keys = [slug if len(slug) >= 16 and slug.count("-") >= 2 else base]
    plan_dir = os.path.dirname(plan_path)
    companions = sorted(
        n for n in os.listdir(plan_dir)
        if n.startswith(base + "-") and n.endswith(".md") and n != os.path.basename(plan_path)
    )
    masked = mask(text)
    for comp in companions:
        try:
            masked += "\n" + mask(open(os.path.join(plan_dir, comp), encoding="utf-8").read())
        except (OSError, UnicodeDecodeError):
            pass
    namespaces = collections.Counter(re.findall(r"^###\s+([A-Z][A-Z0-9]*-DEC)-\d+", masked, re.M))
    namespace = namespaces.most_common(1)[0][0] if namespaces else None
    if namespace and namespace != "DEC":
        keys.append(namespace + "-")
    linked = []
    for target in LINKED_DOC_RE.findall(section(mask(text), "Context For A Clean Session")):
        doc = os.path.splitext(os.path.basename(target.split("#")[0]))[0]
        if DATED_RE.match(doc) and doc != stem and not doc.startswith(base):
            linked.append(doc)
    for doc in sorted(dict.fromkeys(linked), key=len):
        if not any(k in doc for k in keys):
            keys.append(doc)
    fmt = re.search(r"Plan Format\s*:\s*manual-planning\s+v(\d+\.\d+\.\d+)", text)
    status = re.search(r"^\s*-\s*Plan Status\s*:\s*(.+?)\s*$", text, re.M)
    return {
        "repo": os.path.abspath(repo),
        "repo_name": os.path.basename(os.path.abspath(repo).rstrip("\\/")),
        "plan": os.path.abspath(plan_path),
        "stem": stem,
        "format": fmt.group(1) if fmt else None,
        "plan_status": status.group(1) if status else None,
        "plan_kb": round(len(text.encode("utf-8")) / 1024),
        "companions": companions,
        "namespace": namespace,
        "linked_docs": list(dict.fromkeys(linked)),
        "keys": list(dict.fromkeys(keys)),
    }


def event_log(plan_path, repo):
    """Records of manual-planning's status event log, looked up next to the plan
    first, then in the repository (a plan snapshot outside its repo)."""
    stem = os.path.splitext(os.path.basename(plan_path))[0]
    name = "manual-planning/%s.events.jsonl" % stem
    for cwd in (os.path.dirname(plan_path), repo):
        rel = git(["rev-parse", "--git-path", name], cwd)
        candidates = [os.path.join(cwd, rel.strip())] if rel else []
        candidates.append(os.path.join(os.path.dirname(plan_path), ".manual-planning", stem + ".events.jsonl"))
        for path in candidates:
            if os.path.isfile(path):
                out = []
                with open(path, encoding="utf-8") as fh:
                    for line in fh:
                        try:
                            rec = json.loads(line)
                        except ValueError:
                            continue
                        if isinstance(rec, dict):
                            out.append(rec)
                return path, out
    return None, []


def outcomes(subject, A):
    """Lagging quality signals: reverts in the plan's window, TODOs filed against it."""
    out = {"reverts": None, "todos": None, "todo_file": None}
    if "window_epoch" in A:
        since = datetime.datetime.fromtimestamp(A["window_epoch"][0]).isoformat()
        until = datetime.datetime.fromtimestamp(A["window_epoch"][1] + 7 * 86400).isoformat()
        log = git(["log", "--since=" + since, "--until=" + until, "--format=%s"], subject["repo"])
        if log is not None:
            out["reverts"] = sum(1 for s in log.splitlines() if s.startswith("Revert"))
    for rel in ("docs/todo/TODO.md", "TODO.md", "docs/TODO.md"):
        path = os.path.join(subject["repo"], rel)
        if os.path.isfile(path):
            text = open(path, encoding="utf-8", errors="replace").read()
            refs = [subject["stem"]] + ([subject["namespace"] + "-"] if subject["namespace"] else [])
            items = re.split(r"^(?=#{2,4}\s|- \[)", text, flags=re.M)
            out["todos"] = sum(1 for it in items if any(r in it for r in refs))
            out["todo_file"] = rel
            break
    return out


# ----------------------------------------------------------------- findings


def findings(A, tasks):
    """Report rules: (area, finding) pairs."""
    out = []
    if not A.get("sessions"):
        return out
    if A["resume_plan_kb_median"] > 15:
        out.append(("context", "median session read %.0f KB of plan before its first productive action "
                          "(target <= 15 KB): start with `plan-status.py brief`" % A["resume_plan_kb_median"]))
    context = sum(v for k, v in A["stops"].items() if k.endswith("context") or k.endswith("limit"))
    handovers = A["handover_prompts"]
    if A["sessions"] >= 3 and (context + handovers) >= 0.3 * A["sessions"]:
        out.append(("handover", "%d context/limit stops and %d handover requests across %d sessions: "
                             "hand over through the Resume block and cut context intake"
                    % (context, handovers, A["sessions"])))
    asks = sum(v for k, v in A["stops"].items() if k.endswith("asks_permission") or k.endswith("stop:ask"))
    if asks >= 3 or A["stops_ungated_ask"] >= 2:
        out.append(("autonomy", "%d stops asked to continue (%d explicit `Stop: ask` with no gate named): "
                          "continue unless a Project Gate needs the user" % (asks, A["stops_ungated_ask"])))
    if A["auto_run_min_median"] < 20:
        out.append(("autonomy", "median autonomous run %.1f min (target >= 20 min)" % A["auto_run_min_median"]))
    if A["plan_script_writes"]:
        out.append(("plan-writes", "%d plan writes through ad-hoc shell scripts (should be 0): use the Edit tool "
                          "or `plan-status.py`" % A["plan_script_writes"]))
    for row in tasks.get("tasks", []):
        if row["task"][0].isdigit() and row["share_pct"] > 30:
            out.append(("task-size", "Task %s took %.0f%% of active agent time across %d session(s): split it into "
                              "gated, session-sized subtasks" % (row["task"], row["share_pct"], row["sessions"])))
        elif row["task"][0].isdigit() and row["sessions"] > 3:
            out.append(("task-size", "Task %s spanned %d sessions" % (row["task"], row["sessions"])))
    fmt = tuple(int(x) for x in (A.get("format") or "0.0.0").split("."))
    if A["stops_total"] and A["stops_explicit"] == 0 and fmt >= (2, 1, 0):
        out.append(("stop-line", "no explicit `Stop:` lines found; the stop mix below is the regex fallback"))
    if A["ceremony_pct"] > 30:
        out.append(("ceremony", "ceremony is %.0f%% of busy time" % A["ceremony_pct"]))
    return out


# ------------------------------------------------------------------ storage


def home(args):
    for value in (getattr(args, "home", None), os.environ.get("SESSION_TELEMETRY_HOME")):
        if value:
            return os.path.abspath(value)
    xdg = os.environ.get("XDG_DATA_HOME")
    if xdg:
        return os.path.join(xdg, "session-telemetry")
    return os.path.join(os.path.expanduser("~"), ".local", "share", "session-telemetry")


def read_ledger(root):
    rows = []
    try:
        with open(os.path.join(root, "ledger.jsonl"), encoding="utf-8") as fh:
            for line in fh:
                try:
                    rows.append(json.loads(line))
                except ValueError:
                    continue
    except OSError:
        pass
    return rows


# ------------------------------------------------------------------ commands


def build_report(args):
    plan_path = os.path.abspath(args.plan)
    try:
        text = open(plan_path, encoding="utf-8").read()
    except (OSError, UnicodeDecodeError) as exc:
        sys.stderr.write("error: cannot read plan %s: %s\n" % (args.plan, exc))
        return None, 66
    repo = args.repo or (git(["rev-parse", "--show-toplevel"], os.path.dirname(plan_path)) or "").strip()
    if not repo:
        repo = os.path.dirname(plan_path)
        sys.stderr.write("note: plan is outside a git repository; using %s as the repo (pass --repo)\n" % repo)
    subject = derive_subject(plan_path, text, repo)
    if args.no_derive:
        subject["keys"] = []
    subject["keys"] = list(dict.fromkeys(subject["keys"] + (args.key or [])))
    if not subject["keys"]:
        sys.stderr.write("error: no keys: pass --key\n")
        return None, 64
    cov = Coverage()
    sessions = load_claude(repo, subject["keys"], cov) + load_opencode(repo, subject["keys"], cov)
    excluded = set(args.exclude or [])
    sessions = [s for s in sessions if s.sid not in excluded]
    ms = [session_metrics(s) for s in sessions]
    A = aggregate(ms)
    A["format"] = subject["format"]
    log_path, events = event_log(plan_path, repo)
    tasks = per_task([m for m in ms if m], events)
    resumes = collections.Counter(e.get("stop") for e in events if e.get("event") == "resume")
    report = {
        "tool": "session-telemetry %s" % VERSION,
        "generated": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
        "subject": subject,
        "coverage": cov.as_dict(),
        "event_log": {"path": log_path, "events": len(events), "resume_stops": dict(resumes)},
        "totals": {k: v for k, v in A.items() if k not in ("per_session", "window_epoch")},
        "per_task": tasks,
        "outcomes": outcomes(subject, A),
        "findings": [{"area": l, "finding": f} for l, f in findings(A, tasks)],
    }
    if args.sessions or args.json:
        report["sessions"] = A.get("per_session", [])
    return report, 0


def print_report(r, sessions=False):
    s, T, cov = r["subject"], r["totals"], r["coverage"]
    print("session-telemetry report -- %s :: %s" % (s["repo_name"], s["stem"]))
    print("  plan: v%s, %s, %d KB | keys: %s" % (s["format"] or "?", s["plan_status"] or "?", s["plan_kb"],
                                                ", ".join(s["keys"])))
    print("  coverage: " + "; ".join("%s = %s" % kv for kv in cov["sources"].items()))
    print(("            sessions %s | records %d, unrecognised %.2f%% %s" % (
        dict(cov["sessions"]) or "{}", cov["records"], cov["unrecognised_pct"],
        cov["unrecognised_types"] or "")).rstrip())
    if not T.get("sessions"):
        print("  no sessions matched")
        return
    print("  time: %s -> %s | calendar %.1f h | attended %.1f h | agent-busy %.1f h (%.0f%% of attended)" % (
        T["window"][0], T["window"][1], T["calendar_h"], T["attended_h"], T["busy_h"], T["busy_pct_of_attended"]))
    print("  touches: %d sessions | %d prompts | %d handover requests | %d compactions | human wait %.1f h" % (
        T["sessions"], T["prompts"], T["handover_prompts"], T["compactions"], T["human_wait_h"]))
    print("  autonomous run: median %.1f min, p90 %.1f min | resume: median %s min, %.0f KB plan read" % (
        T["auto_run_min_median"], T["auto_run_min_p90"],
        "%.1f" % T["resume_min_median"] if T["resume_min_median"] is not None else "-", T["resume_plan_kb_median"]))
    print("  stops (%d, %d explicit `Stop:` lines): %s" % (T["stops_total"], T["stops_explicit"], ", ".join(
        "%s %d (%.0fm wait)" % (k, v, T["stop_wait_min"].get(k, 0)) for k, v in T["stops"].items())))
    ev = r["event_log"]
    if ev["path"]:
        print("  event log: %d events; resume stops %s" % (ev["events"], ev["resume_stops"] or "{}"))
    print("  ceremony: %.0f%% of busy time, %.0f%% of calls | plan writes: %d tool, %d script" % (
        T["ceremony_pct"], T["ceremony_calls_pct"], T["plan_tool_writes"], T["plan_script_writes"]))
    print("  context intake (KB): " + ", ".join(
        "%s %d (%.0f%%)" % (k, v, T["intake_pct"][k]) for k, v in list(T["intake_kb"].items())[:8]))
    print("  busy time (min): " + ", ".join("%s %s" % kv for kv in list(T["cat_min"].items())[:10]))
    pt = r["per_task"]
    if pt["tasks"]:
        top = sorted(pt["tasks"], key=lambda x: -x["active_min"])[:10]
        print("  per task (source: %s; %.1f h active; top %d):" % (pt["source"], pt["active_h"], len(top)))
        for row in top:
            print("    %-10s %6.1f min %5.1f%%  sessions %d  calls %d (ceremony %d)  started %s" % (
                row["task"], row["active_min"], row["share_pct"], row["sessions"], row["calls"],
                row["ceremony_calls"], row["started"]))
    o = r["outcomes"]
    print("  outcomes: reverts in window %s | TODOs referencing the plan %s%s" % (
        "-" if o["reverts"] is None else o["reverts"], "-" if o["todos"] is None else o["todos"],
        " (%s)" % o["todo_file"] if o["todo_file"] else " (no todo file)"))
    print("  findings:")
    for f in r["findings"] or [{"area": "-", "finding": "none"}]:
        print("    [%s] %s" % (f["area"], f["finding"]))
    if sessions:
        print("  sessions:")
        for p in r.get("sessions", []):
            print("    %s %-11s %s span %4dm busy %4dm prompts %2d compactions %d" % (
                p["sid"], p["harness"], p["start"], p["span_min"], p["busy_min"], p["prompts"], p["compactions"]))


def summary_lines(r):
    T, o = r["totals"], r["outcomes"]
    stops = ", ".join("%s %d" % kv for kv in list(T["stops"].items())[:5])
    top = r["findings"][0] if r["findings"] else None
    return [
        "Telemetry (%s, %s): %d sessions over %.1f h calendar; %.1f h attended, %.1f h agent-busy (%.0f%%)." % (
            r["tool"], r["generated"][:10], T["sessions"], T["calendar_h"], T["attended_h"], T["busy_h"],
            T["busy_pct_of_attended"]),
        "Autonomous runs: median %.1f min, p90 %.1f min; %d prompts, %d compactions, resume median %.0f KB of plan." % (
            T["auto_run_min_median"], T["auto_run_min_p90"], T["prompts"], T["compactions"], T["resume_plan_kb_median"]),
        "Stops (%d explicit of %d): %s." % (T["stops_explicit"], T["stops_total"], stops),
        "Incidents: %d script writes to the plan, %s reverts, %s TODOs filed against the plan." % (
            T["plan_script_writes"], "?" if o["reverts"] is None else o["reverts"],
            "?" if o["todos"] is None else o["todos"]),
        "Top finding: %s" % ("[%s] %s" % (top["area"], top["finding"]) if top else "none"),
    ]


def cmd_report(args):
    r, code = build_report(args)
    if r is None:
        return code
    if args.json:
        print(json.dumps(r, indent=1, ensure_ascii=False))
    else:
        print_report(r, args.sessions)
    return 0 if r["totals"].get("sessions") else 1


def cmd_close(args):
    r, code = build_report(args)
    if r is None:
        return code
    if not r["totals"].get("sessions"):
        print_report(r)
        return 1
    root = home(args)
    s, T = r["subject"], r["totals"]
    os.makedirs(os.path.join(root, "subjects"), exist_ok=True)
    name = "%s--%s.json" % (s["repo_name"], s["stem"])
    with open(os.path.join(root, "subjects", name), "w", encoding="utf-8") as fh:
        json.dump(r, fh, indent=1, ensure_ascii=False)
    row = {
        "repo": s["repo_name"], "stem": s["stem"], "format": s["format"], "plan_status": s["plan_status"],
        "closed": r["generated"], "tool": r["tool"], "plan_kb": s["plan_kb"],
        "sessions": T["sessions"], "calendar_h": round(T["calendar_h"], 2), "attended_h": round(T["attended_h"], 2),
        "busy_h": round(T["busy_h"], 2), "prompts": T["prompts"], "compactions": T["compactions"],
        "handover_prompts": T["handover_prompts"], "auto_run_min_median": round(T["auto_run_min_median"], 1),
        "auto_run_min_p90": round(T["auto_run_min_p90"], 1), "resume_plan_kb_median": round(T["resume_plan_kb_median"], 1),
        "ceremony_pct": round(T["ceremony_pct"], 1), "plan_script_writes": T["plan_script_writes"],
        "stops": T["stops"], "stops_explicit": T["stops_explicit"],
        "reverts": r["outcomes"]["reverts"], "todos": r["outcomes"]["todos"],
        "findings": [f["area"] for f in r["findings"]],
    }
    rows = [x for x in read_ledger(root) if not (x.get("repo") == row["repo"] and x.get("stem") == row["stem"])]
    rows.append(row)
    tmp = os.path.join(root, "ledger.jsonl.tmp")
    with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
        for x in rows:
            fh.write(json.dumps(x, sort_keys=True, ensure_ascii=False) + "\n")
    os.replace(tmp, os.path.join(root, "ledger.jsonl"))
    sys.stderr.write("wrote subjects/%s; ledger now holds %d plan(s); storage %s\n" % (name, len(rows), root))
    print("\n".join(summary_lines(r)))
    return 0


BASELINE_METRICS = ["sessions", "attended_h", "busy_h", "prompts", "auto_run_min_median", "auto_run_min_p90",
                    "resume_plan_kb_median", "ceremony_pct", "plan_script_writes", "compactions"]


def cmd_baseline(args):
    rows = read_ledger(home(args))
    if not rows:
        sys.stderr.write("no ledger rows in %s; `close` a plan first\n" % home(args))
        return 1
    cohorts = collections.defaultdict(list)
    for x in rows:
        fmt = ".".join((x.get("format") or "unknown").split(".")[:2])
        if args.format and fmt != args.format:
            continue
        cohorts[fmt].append(x)
    if not cohorts:
        sys.stderr.write("no ledger rows for format %s\n" % args.format)
        return 1
    out = {}
    for fmt in sorted(cohorts):
        xs = cohorts[fmt]
        med = {m: statistics.median([x[m] for x in xs if isinstance(x.get(m), (int, float))] or [0]) for m in BASELINE_METRICS}
        out[fmt] = {"plans": len(xs), "conclusive": len(xs) >= 3, "medians": med,
                    "members": ["%s/%s" % (x["repo"], x["stem"]) for x in xs]}
    if args.json:
        print(json.dumps(out, indent=1))
        return 0
    for fmt, c in out.items():
        print("cohort manual-planning v%s: %d plan(s)%s" % (
            fmt, c["plans"], "" if c["conclusive"] else " -- do not conclude (fewer than 3 plans)"))
        print("  medians: " + ", ".join("%s %s" % (k, round(v, 1)) for k, v in c["medians"].items()))
        for mbr in c["members"]:
            print("    %s" % mbr)
    return 0


def cmd_sources(args):
    cov = Coverage()
    root = claude_projects_dir()
    print("storage:  %s (%s)" % (home(args), "exists" if os.path.isdir(home(args)) else "not created yet"))
    print("claude:   %s (%s)" % (root, "%d project folders" % len(os.listdir(root)) if os.path.isdir(root) else "missing"))
    if args.repo:
        d = claude_project_dir(args.repo)
        print("          repo folder: %s" % (
            "%s (%d sessions)" % (d, len(glob.glob(os.path.join(d, "*.jsonl")))) if d else "none for %s" % args.repo))
    c, tables = open_opencode(cov)
    print("opencode: %s" % cov.sources["opencode"])
    if c is not None:
        for t in ("session_v2", "session"):
            if t in tables:
                n = c.execute("select count(*) from %s" % t).fetchone()[0]
                line = "          %s: %d sessions" % (t, n)
                if args.repo:
                    fwd = os.path.abspath(args.repo).replace("\\", "/").rstrip("/").lower()
                    k = c.execute("select count(*) from %s where replace(lower(directory), '\\', '/') = ?" % t,
                                  (fwd,)).fetchone()[0]
                    line += ", %d for this repo" % k
                print(line)
        c.close()
    return 0


class Parser(argparse.ArgumentParser):
    def error(self, message):
        self.print_usage(sys.stderr)
        sys.stderr.write("error: %s\n" % message)
        sys.exit(64)


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    common = Parser(add_help=False)
    common.add_argument("--home", help="storage directory (default: see Paths below)")
    subject = Parser(add_help=False)
    subject.add_argument("plan", help="path to the plan file (the subject)")
    subject.add_argument("--repo", help="repository the sessions ran in (default: the plan's git root)")
    subject.add_argument("--key", action="append", help="extra key a session must mention; repeatable")
    subject.add_argument("--no-derive", action="store_true", help="use only --key, not the keys derived from the plan")
    subject.add_argument("--exclude", action="append", help="session id (8 chars) to drop as a false positive; repeatable")
    p = Parser(prog="telemetry.py", description="Measure what a plan cost, from local agent transcripts.",
               epilog=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--version", action="version", version="telemetry.py " + VERSION)
    sub = p.add_subparsers(dest="command", required=True, parser_class=Parser)
    r = sub.add_parser("report", parents=[common, subject], help="report on one plan")
    r.add_argument("--json", action="store_true", help="emit the full report as JSON")
    r.add_argument("--sessions", action="store_true", help="list matched sessions (ids, times, counts)")
    sub.add_parser("close", parents=[common, subject],
                   help="report, store the subject JSON, upsert the ledger row, print a <=5-line summary")
    b = sub.add_parser("baseline", parents=[common], help="medians per Plan Format cohort from the ledger")
    b.add_argument("--format", help="only this cohort, e.g. 2.1")
    b.add_argument("--json", action="store_true")
    s = sub.add_parser("sources", parents=[common], help="which transcript stores exist, and their shape")
    s.add_argument("--repo", help="also count the sessions recorded for this repository")
    args = p.parse_args(argv)
    if args.command in ("report", "close"):
        args.sessions = getattr(args, "sessions", False)
        args.json = getattr(args, "json", False)
        return cmd_report(args) if args.command == "report" else cmd_close(args)
    if args.command == "baseline":
        return cmd_baseline(args)
    return cmd_sources(args)


if __name__ == "__main__":
    sys.exit(main())
