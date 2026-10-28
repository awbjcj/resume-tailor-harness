"""Labeled recruiting examples, including plausible hard negatives."""

import pytest

from resume_tailor_harness.gmail.classify import classify_email
from resume_tailor_harness.gmail.client import EmailMessage
from resume_tailor_harness.gmail.match import match_email_to_application
from resume_tailor_harness.tracking.tables import Job


@pytest.mark.parametrize(
    "text,label",
    [
        ("We have decided not to move forward with your application.", "rejection"),
        ("We will not be proceeding with your candidacy.", "rejection"),
        ("You have not been selected for this position.", "rejection"),
        ("We are moving forward with other candidates for this role.", "rejection"),
        ("We are unable to extend an offer for this position.", "rejection"),
        ("We cannot offer you the role.", "rejection"),
        ("We have selected another candidate for the position.", "rejection"),
        ("We are not able to schedule an interview at this time.", "none"),
        ("You do not need to complete the coding assessment.", "none"),
        ("We no longer need your availability.", "none"),
        (
            "Unfortunately our interviewer is ill. Please reschedule your interview.",
            "interview",
        ),
        ("We are reviewing your application alongside other candidates.", "none"),
        ("Unfortunately our careers website is unavailable today.", "none"),
        ("If selected, we will invite you to an interview.", "none"),
        (
            "We received your application. We will contact you if selected for an interview.",
            "none",
        ),
        ("Explore interview tips and sample offer letters in our newsletter.", "none"),
        ("Your offer letter is not ready yet; no offer has been made.", "none"),
        ("Congratulations! We are pleased to offer you the position.", "offer"),
        ("Please complete the coding assessment by Friday.", "assessment"),
        ("We would like to invite you to an interview on Tuesday.", "interview"),
        ("You are invited to interview with our team on Tuesday.", "interview"),
        ("Please share your availability for a phone screen.", "interview"),
        (
            "We are still reviewing your application.\nOn Monday, HR wrote:\nWe are pleased to offer you the role.",
            "none",
        ),
    ],
)
def test_labeled_decisions(text, label):
    assert (
        classify_email(EmailMessage("HR <hr@acme.com>", "acme.com", "Update", text))
        == label
    )


def test_company_word_and_domain_collisions_are_not_matches():
    box = Job(id=1, source="manual", company="Box", title="Engineer")
    trade = Job(id=2, source="manual", company="The Trade Desk", title="Engineer")
    email = EmailMessage(
        "HR <hr@dropbox.com>", "dropbox.com", "The application update", ""
    )
    assert match_email_to_application(email, [box, trade]) is None


def test_requisition_collision_is_scoped_by_company():
    jobs = [
        Job(
            id=i,
            source="manual",
            company=company,
            title="Engineer",
            url=f"https://{company}.com/jobs/R123456",
        )
        for i, company in enumerate(("Acme", "Beta"), 1)
    ]
    email = EmailMessage("HR <hr@beta.com>", "beta.com", "R123456 update", "")
    assert match_email_to_application(email, jobs) == jobs[1]
