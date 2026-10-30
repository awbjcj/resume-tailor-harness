import type { TFunction } from "i18next";
import { ApiError } from "@/lib/api/client";

const messages = {
  MAILBOX_BUSY: "mailboxes.busy",
  MAILBOX_LIMIT: "mailboxes.limit",
  MAILBOX_CREDENTIALS: "mailboxes.credentialsError",
  MAILBOX_FOLDER: "mailboxes.folderError",
  MAILBOX_PROVIDER_RESPONSE: "mailboxes.providerError",
  MAILBOX_RECONNECT: "mailboxes.needsReconnect",
  VALIDATION_ERROR: "mailboxes.validationError",
} as const;

export function mailboxErrorMessage(error: Error, t: TFunction, language: string) {
  const key = error instanceof ApiError && Object.hasOwn(messages, error.code) ? messages[error.code as keyof typeof messages] : undefined;
  return key ? t(key) : language.startsWith("zh") ? t("mailboxes.error") : error.message;
}

const fieldLabels = {
  email: "mailboxes.email", folder: "mailboxes.folder", host: "mailboxes.host",
  port: "mailboxes.port", security: "mailboxes.security", username: "mailboxes.username", password: "mailboxes.password",
} as const;

export function mailboxFieldLabel(path: string, t: TFunction) {
  const field = path.split(".").at(-1) as keyof typeof fieldLabels;
  return t(fieldLabels[field] ?? "mailboxes.checkField");
}

export function mailboxErrorFields(error: Error | null): string[] {
  if (!(error instanceof ApiError) || !Array.isArray(error.details)) return [];
  return [...new Set(error.details.flatMap((detail: unknown) => {
    if (!detail || typeof detail !== "object" || !("loc" in detail) || !Array.isArray(detail.loc)) return [];
    const path = detail.loc.slice(1).join(".");
    return /^(email|folder|(imap|smtp)\.(host|port|security|username|password))$/.test(path) ? [path] : [];
  }))];
}
