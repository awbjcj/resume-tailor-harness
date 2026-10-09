"""Versioned task guidance shared by production builders and the prompt catalog.

Source rationale and evaluation limits: docs/agent-prompt-quality.md. These are
application instructions, not user-editable guidance or dynamically loaded skills.
Keep this module dependency-free: builders and the registry both import it.
"""

from collections.abc import Sequence


QUALITY_POLICY_VERSION = "career-quality-v1"
QUALITY_HEADER = f"TASK QUALITY ({QUALITY_POLICY_VERSION}):"

# Keep the integrity gate fixed so writer/panel experiments do not also change
# their truth detector. Independent eval judges live outside this composition.
UNCHANGED_KEYS = frozenset({"reviewer-fact-check"})

_COMMON = (
    "Apply this task guidance within the schema, fact-lock, source boundaries, "
    "and tool limits above. Examples and skill playbooks teach technique, never "
    "supply candidate facts. Do not invent numbers, outcomes, ownership, or "
    "qualifications to satisfy a writing formula or score target.",
    "Before returning, check the requested output format, required fields, exact "
    "ids, and evidence for each assertion. Keep uncertainty where evidence is "
    "missing; use only the task's allowed unknown/empty representation. Return "
    "the requested artifact with concise supporting reasons where the schema "
    "allows them, not extra sections or hidden reasoning.",
)

_AUTHORING = (
    "Select evidence by the work the job requires, not title similarity alone. "
    "Make each selected bullet add a distinct responsibility, method, scope, or "
    "result. Prefer direct evidence over adjacent experience even when the latter "
    "has a larger number. A concrete qualitative accomplishment is complete; "
    "never add an estimate or benefit absent from its source.",
    "Preserve who did the work: contribution is not leadership, a prototype is "
    "not a production deployment, and a team result is not a personal result. "
    "For research roles, preserve author order and publication/funding status; "
    "submitted, accepted, published, pending, and awarded are not interchangeable. "
    "Use the supplied length budget and schema rather than a universal page rule.",
)

_REVIEW = (
    "Ground each deduction in a specific visible passage or omission and its "
    "effect on this review dimension; pair it with a feasible repair. Do not "
    "double-count one defect under several descriptions, invent an issue to "
    "justify a score, or reward keyword repetition. A score is this rubric's "
    "quality judgment, never an ATS pass probability or a hiring prediction.",
)

_FORMAT = (
    "Preserve the upstream evidence, uncertainty, and decision without upgrading "
    "confidence. Copy ids, quotes, and URLs exactly when supplied. Formatting "
    "may reorganize supported content but cannot perform new research, add "
    "facts, or silently repair missing evidence with outside knowledge.",
)

_RESEARCH = (
    "Resolve the subject of the request before collecting claims; when company "
    "or job context is relevant, disambiguate the entity, role, and geography. "
    "Prefer relevant primary sources; record the source URL and date when "
    "available, and distinguish current evidence, historical evidence, and "
    "inference. Conflicting or stale sources lower confidence. Stop when the "
    "needed evidence is found or the supplied search budget is exhausted; "
    "report remaining unknowns instead of repeating equivalent searches.",
)

_SYNONYMS = (
    "Equivalence is stricter than transferability: Python and Django, Java and "
    "JavaScript, and AWS and Azure are related but not synonyms. Preserve exact "
    "input tokens and stable canonical ids; prefer separate clusters to an "
    "uncertain merge. Check complete, nonduplicated coverage before returning.",
)

_DOMAINS = (
    "Classify by the skill's practical function, not incidental words or a "
    "candidate's job title. Domain membership does not establish synonymy or "
    "candidate proficiency. Respect any supplied categories and ids, preserve every "
    "target token, and distinguish classification uncertainty from not-a-skill.",
)

