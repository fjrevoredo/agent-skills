#!/usr/bin/env python3
"""Read and move agent-feedback entries while processing them.

  process.py list [--state inbox|proposed|done|wontfix]
      One compact block per entry: id, source, kind, severity, repo, path, then suggestion,
      outcome and link if set, then the text. Oldest first.
  process.py move ID... --to proposed|done|wontfix --outcome TEXT [--link L]
      Moves entries (from any state) and records outcome, link and time. proposed needs --link.
      Deletes a session's transcript copy once none of its entries is in inbox or proposed.
  process.py transcript ID [--minutes 15]
      User and assistant text, tool calls and tool errors in the minutes before the entry.
  process.py paths
      State dir, briefs dir, routing file ($AGENT_FEEDBACK_ROUTING, else <state>/routing.md), template.

State dir: $AGENT_FEEDBACK_DIR, else ${XDG_STATE_HOME:-~/.local/state}/agent-feedback.
Exit codes: 0 ok, 64 usage error or unknown id (nothing moved), 66 no transcript copy.
"""

import argparse
import importlib.util
import json
import sys
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "capture", Path(__file__).resolve().parents[2] / "capture" / "scripts" / "capture.py")
capture = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(capture)

ENTRY_STATES = ("inbox", "proposed", "done", "wontfix")
TEMPLATE = Path(__file__).resolve().parents[1] / "routing.template.md"


def read_entry(path):
    """Return (fields, text) of one entry file."""
    head, _, body = path.read_text(encoding="utf-8", errors="replace").partition("\n---\n")
    fields = {}
    for line in head.splitlines()[1:]:
        key, _, value = line.partition(":")
        value = value.strip()
        try:
            fields[key] = json.loads(value) if value else ""
        except ValueError:
            fields[key] = value
    return fields, body.strip()


def repo_name(remote):
    return remote.rstrip("/").rsplit("/", 1)[-1].removesuffix(".git") if remote else "-"


def cmd_list(args):
    root = capture.state_dir()
    paths = sorted((root / args.state).glob("*.md"))
    if not paths:
        print(f"no entries in {args.state}")
        return 0
    blocks = []
    for path in paths:
        f, text = read_entry(path)
        lines = [" ".join([path.stem, *(f.get(k) or "-" for k in ("source", "kind", "severity")),
                           repo_name(f.get("repo")), f.get("path") or "-"])]
        lines += [f"{k}: {f[k]}" for k in ("suggestion", "outcome", "link") if f.get(k)]
        lines.append(text)
        blocks.append("\n".join(lines))
    print("\n\n".join(blocks))
    return 0


def find_entry(root, entry_id):
    for state in ENTRY_STATES:
        path = root / state / f"{entry_id}.md"
        if path.is_file():
            return path
    return None


def session_is_open(root, session):
    return any(read_entry(p)[0].get("session") == session
               for state in capture.OPEN_STATES for p in (root / state).glob("*.md"))


def cmd_move(args):
    if args.to == "proposed" and not args.link:
        print("agent-feedback: moving to proposed needs --link (the brief, draft or MR it waits on)",
              file=sys.stderr)
        return 64
    root = capture.state_dir()
    paths = {i: find_entry(root, i) for i in args.ids}
    missing = [i for i, p in paths.items() if p is None]
    if missing:
        print(f"agent-feedback: no entry {', '.join(missing)}; nothing moved", file=sys.stderr)
        return 64

    now = capture.datetime.datetime.now().astimezone().isoformat(timespec="seconds")
    sessions = set()
    for entry_id, path in paths.items():
        fields, text = read_entry(path)
        fields.update(outcome=args.outcome, moved=now)
        if args.link:
            fields["link"] = args.link
        dest = root / args.to / path.name
        dest.write_text(f"---\n{capture.header(fields)}\n---\n\n{text}\n", encoding="utf-8")
        if dest != path:
            path.unlink()
        if fields.get("session"):
            sessions.add(fields["session"])

    deleted = []
    for session in sorted(sessions):
        copy = root / "transcripts" / f"{session}.jsonl.gz"
        if copy.exists() and not session_is_open(root, session):
            copy.unlink()
            deleted.append(session)
    print(json.dumps({"moved": list(paths), "to": args.to, "transcripts_deleted": deleted}))
    return 0


