import { useLayoutEffect, useRef, useState, type ClipboardEvent, type KeyboardEvent } from "react";
import { Autocomplete } from "@base-ui/react/autocomplete";
import { Search, X } from "lucide-react";
import { useTranslation } from "react-i18next";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Field, FieldDescription, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import "@/i18n/tag-list-input";

export type TagOption = { value: string; label: string };

const separators = {
  comma: /[,，\r\n]+/,
  semicolon: /[;；\r\n]+/,
  newline: /[\r\n]+/,
};

export function TagListInput({
  id,
  label,
  value,
  onChange,
  placeholder,
  description,
  disabled = false,
  separator = "comma",
  suggestions,
  emptySuggestions,
  getKey = (tag) => tag,
  maxTags,
  validation,
}: {
  id: string;
  label: string;
  value: readonly string[];
  onChange: (next: string[]) => void;
  placeholder?: string;
  description?: string;
  disabled?: boolean;
  separator?: keyof typeof separators;
  suggestions?: readonly TagOption[];
  emptySuggestions?: string;
  getKey?: (tag: string) => string;
  maxTags?: number;
  validation?: { parse: (text: string) => string | null; message: string };
}) {
  const { t } = useTranslation();
  const inputRef = useRef<HTMLInputElement>(null);
  const searchActions = useRef<Autocomplete.Root.Actions>(null);
  const [draft, setDraft] = useState("");
  const [problem, setProblem] = useState<"invalid" | "limit" | "pending" | null>(null);
  const [announcement, setAnnouncement] = useState("");
  const selected = new Set(value.map(getKey));
  const tagLabels = new Map(suggestions?.map((option) => [getKey(option.value), option.label]));
  const available = suggestions?.filter((option) => !selected.has(getKey(option.value)));
  const searchable = suggestions !== undefined;
  const hasDraft = draft.trim().length > 0;
  const pendingMessage = t("tagList.pending");
  const error = problem === "limit"
    ? t("tagList.limit", { count: maxTags })
    : problem === "pending" ? pendingMessage
      : problem === "invalid" ? validation?.message : undefined;
  const descriptionId = description ? `${id}-help` : undefined;
  const errorId = error ? `${id}-error` : undefined;

  useLayoutEffect(() => {
    inputRef.current?.setCustomValidity(hasDraft ? pendingMessage : "");
  }, [hasDraft, pendingMessage, searchable]);

  function editDraft(text: string) {
    setDraft(text);
    setProblem(null);
    setAnnouncement("");
  }

  function addTags(rawValues: string[]) {
    if (disabled) return false;
    const seen = new Set(selected);
    const additions: string[] = [];
    for (const raw of rawValues) {
      const text = raw.trim();
      if (!text) continue;
      const tag = validation ? validation.parse(text) : text;
      if (tag === null) {
        setProblem("invalid");
        return false;
      }
      const key = getKey(tag);
      if (!seen.has(key)) {
        seen.add(key);
        additions.push(tag);
      }
    }
    if (maxTags !== undefined && additions.length && value.length + additions.length > maxTags) {
      setProblem("limit");
      return false;
    }
    editDraft("");
    searchActions.current?.close();
    if (additions.length) {
      onChange([...value, ...additions]);
      setAnnouncement(t("tagList.added", {
        values: additions.map((tag) => tagLabels.get(getKey(tag)) ?? tag).join(", "),
      }));
    } else if (rawValues.some((raw) => raw.trim())) {
      setAnnouncement(t("tagList.alreadyAdded"));
    }
    return true;
  }

  function addDraft() {
    addTags(draft.split(separators[separator]));
    inputRef.current?.focus();
  }

  function handleKeyDown(event: KeyboardEvent<HTMLInputElement>) {
    if (event.key !== "Enter" || event.nativeEvent.isComposing || event.keyCode === 229) return;
    // Leave Enter to the autocomplete when an option has keyboard focus.
    if (event.currentTarget.getAttribute("aria-expanded") === "true"
      && event.currentTarget.getAttribute("aria-activedescendant")) return;
    event.preventDefault();
    addDraft();
  }

  function handlePaste(event: ClipboardEvent<HTMLInputElement>) {
    const pasted = event.clipboardData.getData("text");
    if (!/[\r\n]/.test(pasted.trim())) return;
    // A single-line input strips newlines. Keep each line as a separate value.
    event.preventDefault();
    const input = event.currentTarget;
    const text = draft.slice(0, input.selectionStart ?? draft.length)
      + pasted
      + draft.slice(input.selectionEnd ?? draft.length);
    if (!addTags(text.split(separators[separator]))) {
      setDraft(text.replace(/[\r\n]+/g, separator === "semicolon" ? "; " : ", "));
    }
  }

  const inputProps = {
    id,
    ref: inputRef,
    disabled,
    placeholder,
    autoComplete: "off",
    "aria-describedby": [descriptionId, errorId].filter(Boolean).join(" ") || undefined,
    "aria-invalid": error ? true : undefined,
    "data-pending-tag": hasDraft || undefined,
    onInvalid: () => setProblem((current) => current ?? "pending"),
    onKeyDown: handleKeyDown,
    onPaste: handlePaste,
  };
  const InputRow = available ? Autocomplete.InputGroup : "div";
  const editor = (
    <InputRow className="grid min-w-0 grid-cols-[minmax(0,1fr)_auto] gap-2">
      {available ? (
        <div className="relative min-w-0">
          <Search aria-hidden="true" className="pointer-events-none absolute inset-y-0 left-3 my-auto size-4 text-muted-foreground" />
          <Autocomplete.Input
            {...inputProps}
            onBlur={() => searchActions.current?.close()}
            render={<Input className="min-h-11 pl-9" />}
          />
        </div>
      ) : (
        <Input {...inputProps} className="min-h-11" value={draft} onChange={(event) => editDraft(event.target.value)} />
      )}
      <Button
        type="button"
        variant="outline"
        size="lg"
        aria-label={t("tagList.addTo", { field: label })}
        disabled={disabled || !hasDraft}
        onClick={addDraft}
        className="cursor-pointer motion-reduce:transition-none"
      >
        {t("tagList.add")}
      </Button>
    </InputRow>
  );

  return (
    <Field className="min-w-0" data-slot="tag-list-input">
      <FieldLabel htmlFor={id} className="text-[0.95rem] leading-5 [overflow-wrap:anywhere]">{label}</FieldLabel>
      {available ? (
        <Autocomplete.Root<TagOption>
          items={available}
          filter={(item, query) => `${item.label} ${item.value}`.toLowerCase().includes(query.trim().toLowerCase())}
          limit={30}
          value={draft}
          disabled={disabled}
          openOnInputClick
          actionsRef={searchActions}
          onOpenChange={(open, details) => {
            if (!open) {
              details.preventUnmountOnClose();
              searchActions.current?.unmount();
            }
          }}
          onValueChange={(text, details) => {
            if (details.reason === "input-change") editDraft(text);
          }}
        >
          {editor}
          <Autocomplete.Portal>
            <Autocomplete.Positioner
              sideOffset={4}
              align="start"
              className="z-50 w-[var(--anchor-width)] min-w-44 max-w-[calc(100vw-2rem)] data-closed:hidden"
            >
              {/* Use a nonmodal list so assistive technology can reach Add while searching. */}
              <div className="max-h-[min(15rem,var(--available-height))] overflow-y-auto overscroll-contain rounded-lg border bg-popover p-1 text-sm text-popover-foreground shadow-card-raised">
                <Autocomplete.Empty className="px-2.5 py-2 text-muted-foreground empty:hidden">
                  {emptySuggestions ?? t("tagList.noMatches")}
                </Autocomplete.Empty>
                <Autocomplete.List aria-label={t("tagList.suggestions", { field: label })}>
                  {(option: TagOption, index) => (
                    <Autocomplete.Item
                      key={option.value}
                      value={option}
                      index={index}
                      onClick={() => addTags([option.value])}
                      className="min-h-11 cursor-pointer content-center rounded-md px-2.5 py-2 [overflow-wrap:anywhere] data-highlighted:bg-accent data-highlighted:text-accent-foreground"
                    >
                      {option.label}
                    </Autocomplete.Item>
                  )}
                </Autocomplete.List>
              </div>
            </Autocomplete.Positioner>
          </Autocomplete.Portal>
        </Autocomplete.Root>
      ) : editor}
      {value.length > 0 && (
        <ul role="list" className="flex min-w-0 flex-wrap gap-2">
          {value.map((tag, index) => {
            const text = tagLabels.get(getKey(tag)) ?? tag;
            return (
              <li key={`${tag}-${index}`} className="min-w-0 max-w-full">
                <Badge variant="secondary" className="h-auto min-h-8 max-w-full gap-1.5 overflow-visible py-0.5 pl-2.5 pr-1 text-sm leading-5 whitespace-normal">
                  <span className="min-w-0 [overflow-wrap:anywhere]">{text}</span>
                  <Button
                    type="button"
                    size="icon-xs"
                    variant="ghost"
                    aria-label={t("tagList.remove", { value: text })}
                    className="size-7 cursor-pointer rounded-full hover:bg-background/70 hover:text-destructive pointer-coarse:size-11 motion-reduce:transition-none"
                    disabled={disabled}
                    onClick={(event) => {
                      inputRef.current?.focus({ preventScroll: event.detail > 0 });
                      onChange(value.filter((_, i) => i !== index));
                      setProblem(null);
                      setAnnouncement(t("tagList.removed", { value: text }));
                    }}
                  >
                    <X aria-hidden="true" className="size-3.5" />
                  </Button>
                </Badge>
              </li>
            );
          })}
        </ul>
      )}
      {description && <FieldDescription id={descriptionId}>{description}</FieldDescription>}
      {error && <p id={errorId} role="alert" className="text-sm text-destructive">{error}</p>}
      <span aria-live="polite" aria-atomic="true" className="sr-only">{announcement}</span>
    </Field>
  );
}
