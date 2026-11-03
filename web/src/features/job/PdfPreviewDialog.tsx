import { useCallback, useEffect, useRef, useState } from "react";
import { Download, Loader2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { apiUrl, authHeaders, createDownloadUrl, openDownload } from "@/lib/api/client";

/**
 * The dialog stays mounted for its exit transition (200ms in `dialog.tsx`), so
 * the close-time reset is deferred past it -- clearing the frame the moment
 * `open` flips makes the PDF vanish and leaves an empty box fading out.
 */
const EXIT_RESET_DELAY_MS = 250;

/**
 * Render a stored PDF inline, so a resume or cover letter can be read before
 * it is downloaded. The API's `/preview` routes deliberately serve an `inline`
 * disposition and friendly filename. A short download capability lets native
 * viewers authenticate without replacing the named response with a blob UUID.
 */
export function PdfPreviewDialog({
  open,
  onOpenChange,
  title,
  previewPath,
  downloadPath,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  previewPath: string;
  downloadPath: string;
}) {
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  // Derived rather than stored: the reset clears both results, so "open with no
  // result yet" is exactly the loading state, and the effect body never has to
  // set state synchronously.
  const loading = open && previewUrl === null && error === null;
  const pendingResetRef = useRef<{ id: number; run: () => void } | null>(null);

  // Settle a deferred close-time reset early. Everything that must reset
  // promptly -- a `previewPath` change while open, a reopen, unmount -- calls
  // this rather than waiting out the exit animation.
  const flushPendingReset = useCallback(() => {
    const pending = pendingResetRef.current;
    if (pending === null) return;
    pendingResetRef.current = null;
    window.clearTimeout(pending.id);
    pending.run();
  }, []);

  useEffect(() => {
    if (!open) return;
    flushPendingReset();

    const controller = new AbortController();
    void (async () => {
      try {
        const response = await fetch(apiUrl(previewPath), {
          credentials: "include",
          headers: authHeaders(),
          signal: controller.signal,
        });
        if (!response.ok) {
          const payload = await response.json().catch(() => null);
          throw new Error(payload?.error?.message ?? "Preview failed");
        }
        // Check errors before mounting the frame, then let the native viewer
        // stream the named response itself. Do not buffer another PDF copy.
        await response.body?.cancel();
        if (controller.signal.aborted) return;
        const url = await createDownloadUrl(previewPath, controller.signal);
        if (!controller.signal.aborted) setPreviewUrl(url);
      } catch (cause) {
        // A deliberate abort is not a failure worth reporting.
        if (controller.signal.aborted) return;
        setError(cause instanceof Error ? cause.message : "Preview failed");
      }
    })();

    return () => {
      controller.abort();
      const run = () => {
        setPreviewUrl(null);
        setError(null);
      };
      pendingResetRef.current = {
        id: window.setTimeout(() => {
          pendingResetRef.current = null;
          run();
        }, EXIT_RESET_DELAY_MS),
        run,
      };
    };
  }, [open, previewPath, flushPendingReset]);

  // Unmounting has no exit animation to wait for. Declared after the fetch
  // effect so its cleanup runs second, on the reset that one just scheduled.
  useEffect(() => flushPendingReset, [flushPendingReset]);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="flex h-[85vh] w-full max-w-4xl flex-col gap-0 p-0 sm:max-w-4xl">
        <DialogHeader className="p-4 pb-2">
          <DialogTitle>{title}</DialogTitle>
          <DialogDescription className="sr-only">
            Preview of the generated PDF. Use Download to save a copy.
          </DialogDescription>
        </DialogHeader>
        <div className="flex-1 overflow-hidden p-4 pt-0">
          {loading ? (
            <div className="flex h-full items-center justify-center">
              <Loader2 className="size-6 animate-spin text-muted-foreground" aria-label="Loading preview" />
            </div>
          ) : error ? (
            <p className="flex h-full items-center justify-center text-sm text-destructive" role="alert">
              {error}
            </p>
          ) : previewUrl ? (
            <iframe
              src={previewUrl}
              title={title}
              referrerPolicy="no-referrer"
              className="h-full w-full rounded-lg border-0"
            />
          ) : null}
        </div>
        {/* The footer's default negative margins assume DialogContent's p-4. */}
        <DialogFooter showCloseButton className="mx-0 mb-0">
          <Button variant="outline" onClick={() => void openDownload(downloadPath)}>
            <Download className="size-4" aria-hidden="true" />
            Download
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
