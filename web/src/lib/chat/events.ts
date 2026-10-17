/** Hand-written SSE contract; Python parity is enforced by a backend test. */
export const STREAM_EVENT_TAGS = [
  "text",
  "reasoning",
  "sources",
  "tool_started",
  "tool_completed",
  "notice",
  "settled",
  "completed",
  "failed",
] as const;

export type StreamEventTag = (typeof STREAM_EVENT_TAGS)[number];
export type ChatSource = { url: string; title: string };

export type StreamEvent =
  | { i: number; t: "text"; v: { text: string } }
  | { i: number; t: "reasoning"; v: { text: string } }
  | { i: number; t: "sources"; v: { items: ChatSource[] } }
  | {
      i: number;
      t: "tool_started";
      v: { callId: string; name: string; argsPreview: string };
    }
  | {
      i: number;
      t: "tool_completed";
      v: {
        callId: string;
        name: string;
        resultPreview: string;
        ok: boolean;
      };
    }
  | { i: number; t: "notice"; v: { message: string } }
  | { i: number; t: "settled"; v: Record<string, never> }
  | { i: number; t: "completed"; v: Record<string, never> }
  | { i: number; t: "failed"; v: { message: string; code: string } };

export type ChatPart =
  | { kind: "text"; text: string }
  | {
      kind: "audio";
      url: string;
      transcript: string;
      autoPlay: boolean;
    }
  | { kind: "hints"; hints: string[] }
  | { kind: "reasoning"; text: string }
  | { kind: "sources"; items: ChatSource[] }
  | {
      kind: "tool";
      callId: string;
      name: string;
      argsPreview: string;
      resultPreview: string;
      ok: boolean;
      done: boolean;
    }
  | { kind: "notice"; message: string };

function record(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function strings(value: Record<string, unknown>, ...keys: string[]): boolean {
  return keys.every((key) => typeof value[key] === "string");
}

/** Validate untrusted EventSource JSON before it can move the resume cursor. */
export function parseStreamEvent(value: unknown): StreamEvent | null {
  if (!record(value) || !Number.isInteger(value.i) || (value.i as number) < 0) return null;
  if (!record(value.v) || typeof value.t !== "string") return null;
  const v = value.v;
  switch (value.t) {
    case "text":
    case "reasoning":
      break;
    case "sources":
      if (Array.isArray(v.items) && v.items.every((item) => {
        if (!record(item) || !strings(item, "url", "title")) return false;
        try {
          const url = new URL(item.url as string);
          return ["https:", "http:"].includes(url.protocol) && !url.username && !url.password;
        } catch { return false; }
      })) return value as StreamEvent;
      return null;
    case "tool_started":
      if (strings(v, "callId", "name", "argsPreview")) return value as StreamEvent;
      return null;
    case "tool_completed":
      if (strings(v, "callId", "name", "resultPreview") && typeof v.ok === "boolean") {
        return value as StreamEvent;
      }
      return null;
    case "notice":
      if (typeof v.message === "string") return value as StreamEvent;
      return null;
    case "settled":
    case "completed":
      return value as StreamEvent;
    case "failed":
      if (strings(v, "message", "code")) return value as StreamEvent;
      return null;
    default:
      return null;
  }
  return typeof v.text === "string" ? (value as StreamEvent) : null;
}

export function reduceEvent(parts: ChatPart[], event: StreamEvent): ChatPart[] {
  const last = parts.at(-1);
  if (event.t === "failed" || event.t === "completed") {
    return parts.map((part) => part.kind === "tool" && !part.done
      ? { ...part, done: true, ok: false, resultPreview: event.t === "failed" ? event.v.message : "No result was returned." }
      : part);
  }
  if (event.t === "sources") {
    const existing = parts.findIndex((part) => part.kind === "sources");
    const current = existing >= 0 ? parts[existing] : null;
    const items = current?.kind === "sources" ? current.items : [];
    const merged = [...new Map([...items, ...event.v.items].map((item) => [item.url, item])).values()];
    if (current?.kind === "sources" && JSON.stringify(items) === JSON.stringify(merged)) return parts;
    const sources: ChatPart = { kind: "sources", items: merged };
    return existing < 0 ? [...parts, sources] : parts.map((part, index) => index === existing ? sources : part);
  }
  if (event.t === "text" || event.t === "reasoning") {
    const kind = event.t;
    if (last?.kind === kind) {
      return [...parts.slice(0, -1), { kind, text: last.text + event.v.text }];
    }
    return [...parts, { kind, text: event.v.text }];
  }
  if (event.t === "tool_started") {
    const existing = parts.findIndex((part) => part.kind === "tool" && part.callId === event.v.callId);
    if (existing >= 0) {
      const tool = parts[existing];
      if (tool.kind !== "tool" || tool.done || tool.argsPreview === event.v.argsPreview) return parts;
      return parts.map((part, index) => index === existing ? { ...tool, argsPreview: event.v.argsPreview } : part);
    }
    return [
      ...parts,
      {
        kind: "tool",
        callId: event.v.callId,
        name: event.v.name,
        argsPreview: event.v.argsPreview,
        resultPreview: "",
        ok: true,
        done: false,
      },
    ];
  }
  if (event.t === "tool_completed") {
    const index = parts.findIndex(
      (part) => part.kind === "tool" && part.callId === event.v.callId && !part.done,
    );
    if (index < 0) {
      if (parts.some((part) => part.kind === "tool" && part.callId === event.v.callId)) return parts;
      return [...parts, { kind: "tool", ...event.v, argsPreview: "", done: true }];
    }
    const next = [...parts];
    const tool = parts[index];
    if (tool.kind !== "tool") return parts;
    next[index] = {
      ...tool,
      name: event.v.name,
      resultPreview: event.v.resultPreview,
      ok: event.v.ok,
      done: true,
    };
    return next;
  }
  if (event.t === "notice") {
    return [...parts, { kind: "notice", message: event.v.message }];
  }
  return parts;
}
