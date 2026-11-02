import { useSkillCopy } from "@/i18n/skill-copy";
import { useId, useState, type FormEvent } from "react";
import { FolderPlus, Pencil, Plus, Trash2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import {
  LibrarySelect,
  type LibraryGroup,
  type LibraryCategory,
} from "./SkillEditorFields";
import { useSkillOrganization } from "./use-profile-skills";

type Edit = {
  kind: "group" | "category";
  key?: string;
  label: string;
  category: string;
  remove?: boolean;
};

export function SkillOrganizationDialog({
  groups,
  categories,
  onClose,
  disabled = false,
}: {
  groups: LibraryGroup[];
  categories: LibraryCategory[];
  onClose: () => void;
  disabled?: boolean;
}) {
  const copy = useSkillCopy();
  const id = useId();
  const [edit, setEdit] = useState<Edit | null>(null);
  const mutation = useSkillOrganization();
  const pending = disabled || mutation.isPending;
  function submit(event: FormEvent) {
    event.preventDefault();
    if (edit && !pending)
      mutation.mutate(edit, { onSuccess: () => setEdit(null) });
  }
  return (
    <Dialog
      open
      onOpenChange={(open) => {
        if (!open && !mutation.isPending) onClose();
      }}
    >
      <DialogContent
        overlayClassName="transition-none"
        className="min-w-0 transition-none [overflow-wrap:anywhere] sm:max-w-2xl"
        showCloseButton={!mutation.isPending}
      >
        <DialogHeader>
          <DialogTitle>{copy.groups_categories}</DialogTitle>
          <DialogDescription>{copy.organizationDescription}</DialogDescription>
        </DialogHeader>
        {edit ? (
          <form
            onSubmit={submit}
            className="grid gap-4 rounded-lg border bg-muted/30 p-4"
          >
            <h3 className="font-medium">
              {edit.remove
                ? edit.kind === "group" ? copy.deleteGroup : copy.deleteCategory
                : edit.key
                  ? edit.kind === "group" ? copy.editGroup : copy.editCategory
                  : edit.kind === "group" ? copy.createGroup : copy.createCategory}
            </h3>
            {edit.remove ? (
              <p className="text-sm text-muted-foreground">
                {edit.label} {copy.deleteNotice}
              </p>
            ) : (
              <>
                <label htmlFor={`${id}-name`} className="text-sm font-medium">
                  {copy.name}
                </label>
                <Input
                  id={`${id}-name`}
                  value={edit.label}
                  onChange={(e) => setEdit({ ...edit, label: e.target.value })}
                  maxLength={80}
                  required
                  disabled={pending}
                />
                {edit.kind === "group" ? (
                  <div className="grid gap-1.5">
                    <label
                      htmlFor={`${id}-parent`}
                      className="text-sm font-medium"
                    >
                      Category
                    </label>
                    <LibrarySelect
                      id={`${id}-parent`}
                      value={edit.category}
                      onChange={(category) => setEdit({ ...edit, category })}
                      disabled={pending}
                    >
                      {categories.map((c) => (
                        <option key={c.slug} value={c.slug}>
                          {c.label}
                        </option>
                      ))}
                    </LibrarySelect>
                  </div>
                ) : null}
              </>
            )}
            {mutation.error ? (
              <p role="alert" className="text-sm text-destructive">
                {mutation.error.message}
              </p>
            ) : null}
            <div className="flex flex-wrap justify-end gap-2">
              <Button
                type="button"
                variant="outline"
                onClick={() => setEdit(null)}
                disabled={pending}
              >
                Cancel
              </Button>
              <Button
                type="submit"
                variant={edit.remove ? "destructive" : "default"}
                disabled={pending || !edit.label.trim()}
              >
                {mutation.isPending
                  ? "Saving…"
                  : edit.remove
                    ? edit.kind === "group" ? copy.deleteGroup : copy.deleteCategory
                    : "Save changes"}
              </Button>
            </div>
          </form>
        ) : (
          <div className="flex flex-wrap gap-2">
            <Button
              variant="outline"
              disabled={pending}
              onClick={() =>
                setEdit({ kind: "category", label: "", category: "other" })
              }
            >
              <Plus aria-hidden />
              {copy.add_category}
            </Button>
            <Button
              variant="outline"
              disabled={pending}
              onClick={() =>
                setEdit({
                  kind: "group",
                  label: "",
                  category: categories[0]?.slug ?? "other",
                })
              }
            >
              <FolderPlus aria-hidden />
              {copy.add_group}
            </Button>
          </div>
        )}
        <div className="max-h-[50svh] space-y-5 overflow-y-auto pr-1">
          {categories.map((category) => (
            <section key={category.slug} className="min-w-0">
              <div className="flex min-w-0 items-center gap-2 border-b pb-2">
                <h3 className="min-w-0 flex-1 break-words font-semibold">
                  {category.label}
                </h3>
                <Button
                  size="icon-sm"
                  variant="ghost"
                  aria-label={`Edit category ${category.label}`}
                  disabled={pending}
                  onClick={() =>
                    setEdit({
                      kind: "category",
                      key: category.slug,
                      label: category.label,
                      category: "other",
                    })
                  }
                >
                  <Pencil aria-hidden />
                </Button>
                <Button
                  size="icon-sm"
                  variant="ghost"
                  aria-label={`Delete category ${category.label}`}
                  disabled={pending || category.slug === "other"}
                  onClick={() =>
                    setEdit({
                      kind: "category",
                      key: category.slug,
                      label: category.label,
                      category: "other",
                      remove: true,
                    })
                  }
                >
                  <Trash2 aria-hidden />
                </Button>
              </div>
              <ul className="divide-y">
                {groups
                  .filter((g) => g.category === category.slug)
                  .map((group) => (
                    <li
                      key={group.slug}
                      className="flex min-w-0 items-center gap-2 py-1 pl-3"
                    >
                      <span className="min-w-0 flex-1 break-words text-sm text-muted-foreground">
                        {group.label}
                      </span>
                      <Button
                        size="icon-sm"
                        variant="ghost"
                        aria-label={`Edit group ${group.label}`}
                        disabled={pending}
                        onClick={() =>
                          setEdit({
                            kind: "group",
                            key: group.slug,
                            label: group.label,
                            category: group.category,
                          })
                        }
                      >
                        <Pencil aria-hidden />
                      </Button>
                      <Button
                        size="icon-sm"
                        variant="ghost"
                        aria-label={`Delete group ${group.label}`}
                        disabled={pending || group.slug === "other"}
                        onClick={() =>
                          setEdit({
                            kind: "group",
                            key: group.slug,
                            label: group.label,
                            category: group.category,
                            remove: true,
                          })
                        }
                      >
                        <Trash2 aria-hidden />
                      </Button>
                    </li>
                  ))}
              </ul>
            </section>
          ))}
        </div>
      </DialogContent>
    </Dialog>
  );
}
