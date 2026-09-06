from resume_tailor_harness.discovery.scraper.browser_worker import snapshot_from_html
from resume_tailor_harness.discovery.scraper.extract import extract_observation


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
