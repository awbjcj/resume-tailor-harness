# Services layer developer reference

Migrated from the project root `CLAUDE.md` (2026-08-15, CLAUDE.md split) — loads only when working under `src/resume_tailor_harness/services/`.

- **`ConfigStore.put` writes over a file's keys; it never replaces the file.**
  A Doc deliberately does not declare every key its YAML may hold — rendering
  keeps `template_path`/`output_dir` as runtime-only CLI fields (see
  `render/CLAUDE.md`) and `profile_sources.yaml` keeps the wizard's
  `resume_path` — and the original wholesale rewrite **deleted** each of them
  the first time an unrelated field on that page was saved. So a DTO field
  missing from a Doc means "not editable here", never "safe to destroy". Three
  consequences: the merge is **shallow**, because a key the Doc *does* own must
  be replaced outright or removing a list item would resurrect it;
  `_SUPERSEDED_KEYS` is the one exception, dropping a deprecated spelling whose
  replacement now owns the meaning (`match_plan_enabled`, which `ReviewConfig`
  *rejects* when it disagrees with `evidence_portfolio_enabled`, so preserving
  it would turn a UI toggle into an unloadable config); and adding a field to a
  Doc is now purely a question of whether users should edit it.
  `tests/test_config_store_roundtrip.py` asserts the property against the
  shipped `.example` files rather than comparing Doc fields to domain fields,
  because those two legitimately diverge and the failure mode that matters is
  data loss.
- **`ReviewConfigDoc.length_budget` is not nullable, because
  `ReviewConfig.length_budget` is not.** The settings page used to offer an
  "Enforce a length budget" switch whose off position wrote `length_budget:
null`; the domain model rejects that outright, so turning the budget off
  broke every subsequent tailor run at config load. The switch is gone and the
  budget is always present. A `before` validator still coerces `None` to
  defaults on read, because files written by the old switch exist and a
  settings page that 500s cannot be used to repair itself.
- **The customizable settings surface is declared once.** `settings_sections.py`
  holds `SETTINGS_SECTIONS`: rows naming each transferable, resettable
  unit and the canonical relative paths it owns (`config/connectors.yaml`,
  `data/profile/overrides.yaml`). It is an **allowlist** — it spans the
  workspace root alongside `secrets.env`, `gmail_token.json`,
  `resume_tailor_harness.db`, and `config/gmail_credentials.json`, so a file not named
  there can neither leave a workspace in a settings bundle nor enter one from
  an imported bundle. `services/settings_bundle.py` exports and imports that
  set as a tar.gz (`GET/POST /api/settings/bundle`), replacing the sections a
  bundle names and leaving the rest untouched — a bundle can add or replace
  settings but never clear them. Reset (`POST
/api/settings/sections/{id}/reset`) copies the shipped `.example` when one
  exists and deletes the file otherwise, which is the same rule
  `provision_workspace` uses to seed a fresh workspace. Import validation uses
  the artifacts' **models** but not their read-time loaders:
  `load_group_corrections` and `load_taxonomy_corrections` return an empty
  ledger on corruption, which is right for reading and catastrophic for
  importing.

- **Application handoffs are deterministic.** `application_prompt.py` combines
  the tenant's saved resume facts, job, and optional `application_profile` config.
  Blank application answers mean unknown; inferred skills, employer requirements,
  and salary search filters never become applicant answers. Saved Search settings
  supply a positive sponsorship requirement and selected work-policy preferences
  when application-specific answers are blank. The legacy False sponsorship default
  remains unknown, not an explicit No. Read both settings from the active tenant's
  ConfigStore on each request; never cache or copy them into the application profile.
  Explicit application answers take precedence. Contact overrides are
  explicit. Prompts remain English regardless of UI language, contain no source
  paths, and do not attach files. Render a ready-to-use Markdown prompt with
  populated applicant fields and readable education/work history, never a JSON
  dump. Omit blank free-text answers, empty sections, provenance/GitHub metadata, and
  redundant employer requirements or job-description text. Application profile
  settings are included in settings bundles, validated on import, and reset
  through the section registry.
  Common screening answers keep U.S. worker category, legal-right verification,
  authorization, and sponsorship separate. Employer history, referral sources,
  and friends/relatives answers must name the employer; citizenship country lists
  and government-employment lookback periods must match the live question.
  Saved answers never authorize terms, attestations, or final submission.
  Professional screening answers are explicit text or dated specialty ranges,
  not values derived from resume dates. Keep experience totals dated, office attendance location-specific,
  and employer screening answers scoped to their role and confirmation date.
  Rolling application counts and calendar start dates need fresh confirmation
  when their scope changes; a relative notice period cannot supply a calendar date.
  Structured records in `api/schemas/application_profile.py` preserve countries,
  employer/requisition scope, confirmation dates, and nullable booleans. Unknown
  is distinct from an explicit No; keep unknown markers inside these records.
  Never parse legacy notes into structured facts automatically. Name/address
  PATCHes merge supplied parts; lists replace in full. Filter employer records
  and scoped email aliases by exact normalized company name in readable prompts,
  and require live verification of remaining country/requisition/timeframe limits.
  Keep sex separate from gender, alternate email permission explicit, and optional
  AI matching preferences separate from agreement/submission consent. Degree
  category mappings never alter the actual awarded degree in resume evidence.
  External harnesses use `agent_applications.py` for the full JD/context and
  scoped question ledger. The concise copy prompt also includes matching saved
  questions. `YamlConfigStore.update` serializes read/modify/write with a file
  lock shared by ordinary PUT; profile revision checks happen inside that lock.
  Application questions live in the workspace database, separate from the
  settings bundle. They do not become resume evidence.

- **Employer passwords belong only to the encrypted account vault.**
  `application_accounts.py` owns authenticated, owner-bound Fernet storage,
  atomic writes, exact employer/origin matching, and pending/active/attention
  transitions. The deployment-only `APPLICATION_VAULT_KEYS` never comes from
  workspace secrets. Contexts, questions, profile answers and CLI metadata must
  never carry passwords. Browser filling runs in the external host, not the
  read-only discovery scraper. See `docs/application-password-manager.md`.
