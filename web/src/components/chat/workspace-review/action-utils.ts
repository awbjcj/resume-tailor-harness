import type { components } from "@/lib/api/schema";

type Action = components["schemas"]["ActionOut"];

function removedProfileItems(action: Action): unknown[] {
  if (action.change.operation !== "profile.change" || !Array.isArray(action.before) || !Array.isArray(action.after)) return [];
  const after = action.after;
  return action.before.filter((item, index) => item != null && index < after.length && after[index] == null);
}

export function isRemovalAction(action: Action) {
  return action.change.operation.endsWith(".delete") || removedProfileItems(action).length > 0;
}

export function actionTargetNames(action: Action): string[] {
  const items = action.change.operation === "profile.change" ? removedProfileItems(action) : [action.before];
  return items.flatMap((item) => {
    if (!item || typeof item !== "object" || Array.isArray(item)) return [];
    const record = item as Record<string, unknown>;
    const name = record.title ?? record.name ?? record.question;
    return typeof name === "string" && name.trim() ? [name] : [];
  });
}
