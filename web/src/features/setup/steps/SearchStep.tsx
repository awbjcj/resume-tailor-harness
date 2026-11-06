import { useRef } from "react";
import { useNavigate } from "react-router-dom";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import { SearchConfigForm } from "@/features/settings/forms/SearchConfigForm";
import { useConfig, useSaveConfig, useSearchLocationNormalizationPending } from "@/features/settings/use-config";
import { useDraft } from "@/features/settings/use-draft";
import type { paths } from "@/lib/api/schema";
import { validateTagDrafts } from "@/lib/tag-list-drafts";
import { useSetupContinuation } from "../use-setup-continuation";

type SearchDoc = paths["/api/config/search"]["get"]["responses"][200]["content"]["application/json"];

export function SearchStep() {
  const { data } = useConfig("/api/config/search");
  const save = useSaveConfig("/api/config/search");
  const normalizing = useSearchLocationNormalizationPending();
  const fields = useRef<HTMLDivElement>(null);
  const { draft, setDraft } = useDraft(data as SearchDoc | undefined);
  const navigate = useNavigate();
  const { nextPath } = useSetupContinuation();

  const continueToNext = async () => {
    if (!draft || !validateTagDrafts(fields.current)) return;
    try {
      await save.mutateAsync(draft);
      navigate(nextPath("search"));
    } catch { /* Failed saves leave the form and draft in place. */ }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle><h1>Search</h1></CardTitle>
      </CardHeader>
      <CardContent ref={fields}>
        {draft && (
          <SearchConfigForm
            value={draft}
            disabled={save.isPending}
            onChange={(update) => setDraft((current) => current && update(current))}
          />
        )}
      </CardContent>
      <CardFooter className="justify-end gap-2">
        <Button variant="ghost" disabled={save.isPending} onClick={() => navigate(nextPath("search"))}>Skip for now</Button>
        <Button disabled={!draft || save.isPending || normalizing} onClick={() => void continueToNext()}>Save & continue</Button>
      </CardFooter>
    </Card>
  );
}
