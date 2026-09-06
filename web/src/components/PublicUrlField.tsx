import {
  Field,
  FieldDescription,
  FieldError,
  FieldLabel,
} from "@/components/ui/field";
import { Input } from "@/components/ui/input";

export const MAX_PUBLIC_URL_LENGTH = 8_192;

export function isPublicHttpUrl(value: string): boolean {
  try {
    const url = new URL(value.trim());
    return url.protocol === "http:" || url.protocol === "https:";
  } catch {
    return false;
  }
}

export function PublicUrlField({
  id,
  label,
  value,
  placeholder,
  invalid = false,
  onBlur,
  onChange,
}: {
  id: string;
  label: string;
  value: string;
  placeholder: string;
  invalid?: boolean;
  onBlur?: () => void;
  onChange: (value: string) => void;
}) {
  const descriptionId = `${id}-description`;
  const errorId = `${id}-error`;

  return (
    <Field data-invalid={invalid || undefined}>
      <FieldLabel htmlFor={id}>{label}</FieldLabel>
      <Input
        id={id}
        type="url"
        inputMode="url"
        autoComplete="url"
        spellCheck={false}
        maxLength={MAX_PUBLIC_URL_LENGTH}
        value={value}
        placeholder={placeholder}
        aria-invalid={invalid || undefined}
        aria-describedby={`${descriptionId}${invalid ? ` ${errorId}` : ""}`}
        onBlur={onBlur}
        onChange={(event) => onChange(event.target.value)}
      />
      <FieldDescription id={descriptionId}>
        Use a direct, public http(s) link. Up to 8,192 characters.
      </FieldDescription>
      {invalid ? (
        <FieldError id={errorId}>Enter a complete http(s) URL.</FieldError>
      ) : null}
    </Field>
  );
}
