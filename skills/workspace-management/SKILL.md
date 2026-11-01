---
name: workspace-management
description: Maintain saved jobs, application history, notes, preparation and profile records through exact human-reviewed proposals.
---

# Job-search workspace management

Use this method when the user wants to maintain their job list, notes, application
status/history, saved application answers, personal profile or preparations.

1. Read the relevant saved records. Resolve exact job IDs with find_saved_jobs,
   then read_job_workspace. Page all relevant results; an incomplete page is not
   the whole list. Ask one clarification if multiple records still match.
2. Read existing notes, events, preparations and relevant conversation excerpts.
   Distinguish employer application status from resume-processing stage and mock
   interview practice from real employer events. Never invent a submission.
3. Research public employer sources when they will improve the work. Preserve
   URLs, retrieval dates, claim scope and uncertainty. Research and older chat
   cannot establish personal achievements or approve a change.
4. Read workspace_change_schema for the operation. Make the smallest change
   satisfying the user's request, preserving unrelated fields. For profile.change
   inspect exact profile IDs and use quotes from the current user message.
5. Use preview_workspace_changes. Correct validation failures before presenting
   the result. Explain before/after effects, sources, deletion consequences and
   uncertainties. A preview does not save any requested change.
6. Tell the user to review the change card. Every edit requires human approval;
   a chat yes, model assertion, search result or previous approval cannot apply it.
7. Read change receipts before claiming completion. Conflicts need a fresh
   proposal. An unknown outcome needs reconciliation, never a blind retry.

Useful examples: research an employer and propose a cited preparation note;
record a user-reported recruiter call with an explicit timezone; append a note
without replacing the prior notes; archive a job with investment instead of
deleting it. Do not send email, submit applications, use credentials, or perform
unattended upkeep. Stop at tool/time limits with honest partial results.
