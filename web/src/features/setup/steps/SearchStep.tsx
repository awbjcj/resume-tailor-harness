import { useNavigate } from "react-router-dom";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import { SearchConfigForm } from "@/features/settings/forms/SearchConfigForm";
import { useConfig, useSaveConfig } from "@/features/settings/use-config";
import { useDraft } from "@/features/settings/use-draft";
import type { paths } from "@/lib/api/schema";
import { useSetupContinuation } from "../use-setup-continuation";

type SearchDoc = paths["/api/config/search"]["get"]["responses"][200]["content"]["application/json"];

export function SearchStep() {
  const { data } = useConfig("/api/config/search");
  const save = useSaveConfig("/api/config/search");
  const { draft, setDraft } = useDraft(data as SearchDoc | undefined);
  const navigate = useNavigate();
  const { nextPath } = useSetupContinuation();

  const continueToNext = async () => {
    if (!draft) return;
    try {
      await save.mutateAsync(draft);
      navigate(nextPath("search"));
    } catch { /* Failed saves leave the form and draft in place. */ }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>Search</CardTitle>
        <CardDescription>What discovery looks for.</CardDescription>
      </CardHeader>
      <CardContent>
        {draft && <SearchConfigForm value={draft} onChange={setDraft} />}
      </CardContent>
      <CardFooter className="justify-end gap-2">
        <Button variant="ghost" disabled={save.isPending} onClick={() => navigate(nextPath("search"))}>Skip for now</Button>
        <Button disabled={!draft || save.isPending} onClick={() => void continueToNext()}>Save & continue</Button>
      </CardFooter>
    </Card>
  );
}
