"""Read-only GitHub repository and branch choices for profile sources."""

from pathlib import Path

from resume_tailor_harness.profile.corpus import load_manifest
from resume_tailor_harness.profile.github import GitHubClient
from resume_tailor_harness.profile.github_harvest import (
    branch_for_repo,
    select_repos,
    dossier_repo_urls,
)
from resume_tailor_harness.profile.github_ingest import normalize_repo_url


def list_repositories(
    username: str,
    profile_dir: Path,
    *,
    allow: tuple[str, ...],
    deny: tuple[str, ...],
    limit: int,
    branches: dict[str, str],
) -> list[dict]:
    github = GitHubClient()
    try:
        repos = github.fetch_repos(username)
    finally:
        github.close()
    selected = select_repos(repos, allow=allow, deny=deny, limit=limit)
    excluded = set(load_manifest(profile_dir).excluded_github_repos)
    overrides = dossier_repo_urls(profile_dir)
    result = []
    for repo in repos:
        owner = (repo.get("owner") or {}).get("login") or username
        result.append(
            {
                "owner": owner,
                "name": repo["name"],
                "full_name": repo.get("full_name") or f"{owner}/{repo['name']}",
                "default_branch": repo.get("default_branch"),
                "selected_branch": branch_for_repo(repo, branches),
                "included": repo in selected
                and normalize_repo_url(repo.get("html_url")) not in excluded,
                "uploaded_override": normalize_repo_url(repo.get("html_url"))
                in overrides,
            }
        )
    return sorted(
        result, key=lambda repo: (not repo["included"], repo["full_name"].casefold())
    )


def list_branches(owner: str, repo: str) -> list[str]:
    github = GitHubClient()
    try:
        return github.fetch_branches(owner, repo)
    finally:
        github.close()
