import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Plus } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { useDeferredComponent } from "@/lib/use-deferred-component";

const loadEditor = () => import("./SkillEditorDialog").then((module) => ({
  default: module.SkillEditorDialog,
}));

export function AddJobSkillButton({ skillName }: { skillName: string }) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const [returnFocus, setReturnFocus] = useState<HTMLElement | null>(null);
  const { Component: Editor, failed, retry, reloadRequired } = useDeferredComponent(open, loadEditor);
  return (
    <>
      <Button
        type="button"
        variant="ghost"
        size="icon-xs"
        className="size-4 [&_svg]:size-3"
        aria-label={`Add "${skillName}" to your profile`}
        aria-haspopup="dialog"
        onClick={(event) => {
          event.stopPropagation();
          setReturnFocus(event.currentTarget);
          setOpen(true);
        }}
      >
        <Plus aria-hidden />
      </Button>
      {open ? Editor ? (
        <Editor
          suggestedSkill={skillName}
          returnFocus={returnFocus}
          onClose={() => setOpen(false)}
        />
      ) : (
        <Dialog open onOpenChange={(next) => { if (!next) setOpen(false); }}>
          <DialogContent
            finalFocus={() => (returnFocus?.isConnected ? returnFocus : true)}
            onClick={(event) => event.stopPropagation()}
            onKeyDown={(event) => {
              if (event.key === "ArrowLeft" || event.key === "ArrowRight")
                event.stopPropagation();
            }}
          >
            <DialogHeader>
              <DialogTitle>Add a skill</DialogTitle>
              <DialogDescription role={failed ? "alert" : "status"}>
                {t(failed ? "deferred.failed" : "deferred.loading")}
              </DialogDescription>
            </DialogHeader>
            {failed ? (
              <Button onClick={retry}>{t(reloadRequired ? "deferred.reload" : "deferred.retry")}</Button>
            ) : null}
          </DialogContent>
        </Dialog>
      ) : null}
    </>
  );
}
