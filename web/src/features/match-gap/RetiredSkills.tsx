import { Undo2Icon } from "lucide-react";
import { useState } from "react";
import { Input } from "@/components/ui/input";

import { Button } from "@/components/ui/button";
import {
  Popover,
  PopoverContent,
  PopoverHeader,
  PopoverTitle,
  PopoverTrigger,
} from "@/components/ui/popover";
import type { components } from "@/lib/api/schema";
import { useRestoreSkills } from "./use-taxonomy";

type RetiredSkill = components["schemas"]["RetiredSkillOut"];

/**
 * Retired tokens are removed from the backlog entirely, so they have to stay
 * visible somewhere: a wrong call would otherwise be both invisible and
 * permanent. Restoring returns one to the next regroup.
 */
export function RetiredSkills({ skills }: { skills: RetiredSkill[] }) {
  const restore = useRestoreSkills();
  const [query, setQuery] = useState("");
  const matching = skills.filter((skill) =>
    skill.key.toLowerCase().includes(query.toLowerCase()),
  );
  if (skills.length === 0) return null;

  return (
    <Popover>
      <PopoverTrigger
        render={
          <Button variant="ghost" size="xs" className="text-muted-foreground" />
        }
      >
        {`${skills.length} discarded non-skills`}
      </PopoverTrigger>
      <PopoverContent align="end" className="w-80 p-0">
        <PopoverHeader className="gap-1 p-4 pb-2">
          <PopoverTitle>Discarded non-skills</PopoverTitle>
          <p className="text-xs text-muted-foreground">
            These entries are excluded from skill demand and regrouping. Restore
            any valid entries.
          </p>
          <Input
            aria-label="Search discarded entries"
            placeholder="Search entries…"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
          />
        </PopoverHeader>
        <ul className="max-h-72 overflow-y-auto border-t">
          {matching.slice(0, 100).map((skill) => (
            <li
              key={skill.key}
              className="flex items-center justify-between gap-2 border-b px-4 py-2 last:border-b-0"
            >
              <span
                className="min-w-0 break-words text-sm"
                title={skill.reason}
              >
                {skill.key}
              </span>
              <Button
                variant="outline"
                size="xs"
                disabled={restore.isPending}
                onClick={() => restore.mutate([skill.key])}
              >
                <Undo2Icon data-icon="inline-start" />
                Restore
              </Button>
            </li>
          ))}
        </ul>
        <p className="px-4 pt-2 text-xs text-muted-foreground">{`Showing ${Math.min(matching.length, 100)} of ${matching.length} matching entries`}</p>
        <div className="p-3">
          <Button
            variant="outline"
            size="sm"
            className="w-full"
            disabled={restore.isPending}
            onClick={() => restore.mutate(skills.map((skill) => skill.key))}
          >
            Restore all {skills.length}
          </Button>
        </div>
      </PopoverContent>
    </Popover>
  );
}
