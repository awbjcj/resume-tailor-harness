import { ClipboardCopy } from "lucide-react";
import { useRef, useState } from "react";
import { toast } from "sonner";
import { Button, buttonVariants } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Spinner } from "@/components/ui/spinner";
import { Textarea } from "@/components/ui/textarea";
import { api, unwrap } from "@/lib/api/client";

export function CopyApplicationPromptButton({ jobId, compact = false }: { jobId: number; compact?: boolean }) {
  const [pending, setPending] = useState(false);
  const [fallback, setFallback] = useState<string | null>(null);
  const buttonRef = useRef<HTMLButtonElement>(null);

  async function copy() {
    setPending(true);
    try {
      const { prompt } = await unwrap(api.GET("/api/jobs/{job_id}/application-prompt", {
        params: { path: { job_id: jobId } },
      }));
      try {
        await navigator.clipboard.writeText(prompt);
        toast.success("Application prompt copied in English");
      } catch {
        setFallback(prompt);
      }
    } catch {
      toast.error("Could not load application prompt. Please try again.");
    } finally {
      setPending(false);
    }
  }

  return (
    <>
      <Button
        ref={buttonRef}
        size={compact ? "icon-sm" : "sm"}
        variant={compact ? "ghost" : "outline"}
        aria-label="Copy application prompt"
        title="Copy application prompt"
        disabled={pending}
        aria-busy={pending}
        onClick={(event) => {
          event.stopPropagation();
          void copy();
        }}
      >
        {pending ? <Spinner className="motion-reduce:animate-none" aria-hidden="true" /> : <ClipboardCopy aria-hidden="true" />}
        {!compact && "Copy application prompt"}
      </Button>
      <Dialog open={fallback !== null} onOpenChange={(open) => { if (!open) setFallback(null); }}>
        <DialogContent
          className="sm:max-w-2xl"
          finalFocus={buttonRef}
          onClick={(event) => event.stopPropagation()}
        >
          <DialogHeader className="pr-6">
            <DialogTitle>Copy application prompt</DialogTitle>
            <DialogDescription>
              Clipboard access is unavailable. Select and copy the text below, then paste it into your browser or computer-use assistant.
            </DialogDescription>
          </DialogHeader>
          <Textarea
            aria-label="English application prompt"
            value={fallback ?? ""}
            readOnly
            className="h-80 min-h-32 resize-y font-mono text-sm"
            translate="no"
            onFocus={(event) => event.target.select()}
          />
          <DialogFooter showCloseButton>
            <a href="/settings/application-profile" className={buttonVariants({ variant: "ghost" })}>
              Edit application profile
            </a>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
