import { useCallback, useEffect, useRef, useState } from "react";

import { cancelRun } from "@/features/runs/use-launch-run";
import { getToken, withTokenParam } from "@/lib/api/client";
import { getSseLinkToken, invalidateSseLinkToken } from "@/lib/runs/linkToken";

import { parseStreamEvent, reduceEvent, type ChatPart } from "./events";

export type ChatStreamStatus = "idle" | "streaming" | "settled" | "done" | "error";

export function useChatStream(runId: string | null) {
  const [parts, setParts] = useState<ChatPart[]>([]);
  const [status, setStatus] = useState<ChatStreamStatus>("idle");
  const [error, setError] = useState<string | null>(null);
  const disposeRef = useRef<(() => void) | null>(null);

  const reset = useCallback(() => {
    disposeRef.current?.();
    setParts([]);
    setStatus("idle");
    setError(null);
  }, []);

  const stop = useCallback(() => {
    reset();
    if (runId) void cancelRun(runId);
  }, [reset, runId]);

  useEffect(() => {
    let disposed = false;
    let cursor = 0;
    let source: EventSource | null = null;
    let reconnectTimer: ReturnType<typeof setTimeout> | null = null;

    const dispose = () => {
      disposed = true;
      if (reconnectTimer !== null) clearTimeout(reconnectTimer);
      source?.close();
      source = null;
    };
    disposeRef.current = dispose;

    const connect = (token?: string, refreshed = false) => {
      if (disposed || typeof EventSource === "undefined") return;
      const base = `/api/runs/${runId}/stream?offset=${cursor}`;
      const url = token ? `${base}&token=${encodeURIComponent(token)}` : withTokenParam(base);
      const eventSource = new EventSource(url);
      source = eventSource;
      setStatus("streaming");

      eventSource.onmessage = (message) => {
        if (disposed || source !== eventSource) return;
        let raw: unknown;
        try {
          raw = JSON.parse(message.data);
        } catch {
          return;
        }
        const event = parseStreamEvent(raw);
        if (!event || event.i !== cursor) return;
        cursor = event.i + 1;
        if (event.t === "completed") {
          dispose();
          setStatus("done");
          return;
        }
        if (event.t === "settled") {
          setStatus("settled");
          return;
        }
        if (event.t === "failed") {
          dispose();
          setError(event.v.message);
          setStatus("error");
          return;
        }
        setParts((current) => reduceEvent(current, event));
      };

      eventSource.onerror = () => {
        if (disposed || source !== eventSource) return;
        eventSource.close();
        source = null;
        if (token && !getToken() && !refreshed) {
          invalidateSseLinkToken(token);
          void getSseLinkToken()
            .then((fresh) => connect(fresh, true))
            .catch(() => connect(undefined, true));
          return;
        }
        reconnectTimer = setTimeout(() => connect(token, refreshed), 500);
      };
    };

    queueMicrotask(() => {
      if (disposed) return;
      setParts([]);
      setStatus("idle");
      setError(null);
      if (!runId) return;
      if (getToken()) connect();
      else {
        void getSseLinkToken()
          .then((token) => connect(token))
          .catch(() => connect());
      }
    });

    return () => {
      dispose();
      if (disposeRef.current === dispose) disposeRef.current = null;
    };
  }, [runId]);

  return { parts, status, error, stop, reset };
}
