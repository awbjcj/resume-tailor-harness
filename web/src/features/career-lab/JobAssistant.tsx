import { useRef, useState } from "react";
import { MessageCircle, Sparkles } from "lucide-react";
import { Link } from "react-router-dom";

import { ChatComposer } from "@/components/chat/ChatComposer";
import { ChatRunProgress } from "@/components/chat/ChatRunProgress";
import { ChatThread, type ChatThreadMessage } from "@/components/chat/ChatThread";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { useChatStream } from "@/lib/chat/useChatStream";
import { useRunStore, type RunRecord } from "@/lib/runs/store";
import type { components } from "@/lib/api/schema";
import { CareerLabResumeVersionPicker } from "./CareerLabContextRail";
import { useCareerLabSession, useCareerLabSessions, useSendCareerLabMessage, useStartCareerLab } from "./use-career-lab";

type Props = { jobId: number; jobLabel: string; versions: components["schemas"]["ResumeVersionOut"][] };
const icon = <Sparkles className="size-4" aria-hidden="true" />;

export function JobAssistant(props: Props) {
  const [open, setOpen] = useState(false);
  return <>
    <Button size="sm" variant="outline" className="rounded-full" onClick={() => setOpen(true)}><MessageCircle className="size-4" aria-hidden="true" />Ask about this job</Button>
    <Sheet open={open} onOpenChange={setOpen}>
      <SheetContent className="gap-0 data-[side=right]:w-full data-[side=right]:sm:max-w-xl">
        <SheetHeader className="border-b pr-12"><SheetTitle>Career assistant</SheetTitle><SheetDescription>{props.jobLabel}</SheetDescription></SheetHeader>
        {open ? <JobAssistantConversation key={props.jobId} {...props} /> : null}
      </SheetContent>
    </Sheet>
  </>;
}

