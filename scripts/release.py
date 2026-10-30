"""Batch main's Conventional Commits into SemVer tags and GitHub releases.

Requires only Python's standard library, git, and an authenticated gh CLI.
Both commands preview their work unless --publish is explicitly supplied.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
VERSION = re.compile(r"v(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)")
CONVENTIONAL = re.compile(r"([a-z]+)(?:\(([^)]+)\))?(!)?:\s+(.+)")
BREAKING = re.compile(r"^BREAKING(?: CHANGE|-CHANGE):", re.MULTILINE)
INTERVAL = timedelta(days=7)


def command(*args: str, cwd: Path = ROOT, stdin: str | None = None) -> str:
    result = subprocess.run(
        args, cwd=cwd, input=stdin, capture_output=True, text=True, encoding="utf-8"
    )
    if result.returncode:
        raise RuntimeError(f"{args[0]} failed: {result.stderr.strip()}")
    return result.stdout.strip()


@dataclass(frozen=True, order=True)
class Version:
    major: int
    minor: int
    patch: int

    @classmethod
    def parse(cls, tag: str) -> Version:
        match = VERSION.fullmatch(tag)
        if not match:
            raise ValueError(f"Invalid application version tag: {tag}")
        return cls(*(int(part) for part in match.groups()))

    def __str__(self) -> str:
        return f"v{self.major}.{self.minor}.{self.patch}"

    def bump(self, kind: str) -> Version:
        if kind == "major":
            return Version(self.major + 1, 0, 0)
        if kind == "minor":
            return Version(self.major, self.minor + 1, 0)
        if kind == "patch":
            return Version(self.major, self.minor, self.patch + 1)
        raise ValueError(f"Unknown version bump: {kind}")


@dataclass(frozen=True)
class Commit:
    sha: str
    subject: str
    body: str = ""

    @property
    def bump(self) -> str | None:
        match = CONVENTIONAL.fullmatch(self.subject)
        if BREAKING.search(self.body) or (match and match[3]):
            return "major"
        if self.subject.startswith('Revert "'):
            return "patch"
        if match:
            kind, scope = match[1], match[2] or ""
            if kind == "feat":
                return "minor"
            if kind in {"fix", "perf", "revert"}:
                return "patch"
            if kind in {"build", "chore"} and scope.startswith("deps"):
                return "patch"
        return None


def infer_bump(commits: list[Commit]) -> str | None:
    bumps = {commit.bump for commit in commits}
    return next((kind for kind in ("major", "minor", "patch") if kind in bumps), None)


class Repository:
    def __init__(self, path: Path = ROOT):
        self.path = path

    def git(self, *args: str) -> str:
        return command("git", *args, cwd=self.path)

    def main(self) -> str:
        if self.git("rev-parse", "--is-shallow-repository") != "false":
            raise ValueError("Release planning requires full history (fetch-depth: 0).")
        return self.git("rev-parse", "--verify", "refs/remotes/origin/main^{commit}")

    def tags(self, target: str) -> list[str]:
        return sorted(
            (
                tag
                for tag in self.git("tag", "--merged", target).splitlines()
                if VERSION.fullmatch(tag)
            ),
            key=Version.parse,
        )

    def remote_tags(self) -> dict[str, str]:
        refs = {}
        for line in self.git("ls-remote", "--tags", "origin").splitlines():
            sha, ref = line.split("\t")
            refs[ref.removeprefix("refs/tags/")] = sha
        # Annotated tags point at tag objects; use the peeled commit instead.
        return {
            tag: refs.get(f"{tag}^{{}}", sha)
            for tag, sha in refs.items()
            if not tag.endswith("^{}")
        }

    def commits(self, target: str, previous: str | None = None) -> list[Commit]:
        revision = f"{previous}..{target}" if previous else target
        output = self.git(
            "log", "--no-merges", "--reverse", "--format=%H%x1f%s%x1f%b%x1e", revision
        )
        return [
            Commit(*record.strip().split("\x1f", 2))
            for record in output.split("\x1e")
            if record.strip()
        ]

    def ancestor(self, older: str, newer: str) -> None:
        self.git("merge-base", "--is-ancestor", older, newer)


class GitHub:
    def __init__(self, repo: str):
        if not re.fullmatch(r"[\w.-]+/[\w.-]+", repo):
            raise ValueError("Repository must be OWNER/REPO.")
        self.repo = repo

    def api(self, path: str, payload: dict[str, Any] | None = None) -> Any:
        args = ["gh", "api", f"repos/{self.repo}/{path}"]
        if payload is not None:
            args.extend(["--method", "POST", "--input", "-"])
        return json.loads(
            command(*args, stdin=json.dumps(payload) if payload else None)
        )

    def releases(self) -> list[dict[str, Any]]:
        # Never let old backfill entries hide the latest publication on a later page.
        pages = json.loads(
            command(
                "gh",
                "api",
                f"repos/{self.repo}/releases?per_page=100",
                "--paginate",
                "--slurp",
            )
        )
        return [release for page in pages for release in page]

    def require_ci(self, target: str) -> str:
        runs = self.api(
            f"actions/workflows/ci-main.yml/runs?head_sha={target}&event=push&per_page=100"
        )["workflow_runs"]
        matching = [
            run
            for run in runs
            if run["head_sha"] == target
            and run["head_branch"] == "main"
            and run["event"] == "push"
        ]
        latest = max(matching, key=lambda run: run["id"], default=None)
        if (
            not latest
            or latest["status"] != "completed"
            or latest["conclusion"] != "success"
        ):
            raise ValueError(
                f"main commit {target} has no successful latest full CI push run."
            )
        return latest["html_url"]

    def create_tag(self, tag: str, target: str) -> None:
        self.api("git/refs", {"ref": f"refs/tags/{tag}", "sha": target})

    def create_release(
        self, tag: str, target: str, title: str, notes: str, *, latest: bool
    ) -> None:
        self.api(
            "releases",
            {
                "tag_name": tag,
                "target_commitish": target,
                "name": title,
                "body": notes,
                "draft": False,
                "prerelease": False,
                "make_latest": "true" if latest else "false",
            },
        )


def release_notes(
    repo: str, tag: str, target: str, previous: str | None, commits: list[Commit]
) -> str:
    lines = [f"## {tag}", "", f"Batched release of `{target}` from `main`.", ""]
    for kind, title in (
        ("major", "Breaking changes"),
        ("minor", "Added"),
        ("patch", "Fixed and updated"),
    ):
        selected = list(
            {
                commit.subject: commit for commit in commits if commit.bump == kind
            }.values()
        )
        if selected:
            lines.extend([f"### {title}", ""])
            for commit in selected[:30]:
                subject = commit.subject.replace("\n", " ")
                lines.append(
                    f"- {subject} ([{commit.sha[:7]}](https://github.com/{repo}/commit/{commit.sha}))"
                )
            if len(selected) > 30:
                lines.append(
                    f"- {len(selected) - 30} more changes are included in the full history below."
                )
            lines.append("")
    link = (
        f"https://github.com/{repo}/compare/{previous}...{tag}"
        if previous
        else f"https://github.com/{repo}/commits/{tag}"
    )
    lines.extend([f"[Full history]({link}) ({len(commits)} non-merge commits).", ""])
    return "\n".join(lines)


def cooldown(releases: list[dict[str, Any]], now: datetime) -> bool:
    dates = [
        datetime.fromisoformat(item["published_at"].replace("Z", "+00:00"))
        for item in releases
        if not item["draft"] and not item["prerelease"]
    ]
    return bool(dates and now - max(dates) < INTERVAL)


def release(
    repository: Repository,
    github: GitHub,
    *,
    bump: str = "auto",
    publish: bool = False,
    now: datetime | None = None,
) -> str:
    target = repository.main()
    ci_url = github.require_ci(target)
    tags = repository.tags(target)
    previous = tags[-1] if tags else None
    commits = repository.commits(target, previous)
    if not commits:
        return "No unreleased commits on main."
    inferred = infer_bump(commits)
    kind = inferred if bump == "auto" else bump
    if kind is None:
        return "No release-worthy Conventional Commits; documentation and maintenance stay batched."
    if inferred and ("patch", "minor", "major").index(kind) < (
        "patch",
        "minor",
        "major",
    ).index(inferred):
        raise ValueError(
            f"These commits require a {inferred} bump; {kind} would understate the changes."
        )
    releases = github.releases()
    if bump == "auto" and cooldown(releases, now or datetime.now(timezone.utc)):
        return "Automatic release deferred: the last publication was less than seven days ago."
    version = Version.parse(previous).bump(kind) if previous else Version(0, 1, 0)
    tag = str(version)
    remote = repository.remote_tags()
    if tag in remote and remote[tag] != target:
        raise ValueError(
            f"Existing tag {tag} points to another commit; refusing to move it."
        )
    notes = release_notes(github.repo, tag, target, previous, commits)
    if any(item["tag_name"] == tag for item in releases):
        return f"{tag} is already published."
    if publish:
        # Creating the release also creates a missing tag at this exact SHA.
        github.create_release(tag, target, tag, notes, latest=True)
    return f"{'Published' if publish else 'Preview'} {tag}\nCI: {ci_url}\n\n{notes}"


def history_notes(repo: str, milestones: list[dict[str, Any]], index: int) -> str:
    milestone = milestones[index]
    previous_index = next(
        (i for i in range(index - 1, -1, -1) if milestones[i]["release"]), -1
    )
    lines = [
        "Historical milestone, published retrospectively.",
        "",
        f"Snapshot date: **{milestone['date']}**. Tag: `{milestone['tag']}`.",
        "",
        "Changes are grouped into a few releases; intervening monthly milestones have tags only.",
        "",
    ]
    for item in milestones[previous_index + 1 : index + 1]:
        lines.extend([f"### {item['tag']}: {item['title']}", ""])
        lines.extend(f"- {note}" for note in item["notes"])
        lines.append("")
    previous = milestones[previous_index]["tag"] if previous_index >= 0 else None
    link = (
        f"https://github.com/{repo}/compare/{previous}...{milestone['tag']}"
        if previous
        else f"https://github.com/{repo}/commits/{milestone['tag']}"
    )
    lines.extend([f"[Full history]({link})", ""])
    return "\n".join(lines)


def backfill(
    repository: Repository, github: GitHub, manifest: Path, *, publish: bool = False
) -> str:
    data = json.loads(manifest.read_text(encoding="utf-8"))
    if data["format"] != 1 or not data["milestones"]:
        raise ValueError("Unsupported or empty history manifest.")
    milestones = data["milestones"]
    main = repository.main()
    remote = repository.remote_tags()
    existing = {item["tag_name"] for item in github.releases()}
    previous = None
    first_parent = set(repository.git("rev-list", "--first-parent", main).splitlines())
    # Validate the ENTIRE plan before creating even the first tag.
    for item in milestones:
        version = Version.parse(item["tag"])
        sha = item["sha"]
        if not re.fullmatch(r"[0-9a-f]{40}", sha) or sha not in first_parent:
            raise ValueError(f"{item['tag']} is not an exact main first-parent commit.")
        if repository.git("show", "-s", "--format=%cs", sha) != item["date"]:
            raise ValueError(f"Snapshot date mismatch for {item['tag']}.")
        if previous:
            if version <= Version.parse(previous["tag"]):
                raise ValueError("Historical versions must strictly increase.")
            repository.ancestor(previous["sha"], sha)
        if item["tag"] in remote and remote[item["tag"]] != sha:
            raise ValueError(
                f"Existing tag {item['tag']} points to another commit; refusing to move it."
            )
        previous = item
    output = []
    last_release = max(i for i, item in enumerate(milestones) if item["release"])
    for index, item in enumerate(milestones):
        tag, target = item["tag"], item["sha"]
        if publish and tag not in remote:
            github.create_tag(tag, target)
        output.append(
            f"{'Tag exists' if tag in remote else 'Create tag'} {tag} -> {target}"
        )
        if item["release"]:
            notes = history_notes(github.repo, milestones, index)
            output.extend(
                [
                    f"{'Release exists' if tag in existing else 'Publish release'} {tag}",
                    notes,
                ]
            )
            if publish and tag not in existing:
                github.create_release(
                    tag,
                    target,
                    f"{tag}: {item['title']}",
                    notes,
                    latest=index == last_release,
                )
    return f"{'Applied' if publish else 'Preview'} history backfill\n\n" + "\n".join(
        output
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=["release", "backfill"])
    parser.add_argument("--repo", default=os.environ.get("GITHUB_REPOSITORY"))
    parser.add_argument("--publish", action="store_true")
    parser.add_argument(
        "--bump", choices=["auto", "major", "minor", "patch"], default="auto"
    )
    parser.add_argument(
        "--manifest", type=Path, default=ROOT / ".github/release-history.json"
    )
    args = parser.parse_args()
    repo = args.repo or command(
        "gh", "repo", "view", "--json", "nameWithOwner", "--jq", ".nameWithOwner"
    )
    github = GitHub(repo)
    repository = Repository()
    try:
        result = (
            backfill(repository, github, args.manifest, publish=args.publish)
            if args.mode == "backfill"
            else release(repository, github, bump=args.bump, publish=args.publish)
        )
    except (ValueError, RuntimeError) as error:
        parser.exit(1, f"Release aborted: {error}\n")
    print(result)
    if summary := os.environ.get("GITHUB_STEP_SUMMARY"):
        with Path(summary).open("a", encoding="utf-8") as handle:
            handle.write(result + "\n")


if __name__ == "__main__":
    main()
