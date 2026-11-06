import "@/i18n/long-list-copy";
import { useRef, type ComponentProps } from "react";
import { Search, X } from "lucide-react";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";

export function ListSearch({
  value,
  onChange,
  className,
  ...props
}: Omit<ComponentProps<typeof Input>, "value" | "onChange"> & {
  value: string;
  onChange: (value: string) => void;
}) {
  const { t } = useTranslation();
  const input = useRef<HTMLInputElement>(null);
  return (
    <div className={cn("relative min-w-0", className)}>
      <Search aria-hidden className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
      <Input
        ref={input}
        inputMode="search"
        autoComplete="off"
        className={cn("h-11 pl-9", value && "pr-12")}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        {...props}
      />
      {value && !props.disabled ? (
        <Button
          type="button"
          variant="ghost"
          size="icon"
          className="absolute right-0 top-0 size-11"
          aria-label={t("longLists.clearSearch")}
          onClick={() => {
            onChange("");
            input.current?.focus();
          }}
        >
          <X aria-hidden />
        </Button>
      ) : null}
    </div>
  );
}
