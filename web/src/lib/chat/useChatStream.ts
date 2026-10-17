import { useCallback, useEffect, useRef, useState } from "react";

import { cancelRun } from "@/features/runs/use-launch-run";
import { getToken, withTokenParam } from "@/lib/api/client";
import { getSseLinkToken, invalidateSseLinkToken } from "@/lib/runs/linkToken";

import { parseStreamEvent, reduceEvent, type ChatPart } from "./events";
import { parseAguiEvent } from "./agui";

export type ChatStreamStatus = "idle" | "streaming" | "settled" | "stopping" | "stopped" | "done" | "error";

export function useChatStream(runId: string | null) {
  const [parts, setParts] = useState<ChatPart[]>([]);
  const [status, setStatus] = useState<ChatStreamStatus>("idle");
  const [error, setError] = useState<string | null>(null);
  const [reconnecting, setReconnecting] = useState(false);
  const disposeRef = useRef<(() => void) | null>(null);
  const stoppingRef = useRef(false);
  const terminalRef = useRef(false);
  const settledRef = useRef(false);

  const reset = useCallback(() => {
    disposeRef.current?.();
    setParts([]);
    setStatus("idle");
    setError(null);
    setReconnecting(false);
    stoppingRef.current = false;
    terminalRef.current = true;
  }, []);

  const stop = useCallback(async () => {
    if (!runId || stoppingRef.current || terminalRef.current) return;
    const owner = disposeRef.current;
    const previous = status;
    stoppingRef.current = true;
    setStatus("stopping");
    // Keep the stream and partial reply until the server confirms cancellation.
    const accepted = await cancelRun(runId);
    if (disposeRef.current !== owner || terminalRef.current) return;
    if (!accepted) {
      stoppingRef.current = false;
      setStatus(settledRef.current ? "settled" : previous);
      setError("Could not stop the response. Please try again.");
    }
  }, [runId, status]);

  useEffect(() => {
    let disposed = false;
    let cursor = 0;
    let settled = false;
    let reconnectAttempts = 0;
    let source: EventSource | null = null;
    let reconnectTimer: ReturnType<typeof setTimeout> | null = null;

    const dispose = () => {
      disposed = true;
      if (reconnectTimer !== null) clearTimeout(reconnectTimer);
      source?.close();
      source = null;
    };
    disposeRef.current = dispose;
    stoppingRef.current = false;
    terminalRef.current = false;
    settledRef.current = false;

    const connect = (token?: string, refreshed = false) => {
      if (disposed || typeof EventSource === "undefined") return;
      const base = `/api/runs/${runId}/stream?offset=${cursor}&protocol=ag-ui`;
      const url = token ? `${base}&token=${encodeURIComponent(token)}` : withTokenParam(base);
      const eventSource = new EventSource(url);
      source = eventSource;
      setStatus(stoppingRef.current ? "stopping" : settled ? "settled" : "streaming");

      const reconnect = () => {
        if (disposed || source !== eventSource) return;
        eventSource.close();
        source = null;
        setReconnecting(true);
        if (token && !getToken() && !refreshed) {
          invalidateSseLinkToken(token);
          void getSseLinkToken()
            .then((fresh) => connect(fresh, true))
            .catch(() => connect(undefined, true));
          return;
        }
        const delay = Math.min(500 * 2 ** reconnectAttempts++, 8000);
        reconnectTimer = setTimeout(() => connect(token, refreshed), delay);
      };

      eventSource.onmessage = (message) => {
        if (disposed || source !== eventSource) return;
        let raw: unknown;
        try {
          raw = JSON.parse(message.data);
        } catch {
          return;
        }
        const event = parseAguiEvent(raw) ?? parseStreamEvent(raw);
        if (!event || event.i < cursor) return;
        if (event.i > cursor) {
          reconnect();
          return;
        }
        cursor = event.i + 1;
        reconnectAttempts = 0;
        setReconnecting(false);
        if (event.t === "completed") {
          terminalRef.current = true;
          dispose();
          setParts((current) => reduceEvent(current, event));
          setError(null);
          setStatus("done");
          return;
        }
        if (event.t === "settled") {
          settled = true;
          settledRef.current = true;
          if (!stoppingRef.current) setStatus("settled");
          return;
        }
        if (event.t === "failed") {
          const cancelled = event.v.code === "CANCELLED";
          terminalRef.current = true;
          dispose();
          setParts((current) => reduceEvent(current, event));
          setError(cancelled ? null : event.v.message);
          setStatus(cancelled ? "stopped" : "error");
          return;
        }
        setParts((current) => reduceEvent(current, event));
      };

      eventSource.onerror = reconnect;

    };

    queueMicrotask(() => {
      if (disposed) return;
      setParts([]);
      setStatus("idle");
      setError(null);
      setReconnecting(false);
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

  return { parts, status, error, reconnecting, stop, reset };
}
