import httpx

from resume_tailor_harness.profile.corpus import add_source
from resume_tailor_harness.profile.github import GitHubClient
from resume_tailor_harness.services import profile_github


def test_repository_choices_show_saved_branches_and_uploaded_overrides(
    tmp_path, monkeypatch
):
    profile_dir = tmp_path / "profile"
    dossier = tmp_path / "engine-dossier.md"
    dossier.write_text(
        "---\nrepo_url: https://github.com/ada/engine\n---\n# Engine", encoding="utf-8"
    )
    add_source(profile_dir, dossier)
    http = httpx.Client(
        base_url="https://api.github.com",
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                json=[
                    {
                        "name": "engine",
                        "full_name": "ada/engine",
                        "owner": {"login": "ada"},
                        "html_url": "https://github.com/ada/engine",
                        "default_branch": "main",
                    }
                ],
            )
        ),
    )
    monkeypatch.setattr(
        profile_github, "GitHubClient", lambda: GitHubClient(token="", client=http)
    )
    rows = profile_github.list_repositories(
        "ada",
        profile_dir,
        allow=(),
        deny=(),
        limit=20,
        branches={"ada/engine": "feature/dossier"},
    )
    assert rows == [
        {
            "owner": "ada",
            "name": "engine",
            "full_name": "ada/engine",
            "default_branch": "main",
            "selected_branch": "feature/dossier",
            "included": True,
            "uploaded_override": True,
        }
    ]
    assert http.is_closed