def clip(text, limit):
    text = " ".join(str(text).split())
    return text if len(text) <= limit else text[:limit] + " …"


def parse_time(value):
    return capture.datetime.datetime.fromisoformat(value.replace("Z", "+00:00"))


def transcript_lines(record):
    """Readable lines for one transcript record: user and assistant text, tool calls, tool errors."""
    kind, msg = record.get("type"), record.get("message") or {}
    if kind not in ("user", "assistant") or record.get("isMeta"):
        return []
    content = msg.get("content")
    if isinstance(content, str):
        return [f"{kind}: {clip(content, 600)}"]
    out = []
    for part in content or []:
        t = part.get("type")
        if t == "text":
            out.append(f"{kind}: {clip(part.get('text', ''), 600)}")
        elif t == "tool_use":
            args = part.get("input") or {}
            first = next(iter(args.values()), "") if isinstance(args, dict) else args
            out.append(f"tool: {part.get('name')} {clip(first, 200)}")
        elif t == "tool_result" and part.get("is_error"):
            body = part.get("content")
            if isinstance(body, list):
                body = " ".join(x.get("text", "") for x in body if isinstance(x, dict))
            out.append(f"tool error: {clip(body, 300)}")
    return out


def cmd_transcript(args):
    root = capture.state_dir()
    path = find_entry(root, args.id)
    if path is None:
        print(f"agent-feedback: no entry {args.id}", file=sys.stderr)
        return 64
    fields, _ = read_entry(path)
    copy = root / "transcripts" / f"{fields.get('session')}.jsonl.gz"
    if not fields.get("session") or not copy.is_file():
        print(f"agent-feedback: no transcript copy for {args.id}; the entry text is all there is",
              file=sys.stderr)
        return 66
    end = parse_time(fields["time"]) + capture.datetime.timedelta(minutes=1)
    start = end - capture.datetime.timedelta(minutes=args.minutes + 1)
    with capture.gzip.open(copy, "rt", encoding="utf-8", errors="replace") as f:
        for line in f:
            try:
                record = json.loads(line)
                when = parse_time(record["timestamp"])
            except (ValueError, KeyError, TypeError, AttributeError):
                continue
            if start <= when <= end:
                for text in transcript_lines(record):
                    print(f"{when.astimezone():%H:%M} {text}")
    return 0


def cmd_paths(_args):
    root = capture.state_dir()
    routing = Path(capture.os.environ.get("AGENT_FEEDBACK_ROUTING") or root / "routing.md").expanduser()
    print(json.dumps({"state": str(root), "briefs": str(root / "briefs"), "routing": str(routing),
                      "routing_exists": routing.is_file(), "routing_template": str(TEMPLATE)}, indent=1))
    return 0


def main():
    parser = capture.Parser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True, parser_class=capture.Parser)
    ls = sub.add_parser("list", help="show entries in one state")
    ls.add_argument("--state", choices=ENTRY_STATES, default="inbox")
    ls.set_defaults(func=cmd_list)
    mv = sub.add_parser("move", help="move entries to another state with a one-line outcome")
    mv.add_argument("ids", nargs="+", metavar="ID")
    mv.add_argument("--to", required=True, choices=ENTRY_STATES)
    mv.add_argument("--outcome", required=True, help="one line: what was done or decided")
    mv.add_argument("--link", help="the brief, draft, edited file or MR; required for proposed")
    mv.set_defaults(func=cmd_move)
    pa = sub.add_parser("paths", help="state dir, briefs dir and routing file as JSON")
    pa.set_defaults(func=cmd_paths)
    tr = sub.add_parser("transcript", help="the conversation in the minutes before an entry")
    tr.add_argument("id")
    tr.add_argument("--minutes", type=int, default=15)
    tr.set_defaults(func=cmd_transcript)
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