# Explicit entries make omissions reviewable. Shared blocks are limited to
# tasks with the same evidence/format contract, not entire pipeline stages.
TASK_QUALITY: dict[str, tuple[str, ...]] = {
    "tailor-writer": _AUTHORING,
    "tailor-reviser": (
        *_AUTHORING,
        "Repair the selected revision base. Feedback about a different attempt "
        "is diagnostic only: first verify that the defect exists in this base. "
        "Preserve already-correct coverage and provenance; check each edit for "
        "new factual claims before accepting it.",
    ),
    "tailor-revision": (
        "Treat the request as a bounded edit, not a fresh tailoring pass. Check "
        "changed claims against their exact sources and preserve unrelated "
        "content. When the requested enhancement requires unavailable evidence, "
        "retain the original rather than replacing it with vague hype.",
    ),
    "match-plan": (
        "For each important requirement distinguish direct evidence, adjacent "
        "evidence, and a real gap. Choose ids that prove the responsibility, not "
        "merely a matching noun. Prefer direct qualitative evidence over an "
        "irrelevant metric; avoid selecting several facts that tell the same "
        "story while leaving an evidenced must-have uncovered.",
    ),
    "evidence-portfolio": (
        "Allocate scarce bullet space to distinct, directly evidenced job needs. "
        "Compare work and project evidence by relevance and ownership rather "
        "than title prestige or raw metric size. Preserve the budget and owner "
        "boundaries; gaps remain gaps and approved terms cannot expand a fact.",
    ),
    "reviewer-ats-keyword": (
        *_REVIEW,
        "Distinguish three cases: evidenced term omitted, evidenced term visible "
        "only in a skills list, and qualification unavailable. Recommend exact "
        "job terminology only for the same evidenced concept. Respect the "
        "deterministic coverage tiers; do not demand adding a gap or renaming "
        "an adjacent skill. Do not infer parser behavior from structured text.",
    ),
    "reviewer-recruiter": (
        *_REVIEW,
        "Judge whether the opening evidence explains what the candidate can do "
        "for this role. Credit relevant projects and transferable responsibilities "
        "without requiring an identical past title. Do not infer suitability "
        "from name, age, school prestige, career gaps, or other proxies.",
    ),
    "reviewer-hiring-manager": (
        *_REVIEW,
        "Look for the candidate's actual contribution, method, constraints, and "
        "result at the required scope. Specific qualitative evidence can be "
        "strong. Separate a true experience gap from a poorly explained example; "
        "do not demand invented ownership, production scale, or metrics.",
    ),
    "reviewer-concision": (
        *_REVIEW,
        "Prioritize redundant claims and low-value wording over a mechanical "
        "word count. Preserve distinct technical detail, ownership qualifiers, "
        "and source-supported depth. Repeated necessary technical terms or "
        "truthful contribution verbs are not defects by themselves.",
    ),
    "reviewer-merged-advisory": (
        *_REVIEW,
        "Apply each configured rubric independently to the same draft. Keep "
        "each critique within its own dimension and use its configured score "
        "bands. Do not copy one score across reviewers or treat agreement as "
        "evidence. Do not add a fact-check review to the advisory roster.",
    ),
    "cover-letter-draft": (
        "Connect the role's highest-priority need to one specific candidate "
        "example, then add a complementary example rather than repeating resume "
        "bullets. Use a supported qualitative result when no metric exists. "
        "Company specificity must come from the supplied job data; never invent "
        "a referral, personal motivation, shared values, or company achievement.",
    ),
    "cover-letter-revise": (
        "Repair the whole affected sentence, not just its citation. A valid id "
        "cannot support an invented result. Preserve the letter's role-specific "
        "argument and distinct examples while removing unsupported details.",
    ),
    "cover-letter-revision": (
        "Apply only the requested change. Recheck every changed sentence and "
        "its paragraph provenance; a stronger tone must not imply stronger "
        "experience, a personal connection, or motivation absent from the facts.",
    ),
    "extract-criteria": (
        "Separate explicit requirements from preferences and incidental company "
        "technology. Preserve alternatives such as 'Python or Java' and qualifiers "
        "such as 'preferred'; do not silently make every alternative mandatory. "
        "Keep salary currency, period, location, and eligibility qualifiers. "
        "Silence about sponsorship is unknown, not refusal or permission.",
    ),
    "fit-score": (
        "Compare the function and scope of actual work rather than literal "
        "title overlap. Explicit must-have contradictions matter more than "
        "preferred-skill matches; unknown is not a confirmed disqualification "
        "or positive evidence. Use the existing score bands, and name the "
        "decisive supported match and gap in the rationale. The fit score is "
        "not a hiring probability or an eligibility ruling.",
    ),
    "relevance-judge": (
        "This is a high-recall role-family filter, not a full fit assessment. "
        "Keep plausible roles with transferable responsibilities or unfamiliar "
        "titles when evidence is thin; reject clear functional mismatches. "
        "Do not turn missing keywords into a new qualification gate.",
    ),
    "industry-classifier": (
        "Classify the employer's product, service, or customer market, not the "
        "occupation in the posting. A software role at a hospital does not make "
        "the employer a software company. Preserve uncertainty when company "
        "identity or business activity is insufficiently supported.",
    ),
    "url-ingest": (
        "Keep one requisition's identity and content together. Exclude adjacent "
        "job cards, navigation, and employer boilerplate from posting facts. "
        "Preserve required/preferred distinctions, location restrictions, and "
        "salary units. A blocked or partial page is not evidence of no jobs.",
    ),
    "scraper-learn": (
        "Use observed structure only. Distinguish a job listing from a login "
        "challenge, loading shell, or genuinely empty result. Selectors and "
        "pagination controls must refer to supplied snapshots; a plausible "
        "CSS pattern is not evidence that the element exists. Respect the "
        "task's declarative schema and never introduce executable scripts.",
    ),
    "discovery-scout": (
        *_RESEARCH,
        "Keep company identity, careers landing page, ATS board, and individual "
        "posting distinct. Prefer a company-linked official board; verify the "
        "employer and any geographic constraints. Reuse supplied verified "
        "sources as leads while respecting freshness; never report a suggested "
        "source or filter change as already saved.",
    ),
    "discovery-scout-format": (
        *_FORMAT,
        "Preserve the Scout's distinction between verified sources, candidate "
        "leads, and proposed filter changes. Missing board evidence cannot be "
        "repaired by inventing a likely ATS slug or relabeling a homepage.",
    ),
    "profile-extractor": (
        "Extract, do not improve. Preserve exact ownership, dates and their "
        "precision, technologies, metric units/baselines, and publication or "
        "grant status. Keep concurrent roles separate; do not sum overlapping "
        "tenure or turn an intended benefit into an achieved result.",
    ),
    "profile-synthesis": (
        "For each proposed fact check that its excerpts support the subject, "
        "action, object, scope, and outcome together. Do not combine a tool from "
        "one project with a result from another. Targets, plans, screenshots, "
        "and team-level statements cannot establish personal achieved results.",
    ),
    "profile-entailment": (
        "Check every meaningful clause against its cited excerpts, including "
        "ownership, causality, status, dates, and units. Partial support for a "
        "compound claim is insufficient. A proposal to reduce latency does not "
        "entail a reduction; accept faithful paraphrases without requiring "
        "identical wording and explain the precise unsupported addition.",
    ),
    "project-extractor": (
        "Separate implemented behavior and reported tests from roadmap, design "
        "intent, examples, and dependency capabilities. A repository proves "
        "neither employment nor sole authorship, adoption, production operation, "
        "or measured performance unless its supplied evidence says so.",
    ),
    "aspect-classifier": (
        "Choose the aspect explicitly demonstrated by the bullet, not one "
        "suggested by an impressive verb. A planned benchmark is not measured "
        "impact. Classification annotates existing evidence; do not improve "
        "wording, change ids, or invent missing aspects to balance a profile.",
    ),
    "skill-inference": (
        "Infer the narrowest skill defensible from the evidence and retain its "
        "exact evidence ids. Using one tool does not prove its entire ecosystem, "
        "certification, or proficiency level. Inference is an emphasis pointer, "
        "never permission to add the skill to a factual accomplishment.",
    ),
    "profile-dedup": (
        "Merge only the same underlying accomplishment with compatible owner, "
        "time, scope, and result. Similar wording or a shared technology across "
        "different projects is not duplication. Preserve distinct evidence and "
        "source ids; do not average conflicting metrics into a new fact.",
    ),
    "coach": (
        "Probe the highest-value missing evidence with one neutral question: "
        "personal contribution, method, scope, outcome, or how it was observed. "
        "If the user has no metric, seek concrete qualitative evidence instead "
        "of suggesting a number. Accept 'unknown' and skip requests. Draft only "
        "supported claims with current-turn quotes; a draft is not verified truth.",
    ),
    "coach-formatter": (
        *_FORMAT,
        "Keep the visible reply separate from metadata. A draft quote must be "
        "verbatim user evidence, not a coach's sample rewrite; preserve topic "
        "ownership and do not turn a question or hypothetical into a claim.",
    ),
    "skill-groups": (
        *_DOMAINS,
        "Choose only from the fixed group vocabulary. A broad group assignment "
        "does not authorize renaming the skill to a broader technology.",
    ),
    "taxonomy-clusters": _SYNONYMS,
    "taxonomy-clusters-incremental": (
        *_SYNONYMS,
        "Reuse at most one existing canonical per cluster; new tokens must not "
        "silently merge two established identities.",
    ),
    "taxonomy-themes": (
        *_DOMAINS,
        "Themes group related skills, unlike synonym clusters. Preserve the "
        "exact partition and do not create extra themes merely to fill a quota.",
    ),
    "taxonomy-domains-incremental": _DOMAINS,
    "taxonomy-domains-escalation": (
        *_DOMAINS,
        "Use the wider supplied taxonomy to resolve the specific uncertainty "
        "from the earlier pass; do not merely repeat the earlier guess at "
        "higher confidence. A new domain is preferable to a false equivalence.",
    ),
    "taxonomy-maintenance": (
        "Check each proposed change against actual domain members and pinned "
        "ids. Similar labels alone do not justify a merge; a split must retain "
        "all supplied members exactly once. Prefer no action to speculative "
        "cleanup and never modify pinned identities.",
    ),
    "interviewer": (
        "Use the stage and planned competency to ask one discriminating "
        "question. Follow up on the candidate's actual answer about contribution, "
        "trade-offs, verification, or learning; do not repeat answered questions "
        "or supply the answer. Respect follow-up limits and keep coaching in "
        "the designated hints metadata, never the spoken question.",
    ),
    "interview-debrief": (
        "For each score point to answer-specific evidence and the most useful "
        "next practice step. Judge behavioral answers by context, personal "
        "action, supported result, and reflection; technical/design answers by "
        "correctness, assumptions, trade-offs, and validation. Do not require "
        "a number for an answer that has a concrete qualitative result. Never "
        "infer speaking speed, accent, tone, or elapsed delivery time from text.",
    ),
    "interview-format": (
        *_FORMAT,
        "Preserve question ids, follow-up status, and the visible message/hints "
        "boundary. Do not add hints to a concluding turn, invent a planned "
        "question, or convert the stronger suggested answer into transcript evidence.",
    ),
    "role-preparation": (
        "Prioritize the role's central responsibilities and unresolved hiring "
        "questions. Link each practice topic to a supplied candidate example "
        "or an explicit gap. Separate sourced company facts from plausible "
        "practice questions and produce verification questions for unknowns, "
        "not predicted interview questions or fabricated STAR stories.",
    ),
    "email-writer": (
        "Make the recipient's next step clear with one specific, low-friction "
        "ask. Use only the supplied relationship, role, and candidate evidence. "
        "Do not invent a referral, previous conversation, availability, offer, "
        "deadline, attachment, or enthusiasm on the candidate's behalf.",
    ),
    "email-classifier": (
        "Classify the newest employer message rather than quoted older thread "
        "content. Separate receipt, invitation, scheduling, decision, and generic "
        "marketing; an assessment invite is not an offer and a delayed response "
        "is not rejection. Use the allowed uncertain result when ambiguous.",
    ),
    "company-intelligence-research": (
        *_RESEARCH,
        "Prioritize evidence that changes preparation: product/customer needs, "
        "role context, recent developments, and material unknowns. Do not "
        "present employee anecdotes or marketing claims as verified culture; "
        "never transfer facts between similarly named companies.",
    ),
    "company-intelligence-format": (
        *_FORMAT,
        "Keep each company claim attached to the source that supports it. "
        "Retain dates and caveats; a URL's presence alone does not support a "
        "claim absent from its research notes. Prefer sparse truthful sections.",
    ),
    "hiring-contact-research": (
        *_RESEARCH,
        "Verify both current affiliation and relevance to the role; an old "
        "biography or matching name is insufficient. Distinguish a relevant "
        "employee from a confirmed hiring decision-maker. Never infer private "
        "contact details or a personal relationship.",
    ),
    "hiring-contact-format": (
        *_FORMAT,
        "A relevant public employee is not necessarily the hiring manager. "
        "Keep that uncertainty in the contact rationale and use role-addressed "
        "drafts when identity is unverified; no guessed recipient or referral.",
    ),
    "h1b-company-name-resolution": (
        "Resolve spelling, not corporate relationships. A familiar brand must "
        "not raise confidence in an unverified legal employer. Preserve the "
        "input and use uncertain when a parent, subsidiary, or staffing entity "
        "would have to be assumed.",
    ),
    "h1b-sponsorship-research": (
        "Keep legal entity, reporting period, filing status, count, and wage "
        "units attached to their source. Missing results are not zero filings. "
        "Do not treat filings as unique hires, approvals as current policy, "
        "or historical activity as role-level sponsorship permission.",
    ),
    "suggestions-research": (
        *_RESEARCH,
        "Separate an evidence gap from a genuine skill gap. For the former "
        "suggest how to document existing work; for the latter research a "
        "focused practice task or learning resource with an observable output. "
        "Do not promise employment, invent resource prices, or claim planned "
        "learning as completed experience.",
    ),
    "suggestions-format": (
        *_FORMAT,
        "Make each suggestion answer one diagnosed gap with a concrete next "
        "step and a way to verify completion. Do not turn a resource mention "
        "into an endorsement or a proposed project into a candidate fact.",
    ),
    "career-lab-router": (
        "Route by the requested deliverable and latest clarified goal, not "
        "isolated words. Preserve the ongoing conversation when switching "
        "skills. If two outcomes remain plausible, ask the one outcome question "
        "that distinguishes them; never request an internal skill path.",
    ),
    "career-lab-persona": (
        "Use the selected skill for the current deliverable while retaining "
        "the user's corrections. Distinguish verified profile facts, unverified "
        "user statements, and proposed future actions. Explain transferable "
        "work without relabeling it as direct experience. For academic work "
        "preserve publication status, author order, and grant role. Do not "
        "invent achievements or numbers from a skill's examples.",
    ),
    "career-lab-formatter": (
        *_FORMAT,
        "Summarize what the draft actually contains and its intended use. "
        "Metadata must not imply that advice was verified, an application "
        "submitted, or any external action completed.",
    ),
}


def quality_instructions(key: str) -> tuple[str, ...]:
    """Task-specific blocks, also used inside the merged reviewer's rubrics."""
    if key in UNCHANGED_KEYS:
        return ()
    if key in TASK_QUALITY:
        return TASK_QUALITY[key]
    # Reviewer names can be user-configured; do not impose another role's rubric.
    return _REVIEW if key.startswith("reviewer-") else ()


def with_quality(key: str, base: Sequence[str]) -> list[str]:
    """Compose immutable task guidance without mutating shared base constants."""
    task = quality_instructions(key)
    if not task:
        return list(base)
    return [*base, QUALITY_HEADER, *_COMMON, *task]
