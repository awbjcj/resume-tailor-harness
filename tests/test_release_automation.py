"""Offline release guards, including real git history on a local bare remote.

Also runnable without project dependencies:
python -m unittest discover -s tests -p test_release_automation.py -v
"""

from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from unittest.mock import patch

from scripts import release as automation


NOW = datetime(2026, 10, 29, tzinfo=timezone.utc)


class VersionTests(unittest.TestCase):
    def test_numeric_order_and_reset(self):
        self.assertGreater(
            automation.Version.parse("v1.10.0"), automation.Version.parse("v1.9.12")
        )
        version = automation.Version(1, 9, 12)
        self.assertEqual(str(version.bump("major")), "v2.0.0")
        self.assertEqual(str(version.bump("minor")), "v1.10.0")
        self.assertEqual(str(version.bump("patch")), "v1.9.13")
        self.assertEqual(str(automation.Version(0, 5, 0).bump("major")), "v1.0.0")

    def test_reject_noncanonical_versions(self):
        for tag in (
            "1.2.3",
            "v01.2.3",
            "v1.2",
            "v1.2.3-beta.1",
            "sdk-v1.2.3",
            "v1.2.3x",
        ):
            with self.subTest(tag=tag), self.assertRaises(ValueError):
                automation.Version.parse(tag)

    def test_conventional_commit_policy(self):
        cases = {
            "feat: new capability": "minor",
            "feat(api): new capability": "minor",
            "feat(api)!: remove an argument": "major",
            "fix!: incompatible correction": "major",
            "fix: correct a failure": "patch",
            "perf(api): faster queries": "patch",
            "revert: roll back a change": "patch",
            'Revert "feat: a capability"': "patch",
            "chore(deps): upgrade provider": "patch",
            "chore(deps-dev): patch vulnerable tool": "patch",
            "build(deps): upgrade provider": "patch",
            "docs: update instructions": None,
            "test: add regression coverage": None,
            "ci: improve quality gate": None,
            "refactor: simplify internals": None,
            "chore: sync main into dev after promotion": None,
            "unclassified commit": None,
        }
        for subject, expected in cases.items():
            with self.subTest(subject=subject):
                self.assertEqual(automation.Commit("a" * 40, subject).bump, expected)

    def test_breaking_footers_and_highest_bump(self):
        for footer in ("BREAKING CHANGE: new API", "BREAKING-CHANGE: new API"):
            commits = [
                automation.Commit("a" * 40, "fix: correction"),
                automation.Commit("b" * 40, "feat: addition"),
                automation.Commit(
                    "c" * 40, "refactor: simplify", f"Context\n\n{footer}"
                ),
            ]
            self.assertEqual(automation.infer_bump(commits), "major")
        self.assertIsNone(automation.infer_bump([]))

    def test_notes_keep_complete_history_and_bound_long_lists(self):
        commits = [
            automation.Commit(f"{i:040x}", f"fix: correction {i}") for i in range(35)
        ]
        commits.append(commits[0])
        notes = automation.release_notes(
            "owner/repo", "v1.2.4", "a" * 40, "v1.2.3", commits
        )
        self.assertEqual(notes.count("- fix:"), 30)
        self.assertIn("5 more changes", notes)
        self.assertIn("36 non-merge commits", notes)
        self.assertIn("compare/v1.2.3...v1.2.4", notes)


class FakeGitHub(automation.GitHub):
    def __init__(self, repository: automation.Repository):
        super().__init__("example/repository")
        self.repository = repository
        self.published: list[dict[str, Any]] = []
        self.posts: list[tuple[str, dict[str, Any]]] = []
        self.runs = [
            {
                "id": 10,
                "head_sha": repository.main(),
                "head_branch": "main",
                "event": "push",
                "status": "completed",
                "conclusion": "success",
                "html_url": "https://example.test/ci/10",
            }
        ]

    def releases(self) -> list[dict[str, Any]]:
        return self.published

    def api(self, path: str, payload: dict[str, Any] | None = None) -> Any:
        if path.startswith("actions/"):
            return {"workflow_runs": self.runs}
        assert payload is not None
        self.posts.append((path, payload))
        if path == "git/refs":
            tag = payload["ref"].removeprefix("refs/tags/")
            self.repository.git("tag", tag, payload["sha"])
            self.repository.git("push", "origin", tag)
        elif path == "releases":
            tag = payload["tag_name"]
            if tag not in self.repository.remote_tags():
                self.repository.git("tag", tag, payload["target_commitish"])
                self.repository.git("push", "origin", tag)
            self.published.append({**payload, "published_at": NOW.isoformat()})
        return {}


class GitReleaseTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="release tests ")
        self.addCleanup(self.temporary.cleanup)
        self.folder = Path(self.temporary.name)
        self.path = self.folder / "checkout"
        self.path.mkdir()
        automation.command(
            "git", "init", "--bare", str(self.folder / "origin.git"), cwd=self.folder
        )
        self.repository = automation.Repository(self.path)
        self.repository.git("init", "-b", "main")
        self.repository.git("config", "user.name", "Release tests")
        self.repository.git("config", "user.email", "release@example.test")
        self.repository.git("config", "commit.gpgsign", "false")
        self.repository.git("config", "tag.gpgsign", "false")
        self.repository.git("config", "core.autocrlf", "false")
        self.repository.git("remote", "add", "origin", str(self.folder / "origin.git"))
        self.counter = 0
        self.first = self.commit("feat: initial application")
        self.tag("v0.5.0", self.first)
        self.target = self.commit(
            "fix(api): handle an empty response", "Details preserved\n\nMore context."
        )
        self.github = FakeGitHub(self.repository)

    def commit(self, subject: str, body: str = "") -> str:
        self.counter += 1
        (self.path / "app.txt").write_text(str(self.counter), encoding="utf-8")
        self.repository.git("add", "app.txt")
        self.repository.git("commit", "-m", subject, "-m", body)
        self.repository.git("push", "origin", "main")
        return self.repository.git("rev-parse", "HEAD")

    def tag(self, tag: str, sha: str, *, annotated: bool = False):
        args = ["tag", tag, sha]
        if annotated:
            args.extend(["-m", "Annotated milestone"])
        self.repository.git(*args)
        self.repository.git("push", "origin", tag)

    def manifest(self) -> Path:
        path = self.folder / "history.json"
        path.write_text(
            json.dumps(
                {
                    "format": 1,
                    "milestones": [
                        {
                            "tag": "v0.1.0",
                            "sha": self.first,
                            "date": self.repository.git(
                                "show", "-s", "--format=%cs", self.first
                            ),
                            "title": "Foundation",
                            "release": False,
                            "notes": ["Initial capability."],
                        },
                        {
                            "tag": "v0.2.0",
                            "sha": self.target,
                            "date": self.repository.git(
                                "show", "-s", "--format=%cs", self.target
                            ),
                            "title": "Corrections",
                            "release": True,
                            "notes": ["Corrected a response."],
                        },
                    ],
                }
            ),
            encoding="utf-8",
        )
        return path

    def test_real_git_reads_range_and_annotated_tags(self):
        self.tag("v0.4.0", self.first, annotated=True)
        self.assertEqual(self.repository.tags(self.target), ["v0.4.0", "v0.5.0"])
        self.assertEqual(self.repository.remote_tags()["v0.4.0"], self.first)
        commits = self.repository.commits(self.target, "v0.5.0")
        self.assertEqual(len(commits), 1)
        self.assertIn("More context.", commits[0].body)

    def test_preview_is_read_only(self):
        result = automation.release(self.repository, self.github, now=NOW)
        self.assertIn("Preview v0.5.1", result)
        self.assertEqual(self.github.posts, [])
        self.assertNotIn("v0.5.1", self.repository.remote_tags())

    def test_publish_uses_exact_main_sha_and_latest_once(self):
        result = automation.release(self.repository, self.github, publish=True, now=NOW)
        self.assertIn("Published v0.5.1", result)
        payload = self.github.posts[0][1]
        self.assertEqual(payload["target_commitish"], self.target)
        self.assertEqual(payload["make_latest"], "true")
        again = automation.release(self.repository, self.github, publish=True, now=NOW)
        self.assertIn("No unreleased commits", again)
        self.assertEqual(len(self.github.posts), 1)

    def test_failed_running_missing_and_wrong_ci_block_all_writes(self):
        original = self.github.runs[0]
        for changes in (
            {"conclusion": "failure"},
            {"status": "in_progress"},
            {"conclusion": "cancelled"},
            {"head_branch": "dev"},
            {"head_sha": self.first},
            {"event": "pull_request"},
        ):
            self.github.runs = [{**original, **changes}]
            with (
                self.subTest(changes=changes),
                self.assertRaisesRegex(ValueError, "CI push run"),
            ):
                automation.release(self.repository, self.github, publish=True, now=NOW)
        self.github.runs = []
        with self.assertRaises(ValueError):
            automation.release(self.repository, self.github, publish=True, now=NOW)
        self.assertEqual(self.github.posts, [])

    def test_newer_failed_run_cannot_fall_back_to_old_success(self):
        self.github.runs.append(
            {**self.github.runs[0], "id": 11, "conclusion": "failure"}
        )
        with self.assertRaises(ValueError):
            automation.release(self.repository, self.github, publish=True, now=NOW)

    def test_unreleased_dev_commits_are_not_tagged(self):
        self.repository.git("switch", "-c", "dev")
        (self.path / "app.txt").write_text("unreleased dev change", encoding="utf-8")
        self.repository.git("commit", "-am", "feat!: unreleased dev API")
        result = automation.release(self.repository, self.github, publish=True, now=NOW)
        self.assertIn("Published v0.5.1", result)
        self.assertEqual(self.github.posts[0][1]["target_commitish"], self.target)

    def test_automatic_cooldown_and_manual_early_release(self):
        self.github.published = [
            {
                "tag_name": "v0.5.0",
                "draft": False,
                "prerelease": False,
                "published_at": (NOW - timedelta(days=6)).isoformat(),
            }
        ]
        self.assertIn(
            "deferred",
            automation.release(self.repository, self.github, publish=True, now=NOW),
        )
        self.assertEqual(self.github.posts, [])
        self.assertIn(
            "Published v0.5.1",
            automation.release(
                self.repository, self.github, bump="patch", publish=True, now=NOW
            ),
        )

    def test_cooldown_boundary_and_drafts(self):
        releases = [
            {
                "draft": False,
                "prerelease": False,
                "published_at": (NOW - timedelta(days=7)).isoformat(),
            },
            {"draft": True, "prerelease": False, "published_at": None},
            {"draft": False, "prerelease": True, "published_at": NOW.isoformat()},
        ]
        self.assertFalse(automation.cooldown(releases, NOW))

    def test_documentation_only_waits(self):
        self.tag("v0.5.1", self.target)
        self.commit("docs: update the guide")
        self.github = FakeGitHub(self.repository)
        result = automation.release(self.repository, self.github, publish=True, now=NOW)
        self.assertIn("No release-worthy", result)
        self.assertEqual(self.github.posts, [])

    def test_explicit_bump_cannot_understate_breaking_changes(self):
        self.commit("feat!: incompatible API")
        self.github = FakeGitHub(self.repository)
        with self.assertRaisesRegex(ValueError, "require a major bump"):
            automation.release(
                self.repository, self.github, bump="patch", publish=True, now=NOW
            )
        self.assertEqual(self.github.posts, [])

    def test_features_in_merged_branches_are_included(self):
        self.repository.git("switch", "-c", "feature")
        (self.path / "feature.txt").write_text("new capability", encoding="utf-8")
        self.repository.git("add", "feature.txt")
        self.repository.git("commit", "-m", "feat: capability from a merged branch")
        self.repository.git("switch", "main")
        self.repository.git("merge", "--no-ff", "feature", "-m", "Merge feature")
        self.repository.git("push", "origin", "main")
        self.github = FakeGitHub(self.repository)
        result = automation.release(self.repository, self.github, now=NOW)
        self.assertIn("Preview v0.6.0", result)
        self.assertIn("capability from a merged branch", result)

    def test_off_main_version_collision_cannot_move_a_tag(self):
        self.repository.git("switch", "-c", "other")
        (self.path / "app.txt").write_text("other branch", encoding="utf-8")
        self.repository.git("commit", "-am", "feat: private branch")
        other = self.repository.git("rev-parse", "HEAD")
        self.tag("v0.5.1", other)
        with self.assertRaisesRegex(ValueError, "refusing to move"):
            automation.release(self.repository, self.github, publish=True, now=NOW)
        self.assertEqual(self.github.posts, [])

    def test_backfill_is_sparse_idempotent_and_keeps_snapshot_dates(self):
        manifest = self.manifest()
        preview = automation.backfill(self.repository, self.github, manifest)
        self.assertIn("Preview history", preview)
        self.assertEqual(self.github.posts, [])
        automation.backfill(self.repository, self.github, manifest, publish=True)
        self.assertEqual(
            [path for path, _ in self.github.posts],
            ["git/refs", "git/refs", "releases"],
        )
        notes = self.github.published[0]["body"]
        self.assertIn("v0.1.0", notes)
        self.assertIn("Initial capability", notes)
        self.assertIn("published retrospectively", notes)
        before = len(self.github.posts)
        automation.backfill(self.repository, self.github, manifest, publish=True)
        self.assertEqual(len(self.github.posts), before)

    def test_backfill_validates_whole_manifest_before_first_mutation(self):
        manifest = self.manifest()
        data = json.loads(manifest.read_text(encoding="utf-8"))
        data["milestones"][-1]["sha"] = "f" * 40
        manifest.write_text(json.dumps(data), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "first-parent"):
            automation.backfill(self.repository, self.github, manifest, publish=True)
        self.assertEqual(self.github.posts, [])
        self.assertNotIn("v0.1.0", self.repository.remote_tags())

    def test_backfill_rejects_date_and_existing_tag_mismatch(self):
        manifest = self.manifest()
        data = json.loads(manifest.read_text(encoding="utf-8"))
        data["milestones"][-1]["date"] = "2000-01-01"
        manifest.write_text(json.dumps(data), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "date mismatch"):
            automation.backfill(self.repository, self.github, manifest, publish=True)
        manifest = self.manifest()
        self.tag("v0.2.0", self.first)
        with self.assertRaisesRegex(ValueError, "refusing to move"):
            automation.backfill(self.repository, self.github, manifest, publish=True)
        self.assertEqual(self.github.posts, [])

    def test_backfill_recovers_tag_without_release(self):
        manifest = self.manifest()
        self.tag("v0.1.0", self.first)
        self.tag("v0.2.0", self.target)
        automation.backfill(self.repository, self.github, manifest, publish=True)
        self.assertEqual([path for path, _ in self.github.posts], ["releases"])


class ApiTests(unittest.TestCase):
    def test_release_pagination_is_flattened(self):
        with patch.object(
            automation,
            "command",
            return_value='[[{"tag_name":"v1.0.0"}],[{"tag_name":"v0.9.0"}]]',
        ):
            self.assertEqual(len(automation.GitHub("owner/repo").releases()), 2)

    def test_release_payload_uses_structured_json(self):
        with patch.object(automation, "command", return_value="{}") as run:
            automation.GitHub("owner/repo").create_release(
                "v1.0.0",
                "a" * 40,
                "v1.0.0",
                "Two lines\nWith `literal` text",
                latest=False,
            )
            payload = json.loads(run.call_args.kwargs["stdin"])
            self.assertEqual(payload["body"], "Two lines\nWith `literal` text")
            self.assertEqual(payload["make_latest"], "false")


if __name__ == "__main__":
    unittest.main()
