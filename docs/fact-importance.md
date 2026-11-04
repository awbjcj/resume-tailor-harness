# Fact importance and resume emphasis

Every provenance-addressable fact has additive `importance` assessment metadata
and an application-computed `importance_score`. Extraction keeps the complete
evidence bank. A lower rating never deletes a source fact or changes its wording,
identity, provenance, or eligibility under fact-lock.

The initial policy is a heuristic for resume selection, not a measured hiring
probability. It follows the resume-customizer and resume-tailor guidance on
target-role relevance and preserving a complete master record, and the
resume-bullet-writer and resume-quantifier guidance on contribution, results,
scale and defensible evidence. Missing metrics never authorize estimation or
arithmetic; the repository's fact-lock rules govern those claims.

## Version 1 metrics

| Factor | Weight | Meaning |
| --- | ---: | --- |
| Significance | 25% | How substantial or defining the achievement, responsibility or qualification is |
| Essentiality | 20% | Whether omission would hide the core contribution or qualification |
| Experience context | 20% | Professional, research, personal project, academic project, education, volunteering or unknown |
| Impact | 15% | Explicit activity, qualitative result, measured outcome, or major measured outcome with comparison |
| Ownership | 10% | Explicit participation, individual contribution, ownership, or end-to-end accountability |
| Evidence traceability | 10% | Source reference or valid literal evidence pointers; this does not certify source truth |

Significance and essentiality use 0 incidental/dispensable, 1 supporting,
2 useful, 3 major/core, and 4 defining/indispensable. Impact uses 0 unstated,
1 activity/deliverable, 2 explicit qualitative result, 3 measured result with
scope, and 4 major measured result with baseline/comparison. Ownership uses
0 unstated, 1 participation, 2 specific personal contribution, 3 explicit
ownership/leadership, and 4 explicit end-to-end accountability.

The context scale is professional 100, research 80, personal project 65,
academic project 55, education 60, volunteer 60, and unknown 50. Employment,
internships and client work are professional. Source-supported context is
inherited by nested bullets. A repository or dossier does not imply personal
authorship or paid employment. Unknown stays explicit.

Evidence traceability is 50 for an unlinked literal fact, 75 with a source
reference, and 100 for a skill with resolvable literal evidence pointers. An
inferred skill without resolvable evidence receives 0 for that factor. Stars,
forks, document length, duplicate examples and citation count add no points.
An owner uses the strongest assessment from itself and its children in each
dimension, without a bonus for having more bullets. This lets the complete
dossier evidence bank inform an owner whose initial metadata assessment saw
only a shorter extraction document. Legacy bullet fallback
uses only the closed aspect classification and does not guess measured
results or personal ownership.

Each ordinal rating is normalized to 0–100. The total is the weighted sum;
`importance_score.components` records each factor's point contribution and
sums to `importance_score.score` (0–100). `version=1`, `context`, and `method`
(`assessed` or `fallback`) make the result inspectable. Job relevance and
recency remain separate from this reusable, job-independent score.

## Selection and frequency

Direct must-have coverage, other direct coverage and adjacent coverage remain
the first deterministic ranking signals. Weighted importance then precedes
raw metric counts, recency and source-order tie breakers. Thus equally
relevant paid work has a context advantage, while a strong school or personal
project can beat a weak work fact. Strong technical or qualitative evidence
does not need an invented number to rank well.

The evidence catalog exposes owner scores, context and individually addressable
project highlights. The planner and writer use the scores to lead with stronger
facts and emphasize core capabilities naturally in summary, skills and distinct
supporting examples. Employment remains reverse chronological. Importance
never licenses claim repetition or keyword stuffing.

The deterministic fallback allocates at least one bullet per selected owner,
then distributes remaining slots by weight per next slot. The allocation weight
is `4 * must-have matches + 2 * direct matches + adjacent matches + score / 100`
(with a 0.01 minimum importance term). Each owner remains bounded by its selected
distinct evidence, per-owner limit and total page budget. Normalization applies
the same distribution within the planner's requested caps, ranks supplied facts
before truncating, and rejects foreign ids. Existing portfolios selecting a
whole project by owner id retain that meaning.

Writer, reviser and reviewer depth plans use those same selected facts and
allocated counts. The depth advisory does not demand omitted owners or ask a
one-bullet allocation to restore the rest of a dossier.

## Contract and lifecycle

Assessment input (`FactImportanceSignals`) and computed output
(`FactImportanceScore`) are separate typed models. Both fields are optional on
`FactItem`, keeping older documents valid; their closed enums and bounded scales
are validated at the structured-output/storage boundary. No REST endpoint or
existing identifier changes. Scores do not establish factual claims.

Literal, project and verified synthesis extraction retain assessments. The
existing bullet classification pass backfills missing assessments for copied
dossier evidence and legacy bullets, preserving populated assessments and
aspects. All extraction prompt versions were incremented to invalidate old
fragments. Cached/new facts receive deterministic scoring after the corpus
merge. A later source can fill missing context during entity merging while the
primary assessment remains authoritative.

`load_facts` backfills/recomputes scores in memory without rewriting a profile;
`save_facts` recomputes them on a copy before atomic publication, including
approved edits and skill mutations. Extractor- or file-supplied totals are never
trusted. No additional model request is needed merely to load or save facts.
Conversation tools cannot write assessments or computed scores. Semantic edits
retire stale assessments and use fallback until reclassified. Replacing a bullet's
text also retires its former aspect unless the approved edit supplies a new one;
a renamed skill
also retires its old assessment. Matrix bindings exclude ranking metadata, so
backfilling scores preserves existing skill coverage while changed evidence
still invalidates the binding.
Verbatim education, language and additional-entry gates compare all source
values while ignoring these two ranking fields; omitting metadata cannot cause
a false rejection, and changing actual content still fails the same gate.
Full profile rebuilds obtain the richer source assessments; old profiles remain
usable immediately with conservative fallback scores. Repeated scoring is
deterministic and does not mutate shared cached models.
