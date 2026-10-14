"""JSON CLI for agent harnesses that can execute shell commands."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

import httpx

from .client import APIError, ResumeHarness, RunFailed, RunTimeout


def main() -> int:
    parser = argparse.ArgumentParser(prog="resume-harness")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("me")
    commands.add_parser("sources")
    commands.add_parser("runs")
    jobs = commands.add_parser("jobs")
    jobs.add_argument(
        "--board", choices=["triage", "shortlist", "pipeline"], default="triage"
    )
    jobs.add_argument("--page", type=int, default=1)
    jobs.add_argument("--query")
    pull = commands.add_parser("pull")
    pull.add_argument("--source-id", action="append")
    pull.add_argument("--limit", type=int)
    commands.add_parser("discover")
    for name in ("job", "context", "tailor"):
        sub = commands.add_parser(name)
        sub.add_argument("job_id", type=int)
    for name in ("validate", "submit"):
        sub = commands.add_parser(name)
        sub.add_argument("job_id", type=int)
        sub.add_argument("--draft", type=Path, required=True)
        sub.add_argument("--revision", required=True)
        if name == "submit":
            sub.add_argument("--agent", default="external")
    for name in ("run", "wait", "cancel"):
        sub = commands.add_parser(name)
        sub.add_argument("run_id")
        if name == "wait":
            sub.add_argument("--timeout", type=float, default=600)
    for name in ("render", "download"):
        sub = commands.add_parser(name)
        sub.add_argument("version_id", type=int)
        if name == "download":
            sub.add_argument("--output", type=Path, required=True)
    install = commands.add_parser("install-skills")
    install.add_argument(
        "--directory",
        type=Path,
        required=True,
        help="Agent skill root; existing skill folders are never overwritten",
    )
    args = parser.parse_args()
    try:
        if args.command == "install-skills":
            sources = sorted((Path(__file__).parent / "skills").iterdir())
            for source in sources:
                if (args.directory / source.name).exists():
                    raise ValueError(f"Skill already exists: {source.name}")
            for source in sources:
                shutil.copytree(source, args.directory / source.name)
            result = {"installed": [str(args.directory / s.name) for s in sources]}
        else:
            with ResumeHarness.from_env() as client:
                command = args.command
                if command == "me":
                    result = client.me()
                elif command == "sources":
                    result = client.list_sources()
                elif command == "runs":
                    result = client.list_runs()
                elif command == "jobs":
                    result = client.list_jobs(
                        board=args.board, page=args.page, q=args.query or ""
                    )
                elif command == "pull":
                    result = client.pull_jobs(
                        source_ids=args.source_id, limit=args.limit
                    )
                elif command == "discover":
                    result = client.discover_jobs()
                elif command == "job":
                    result = client.get_job(args.job_id)
                elif command == "context":
                    result = client.authoring_context(args.job_id)
                elif command == "tailor":
                    result = client.tailor([args.job_id])
                elif command in {"validate", "submit"}:
                    content = json.loads(args.draft.read_text(encoding="utf-8"))
                    if command == "validate":
                        result = client.validate_resume(
                            args.job_id, content, context_revision=args.revision
                        )
                    else:
                        result = client.submit_resume(
                            args.job_id,
                            content,
                            context_revision=args.revision,
                            agent=args.agent,
                        )
                elif command == "run":
                    result = client.get_run(args.run_id)
                elif command == "wait":
                    result = client.wait(args.run_id, timeout=args.timeout)
                elif command == "cancel":
                    result = client.cancel_run(args.run_id)
                elif command == "render":
                    result = client.render_resume(args.version_id)
                else:
                    data = client.download_resume(args.version_id)
                    with args.output.open("xb") as output:
                        output.write(data)
                    result = {"path": str(args.output), "bytes": len(data)}
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except (APIError, RunFailed, RunTimeout, ValueError, OSError, KeyError) as exc:
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        return 1
    except httpx.HTTPError:
        print(
            json.dumps(
                {
                    "error": "HTTP transport failed; inspect the run before retrying a write"
                }
            ),
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
