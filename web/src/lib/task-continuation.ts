/** Local destinations only; authentication and setup never choose an external redirect. */
const STORAGE_KEY = "resume-tailor-harness-return-to";
const APP_ROUTES = new Set(["", "pipeline", "shortlist", "triage", "profile", "coach", "settings", "sources", "match-gap", "applications", "analytics", "interview", "career-lab", "scout", "account", "admin"]);

function hasUnsafeCharacters(value: string): boolean {
  return [...value].some((character) => character === "\\" || character.charCodeAt(0) < 32 || character.charCodeAt(0) === 127);
}

export function localTaskDestination(value: unknown): string | null {
  if (typeof value !== "string" || value.length > 4096) return null;
  let decoded = value;
  try {
    for (let i = 0; i < 3; i++) {
      if (!decoded.startsWith("/") || decoded.startsWith("//") || hasUnsafeCharacters(decoded)) return null;
      const next = decodeURIComponent(decoded);
      if (next === decoded) break;
      decoded = next;
    }
    if (!decoded.startsWith("/") || decoded.startsWith("//") || hasUnsafeCharacters(decoded)) return null;
    const url = new URL(value, "https://workspace.invalid");
    if (url.origin !== "https://workspace.invalid" || url.pathname.startsWith("//") || !APP_ROUTES.has(url.pathname.split("/")[1])) return null;
    for (const key of [...url.searchParams.keys()]) {
      if (["token", "returnto"].includes(key.toLowerCase())) url.searchParams.delete(key);
    }
    return url.pathname + url.search + url.hash;
  } catch { return null; }
}

export function rememberTaskDestination(value: unknown): void {
  const destination = localTaskDestination(value);
  if (!destination) return;
  try { sessionStorage.setItem(STORAGE_KEY, destination); } catch { /* URL still carries intent. */ }
}

export function taskDestination(params?: URLSearchParams): string {
  const explicit = localTaskDestination(params?.get("returnTo"));
  if (explicit) return explicit;
  try { return localTaskDestination(sessionStorage.getItem(STORAGE_KEY)) ?? "/"; } catch { return "/"; }
}

export function taskDestinationForLocation(pathname: string, search: string, hash = ""): string {
  const params = new URLSearchParams(search);
  return pathname === "/setup" || pathname.startsWith("/setup/")
    ? taskDestination(params)
    : localTaskDestination(pathname + search + hash) ?? taskDestination(params);
}

export function consumeTaskDestination(params?: URLSearchParams): string {
  const destination = taskDestination(params);
  try { sessionStorage.removeItem(STORAGE_KEY); } catch { /* Navigation still works. */ }
  return destination;
}

export function withTaskDestination(path: string, destination: unknown): string {
  const safe = localTaskDestination(destination);
  if (!safe || safe === "/") return path;
  const url = new URL(path, "https://workspace.invalid");
  url.searchParams.set("returnTo", safe);
  return url.pathname + url.search + url.hash;
}
