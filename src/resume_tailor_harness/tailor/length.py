from resume_tailor_harness.models.resume import ResumeContent
from resume_tailor_harness.profile.depth import (
    clamped_ceiling,
    clamped_floor,
    planned_owners,
)
from resume_tailor_harness.models.profile import ProfileFacts
from resume_tailor_harness.tailor.review_config import LengthBudget


def format_budget(budget: LengthBudget) -> str:
    """Render the budget as one prompt instruction for tailor/reviser agents.

    The prose ranges and the skills target are stated as two separate budgets on
    purpose. Given only caps and "drop the rest", the writer economized on the
    skills section as hard as on bullets, even though the two cost wildly
    different amounts of page space - so the skills sentence has to say what it
    actually costs, or the one-page instruction reads as a reason to cut it.
    """
    budget = budget.for_pages()
    shape = (
        "ONE-PAGE PRIORITY: Include a concise, evidence-backed summary of 25–40 words "
        "with summary_provenance, explaining fit for this position by connecting the job's "
        "main requirements to verified candidate evidence. Preserve professional experience and projects. Keep both "
        "sections when relevant evidence exists; compress older roles before dropping "
        "project evidence. Aim for 400–550 words overall including the summary and "
        "optional sections, and 15–25 words per bullet, normally one or two rendered lines. "
        if budget.page_target == 1
        else "TWO-PAGE PRIORITY: Include an evidence-backed summary within 40 words with "
        "summary_provenance that connects the job's main requirements to verified candidate "
        "evidence and explains fit for this position. Aim for 650–900 words when distinct relevant source evidence "
        "supports it, with both pages nearly full (at least 80% of their usable height). "
        "Avoid a one-and-a-half-page resume: expand relevant work, projects, portfolio, "
        "publications or credentials from verified facts, or edit into a concise one-page "
        "draft when evidence is sparse. Never pad with repeated claims or filler. "
    )
    shape += (
        "Optional sections are selected by relevance and available evidence: honors and "
        "awards, publications, certifications, portfolio, languages, volunteering, interests, "
        "and source-backed additional_sections. Do not create empty sections. Preserve "
        "publication authors and source URLs; portfolio entries cite project facts and "
        "count toward the project and evidence-owner limits, never duplicate projects. "
        "Keep additional-section headings and selected entries verbatim from the profile. "
        "Adjust wording, bullet counts and section selection during drafting/revision; "
        "the renderer adjusts font size and spacing but never cuts approved content. "
    )
    return shape + (
        f"Target {budget.page_target} pages. Use at most {budget.max_experiences} experiences, "
        f"{budget.max_projects} projects, and {budget.max_evidence_owners} combined "
        f"evidence owners; roles render {budget.min_bullets_per_role}–"
        f"{budget.max_bullets_per_role} bullets and projects render "
        f"{budget.min_bullets_per_project}–{budget.max_bullets_per_project}, "
        f"subject to the per-owner depth plan. Aim for about "
        f"{budget.target_total_bullets} bullets in total. Within each owner, "
        f"cover at least {budget.min_aspects_per_owner} different aspects when "
        "the cited source supply permits it. "
        "The skills section is budgeted separately: use compact comma-joined "
        "categories, remembering long technology names wrap onto more lines. Aim for "
        f"{budget.target_skills} skills entries, at most "
        f"{budget.max_skills_per_category} per category, and include every profile "
        "skill this job names as well as every adjacent skill from the same stack, "
        "toolchain, or domain. Listing an adjacent skill under its own true name "
        "from the cited fact is correct and expected; renaming it to the job's own "
        "term is not, and still fails. Preserve evidenced must-have skills; trim "
        "irrelevant or redundant supporting entries before reducing work evidence."
    )


def format_depth_plan(facts: ProfileFacts, budget: LengthBudget) -> str:
    """Deterministic, fact-clamped render ranges for the selected owners."""
    budget = budget.for_pages()
    owners = planned_owners(facts, budget)
    if not owners:
        return ""
    lines = ["BULLET DEPTH PLAN (deterministic; per evidence owner):"]
    for owner in owners:
        supply = len(owner.bullets)
        floor = clamped_floor(owner, budget)
        ceiling = clamped_ceiling(owner, budget)
        span = str(floor) if floor == ceiling else f"{floor}–{ceiling}"
        limited = supply < (
            budget.min_bullets_per_role
            if owner.kind == "experience"
            else budget.min_bullets_per_project
        )
        note = " (supply-limited; do not invent)" if limited else ""
        lines.append(
            f'- {owner.id} "{owner.label}": {supply} source -> render {span}{note}'
        )
    return "\n".join(lines)


def resume_stats(content: ResumeContent) -> str:
    """Deterministic size summary for reviewers."""
    total_bullets = sum(len(e.bullets) for e in content.experience) + sum(
        len(p.bullets) for p in (*content.projects, *content.portfolio)
    )
    return (
        f"experiences={len(content.experience)} projects={len(content.projects) + len(content.portfolio)} "
        f"portfolio_entries={len(content.portfolio)} "
        f"total_bullets={total_bullets} "
        f"summary_words={len((content.summary or '').split())} "
        f"bullet_words={sum(len(b.text.split()) for e in (*content.experience, *content.projects, *content.portfolio) for b in e.bullets)}"
    )


def prepare_draft(content: ResumeContent, budget: LengthBudget) -> ResumeContent:
    """Keep authored summaries and their evidence intact for every review round.

    Length guidance belongs in the writer/reviser budget. Deterministic deletion
    would hide unsupported summary claims from provenance and fact-check gates.
    """
    return content
