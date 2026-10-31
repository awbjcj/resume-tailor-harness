"""Role-targeted craft guidance distilled from resume-writing playbooks.

These blocks teach HOW to write well; they never establish WHAT is true.
They are appended after the integrity (fact-lock) instructions and before
the user's house style, and must never contain wording that authorizes
inventing or embellishing evidence (guarded by tests/test_tailor_craft.py).
The fact-check reviewer deliberately has no entry here: it is the safety
gate, and holding its prompt fixed keeps trap-recall measurements
attributable to writer changes rather than checker drift.
"""

CRAFT_WRITER = [
    "Write every bullet as an accomplishment. When a cited profile fact supplies "
    "a number, lead with the outcome and its number, then the action that "
    "produced it. When the cited facts carry no number, lead with the concrete "
    "action, its scope, and the specific systems involved - that is a complete "
    "accomplishment bullet, not a lesser one, and inventing an outcome to fill "
    "the gap fails the round.",
    "Start bullets with strong past-tense verbs such as built, shipped, scaled, "
    "reduced, led, or designed only when the source supports that ownership. "
    "Use 'contributed to' or 'supported' when that is the truthful role; "
    "never upgrade participation to leadership for a stronger verb. Replace "
    "vague duty phrasing with the specific contribution the fact describes.",
    "Place the most role-relevant evidence in the top third of the resume, and "
    "order bullets within each role by relevance to this job rather than their "
    "original order.",
    "When a cited fact names the same thing the job names, prefer the job's "
    "exact term (a fact stating Amazon Web Services experience may be written "
    "as AWS); never relabel an adjacent or merely similar activity as the "
    "job's own term. Cover a must-have skill both as a skills-section entry "
    "and inside one supporting bullet when the evidence exists.",
    "When a cited fact supplies both endpoints of a change, write it as "
    "before-to-after (reduced p95 latency from 500ms to 200ms) rather than a "
    "bare percentage; a number persuades only with its baseline or scale "
    "context. Keep each bullet to one claim and at most three numbers.",
    "Name the specific technologies, tools, or methods inside a bullet when "
    "the cited fact names them; a job-critical skill shown in working context "
    "outweighs the same token sitting only in the skills list.",
    "Make the skills section broad, then ordered. Breadth first: include every "
    "profile skill this job names, then every adjacent skill from the same "
    "stack, toolchain, or domain, each listed under its own true name from the "
    "cited fact - an adjacent skill named truthfully is a legitimate entry, "
    "renaming one to the job's own term is not. Then order by this job's "
    "priorities: must-have skills first, then supporting skills. Cut only "
    "low-signal entries (default office tools, tech irrelevant to this role); "
    "use compact comma-joined categories and account for wrapped lines. "
    "Preserve evidenced must-haves; prune redundant supporting entries before "
    "reducing professional experience or project evidence.",
    "Give the most recent and most role-relevant positions the largest bullet "
    "share; compress older or off-target roles to one or two bullets instead "
    "of trimming every role evenly.",
    "Include a concise professional summary in both page modes, normally two "
    "or three lines and at most 40 words explaining why the candidate is a good fit "
    "for this specific position. Connect the job's one or two highest-priority "
    "responsibilities to the candidate's strongest matching skills and a signature "
    "outcome or concrete contribution; show the fit through evidence, "
    "each supported by facts listed in summary_provenance. Never fill it with empty self-praise "
    "such as 'results-driven', 'team player', or 'detail-oriented', and never "
    "state what the candidate is seeking.",
    "Start layout_density at 0. When rendered-layout feedback calls for more breathing "
    "room, lower it toward -1 (up to 12pt body); for a short spill, raise it toward 1 "
    "(10pt body with tighter spacing). The renderer still enforces page limits. "
    "Revise repeated wording or add distinct relevant source evidence when spacing "
    "alone cannot produce one page or two nearly full pages. Keep the summary's "
    "role-fit explanation and preserve correct evidence and provenance.",
    "Include optional sections only when supported and relevant. Preserve publication "
    "author order, venue, date and URLs; show certification issuer, date and credential "
    "ID when supplied. Use awards for standalone honors, education.honors for academic "
    "honors, and portfolio for selected project-backed case studies with source links. "
    "Never repeat a project in both projects and portfolio. Preserve additional_sections "
    "headings and entries verbatim for teaching, grants, patents, service or board roles.",
    "Prefer concrete nouns and numbers over adjectives, delete filler words, "
    "and keep each bullet under roughly thirty words.",
]

