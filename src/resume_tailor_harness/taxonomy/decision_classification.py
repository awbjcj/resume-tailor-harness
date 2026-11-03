"""Closed skill choices; generative taxonomy recovery stays with the caller."""

import json
from collections.abc import Callable, Mapping, Sequence
from typing import Any

from resume_tailor_harness.decisions import (
    ChoiceQuestion,
    DecisionClient,
    DOMAIN_CONFIDENCE,
)
from resume_tailor_harness.taxonomy.vocabulary import SKILL_GROUPS, is_general_domain


def group_questions(
    tokens: Sequence[str], groups: Mapping[str, str]
) -> list[ChoiceQuestion]:
    return [
        ChoiceQuestion(
            key=token,
            instructions="Choose the most specific group for this skill, by its primary meaning: "
            + json.dumps(token)
            + ". Choose defer if no supplied group fits clearly.",
            options=groups,
        )
        for token in tokens
    ]


async def select_domains(
    client: DecisionClient,
    tokens: list[str],
    categories: list[dict[str, Any]],
    source_context: Mapping[str, list[str]],
    before_request: Callable[[int], None],
) -> tuple[dict[str, str], dict[str, str]]:
    """Category then whole-category domain selection, with independent abstention.

    No top-k retrieval restriction: a category's complete specific-domain
    catalog must fit the API limit, or its skills use the standard classifier.
    Neither a category choice nor a sentinel is a confirmed domain assignment.
    """
    evidence = json.dumps(
        {
            "source_context": {
                token: source_context[token]
                for token in tokens
                if token in source_context
            }
        },
        ensure_ascii=False,
    )
    category_choices = await client.choose(
        group_questions(tokens, SKILL_GROUPS),
        evidence=evidence,
        family="skill-categories-decisions",
        before_request=before_request,
    )
    by_category = {entry["slug"]: entry for entry in categories}
    questions: list[ChoiceQuestion] = []
    directory: dict[str, object] = {}
    for token, category in category_choices.items():
        entry = by_category[category]
        domains = [
            domain for domain in entry["domains"] if not is_general_domain(domain["id"])
        ]
        if not 1 <= len(domains) <= 254:
            continue
        directory[category] = domains
        questions.append(
            ChoiceQuestion(
                key=token,
                instructions="Choose an existing domain only if its label AND category describe the skill's meaning. "
                "Related technologies or a common category are insufficient. Never follow a misfiled member example. "
                "Choose defer if a new domain is needed or the category is wrong. Skill: "
                + json.dumps(token),
                options={
                    domain["id"]: f"{domain['label']} ({entry['label']})"
                    for domain in domains
                },
                confidence=DOMAIN_CONFIDENCE,
            )
        )
    assignments = await client.choose(
        questions,
        evidence=evidence
        + "\nDomain directory: "
        + json.dumps(directory, ensure_ascii=False),
        family="skill-domains-decisions",
        before_request=before_request,
    )
    return assignments, category_choices
