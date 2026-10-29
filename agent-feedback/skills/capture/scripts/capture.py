#!/usr/bin/env python3
"""Record one agent-feedback entry, or refresh a session's transcript copy at SessionEnd.

  capture.py add [--source agent|user|retro] [--kind K] [--severity S] [--suggestion S] [--text T]
      Writes inbox/<id>.md and prints {"id", "path"} as JSON. Without --text, reads the text from stdin.
  capture.py session-end
      Claude Code SessionEnd hook: reads the hook JSON on stdin; refreshes the transcript copy
      if the session has an open entry. Always exits 0.

State dir: $AGENT_FEEDBACK_DIR, else ${XDG_STATE_HOME:-~/.local/state}/agent-feedback.
Metadata (session, agent, model, repo, path, branch) is best effort: missing details stay blank.
Exit codes: 0 ok, 64 usage error (nothing written), 73 state dir not writable.
"""

import argparse
import datetime
import gzip
import json
import os
import re
import secrets
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

SOURCES = ("agent", "user", "retro")
KINDS = ("instruction", "skill", "tooling", "access", "infra", "docs", "knowledge", "other")
SEVERITIES = ("high", "medium", "low")
STATES = ("inbox", "proposed", "done", "wontfix", "transcripts", "briefs")
OPEN_STATES = ("inbox", "proposed")


def state_dir():
    if os.environ.get("AGENT_FEEDBACK_DIR"):
        return Path(os.environ["AGENT_FEEDBACK_DIR"]).expanduser()
    xdg = os.environ.get("XDG_STATE_HOME") or Path.home() / ".local" / "state"
    return Path(xdg).expanduser() / "agent-feedback"


def ensure_dirs(root):
    for name in STATES:
        (root / name).mkdir(parents=True, exist_ok=True)


def one_line(value):
    return " ".join((value or "").split())


def git(*args):
    try:
        r = subprocess.run(["git", *args], capture_output=True, text=True, timeout=5)
        return r.stdout.strip() if r.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError):
        return ""


def clean_remote(remote):
    """Drop credentials from URL remotes; blank local paths so no home path lands in an entry."""
    if re.match(r"^[\w+.-]+://", remote) and not remote.startswith("file:"):
        return re.sub(r"^([\w+.-]+://)[^/@]+@", r"\1", remote)
    if re.match(r"^[\w.-]+@[\w.-]+:", remote):  # scp-style ssh
        return remote
    return ""


def repo_fields():
    remote = clean_remote(git("remote", "get-url", "origin"))
    return {
        "repo": remote,
        "path": git("rev-parse", "--show-prefix").rstrip("/"),
        "branch": git("branch", "--show-current"),
    }


