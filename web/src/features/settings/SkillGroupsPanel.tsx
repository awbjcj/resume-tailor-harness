import { SkillLibrary } from "@/features/profile-skills/SkillLibrary";

/** Shared entry point for the Profile workspace and legacy settings links. */
export function SkillGroupsPanel({ disabled = false }: { disabled?: boolean }) {
  return <SkillLibrary disabled={disabled} />;
}
