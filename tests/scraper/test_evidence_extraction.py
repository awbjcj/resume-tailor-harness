from resume_tailor_harness.discovery.scraper.browser_worker import snapshot_from_html
from resume_tailor_harness.discovery.scraper.extract import extract_observation


def test_real_quote_does_not_validate_an_invented_title():
    from types import SimpleNamespace
    from resume_tailor_harness.discovery.scraper.contracts import (
        Evidence,
        JobFacts,
        Observation,
    )

    snapshot = snapshot_from_html(
        "https://example.com/jobs/1",
        "<h1>Designer</h1><p>Design useful products for our customers.</p>",
    )

    class Runner:
        def run(self, message):
            return SimpleNamespace(
                content=Observation(
                    source_id="ignored",
                    revision=0,
                    facts=JobFacts(
                        source_url=snapshot.final_url,
                        title="Chief Scientist",
                        jd_text="Design useful products for our customers.",
                    ),
                    evidence=[
                        Evidence(
                            field="title", snapshot_id=snapshot.id, quote="Designer"
                        ),
                        Evidence(
                            field="jd_text",
                            snapshot_id=snapshot.id,
                            quote="Design useful products for our customers.",
                        ),
                    ],
                )
            )

    assert not extract_observation(snapshot, "board", 1, Runner()).accepted


def test_jsonld_preserves_salary_units_locations_and_unknown_policy():
    html = """<script type="application/ld+json">{"@type":"JobPosting","title":"Engineer","description":"Build reliable systems. Work with the team to design and maintain services.","jobLocation":[{"address":{"addressLocality":"New York"}},{"address":{"addressLocality":"Toronto"}}],"baseSalary":{"currency":"USD","value":{"minValue":40,"maxValue":60,"unitText":"HOUR"}}}</script><h1>Engineer</h1>"""
    observation = extract_observation(
        snapshot_from_html("https://example.com/jobs/1", html), "board", 1, None
    )
    assert observation.accepted
    assert observation.facts.locations == ["New York", "Toronto"]
    assert observation.facts.salary_bands[0].minimum == 40
    assert observation.facts.salary_bands[0].period == "HOUR"
    assert observation.facts.remote_policy is None
    assert (
        observation.facts.jd_text
        == "Build reliable systems. Work with the team to design and maintain services."
    )


def test_list_with_multiple_unmatched_jobs_is_not_one_posting():
    html = """<script type="application/ld+json">[{"@type":"JobPosting","title":"One","description":"First job"},{"@type":"JobPosting","title":"Two","description":"Second job"}]</script>"""
    observation = extract_observation(
        snapshot_from_html("https://example.com/jobs", html), "board", 1, None
    )
    assert not observation.accepted


def test_access_page_is_not_a_description():
    observation = extract_observation(
        snapshot_from_html(
            "https://example.com/jobs/1",
            "<h1>Access denied</h1><p>Verify you are human</p>",
        ),
        "board",
        1,
        None,
    )
    assert not observation.accepted


def test_real_quote_cannot_support_invented_attendance():
    from resume_tailor_harness.discovery.scraper.contracts import (
        Evidence,
        JobFacts,
        Observation,
    )
    from resume_tailor_harness.discovery.scraper.validate import validate_evidence
    from resume_tailor_harness.discovery.scraper.browser_worker import (
        snapshot_from_html,
    )

    snap = snapshot_from_html(
        "https://example.com/1",
        "<h1>Engineer</h1><p>Build tools</p><p>Team meetings weekly</p>",
    )
    observation = Observation(
        source_id="x",
        revision=0,
        job_key="one",
        facts=JobFacts(
            source_url=snap.final_url,
            title="Engineer",
            jd_text="Build tools",
            attendance="Five days in office",
        ),
        evidence=[
            Evidence(field=field, snapshot_id=snap.id, quote=quote)
            for field, quote in [
                ("title", "Engineer"),
                ("jd_text", "Build tools"),
                ("attendance", "Team meetings weekly"),
            ]
        ],
    )
    assert not validate_evidence(observation, [snap]).valid


def test_salary_band_cannot_invent_location_association():
    from resume_tailor_harness.discovery.scraper.validate import _supports_value

    assert not _supports_value(
        "salary_bands",
        [
            {
                "minimum": 40,
                "maximum": 60,
                "currency": "USD",
                "period": "HOUR",
                "raw_text": "USD 40-60 per HOUR",
                "locations": ["Toronto"],
            }
        ],
        "New York: USD 40-60 per HOUR. Toronto: CAD 50-70 per HOUR",
    )
