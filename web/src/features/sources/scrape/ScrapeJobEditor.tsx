import { useId } from "react";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import type { JobFacts } from "./use-scrape";

export function ScrapeJobEditor({
  value,
  onChange,
}: {
  value: JobFacts;
  onChange: (value: JobFacts) => void;
}) {
  const id = useId();
  const bands = value.salaryBands ?? [];
  return (
    <div className="grid gap-3 sm:grid-cols-2">
      {(
        [
          ["title", "Title"],
          ["company", "Company"],
          ["employmentType", "Employment type"],
          ["remoteRestrictions", "Remote geographic restrictions"],
          ["attendance", "Office attendance"],
          ["postedAt", "Posted date"],
          ["closesAt", "Closing date"],
          ["applicationUrl", "Application URL"],
        ] as const
      ).map(([field, label]) => (
        <label key={field} className="space-y-1 text-sm">
          {label}
          <Input
            value={value[field] ?? ""}
            placeholder="Not stated"
            onChange={(event) =>
              onChange({ ...value, [field]: event.target.value || null })
            }
          />
        </label>
      ))}
      <label className="space-y-1 text-sm" htmlFor={`${id}-policy`}>
        Work policy
        <select
          id={`${id}-policy`}
          className="block w-full rounded border bg-background p-2"
          value={value.remotePolicy ?? ""}
          onChange={(event) =>
            onChange({
              ...value,
              remotePolicy: (event.target.value ||
                null) as JobFacts["remotePolicy"],
            })
          }
        >
          <option value="">Unknown</option>
          <option value="remote">Remote</option>
          <option value="hybrid">Hybrid</option>
          <option value="onsite">Onsite</option>
        </select>
      </label>
      <label className="space-y-1 text-sm">
        Locations (one per line)
        <textarea
          className="block min-h-20 w-full rounded border bg-background p-2"
          value={value.locations?.join("\n") ?? ""}
          onChange={(event) =>
            onChange({
              ...value,
              locations: event.target.value
                ? event.target.value.split("\n")
                : null,
            })
          }
        />
      </label>
      <fieldset className="space-y-3 sm:col-span-2">
        <legend className="text-sm font-medium">Compensation</legend>
        {bands.map((band, index) => (
          <div
            key={index}
            className="grid gap-2 rounded border p-3 sm:grid-cols-3"
          >
            {(
              [
                ["minimum", "Minimum"],
                ["maximum", "Maximum"],
                ["currency", "Currency"],
                ["period", "Pay period"],
                ["rawText", "Original salary text"],
              ] as const
            ).map(([field, label]) => (
              <label key={field} className="text-sm">
                {label}
                <Input
                  value={band[field] ?? ""}
                  onChange={(event) =>
                    onChange({
                      ...value,
                      salaryBands: bands.map((item, i) =>
                        i === index
                          ? {
                              ...item,
                              [field]:
                                event.target.value ||
                                (field === "rawText" ? "" : null),
                            }
                          : item,
                      ),
                    })
                  }
                />
              </label>
            ))}
            <label className="text-sm">
              Salary locations
              <Input
                value={band.locations?.join("; ") ?? ""}
                onChange={(event) =>
                  onChange({
                    ...value,
                    salaryBands: bands.map((item, i) =>
                      i === index
                        ? {
                            ...item,
                            locations: event.target.value
                              .split(";")
                              .map((v) => v.trim())
                              .filter(Boolean),
                          }
                        : item,
                    ),
                  })
                }
              />
            </label>
            <Button
              variant="ghost"
              onClick={() =>
                onChange({
                  ...value,
                  salaryBands: bands.filter((_, i) => i !== index).length
                    ? bands.filter((_, i) => i !== index)
                    : null,
                })
              }
            >
              Remove salary band
            </Button>
          </div>
        ))}
        <Button
          variant="outline"
          onClick={() =>
            onChange({ ...value, salaryBands: [...bands, { rawText: "" }] })
          }
        >
          Add salary band
        </Button>
      </fieldset>
      <label className="space-y-1 text-sm sm:col-span-2">
        Full description
        <textarea
          className="block min-h-52 w-full rounded border bg-background p-2"
          value={value.jdText ?? ""}
          onChange={(event) =>
            onChange({ ...value, jdText: event.target.value || null })
          }
        />
      </label>
    </div>
  );
}
