import { useMemo, useState } from "react";
import { ListFilterIcon } from "lucide-react";
import { useTranslation } from "react-i18next";
import { localizeDisplayValue } from "@/i18n/dynamic-labels";

import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import type { components } from "@/lib/api/schema";
import { useDiscardSkills } from "./use-taxonomy";

type MatchGap = components["schemas"]["MatchGapOut"];
const PAGE_SIZE = 100;

export function CleanupSkills({ data }: { data: MatchGap }) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <Button variant="outline" size="sm" onClick={() => setOpen(true)}>
        <ListFilterIcon data-icon="inline-start" />
        Clean up skills
      </Button>
      <Dialog open={open} onOpenChange={setOpen}>
        {open && <CleanupDialog data={data} onClose={() => setOpen(false)} />}
      </Dialog>
    </>
  );
}

function CleanupDialog({
  data,
  onClose,
}: {
  data: MatchGap;
  onClose: () => void;
}) {
  const { i18n } = useTranslation();
  const discard = useDiscardSkills();
  const [allSkills, setAllSkills] = useState(false);
  const [query, setQuery] = useState("");
  const [page, setPage] = useState(0);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const entries = useMemo(() => {
    const candidates = new Map(
      (data.cleanupCandidates ?? []).map((entry) => [entry.key, entry.reason]),
    );
    const skills = new Map(
      data.skills.map((skill) => [skill.key, skill.skill]),
    );
    const keys = allSkills
      ? new Set([...skills.keys(), ...candidates.keys()])
      : candidates.keys();
    return [...keys]
      .map((key) => ({
        key,
        label: skills.get(key) ?? key,
        reason: candidates.get(key),
      }))
      .filter((entry) =>
        `${entry.label} ${entry.key}`
          .toLowerCase()
          .includes(query.toLowerCase()),
      )
      .sort((a, b) => a.label.localeCompare(b.label));
  }, [data, allSkills, query]);
  const visible = entries.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE);
  const toggle = (key: string, checked: boolean) =>
    setSelected((current) => {
      const next = new Set(current);
      if (checked && next.size < 500) next.add(key);
      else if (!checked) next.delete(key);
      return next;
    });

  return (
    <DialogContent className="flex max-h-[90dvh] flex-col sm:max-w-2xl">
      <DialogHeader>
        <DialogTitle>Clean up skills</DialogTitle>
        <DialogDescription>
          Review degrees, experience durations, and other requirements that are
          not skills. Discarded entries leave the skill map and future
          regrouping. Original job descriptions stay intact, and entries can be
          restored.
        </DialogDescription>
      </DialogHeader>
      <div className="flex flex-wrap gap-2">
        <Button
          variant={!allSkills ? "secondary" : "outline"}
          size="sm"
          aria-pressed={!allSkills}
          onClick={() => {
            setAllSkills(false);
            setPage(0);
            setSelected(new Set());
          }}
        >
          Suggested non-skills
        </Button>
        <Button
          variant={allSkills ? "secondary" : "outline"}
          size="sm"
          aria-pressed={allSkills}
          onClick={() => {
            setAllSkills(true);
            setPage(0);
            setSelected(new Set());
          }}
        >
          All skill entries
        </Button>
      </div>
      <Input
        aria-label="Search cleanup entries"
        placeholder="Search entries…"
        value={query}
        onChange={(event) => {
          setQuery(event.target.value);
          setPage(0);
        }}
      />
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="text-sm text-muted-foreground">{`${entries.length} entries · ${selected.size} selected (up to 500)`}</span>
        <div className="flex gap-2">
          <Button
            variant="ghost"
            size="xs"
            disabled={
              discard.isPending || !visible.length || selected.size >= 500
            }
            onClick={() =>
              setSelected(
                (current) =>
                  new Set(
                    [...new Set([...current, ...visible.map((entry) => entry.key)])].slice(
                      0,
                      500,
                    ),
                  ),
              )
            }
          >
            Select visible
          </Button>
          <Button
            variant="ghost"
            size="xs"
            disabled={discard.isPending || !selected.size}
            onClick={() => setSelected(new Set())}
          >
            Clear selection
          </Button>
        </div>
      </div>
      <ul className="min-h-24 flex-1 overflow-y-auto rounded-md border">
        {!visible.length && (
          <li className="p-5 text-sm text-muted-foreground">
            No matching entries. Use All skill entries to review other unwanted
            items.
          </li>
        )}
        {visible.map((entry) => (
          <li key={entry.key} className="border-b last:border-b-0">
            <label className="flex cursor-pointer items-start gap-3 px-3 py-3">
              <Checkbox
                checked={selected.has(entry.key)}
                aria-label={`Discard ${entry.label}`}
                disabled={
                  discard.isPending ||
                  (!selected.has(entry.key) && selected.size >= 500)
                }
                onCheckedChange={(checked) => toggle(entry.key, checked)}
              />
              <span className="min-w-0 break-words text-sm">
                <span className="block">{entry.label}</span>
                {entry.reason && (
                  <span className="block text-xs text-muted-foreground">
                    {localizeDisplayValue(entry.reason, i18n.resolvedLanguage)}
                  </span>
                )}
              </span>
            </label>
          </li>
        ))}
      </ul>
      {entries.length > PAGE_SIZE && (
        <div className="flex items-center justify-between">
          <Button
            variant="outline"
            size="xs"
            disabled={!page}
            onClick={() => setPage(page - 1)}
          >
            Previous
          </Button>
          <span className="text-xs text-muted-foreground">
            {page + 1} / {Math.ceil(entries.length / PAGE_SIZE)}
          </span>
          <Button
            variant="outline"
            size="xs"
            disabled={(page + 1) * PAGE_SIZE >= entries.length}
            onClick={() => setPage(page + 1)}
          >
            Next
          </Button>
        </div>
      )}
      <DialogFooter>
        <Button variant="outline" onClick={onClose}>
          Cancel
        </Button>
        <Button
          variant="destructive"
          disabled={!selected.size || discard.isPending}
          onClick={() => discard.mutate([...selected], { onSuccess: onClose })}
        >
          {`Discard selected (${selected.size})`}
        </Button>
      </DialogFooter>
    </DialogContent>
  );
}
