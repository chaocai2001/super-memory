"""CLI entry point: supermemory ingest / pending / apply / search / inject / status."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date as date_type
from pathlib import Path

from .distill import DistillError, distill, load_config, validate_ops
from .parser import DEFAULT_SESSIONS_DIR, find_log_files, parse_file, render_transcript
from .search import build_injection, search
from .state import DEFAULT_STATE_DIR, State
from .wiki import DEFAULT_WIKI_DIR, WikiStore


def _date_of(ts: str) -> str:
    return ts[:10] if ts else date_type.today().isoformat()


def _collect_pending(sessions_dir: Path, state: State, wiki: WikiStore, limit: int = 0) -> list[dict]:
    """Parse every log file past its saved offset; return pending session chunks."""
    pending = []
    for path in find_log_files(sessions_dir):
        if limit and len(pending) >= limit:
            break
        key = str(path)
        offset = state.offset_for(key)
        try:
            transcript, end_offset = parse_file(path, offset)
        except OSError:
            continue
        if end_offset == offset:
            continue
        if transcript is None or not transcript.has_content():
            state.mark_distilled(key, end_offset, transcript.session_id if transcript else "")
            continue
        pending.append({
            "source_file": key,
            "session_id": transcript.session_id,
            "date": _date_of(transcript.started_at),
            "cwd": transcript.cwd,
            "end_offset": end_offset,
            "turns": len(transcript.turns),
            "transcript": render_transcript(transcript),
        })
    return pending


def cmd_ingest(args) -> int:
    sessions_dir = Path(args.sessions_dir).expanduser()
    wiki = WikiStore(Path(args.wiki_dir))
    state = State(Path(args.state_dir) / "state.json")

    files = find_log_files(sessions_dir)
    if not files:
        print(f"No jsonl logs found under {sessions_dir}", file=sys.stderr)
        return 1

    cfg = None
    if not args.dry_run:
        try:
            cfg = load_config()
        except DistillError as e:
            print(f"error: {e}", file=sys.stderr)
            return 2

    processed = skipped = failed = 0
    for path in files:
        key = str(path)
        offset = 0 if args.reprocess else state.offset_for(key)
        if args.reprocess:
            state.reset(key)
        try:
            transcript, end_offset = parse_file(path, offset)
        except OSError as e:
            print(f"skip {path.name}: {e}", file=sys.stderr)
            skipped += 1
            continue

        if transcript is None or not transcript.has_content():
            state.mark_distilled(key, end_offset, transcript.session_id if transcript else "")
            skipped += 1
            continue

        text = render_transcript(transcript)
        index = wiki.index_summary()
        sess_date = _date_of(transcript.started_at)

        if args.dry_run:
            print(f"===== {path.name} (session {transcript.session_id[:8]}, {len(transcript.turns)} turns) =====")
            print(text[:2000])
            if len(text) > 2000:
                print(f"…[{len(text) - 2000} more chars]")
            print()
            processed += 1
            continue

        try:
            result = distill(text, index, transcript.session_id, sess_date, cfg=cfg)
        except DistillError as e:
            print(f"distill failed for {path.name}: {e}", file=sys.stderr)
            failed += 1
            continue

        source_tag = f"session {transcript.session_id[:8]}, {sess_date}"
        applied = wiki.apply_ops(result["ops"], source_tag, today=sess_date)
        if result.get("log_entry"):
            wiki.append_log(sess_date, transcript.cwd, result["log_entry"], transcript.session_id)
        state.mark_distilled(key, end_offset, transcript.session_id)
        state.save()
        print(f"ingested {path.name}: {len(applied)} ops ({', '.join(applied) or 'none'})")
        processed += 1

    if not args.dry_run:
        state.save()
    print(f"\ndone: {processed} ingested, {skipped} unchanged, {failed} failed")
    return 0 if failed == 0 else 3


def cmd_pending(args) -> int:
    sessions_dir = Path(args.sessions_dir).expanduser()
    wiki = WikiStore(Path(args.wiki_dir))
    state = State(Path(args.state_dir) / "state.json")
    pending = _collect_pending(sessions_dir, state, wiki, limit=args.limit)
    state.save()

    if args.json:
        out = {
            "index": wiki.index_summary(),
            "sessions": pending,
        }
        print(json.dumps(out, ensure_ascii=False, indent=2))
    else:
        if not pending:
            print("no pending sessions")
            return 0
        print(f"index:\n{wiki.index_summary() or '(empty)'}\n")
        for s in pending:
            print(f"===== session {s['session_id'][:8]} ({s['date']}, {s['cwd']}, {s['turns']} turns) =====")
            print(s["transcript"])
            print()
    return 0


def cmd_apply(args) -> int:
    wiki = WikiStore(Path(args.wiki_dir))
    state = State(Path(args.state_dir) / "state.json")

    try:
        ops_data = json.loads(Path(args.ops).read_text() if args.ops != "-" else sys.stdin.read())
        checkpoint = json.loads(Path(args.checkpoint).read_text())
    except (OSError, json.JSONDecodeError) as e:
        print(f"error: cannot read ops/checkpoint JSON: {e}", file=sys.stderr)
        return 2

    sessions_meta = {s["session_id"]: s for s in checkpoint.get("sessions", [])}

    results = ops_data.get("sessions")
    if results is None:
        results = [ops_data]
    acked = {str(r.get("session_id", "")) for r in results if isinstance(r, dict)}
    acked.discard("")

    total_applied = 0
    for result in results:
        session_id = result.get("session_id", "")
        meta = sessions_meta.get(session_id, {})
        sess_date = meta.get("date") or date_type.today().isoformat()
        try:
            clean = validate_ops(result)
        except DistillError as e:
            print(f"invalid ops for session {session_id[:8]}: {e}", file=sys.stderr)
            continue
        source_tag = f"session {session_id[:8]}, {sess_date}"
        applied = wiki.apply_ops(clean["ops"], source_tag, today=sess_date)
        if clean.get("log_entry"):
            wiki.append_log(sess_date, meta.get("cwd", ""), clean["log_entry"], session_id)
        total_applied += len(applied)
        if applied:
            print(f"session {session_id[:8]}: {', '.join(applied)}")

    for s in checkpoint.get("sessions", []):
        if s["session_id"] in acked:
            state.mark_distilled(s["source_file"], s["end_offset"], s["session_id"])
    state.save()
    leftover = len(checkpoint.get("sessions", [])) - len(acked & {s["session_id"] for s in checkpoint.get("sessions", [])})
    print(f"applied {total_applied} ops across {len(results)} session(s); "
          f"{len(acked)} session(s) checkpointed" +
          (f"; {leftover} pending session(s) NOT acknowledged, left for next run" if leftover else ""))
    return 0


def cmd_search(args) -> int:
    wiki = WikiStore(Path(args.wiki_dir))
    hits = search(wiki, args.query, limit=args.n)
    if not hits:
        print("no matches")
        return 1
    for hit in hits:
        print(f"{hit.score:6.1f}  wiki/pages/{hit.page.slug}.md")
        print(f"         {hit.snippet}")
    return 0


def cmd_inject(args) -> int:
    wiki = WikiStore(Path(args.wiki_dir))
    block = build_injection(wiki, args.query, max_chars=args.max_chars)
    if not block:
        print("no relevant memory found", file=sys.stderr)
        return 1
    print(block)
    return 0


def cmd_status(args) -> int:
    wiki = WikiStore(Path(args.wiki_dir))
    state = State(Path(args.state_dir) / "state.json")
    pages = wiki.list_pages()
    print(f"wiki dir:      {wiki.root.resolve()}")
    print(f"pages:         {len(pages)}")
    print(f"tracked files: {len(state.files)}")
    if state.files:
        recent = max(
            ((Path(f).name, v.get("session_id", "")) for f, v in state.files.items()),
            default=None,
        )
        if recent:
            print(f"latest log:    {recent[0]}")
    if pages:
        newest = max(pages, key=lambda p: p.updated)
        print(f"latest page:   {newest.slug} (updated {newest.updated})")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="supermemory",
        description="Distill codex session logs into an LLM-curated memory wiki.",
    )
    ap.add_argument("--wiki-dir", default=str(DEFAULT_WIKI_DIR), help="wiki directory (default: ~/.super-memory/wiki)")
    ap.add_argument("--state-dir", default=str(DEFAULT_STATE_DIR), help="state directory (default: ~/.super-memory)")
    sub = ap.add_subparsers(dest="command", required=True)

    p_ingest = sub.add_parser("ingest", help="parse new log bytes and distill them into the wiki")
    p_ingest.add_argument("--sessions-dir", default=str(DEFAULT_SESSIONS_DIR))
    p_ingest.add_argument("--reprocess", action="store_true", help="ignore saved offsets and redo everything")
    p_ingest.add_argument("--dry-run", action="store_true", help="print transcripts, do not call the LLM or write the wiki")
    p_ingest.set_defaults(func=cmd_ingest)

    p_pending = sub.add_parser("pending", help="list sessions with unprocessed log bytes (for agent-driven distillation)")
    p_pending.add_argument("--sessions-dir", default=str(DEFAULT_SESSIONS_DIR))
    p_pending.add_argument("--json", action="store_true", help="emit JSON checkpoint usable by 'apply'")
    p_pending.add_argument("--limit", type=int, default=0, help="max sessions per batch (0 = all)")
    p_pending.set_defaults(func=cmd_pending)

    p_apply = sub.add_parser("apply", help="apply wiki ops JSON produced by an agent, then checkpoint")
    p_apply.add_argument("--ops", required=True, help="ops JSON file path, or '-' for stdin")
    p_apply.add_argument("--checkpoint", required=True, help="JSON file previously produced by 'pending --json'")
    p_apply.set_defaults(func=cmd_apply)

    p_search = sub.add_parser("search", help="keyword search over wiki pages")
    p_search.add_argument("query")
    p_search.add_argument("-n", type=int, default=5)
    p_search.set_defaults(func=cmd_search)

    p_inject = sub.add_parser("inject", help="render relevant memory as a paste-ready markdown block")
    p_inject.add_argument("query")
    p_inject.add_argument("--max-chars", type=int, default=4000)
    p_inject.set_defaults(func=cmd_inject)

    p_status = sub.add_parser("status", help="show wiki and ingest state")
    p_status.set_defaults(func=cmd_status)

    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
