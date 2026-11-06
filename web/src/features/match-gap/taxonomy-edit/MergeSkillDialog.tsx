import { useState } from "react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Field, FieldLabel } from "@/components/ui/field";
import { SearchableSelect } from "@/components/ui/searchable-select";
import type { CategoryRow, SkillRow } from "../aggregate";
import { useMergeSkills } from "../use-taxonomy";
export function MergeSkillDialog({
  skill,
  categoryRows,
  open,
  onOpenChange,
}: {
  skill: SkillRow;
  categoryRows: CategoryRow[];
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const mutation = useMergeSkills();
  const [canonical, setCanonical] = useState("");
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Merge skill</DialogTitle>
          <DialogDescription>
            {skill.skill} becomes an alias of the selected skill.
          </DialogDescription>
        </DialogHeader>
        <Field>
          <FieldLabel>Canonical skill</FieldLabel>
          <SearchableSelect
            label="Canonical skill"
            placeholder="Choose a skill"
            groups={categoryRows.flatMap((category) => category.domains.map((domain) => ({
              id: domain.id,
              label: `${category.label} / ${domain.label}`,
              items: domain.skills.filter((item) => item.key !== skill.key).map((item) => ({
                value: item.key,
                label: item.skill,
                keywords: Object.keys(item.members),
              })),
            })))}
            value={canonical || null}
            onChange={setCanonical}
            disabled={mutation.isPending}
          />
        </Field>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button
            disabled={!canonical || mutation.isPending}
            onClick={() =>
              mutation.mutate(
                { token: skill.key, canonical },
                { onSuccess: () => onOpenChange(false) },
              )
            }
          >
            Merge skill
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
