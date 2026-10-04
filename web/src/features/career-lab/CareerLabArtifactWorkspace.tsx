import { useId, useState } from "react";
import { FileText } from "lucide-react";
import { TextPart } from "@/components/chat/parts/TextPart";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import type { CareerLabSession } from "./use-career-lab";

type Turn = NonNullable<CareerLabSession["turns"]>[number];

export function CareerLabArtifactWorkspace({ turns, selectedId, onSelect, onRevise, busy, liveText = "" }: {
  turns: Turn[];
  selectedId: string | null;
  onSelect: (id: string) => void;
  onRevise: (turnId: string, message: string) => void;
  busy: boolean;
  liveText?: string;
}) {
  const id = useId();
  const drafts = turns.filter((turn) => turn.artifact);
  const selected = drafts.find((turn) => turn.turnId === selectedId) ?? drafts.at(-1);
  const [feedback, setFeedback] = useState("");
  const [section, setSection] = useState("");
  const [revisionTurnId, setRevisionTurnId] = useState(selected?.turnId);
  // Selection can change from the chat or when a new latest draft arrives,
  // not only through the version dropdown. Never carry feedback across drafts.
  if (revisionTurnId !== selected?.turnId) {
    setRevisionTurnId(selected?.turnId);
    setSection("");
    setFeedback("");
  }
  const headings = selected?.text.split("\n").filter((line) => /^#{1,6}\s+/.test(line)).map((line) => line.replace(/^#+\s+/, "")) ?? [];
  if (!selected && !liveText) return null;
  return <Card className="min-w-0" aria-label="Draft workspace">
    <CardHeader className="gap-3 border-b">
      <div className="flex items-center gap-2"><FileText className="size-4 text-primary" aria-hidden="true" /><CardTitle className="flex-1 text-base">Draft workspace</CardTitle><Badge variant="outline">Draft</Badge></div>
      {drafts.length ? <><Label htmlFor={`${id}-version`}>Draft version</Label><select id={`${id}-version`} className="w-full rounded-lg border bg-background p-2 text-sm" value={selected?.turnId ?? ""} onChange={(event) => { onSelect(event.target.value); setSection(""); setFeedback(""); }}>{drafts.map((turn, index) => <option key={turn.turnId} value={turn.turnId}>{index + 1}. {turn.artifact?.title}</option>)}</select></> : null}
      <p className="text-xs text-muted-foreground">Revisions create a new response. Previous drafts remain available.</p>
    </CardHeader>
    <CardContent className="space-y-4 pt-4">
      <div className="max-h-[50vh] overflow-y-auto overscroll-contain" tabIndex={0} aria-label="Draft content"><TextPart text={selected?.text ?? liveText} /></div>
      {liveText && selected ? <details className="rounded-lg border p-3"><summary className="cursor-pointer text-sm font-medium">Response in progress</summary><div className="mt-3 max-h-64 overflow-y-auto"><TextPart text={liveText} caret /></div></details> : null}
      {selected ? <form className="space-y-3 border-t pt-4" onSubmit={(event) => { event.preventDefault(); if (!feedback.trim() || busy) return; onRevise(selected.turnId, `Revise ${section ? `the section "${section}" in` : ""} the selected draft.\n\n${feedback.trim()}`); setFeedback(""); }}>
        <Label htmlFor={`${id}-section`}>Revision scope</Label>
        <select id={`${id}-section`} value={section} onChange={(event) => setSection(event.target.value)} className="w-full rounded-lg border bg-background p-2 text-sm"><option value="">Whole draft</option>{[...new Set(headings)].map((heading) => <option key={heading}>{heading}</option>)}</select>
        <Label htmlFor={`${id}-feedback`}>Feedback</Label>
        <Textarea id={`${id}-feedback`} value={feedback} onChange={(event) => setFeedback(event.target.value)} placeholder="What should change in the next revision?" maxLength={8000} />
        <Button type="submit" disabled={busy || !feedback.trim()} className="w-full">Prepare revision request</Button>
      </form> : null}
    </CardContent>
  </Card>;
}