export function JobAssistantConversation({ jobId, jobLabel, versions }: Props) {
  const sessions = useCareerLabSessions({ jobId });
  const activeSummary = (sessions.data?.activeSessions ?? sessions.data?.sessions ?? []).find((row) => row.status === "active" && row.jobId === jobId);
  const [openedId, setOpenedId] = useState<string | null>(null);
  const sessionId = openedId ?? activeSummary?.sessionId ?? null;
  const session = useCareerLabSession(sessionId);
  const start = useStartCareerLab();
  const send = useSendCareerLabMessage();
  const [message, setMessage] = useState("");
  const [resumeVersionId, setResumeVersionId] = useState<number>();
  const [includeProfile, setIncludeProfile] = useState(false);
  const [localRunId, setLocalRunId] = useState<string | null>(null);
  const [stoppedId, setStoppedId] = useState<string | null>(null);
  const [pending, setPending] = useState<{ text: string; baseline: number } | null>(null);
  const [error, setError] = useState("");
  const finished = useRef(new Set<string>());
  const ignored = useRef(new Set<string>());
  const recovered = useRunStore((state) => Object.values(state.runs).find((run) =>
    run.kind.startsWith("career-lab") && ["queued", "running", "cancelling"].includes(run.status) &&
    (run.meta?.jobId === jobId || (sessionId && run.meta?.sessionId === sessionId)),
  ));
  const runId = localRunId ?? (recovered?.runId !== stoppedId ? recovered?.runId ?? null : null);
  const stream = useChatStream(runId);
  const busy = Boolean(runId) || start.isPending || send.isPending;
  const turns = session.data?.turns ?? [];
  const baseline = pending?.baseline ?? (typeof recovered?.meta?.turnCount === "number" ? recovered.meta.turnCount : turns.length);
  const advanced = turns.length > baseline;
  const messages: ChatThreadMessage[] = turns.map((turn) => ({ id: turn.turnId, role: turn.role, parts: [{ kind: "text", text: turn.text }] }));
  if (pending && !advanced) messages.push({ id: "pending", role: "user", parts: [{ kind: "text", text: pending.text }] });

  const onDone = (run: RunRecord, submitted: string) => {
    finished.current.add(run.runId);
    if (ignored.current.delete(run.runId)) return;
    setLocalRunId((current) => current === run.runId ? null : current);
    setPending(null);
    if (run.status !== "succeeded") { setError(run.error ?? "The response could not be completed. Your request is ready to retry."); return; }
    const result = run.result as { sessionId?: string } | null;
    if (result?.sessionId) setOpenedId(result.sessionId);
    setMessage((current) => current.trim() === submitted ? "" : current);
  };
  const submit = async () => {
    if (!message.trim() || busy || sessions.isPending || sessions.isError || session.isError || (sessionId && session.isPending)) return;
    const text = message.trim();
    setError(""); setStoppedId(null); stream.reset();
    setPending({ text, baseline: turns.length });
    const context = { jobId, resumeVersionId, profileSnapshot: includeProfile ? "current" as const : undefined, offerApplicationIds: [] };
    try {
      const run = sessionId
        ? await send.mutateAsync({ sessionId, message: text, context, onDone: (run) => onDone(run, text) })
        : await start.mutateAsync({ message: text, goal: `Discuss ${jobLabel}`, context, onDone: (run) => onDone(run, text) });
      if (!finished.current.delete(run.runId)) setLocalRunId(run.runId);
    } catch (caught) { setPending(null); setError(caught instanceof Error ? caught.message : "Unable to start the response."); }
  };
  const stop = () => {
    if (runId) { ignored.current.add(runId); setStoppedId(runId); }
    stream.stop(); setLocalRunId(null); setPending(null);
  };
  return <div className="flex min-h-0 flex-1 flex-col gap-4 p-4">
    <details className="rounded-xl border bg-muted/20 p-3">
      <summary className="cursor-pointer text-sm font-medium"><span>Context: this job</span>{resumeVersionId ? <>{" · "}<span>Selected resume</span></> : null}{includeProfile ? <>{" · "}<span>Current profile</span></> : null}</summary>
      <div className="mt-3 space-y-3">
        <CareerLabResumeVersionPicker id={`job-assistant-resume-${jobId}`} versions={versions} value={resumeVersionId} onChange={setResumeVersionId} emptyLabel="No resume selected" disabled={busy} />
        <label className="flex items-center gap-2 text-sm"><Checkbox checked={includeProfile} disabled={busy} onCheckedChange={(value) => setIncludeProfile(value === true)} />Include current profile</label>
        <p className="text-xs text-muted-foreground">These references apply to the next message. Outputs remain drafts.</p>
      </div>
    </details>
    {sessions.isError || session.isError ? <div role="alert" className="text-sm text-destructive">Unable to load this job’s conversation.<Button variant="outline" size="sm" onClick={() => { void sessions.refetch(); void session.refetch(); }}>Retry loading</Button></div> : null}
    {!messages.length && !busy ? <div className="space-y-3 py-6 text-sm text-muted-foreground"><p>Ask a question while keeping the job open.</p><div className="flex flex-wrap gap-2">{["Which requirements should I address?", "Help me draft an application answer", "Prepare questions for the recruiter"].map((prompt) => <Button key={prompt} size="sm" variant="outline" onClick={() => setMessage(prompt)}>{prompt}</Button>)}</div></div> : null}
    <ChatThread messages={messages} streaming={advanced ? null : stream.parts} streamingActive={stream.status === "streaming"} showReasoning={false} assistantName="Career assistant" assistantIcon={icon} />
    <ChatRunProgress runId={runId} status={stream.status} />
    {error || stream.error ? <p role="alert" className="text-sm text-destructive">{error || stream.error}</p> : null}
    <ChatComposer value={message} onChange={setMessage} onSend={() => void submit()} onStop={stop} busy={busy} disabled={sessions.isPending || sessions.isError || session.isError || Boolean(sessionId && session.isPending)} settling={stream.status === "settled"} ariaLabel="Ask about this job" placeholder="Ask about this role or selected resume…" />
    {sessionId ? <Link to={`/career-lab?session=${encodeURIComponent(sessionId)}`} className="text-center text-xs font-medium text-primary underline underline-offset-4">Open full workspace</Link> : null}
  </div>;
}
