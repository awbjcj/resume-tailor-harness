import { useId, useState } from "react";
import { useTranslation } from "react-i18next";

import { TagListInput } from "@/components/ui/tag-list-input";
import { useApplications } from "@/features/applications/use-applications";

function parseOfferId(text: string) {
  const id = Number(text.replace(/^#/, ""));
  return /^#?\d+$/.test(text) && Number.isSafeInteger(id) && id > 0 ? String(id) : null;
}

export function CareerLabOfferReferences({
  value,
  onChange,
}: {
  value: number[];
  onChange: (next: number[]) => void;
}) {
  const { t } = useTranslation();
  const id = useId();
  const [open, setOpen] = useState(false);
  const applications = useApplications(open);
  const rows = applications.data?.rows ?? [];
  const suggestions = rows.flatMap((row) => {
    if (row.status !== "offer" || row.applicationId == null) return [];
    return [{
      value: String(row.applicationId),
      label: [row.company, row.title, `#${row.applicationId}`].filter(Boolean).join(" · "),
    }];
  });
  const validateOfferId = (text: string) => {
    const id = parseOfferId(text);
    if (!id || rows.some((row) => row.applicationId === Number(id) && row.status !== "offer")) return null;
    return id;
  };
  const emptyMessage = applications.isFetching
    ? t("tagList.offers.loading")
    : applications.isError
      ? t("tagList.offers.unavailable")
      : !suggestions.length ? t("tagList.offers.empty") : undefined;

  return (
    <details
      className="rounded-lg border bg-muted/20 p-3"
      onToggle={(event) => setOpen(event.currentTarget.open)}
    >
      <summary className="cursor-pointer text-sm font-medium">{t("tagList.offers.heading")}</summary>
      <div className="mt-4">
        <TagListInput
          id={id}
          label={t("tagList.offers.label")}
          placeholder={t("tagList.offers.search")}
          description={t("tagList.offers.help")}
          value={value.map(String)}
          onChange={(next) => onChange(next.map(Number))}
          suggestions={suggestions}
          emptySuggestions={emptyMessage}
          maxTags={10}
          validation={{ parse: validateOfferId, message: t("tagList.offers.invalid") }}
        />
      </div>
    </details>
  );
}
