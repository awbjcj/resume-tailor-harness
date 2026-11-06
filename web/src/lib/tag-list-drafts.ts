/** Checks an explicit Save action outside a native form. */
export function validateTagDrafts(root: HTMLElement | null): boolean {
  const input = root?.querySelector<HTMLInputElement>("input[data-pending-tag]:enabled");
  if (!input) return true;
  const details = input.closest<HTMLDetailsElement>("details:not([open])");
  if (details) details.open = true;
  input.focus();
  return input.reportValidity();
}
