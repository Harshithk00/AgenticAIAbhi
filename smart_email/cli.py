"""Command-line interface: python -m smart_email <command> ..."""

from __future__ import annotations

import argparse
import json
import sys

from .mailbox import Mailbox

PRIORITY_ORDER = {"high": 0, "medium": 1, "low": 2, None: 3}


def _print_tool_call(name: str, args: dict) -> None:
    shown = {k: v for k, v in args.items() if k != "body"}
    print(f"  -> {name}({json.dumps(shown, ensure_ascii=False)})", file=sys.stderr)


def cmd_show(mailbox: Mailbox, args) -> None:
    emails = sorted(mailbox.list(include_archived=args.all), key=lambda e: PRIORITY_ORDER[e.priority])
    for e in emails:
        tag = f"[{e.priority or '-':6}] [{e.category or 'untriaged':15}]"
        archived = " (archived)" if e.archived else ""
        print(f"{tag} {e.id}  {e.sender}: {e.subject}{archived}")
        if e.summary:
            print(f"{'':28}{e.summary}")
        if e.labels:
            print(f"{'':28}labels: {', '.join(e.labels)}")
        if e.follow_up:
            print(f"{'':28}follow-up: {e.follow_up}")
    if mailbox.drafts:
        print(f"\n{len(mailbox.drafts)} draft(s) awaiting review (run `drafts` to read them).")


def cmd_drafts(mailbox: Mailbox, args) -> None:
    if not mailbox.drafts:
        print("No drafts.")
    for d in mailbox.drafts:
        print(f"To: {d.to}\nSubject: {d.subject}\n\n{d.body}\n{'-' * 60}")


def _run_agent(mailbox: Mailbox, args, instruction: str | None) -> None:
    from .agent import EmailAgent

    agent = EmailAgent(mailbox, model=args.model, effort=args.effort)
    callback = None if args.quiet else _print_tool_call
    reply = agent.triage(callback) if instruction is None else agent.run(instruction, callback)
    mailbox.save(args.output)
    print(reply)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="smart_email", description="Smart email management with Claude.")
    parser.add_argument("--inbox", default="data/sample_inbox.json", help="Path to the inbox JSON file.")
    sub = parser.add_subparsers(dest="command", required=True)

    def agent_options(p):
        p.add_argument("--model", default="claude-opus-5-5")
        p.add_argument("--effort", default="medium", choices=["low", "medium", "high", "xhigh", "max"])
        p.add_argument("--output", help="Save the updated inbox here instead of overwriting --inbox.")
        p.add_argument("-q", "--quiet", action="store_true", help="Don't print tool calls.")

    agent_options(sub.add_parser("triage", help="Let the agent triage every untriaged email."))
    ask = sub.add_parser("ask", help="Give the agent a free-form instruction about your inbox.")
    ask.add_argument("instruction")
    agent_options(ask)
    show = sub.add_parser("show", help="Show the inbox, most important first.")
    show.add_argument("--all", action="store_true", help="Include archived emails.")
    sub.add_parser("drafts", help="Show reply drafts awaiting review.")

    args = parser.parse_args(argv)
    mailbox = Mailbox.load(args.inbox)

    if args.command == "triage":
        _run_agent(mailbox, args, None)
    elif args.command == "ask":
        _run_agent(mailbox, args, args.instruction)
    elif args.command == "show":
        cmd_show(mailbox, args)
    elif args.command == "drafts":
        cmd_drafts(mailbox, args)


if __name__ == "__main__":
    main()
