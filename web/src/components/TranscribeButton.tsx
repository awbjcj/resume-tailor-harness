import { useEffect, useRef, useState } from "react";
import { Loader2, Mic, RotateCcw, Square } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { api, authHeaders, unwrap } from "@/lib/api/client";

type Phase = "idle" | "starting" | "recording" | "uploading" | "failed";

async function upload(blob: Blob, signal: AbortSignal): Promise<string> {
  const body = new FormData();
  const extension = blob.type.includes("mp4") ? "mp4" : blob.type.includes("ogg") ? "ogg" : "webm";
  body.append("file", blob, `clip.${extension}`);
  const response = await fetch("/api/transcribe", {
    method: "POST", body, credentials: "include", headers: authHeaders(), signal,
  });
  if (!response.ok) throw new Error("Transcription failed");
  const data = (await response.json()) as { text: string };
  return data.text;
}

export function TranscribeButton({
  onText,
  disabled,
}: {
  onText: (text: string) => void;
  disabled?: boolean;
}) {
  const { t } = useTranslation();
  const [phase, setPhase] = useState<Phase>("idle");
  const [elapsed, setElapsed] = useState(0);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const blobRef = useRef<Blob | null>(null);
  const requestRef = useRef<AbortController | null>(null);
  const busyRef = useRef(false);

  useEffect(() => () => {
    requestRef.current?.abort();
    const recorder = recorderRef.current;
    if (recorder) {
      recorder.ondataavailable = null;
      recorder.onstop = null;
      if (recorder.state !== "inactive") recorder.stop();
      recorder.stream.getTracks().forEach((track) => track.stop());
      recorderRef.current = null;
    }
  }, []);

  const availability = useQuery({
    queryKey: ["transcribe-availability"],
    queryFn: () =>
      unwrap(api.GET("/api/transcribe/availability", {} as never)) as Promise<{
        available: boolean;
      }>,
    staleTime: Infinity,
  });

  useEffect(() => {
    if (phase !== "recording") return;
    const timer = setInterval(() => setElapsed((s) => s + 1), 1000);
    return () => clearInterval(timer);
  }, [phase]);

  if (!availability.data?.available || !navigator.mediaDevices?.getUserMedia ||
      typeof MediaRecorder === "undefined") return null;

  const send = async (blob: Blob) => {
    const controller = new AbortController();
    requestRef.current = controller;
    busyRef.current = true;
    blobRef.current = blob;
    setPhase("uploading");
    try {
      const text = await upload(blob, controller.signal);
      if (controller.signal.aborted) return;
      onText(text);
      blobRef.current = null;
      setPhase("idle");
    } catch {
      if (controller.signal.aborted) return;
      toast.error("Transcription failed. Tap Retry.");
      setPhase("failed");
    } finally {
      if (requestRef.current === controller) busyRef.current = false;
    }
  };

  const start = async () => {
    if (busyRef.current || disabled) return;
    busyRef.current = true;
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
      recorder.ondataavailable = (event) => chunks.push(event.data);
      recorder.onstop = () => {
        recorder.stream.getTracks().forEach((track) => track.stop());
        recorderRef.current = null;
        if (!controller.signal.aborted) {
          void send(new Blob(chunks, { type: recorder.mimeType || chunks[0]?.type || "audio/webm" }));
        }
      };
      recorderRef.current = recorder;
      recorder.start();
      setElapsed(0);
      setPhase("recording");
    } catch {
      stream?.getTracks().forEach((track) => track.stop());
      recorderRef.current = null;
      busyRef.current = false;
      if (controller.signal.aborted) return;
      setPhase("idle");
      toast.error("Microphone access was denied");
    }
  };

  if (phase === "recording") {
    return (
      <Button
        type="button"
        variant="destructive"
        size="sm"
        onClick={() => {
          const recorder = recorderRef.current;
          if (recorder?.state === "recording") recorder.stop();
        }}
        aria-label="Stop recording"
      >
        <Square className="h-4 w-4 animate-pulse" />
        <span className="ml-1 tabular-nums">{t("common.elapsedSeconds", { count: elapsed })}</span>
      </Button>
    );
  }
  // The icon-only phases use `icon-sm` so this button is the same 36px square as
  // the composer's send/stop control it sits beside; `recording` keeps the wider
  // `sm` size because it also renders the elapsed-seconds readout.
  if (phase === "uploading") {
    return (
      <Button type="button" variant="ghost" size="icon-sm" disabled aria-label="Transcribing">
        <Loader2 className="h-4 w-4 animate-spin" />
      </Button>
    );
  }
  if (phase === "failed") {
    return (
      <Button
        type="button"
        variant="outline"
        size="icon-sm"
        disabled={disabled}
        onClick={() => {
          if (blobRef.current && !busyRef.current) void send(blobRef.current);
        }}
        aria-label="Retry transcription"
      >
        <RotateCcw className="h-4 w-4" />
      </Button>
    );
  }
  return (
    <Button
      type="button"
      variant="ghost"
      size="icon-sm"
      disabled={disabled || phase === "starting"}
      onClick={() => void start()}
      aria-label="Record a voice answer"
    >
      {phase === "starting" ? <Loader2 className="h-4 w-4 animate-spin" /> : <Mic className="h-4 w-4" />}
    </Button>
  );
}
