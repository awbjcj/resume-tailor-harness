import { Languages } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useEffect, useRef } from "react";
import { toast } from "sonner";
import { api, unwrap } from "@/lib/api/client";

import {
  changeLanguage,
  normalizeLanguage,
  type SupportedLanguage,
} from "@/i18n";

const languageOptions: {
  value: SupportedLanguage;
  labelKey: "common.english" | "common.chinese";
}[] = [
  { value: "en", labelKey: "common.english" },
  { value: "zh-CN", labelKey: "common.chinese" },
];

export function LanguageSwitcher({ persist = false }: { persist?: boolean }) {
  const { t, i18n } = useTranslation();
  const lastQueuedLanguage = useRef<SupportedLanguage | null>(null);
  const pendingSaves = useRef(Promise.resolve());
  const mounted = useRef(false);
  const currentLanguage = normalizeLanguage(i18n.resolvedLanguage ?? i18n.language) ?? "en";

  useEffect(() => {
    if (!persist) return;
    mounted.current = true;
    const save = (language: string) => {
      const normalized = normalizeLanguage(language) ?? "en";
      if (lastQueuedLanguage.current === normalized) return;
      lastQueuedLanguage.current = normalized;
      // Serialize quick toggles so a slower earlier save cannot win.
      pendingSaves.current = pendingSaves.current.then(async () => {
        if (!mounted.current) return;
        try {
          await unwrap(api.PUT("/api/config/language", { body: { language: normalized } }));
        } catch {
          if (lastQueuedLanguage.current === normalized) lastQueuedLanguage.current = null;
          if (mounted.current) toast.error(i18n.t("emailNotifications.languageSaveError"));
        }
      });
    };
    save(i18n.resolvedLanguage ?? i18n.language);
    i18n.on("languageChanged", save);
    return () => { mounted.current = false; i18n.off("languageChanged", save); };
  }, [i18n, persist]);

  return (
    <label className="relative inline-flex shrink-0 items-center">
      <span className="sr-only">{t("common.language")}</span>
      <Languages
        className="pointer-events-none absolute left-2.5 size-4 text-muted-foreground"
        aria-hidden="true"
      />
      <select
        className="h-10 appearance-none rounded-lg border border-transparent bg-transparent py-1 pl-8 pr-2 text-sm font-medium text-foreground outline-none transition-colors hover:bg-muted focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50"
        aria-label={t("common.language")}
        value={currentLanguage}
        onChange={(event) => void changeLanguage(event.target.value as SupportedLanguage)}
      >
        {languageOptions.map((option) => (
          <option key={option.value} value={option.value} lang={option.value}>
            {t(option.labelKey)}
          </option>
        ))}
      </select>
    </label>
  );
}
