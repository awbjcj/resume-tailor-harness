import { useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  Mail,
  ShieldCheck,
  Bell,
  ListChecks,
  ChartNoAxesCombined,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import {
  Field,
  FieldContent,
  FieldDescription,
  FieldLabel,
} from "@/components/ui/field";
import { useDraft } from "../use-draft";
import {
  useEmailNotifications,
  EmailNotificationError,
  type EmailUpdate,
} from "../use-email-notifications";

const TOPICS = [
  { key: "pendingReviews", icon: ListChecks },
  { key: "statistics", icon: ChartNoAxesCombined },
  { key: "reminders", icon: Bell },
] as const;
const FREQUENCIES = ["daily", "weekly", "monthly"] as const;
const ERROR_KEYS = {
  INVALID_CODE: "emailNotifications.errors.invalidCode",
  RATE_LIMITED: "emailNotifications.errors.rateLimited",
  EMAIL_REQUIRED: "emailNotifications.errors.emailRequired",
  MAIL_UNAVAILABLE: "emailNotifications.errors.mailUnavailable",
  VALIDATION_ERROR: "emailNotifications.errors.validation",
} as const;

export function EmailNotificationsPage() {
  const { t, i18n } = useTranslation();
  const { query, save, sendCode, verify } = useEmailNotifications();
  const data = query.data;
  const { draft, setDraft, dirty } = useDraft<EmailUpdate>(
    data
      ? {
          email: data.email,
          enabled: data.enabled,
          frequency: data.frequency,
          pendingReviews: data.pendingReviews,
          statistics: data.statistics,
          reminders: data.reminders,
        }
      : undefined,
  );
  const codeInput = useRef<HTMLInputElement>(null);
  const [code, setCode] = useState("");
  const [feedbackKey, setFeedbackKey] = useState<
    "saved" | "codeSent" | "confirmed" | null
  >(null);
  const busy = save.isPending || sendCode.isPending || verify.isPending;
  const error = save.error || sendCode.error || verify.error;
  const errorKey = error instanceof EmailNotificationError
    ? ERROR_KEYS[error.code as keyof typeof ERROR_KEYS]
    : undefined;
  const resetFeedback = () => {
    setFeedbackKey(null);
    save.reset();
    sendCode.reset();
    verify.reset();
  };

  if (query.isError)
    return (
      <div role="alert">
        <p>{t("emailNotifications.loadError")}</p>
        <Button variant="outline" onClick={() => void query.refetch()}>
          {t("emailNotifications.retry")}
        </Button>
      </div>
    );
  if (!draft || !data)
    return <p role="status">{t("emailNotifications.loading")}</p>;

  const needsVerification = data.enabled && !data.verifiedAt;
  const savePreferences = (values: EmailUpdate) => {
    resetFeedback();
    save.mutate(values, {
      onSuccess: () => {
        setDraft(null);
        setCode("");
        setFeedbackKey("saved");
      },
    });
  };
  return (
    <div className="flex max-w-3xl flex-col gap-7">
      <header className="border-b pb-6">
        <h1 className="flex items-center gap-3 text-xl font-semibold tracking-tight">
          <Mail className="size-5" aria-hidden="true" />
          {t("emailNotifications.title")}
        </h1>
        <p className="mt-1 text-sm text-muted-foreground">
          {t("emailNotifications.description")}
        </p>
        <p className="mt-2 text-sm text-muted-foreground">
          {t("emailNotifications.languageHelp")}
        </p>
      </header>
      {!data.deliveryAvailable && (
        <p role="status" className="rounded-lg border bg-muted/50 p-4 text-sm">
          {t("emailNotifications.unavailable")}
        </p>
      )}
      {data.deliveryFailed && (
        <p role="status" className="text-sm text-destructive">
          {t("emailNotifications.deliveryFailed")}
        </p>
      )}
      <form
        className="flex flex-col gap-7"
        onSubmit={(event) => {
          event.preventDefault();
          savePreferences(draft);
        }}
      >
        <Field>
          <FieldLabel htmlFor="notification-email">
            {t("emailNotifications.email")}
          </FieldLabel>
          <Input
            id="notification-email"
            type="email"
            autoComplete="email"
            maxLength={254}
            required={draft.enabled}
            value={draft.email}
            disabled={busy}
            onChange={(event) => {
              resetFeedback();
              setDraft({ ...draft, email: event.target.value });
            }}
            aria-describedby="notification-email-help"
          />
          <FieldDescription id="notification-email-help">
            {t("emailNotifications.emailHelp")}
          </FieldDescription>
        </Field>
        <Field orientation="horizontal">
          <Switch
            id="notification-enabled"
            checked={draft.enabled}
            disabled={busy}
            onCheckedChange={(enabled) => {
              resetFeedback();
              setDraft({ ...draft, enabled });
            }}
          />
          <FieldContent>
            <FieldLabel htmlFor="notification-enabled">
              {t("emailNotifications.optIn")}
            </FieldLabel>
            <FieldDescription>
              {t("emailNotifications.optInHelp")}
            </FieldDescription>
          </FieldContent>
        </Field>
        <fieldset
          disabled={busy}
          aria-describedby="notification-frequency-help"
        >
          <legend className="mb-3 text-sm font-medium">
            {t("emailNotifications.frequency")}
          </legend>
          <div className="grid grid-cols-3 gap-2">
            {FREQUENCIES.map((frequency) => (
              <label key={frequency} className="relative cursor-pointer">
                <input
                  type="radio"
                  name="notification-frequency"
                  value={frequency}
                  checked={draft.frequency === frequency}
                  className="peer absolute inset-0 z-10 size-full cursor-pointer opacity-0 disabled:cursor-not-allowed"
                  onChange={() => {
                    resetFeedback();
                    setDraft({ ...draft, frequency });
                  }}
                />
                <span className="flex min-h-12 items-center justify-center rounded-lg border px-2 py-3 text-center text-sm font-medium peer-checked:border-primary peer-checked:bg-primary/5 peer-checked:text-primary peer-focus-visible:ring-2 peer-focus-visible:ring-ring peer-focus-visible:ring-offset-2 peer-disabled:cursor-not-allowed peer-disabled:opacity-50">
                  {t(`emailNotifications.${frequency}`)}
                </span>
              </label>
            ))}
          </div>
          <p
            id="notification-frequency-help"
            className="mt-3 text-sm leading-relaxed text-muted-foreground"
          >
            {t("emailNotifications.frequencyHelp")}
          </p>
        </fieldset>
        <fieldset disabled={busy}>
          <legend className="mb-3 text-sm font-medium">
            {t("emailNotifications.topics")}
          </legend>
          <div className="divide-y rounded-xl border px-4 sm:px-5">
            {TOPICS.map(({ key: topic, icon: Icon }) => (
              <Field
                orientation="horizontal"
                key={topic}
                className="gap-4 py-5"
              >
                <Icon
                  className="mt-0.5 size-5 shrink-0 text-muted-foreground"
                  aria-hidden="true"
                />
                <FieldContent>
                  <FieldLabel htmlFor={`email-${topic}`}>
                    {t(`emailNotifications.${topic}`)}
                  </FieldLabel>
                  <FieldDescription>
                    {t(`emailNotifications.${topic}Help`)}
                  </FieldDescription>
                </FieldContent>
                <Switch
                  id={`email-${topic}`}
                  checked={draft[topic]}
                  onCheckedChange={(value) => {
                    resetFeedback();
                    setDraft({ ...draft, [topic]: value });
                  }}
                />
              </Field>
            ))}
          </div>
        </fieldset>
        <div className="flex flex-wrap items-center gap-3 border-t pt-5">
          <Button
            type="submit"
            disabled={
              !dirty ||
              busy ||
              (draft.enabled &&
                !draft.pendingReviews &&
                !draft.statistics &&
                !draft.reminders)
            }
          >
            {t(
              save.isPending
                ? "emailNotifications.saving"
                : "emailNotifications.save",
            )}
          </Button>
          {data.enabled && (
            <Button
              type="button"
              variant="outline"
              disabled={busy}
              onClick={() =>
                savePreferences({
                  email: data.email,
                  enabled: false,
                  frequency: data.frequency,
                  pendingReviews: data.pendingReviews,
                  statistics: data.statistics,
                  reminders: data.reminders,
                })
              }
            >
              {t("emailNotifications.optOut")}
            </Button>
          )}
        </div>
      </form>
      <section
        className="space-y-4 rounded-xl border bg-muted/30 p-5 sm:p-6"
        aria-label={t("emailNotifications.verifyTitle")}
      >
        <p className="flex items-center gap-2 text-sm font-medium">
          {data.verifiedAt && (
            <ShieldCheck
              className="size-4 text-primary"
              aria-label={t("emailNotifications.verified")}
            />
          )}
          {t(
            !data.enabled
              ? "emailNotifications.off"
              : needsVerification
                ? "emailNotifications.pending"
                : "emailNotifications.active",
          )}
        </p>
        {needsVerification && (
          <>
            <p className="break-words text-sm leading-relaxed text-muted-foreground">
              {t("emailNotifications.verifyHelp", { email: data.email })}
            </p>
            {dirty && (
              <p className="text-sm">{t("emailNotifications.saveFirst")}</p>
            )}
            <Button
              variant="outline"
              disabled={busy || dirty || !data.deliveryAvailable}
              onClick={() => {
                resetFeedback();
                sendCode.mutate(undefined, {
                  onSuccess: () => {
                    setFeedbackKey("codeSent");
                    requestAnimationFrame(() => codeInput.current?.focus());
                  },
                });
              }}
            >
              {t(
                sendCode.isPending
                  ? "emailNotifications.sending"
                  : data.verificationPending
                    ? "emailNotifications.resendCode"
                    : "emailNotifications.sendCode",
              )}
            </Button>
            <form
              className="flex flex-wrap items-end gap-3"
              onSubmit={(event) => {
                event.preventDefault();
                resetFeedback();
                verify.mutate(
                  { email: data.email, code },
                  {
                    onSuccess: () => {
                      setCode("");
                      setFeedbackKey("confirmed");
                    },
                  },
                );
              }}
            >
              <Field className="max-w-xs">
                <FieldLabel htmlFor="notification-code">
                  {t("emailNotifications.code")}
                </FieldLabel>
                <Input
                  ref={codeInput}
                  className="font-mono text-lg tracking-[0.3em]"
                  id="notification-code"
                  inputMode="numeric"
                  autoComplete="one-time-code"
                  pattern="[0-9]{6}"
                  maxLength={6}
                  value={code}
                  disabled={busy || dirty}
                  onChange={(event) => {
                    resetFeedback();
                    setCode(event.target.value);
                  }}
                />
              </Field>
              <Button
                type="submit"
                disabled={busy || dirty || !/^[0-9]{6}$/.test(code)}
              >
                {t(
                  verify.isPending
                    ? "emailNotifications.verifying"
                    : "emailNotifications.confirm",
                )}
              </Button>
            </form>
          </>
        )}
        {data.enabled && data.verifiedAt && data.nextSendAt && (
          <p className="text-sm text-muted-foreground">
            {t("emailNotifications.nextSend", {
              date: new Date(data.nextSendAt).toLocaleString(i18n.language),
            })}
          </p>
        )}
        {data.lastSentAt && (
          <p className="text-sm text-muted-foreground">
            {t("emailNotifications.lastSent", {
              date: new Date(data.lastSentAt).toLocaleString(i18n.language),
            })}
          </p>
        )}
      </section>
      {feedbackKey && (
        <p role="status" className="text-sm text-primary">
          {t(`emailNotifications.${feedbackKey}`)}
        </p>
      )}
      {error && (
        <p role="alert" className="text-sm text-destructive">
          {(i18n.resolvedLanguage ?? i18n.language).startsWith("zh")
            ? t(errorKey ?? "emailNotifications.errors.unexpected")
            : error.message}
        </p>
      )}
    </div>
  );
}
