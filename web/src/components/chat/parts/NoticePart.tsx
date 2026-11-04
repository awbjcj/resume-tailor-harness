import { TriangleAlert } from "lucide-react";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

type NoticeLocalizer = typeof import("@/i18n/notice-labels").localizeNotice;

export function NoticePart({ message }: { message: string }) {
  const { i18n } = useTranslation();
  const [localize, setLocalize] = useState<NoticeLocalizer | null>(null);
  useEffect(() => {
    let active = true;
    void import("@/i18n/notice-labels").then(
      (module) => { if (active) setLocalize(() => module.localizeNotice); },
      () => { /* Keep the original notice if the optional translation cannot load. */ },
    );
    return () => { active = false; };
  }, []);
  return (
    <p
      data-testid="chat-part-notice"
      className="tone-panel flex items-start gap-2 rounded-lg p-2.5 text-xs leading-relaxed"
      data-tone="warning"
    >
      <TriangleAlert className="tone-accent mt-0.5 size-3.5 shrink-0" aria-hidden="true" />
      <span>{localize?.(message, i18n.resolvedLanguage) ?? message}</span>
    </p>
  );
}
