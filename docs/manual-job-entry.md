# Manual job entry

Use **Add job manually** in the discovery actions or **Triage** when a posting
cannot be imported automatically (for example, it requires an interactive
browser). A person or a browser/computer-use agent can complete the same form.

1. Read the posting and copy the **job title**, **company**, and **full job
   description**. These three fields are required by the form.
2. Fill known optional information: posting and application URLs, requisition ID,
   posted/closing dates, locations, work policy and restrictions, office
   attendance, employment type, seniority, sponsorship wording, industry,
   company size, experience, technology stack, required/preferred skills, and
   salary range. Separate locations with semicolons and skills with newlines.
   Leave information that the posting does not state blank; do not infer it.
3. For salary amounts, specify the original three-letter currency and pay period.
   No currency conversion takes place when saving.
4. Select **Save job** and wait for the confirmation containing the saved ID.
   **View saved job** opens its detail in Triage. **Add another job** clears the
   form for a new posting. Duplicate, quota, validation, and request errors leave
   the entered data available for correction/retry.

Every field has an associated visible label and a stable HTML `name`. All
optional sections are expanded, and selectors are native HTML selects. The form
supports English and Simplified Chinese and narrow screens.

Saving calls the existing authenticated `POST /api/jobs` route and does not
fetch the website or call an LLM. The job enters the normal workflow as `raw`
with source `manual`, using the existing active-job quota and deduplication
rules. Discovery, approval, tailoring, and application tracking remain the
normal next steps. When an application URL is supplied, it becomes the job's
actionable URL; the original posting URL remains in the manual metadata.

The API remains compatible with older `jdText`-only requests. Optional
`postedAt` and `details` extend its camelCase request. Supplied structured values
are immediately available in `criteriaJson`; `manual_details` records their
provenance, including references that are not board facets. Later criteria
extraction retains explicit manual values and can fill unknown fields. Reprocess
and richer-description refreshes also retain those manual facts when resetting
derived criteria. Existing
progressed duplicates retain their criteria and artifacts under the shared
ingestion policy. No database migration is required.

Validation covers the API/service path, extraction preservation, form submission
and error recovery, plus browser entry of every field in both languages at
375px and 1440px. Browser fixture tests mock the API; API tests use isolated
SQLite databases. These checks do not constitute hosted deployment validation.
