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
import type { CategoryRow } from "../aggregate";
import { domainSearchGroups } from "./domain-search-groups";
import { useMergeDomains } from "../use-taxonomy";
export function MergeDomainDialog({
  domainId,
  categoryRows,
  open,
  onOpenChange,
}: {
  domainId: string;
  categoryRows: CategoryRow[];
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const [into, setInto] = useState("");
  const mutation = useMergeDomains();
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Merge domain</DialogTitle>
          <DialogDescription>
            Skills in this domain move to the target; this domain disappears.
          </DialogDescription>
        </DialogHeader>
        <Field>
          <FieldLabel>Target domain</FieldLabel>
          <SearchableSelect
            label="Target domain"
            placeholder="Choose a domain"
            groups={domainSearchGroups(categoryRows, domainId)}
            value={into || null}
            onChange={setInto}
            disabled={mutation.isPending}
          />
        </Field>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button
            disabled={!into || mutation.isPending}
            onClick={() =>
              mutation.mutate(
                { domainId, into },
                { onSuccess: () => onOpenChange(false) },
              )
            }
          >
            Merge domain
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
