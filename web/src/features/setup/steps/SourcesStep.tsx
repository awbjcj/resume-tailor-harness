import { useNavigate } from "react-router-dom";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import { SourcesManager } from "@/features/sources/SourcesPage";
import { useSetupContinuation } from "../use-setup-continuation";

export function SourcesStep() {
  const navigate = useNavigate();
  const { nextPath } = useSetupContinuation();
  return (
    <Card>
      <CardHeader>
        <CardTitle><h1>Sources</h1></CardTitle>
        <CardDescription>
          Add at least one board or careers page to pull jobs from.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <SourcesManager />
      </CardContent>
      <CardFooter className="justify-end gap-2">
        <Button variant="ghost" onClick={() => navigate(nextPath("sources"))}>Skip for now</Button>
        <Button onClick={() => navigate(nextPath("sources"))}>Continue</Button>
      </CardFooter>
    </Card>
  );
}
