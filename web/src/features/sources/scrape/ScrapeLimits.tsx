import { Input } from "@/components/ui/input";
import type { CrawlLimits } from "./use-scrape";

export function ScrapeLimits({
  value,
  onChange,
}: {
  value: CrawlLimits;
  onChange: (value: CrawlLimits) => void;
}) {
  return (
    <fieldset className="grid gap-3 sm:grid-cols-3">
      <legend className="mb-2 text-sm font-medium">Crawl limits</legend>
      {(
        [
          ["listingPages", "Listing pages", 50, 10],
          ["detailPages", "Job details", 200, 50],
          ["elapsedSeconds", "Time limit (seconds)", 900, 300],
        ] as const
      ).map(([field, label, max, fallback]) => (
        <label key={field} className="space-y-1 text-sm">
          {label}
          <Input
            type="number"
            min={1}
            max={max}
            value={value[field] ?? fallback}
            onChange={(event) =>
              onChange({
                ...value,
                [field]: Math.max(1, Math.min(max, Number(event.target.value))),
              })
            }
          />
        </label>
      ))}
    </fieldset>
  );
}
