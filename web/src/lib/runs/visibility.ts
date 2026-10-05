// Mirrored by services/run_visibility.py; the Python contract test checks parity.
export const CHAT_RUN_KINDS = new Set([
  "career-lab-turn",
  "career-lab-end",
  "profile-coach-open",
  "profile-coach-turn",
  "profile-coach-end",
  "mock-interview-open",
  "mock-interview-turn",
  "mock-interview-end",
  "scout-start",
  "scout-turn",
  "scout-end",
]);

export function visibleRunCompletion(run: { kind: string; status: string }): boolean {
  return !CHAT_RUN_KINDS.has(run.kind) || run.status === "failed";
}
