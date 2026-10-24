import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import type { SkillRow } from "../aggregate";
import { useDiscardSkills } from "../use-taxonomy";
export function RemoveSkillDialog({
  skill,
  open,
  onOpenChange,
}: {
  skill: SkillRow;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const mutation = useDiscardSkills();
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Remove {skill.skill}?</DialogTitle>
          <DialogDescription>
            Discards this entry from skill demand and future regrouping. You can
            restore it from discarded non-skills. Original job descriptions stay
            intact.
          </DialogDescription>
        </DialogHeader>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button
            variant="destructive"
            disabled={mutation.isPending}
            onClick={() =>
              mutation.mutate([skill.key], {
                onSuccess: () => onOpenChange(false),
              })
            }
          >
            Remove skill
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
