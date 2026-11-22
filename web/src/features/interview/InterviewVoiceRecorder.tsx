import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { useQuery } from "@tanstack/react-query";
import { Loader2, Mic, RotateCcw, Square, Trash2, X } from "lucide-react";

import { TranscribeButton } from "@/components/TranscribeButton";
import { Button } from "@/components/ui/button";
import { authHeaders } from "@/lib/api/client";

type Phase = "idle" | "starting" | "recording" | "uploading" | "failed";
type Availability = {
  available: boolean;
  enabled: boolean;
  warning: boolean;
  optionalWorkPaused: boolean;
  spentMicros: number | null;
  heldMicros: number | null;
  remainingMicros: number | null;
};

const RECORDING_LIMIT_MS = 120_000;

export function InterviewVoiceRecorder({
  disabled, onText, onBusyChange,
}: {
  disabled: boolean;
  onText: (text: string) => void;
  onBusyChange: (busy: boolean) => void;
}) {
  const { t, i18n } = useTranslation();
  const [phase, setPhase] = useState<Phase>("idle");
  const [elapsed, setElapsed] = useState(0);
  const [notice, setNotice] = useState("");
  const recorderRef = useRef<MediaRecorder | null>(null);
  const requestRef = useRef<AbortController | null>(null);
  const savedRef = useRef<{ blob: Blob; id: string } | null>(null);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const busyRef = useRef(false);
  const onTextRef = useRef(onText);

  useEffect(() => { onTextRef.current = onText; }, [onText]);
  useEffect(() => {
    onBusyChange(["starting", "recording", "uploading"].includes(phase));
  }, [onBusyChange, phase]);
  useEffect(() => () => {
    requestRef.current?.abort();
    if (timerRef.current) clearTimeout(timerRef.current);
    timerRef.current = null;
    const recorder = recorderRef.current;
    if (recorder) {
      recorder.ondataavailable = null;
      recorder.onstop = null;
      if (recorder.state !== "inactive") recorder.stop();
      recorder.stream.getTracks().forEach((track) => track.stop());
    }
  }, []);

  const availability = useQuery({
    queryKey: ["official-interview-transcription"],
    queryFn: async (): Promise<Availability> => {
      const response = await fetch("/api/transcribe/official/availability", {
        credentials: "include", headers: authHeaders(),
      });
      if (!response.ok) throw new Error();
      return response.json() as Promise<Availability>;
    },
    retry: false,
    refetchInterval: 30_000,
  });

  useEffect(() => {
    if (phase !== "recording") return;
    const started = performance.now();
    const interval = setInterval(() => setElapsed(Math.min(120, Math.floor((performance.now() - started) / 1000))), 250);
    return () => clearInterval(interval);
  }, [phase]);

  const upload = async (saved: { blob: Blob; id: string }) => {
    const controller = new AbortController();
    requestRef.current = controller;
    savedRef.current = saved;
    busyRef.current = true;
    setNotice("");
    setPhase("uploading");
    const body = new FormData();
    const extension = saved.blob.type.includes("mp4") ? "mp4" : saved.blob.type.includes("ogg") ? "ogg" : "webm";
    body.append("file", saved.blob, `answer.${extension}`);
    body.append("request_id", saved.id);
    try {
      const response = await fetch("/api/transcribe/official", {
        method: "POST", credentials: "include", headers: authHeaders(), body, signal: controller.signal,
      });
      if (!response.ok) throw new Error();
      const data = await response.json() as { text: string; billingPending: boolean };
      if (controller.signal.aborted) return;
      onTextRef.current(data.text);
      savedRef.current = null;
      setNotice(data.billingPending ? t("interviewVoice.pendingBilling") : t("interviewVoice.review"));
      setPhase("idle");
      void availability.refetch();
    } catch {
      if (!controller.signal.aborted) {
        setNotice(t("interviewVoice.failed"));
        setPhase("failed");
      }
    } finally {
      if (requestRef.current === controller) busyRef.current = false;
    }
  };

  const discard = () => {
    requestRef.current?.abort();
    if (timerRef.current) clearTimeout(timerRef.current);
    timerRef.current = null;
    const recorder = recorderRef.current;
    if (recorder) {
      if (recorder.state !== "inactive") recorder.stop();
      recorder.stream.getTracks().forEach((track) => track.stop());
      recorderRef.current = null;
    }
    savedRef.current = null;
    busyRef.current = false;
    setNotice("");
    setPhase("idle");
  };

  const start = async () => {
    if (busyRef.current || disabled) return;
    busyRef.current = true;
    setNotice("");
    setPhase("starting");
    const controller = new AbortController();
    requestRef.current = controller;
    let stream: MediaStream | null = null;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      if (controller.signal.aborted) {
        stream.getTracks().forEach((track) => track.stop());
        return;
      }
      const recorder = new MediaRecorder(stream);
      const chunks: Blob[] = [];
      recorder.ondataavailable = (event) => { if (event.data.size) chunks.push(event.data); };
      recorder.onstop = () => {
        if (recorderRef.current === recorder) {
          if (timerRef.current) clearTimeout(timerRef.current);
          timerRef.current = null;
          recorderRef.current = null;
        }
        recorder.stream.getTracks().forEach((track) => track.stop());
        if (!controller.signal.aborted) {
          const blob = new Blob(chunks, { type: recorder.mimeType || chunks[0]?.type || "audio/webm" });
          void upload({ blob, id: crypto.randomUUID() });
        }
      };
      recorderRef.current = recorder;
      recorder.start();
      setElapsed(0);
      setPhase("recording");
      timerRef.current = setTimeout(() => {
        if (recorder.state === "recording") recorder.stop();
      }, RECORDING_LIMIT_MS);
    } catch {
      stream?.getTracks().forEach((track) => track.stop());
      recorderRef.current = null;
      busyRef.current = false;
      if (!controller.signal.aborted) {
        setNotice(t("interviewVoice.microphoneError"));
        setPhase("idle");
      }
    }
  };

  if (availability.isPending) return null;
  if (availability.data && !availability.data.enabled) {
    return <TranscribeButton onText={onText} disabled={disabled} />;
  }
  const budget = availability.data;
  const money = (micros: number | null) => new Intl.NumberFormat(i18n.resolvedLanguage, {
    style: "currency", currency: "USD", maximumFractionDigits: 4,
  }).format((micros ?? 0) / 1_000_000);
  const budgetLabel = budget?.spentMicros != null && budget.heldMicros != null && budget.remainingMicros != null
    ? t("interviewVoice.budget", {
      spent: money(budget.spentMicros), held: money(budget.heldMicros), remaining: money(budget.remainingMicros),
    }) : null;
  if (phase === "idle" && (availability.isError || !budget?.available ||
      !navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === "undefined")) {
    return <div className="space-y-1 px-2 pb-1 text-sm text-muted-foreground" role="status">
      <p>{t(budget?.optionalWorkPaused ? "interviewVoice.budgetPaused" : "interviewVoice.unavailable")}</p>
      {budgetLabel ? <p>{budgetLabel}</p> : null}
    </div>;
  }
  return (
    <div className="space-y-2 px-2 pb-1 text-sm">
      <div className="flex flex-wrap items-center gap-2">
        {phase === "idle" ? (
          <Button type="button" variant="outline" size="sm" disabled={disabled} onClick={() => void start()}>
            <Mic aria-hidden="true" />{t("interviewVoice.record")}
          </Button>
        ) : null}
        {phase === "starting" || phase === "uploading" ? (
          <>
            <span className="inline-flex items-center gap-2" role="status">
              <Loader2 className="size-4 animate-spin motion-reduce:animate-none" aria-hidden="true" />
              {t(phase === "starting" ? "interviewVoice.starting" : "interviewVoice.transcribing")}
            </span>
            <Button type="button" variant="ghost" size="sm" onClick={discard}><X aria-hidden="true" />{t("common.cancel")}</Button>
          </>
        ) : null}
        {phase === "recording" ? (
          <>
            <span className="tabular-nums" role="status">{t("interviewVoice.recording", { count: elapsed })}</span>
            <Button type="button" variant="secondary" size="sm" onClick={() => {
              if (recorderRef.current?.state === "recording") recorderRef.current.stop();
            }}><Square aria-hidden="true" />{t("interviewVoice.stop")}</Button>
            <Button type="button" variant="ghost" size="sm" onClick={discard}><Trash2 aria-hidden="true" />{t("interviewVoice.discard")}</Button>
          </>
        ) : null}
        {phase === "failed" ? (
          <>
            <Button type="button" variant="outline" size="sm" onClick={() => { if (savedRef.current && !busyRef.current) void upload(savedRef.current); }}><RotateCcw aria-hidden="true" />{t("common.retry")}</Button>
            <Button type="button" variant="ghost" size="sm" onClick={discard}><Trash2 aria-hidden="true" />{t("interviewVoice.discard")}</Button>
          </>
        ) : null}
      </div>
      {notice ? <p role="status">{notice}</p> : null}
      {budget?.warning ? <p>{t("interviewVoice.warning")}</p> : null}
      {budgetLabel ? <p className="text-muted-foreground">{budgetLabel}</p> : null}
    </div>
  );
}
