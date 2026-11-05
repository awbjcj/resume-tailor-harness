"use client";

import { useId, useRef, useState, type FormEvent } from "react";
import { Alert, Badge, Button, Card, CardHeader, CardTitle, CompactRows, MetricRow, PageHeader, TextField, ThemeBoundary, type Theme } from "../adapters/react";

/** Import styles/index.css once in the host entry. Supply translated labels. */
export function Workspace({ theme = "system" }: { theme?: Theme }) {
  const [name, setName] = useState("");
  const [error, setError] = useState<string>();
  const [message, setMessage] = useState("");
  const dialogRef = useRef<HTMLDialogElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const dialogId = useId();

  function review(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!name.trim()) {
      setError("Enter a project name to continue.");
      inputRef.current?.focus();
      return;
    }
    setError(undefined);
    if (dialogRef.current) {
      dialogRef.current.returnValue = "";
      dialogRef.current.showModal();
    }
  }

  return (
    <ThemeBoundary theme={theme}>
      <main className="ti-container ti-stack">
        <PageHeader title="Project workspace" description="A local example of the review pattern." />
        <MetricRow items={[{ id: "sources", label: "Sources", value: "12" }, { id: "review", label: "Awaiting review", value: "03" }]} />
        <Card>
          <CardHeader><CardTitle>Project details</CardTitle><Badge tone="warning">Needs review</Badge></CardHeader>
          <form className="ti-stack" onSubmit={review} noValidate>
            <TextField ref={inputRef} name="project" label="Project name" value={name} onChange={(event) => setName(event.target.value)} required hint="Use a name your team recognizes." error={error} />
            <CompactRows rows={[{ id: "interface", label: "Interface", content: <><Badge>Keyboard access</Badge><Badge>Theme support</Badge><Badge>Localization</Badge></> }]} />
            <div className="ti-cluster"><Button type="submit">Review changes</Button><Button variant="outline" onClick={() => { setName(""); setError(undefined); }}>Reset</Button></div>
          </form>
        </Card>
        <p role="status" aria-live="polite">{message}</p>
        <dialog ref={dialogRef} className="ti-dialog" aria-labelledby={`${dialogId}-title`} aria-describedby={`${dialogId}-description`} onClose={() => { if (dialogRef.current?.returnValue === "confirm") setMessage("Example confirmed locally."); }}>
          <div className="ti-stack">
            <h2 id={`${dialogId}-title`} className="ti-heading">Review project name</h2>
            <p id={`${dialogId}-description`}>This example updates the on-page message only.</p>
            <Alert><div><strong>Proposed name</strong><p>{name}</p></div></Alert>
            <form method="dialog" className="ti-cluster"><Button type="submit" variant="outline" value="cancel">Cancel</Button><Button type="submit" value="confirm">Confirm example</Button></form>
          </div>
        </dialog>
      </main>
    </ThemeBoundary>
  );
}