def find_transcript(session):
    if not session:
        return None
    config = Path(os.environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude").expanduser()
    matches = sorted((config / "projects").glob(f"*/{session}.jsonl"))
    return matches[0] if matches else None


def last_model(transcript):
    """Model of the last assistant message, read from the transcript tail."""
    try:
        with open(transcript, "rb") as f:
            f.seek(0, os.SEEK_END)
            f.seek(max(0, f.tell() - 256 * 1024))
            tail = f.read().decode("utf-8", "replace")
    except OSError:
        return ""
    for line in reversed(tail.splitlines()):
        try:
            model = json.loads(line).get("message", {}).get("model")
        except (ValueError, AttributeError):
            continue
        if model:
            return model
    return ""


def copy_transcript(root, session, transcript):
    """Gzip the transcript to transcripts/<session>.jsonl.gz, replacing it atomically."""
    if not (session and transcript and Path(transcript).is_file()):
        return False
    dest = root / "transcripts" / f"{session}.jsonl.gz"
    tmp = None
    try:
        fd, tmp = tempfile.mkstemp(dir=dest.parent, prefix=f".{session}.", suffix=".tmp")
        with open(transcript, "rb") as src, os.fdopen(fd, "wb") as raw, \
                gzip.GzipFile(fileobj=raw, mode="wb", compresslevel=1) as out:
            shutil.copyfileobj(src, out)
        os.replace(tmp, dest)
        return True
    except OSError as e:
        print(f"agent-feedback: transcript copy skipped: {e}", file=sys.stderr)
        if tmp:
            Path(tmp).unlink(missing_ok=True)
        return False


def new_id(now):
    return f"{now:%Y%m%d-%H%M%S}-{secrets.token_hex(2)}"


def header(fields):
    """One `key: value` line per field; values are JSON strings, which YAML parsers also read."""
    return "\n".join(f"{k}: {json.dumps(one_line(v), ensure_ascii=False)}" if one_line(v) else f"{k}:"
                     for k, v in fields.items())


def write_entry(inbox, now, fields, text):
    while True:
        entry_id = new_id(now)
        path = inbox / f"{entry_id}.md"
        try:
            with open(path, "x", encoding="utf-8") as f:
                f.write(f"---\n{header({**fields, 'id': entry_id})}\n---\n\n{text}\n")
            return entry_id, path
        except FileExistsError:
            continue


def cmd_add(args):
    text = args.text if args.text is not None else sys.stdin.buffer.read().decode("utf-8", "replace")
    text = text.strip()
    if not text:
        print("agent-feedback: empty text; pass --text or pipe the text on stdin", file=sys.stderr)
        return 64

    root = state_dir()
    try:
        ensure_dirs(root)
    except OSError as e:
        print(f"agent-feedback: cannot create state dir {root}: {e}", file=sys.stderr)
        return 73

    session = os.environ.get("CLAUDE_CODE_SESSION_ID", "")
    transcript = find_transcript(session)
    now = datetime.datetime.now().astimezone()
    fields = {
        "id": "",
        "time": now.isoformat(timespec="seconds"),
        "source": args.source,
        "kind": args.kind or "",
        "severity": args.severity or "",
        "session": session,
        "agent": os.environ.get("AI_AGENT") or ("claude-code" if os.environ.get("CLAUDECODE") else ""),
        "model": last_model(transcript) if transcript else "",
        **repo_fields(),
        "suggestion": args.suggestion or "",
    }
    try:
        entry_id, path = write_entry(root / "inbox", now, fields, text)
    except OSError as e:
        print(f"agent-feedback: cannot write entry in {root / 'inbox'}: {e}", file=sys.stderr)
        return 73

    copy_transcript(root, session, transcript)
    print(json.dumps({"id": entry_id, "path": str(path)}))
    return 0


def has_open_entry(root, session):
    marker = f"\nsession: {json.dumps(session)}\n"
    for state in OPEN_STATES:
        for entry in (root / state).glob("*.md"):
            try:
                if marker in entry.read_text(errors="replace"):
                    return True
            except OSError:
                continue
    return False


def cmd_session_end(_args):
    try:
        data = json.load(sys.stdin)
        session, transcript = data.get("session_id"), data.get("transcript_path")
        root = state_dir()
        if session and (root / "inbox").is_dir() and has_open_entry(root, session):
            copy_transcript(root, session, transcript)
    except Exception as e:  # a hook must never break the session's end
        print(f"agent-feedback: session-end skipped: {e}", file=sys.stderr)
    return 0


class Parser(argparse.ArgumentParser):
    def error(self, message):
        self.print_usage(sys.stderr)
        print(f"{self.prog}: error: {message}", file=sys.stderr)
        sys.exit(64)


def main():
    parser = Parser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True, parser_class=Parser)
    add = sub.add_parser("add", help="record one entry")
    add.add_argument("--source", choices=SOURCES, default="agent")
    add.add_argument("--kind", choices=KINDS)
    add.add_argument("--severity", choices=SEVERITIES)
    add.add_argument("--suggestion", help="optional one-line fix idea")
    add.add_argument("--text", help="the entry text; read from stdin when omitted")
    add.set_defaults(func=cmd_add)
    end = sub.add_parser("session-end", help="SessionEnd hook: refresh the transcript copy")
    end.set_defaults(func=cmd_session_end)
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