CRAFT_MATCH_PLAN = [
    "Plan coverage for every must-have requirement before any nice-to-have, "
    "and for each requirement prefer the strongest evidence: quantified "
    "outcomes over plain statements, recent over old, direct over transferable.",
    "Read the JD's own emphasis signals: a requirement it repeats, lists "
    "first, or marks required outranks one marked preferred, bonus, or a "
    "plus; weight coverage planning accordingly.",
]

CRAFT_REVIEWERS: dict[str, list[str]] = {
    "ats-keyword": [
        "Strong coverage places a must-have skill both as a skills-section "
        "entry and in context inside at least one bullet; a skills-list-only "
        "mention is weak coverage. Weight must-have coverage above "
        "nice-to-have coverage.",
        "Check that the headline or most recent title visibly aligns with the "
        "job's role name and seniority when the underlying evidence supports it.",
        "Treat a near-synonym of a JD term as weak coverage when the evidence "
        "would support the exact term ('risk mitigation' where the job says "
        "'risk management'); suggest the exact term. Flag a term repeated far "
        "beyond natural use as stuffing rather than coverage.",
        "When MUST-HAVE COVERAGE is present it is authoritative. A requirement "
        "marked 'gap' is a qualification the candidate genuinely lacks: never "
        "score it as a missing keyword and never suggest adding it. Score "
        "coverage only over requirements marked 'covered', and treat one marked "
        "'adjacent' as emphasis material that may never be named as the job's "
        "own term.",
    ],
    "recruiter": [
        "Apply a six-second scan standard: the headline, first role, and its "
        "first bullets must carry the strongest role-relevant evidence, and a "
        "resume whose best material sits below the top third scans poorly.",
        "Bullet lead words carry the scan: flag bullets that open with weak, "
        "generic, or duty phrasing instead of a strong verb or outcome.",
        "Flag empty self-praise in the summary ('results-driven', 'team "
        "player', 'detail-oriented') and any statement of what the candidate "
        "is seeking; summary lines must read as evidence, not adjectives.",
        "Require the summary to explain why the candidate is a good fit for this "
        "specific position by connecting cited accomplishments or capabilities to "
        "the job's main responsibilities. Flag a missing summary or a generic "
        "biography with no clear requirement-to-evidence connection; a bare "
        "'excellent fit' claim is not that connection.",
    ],
    "hiring-manager": [
        "Reward concrete scale signals such as users, throughput, data volume, "
        "latency, revenue, or team size that make evidence credible at the "
        "expected seniority.",
        "Distinguish ownership verbs (designed, led, built) from participation "
        "verbs (contributed to, assisted with), and flag evidence whose "
        "ownership level does not match the role's seniority.",
    ],
    "concision": [
        "Preserve professional experience and projects when resolving length "
        "pressure. Retain a useful concise summary; shorten repeated wording and "
        "secondary details before recommending cuts to distinct work evidence.",
        "Flag bullets over roughly thirty words when excess wording obscures "
        "their evidence, vague duty phrasing, and duplicated evidence across "
        "bullets. A repeated verb or truthful participation qualifier alone "
        "is not a defect; preserve distinct evidence and actual ownership.",
        "Flag filler words and empty intensifiers (various, numerous, "
        "successfully, effectively), bullets packing more than three numbers, "
        "and any bullet carrying more than one distinct claim.",
    ],
}
