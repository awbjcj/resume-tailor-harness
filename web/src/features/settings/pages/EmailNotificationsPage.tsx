import { useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  ShieldCheck,
  Bell,
  ListChecks,
  ChartNoAxesCombined,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Input } from "@/components/ui/input";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { Spinner } from "@/components/ui/spinner";
import { Switch } from "@/components/ui/switch";
import {
  Field,
  FieldContent,
  FieldDescription,
  FieldGroup,
  FieldLabel,
  FieldLegend,
  FieldSet,
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
    <div className="flex flex-col gap-6">
      <header className="space-y-1">
        <h1 className="text-lg font-semibold">
          {t("emailNotifications.title")}
        </h1>
        <p className="text-sm text-muted-foreground">
          {t("emailNotifications.description")}
        </p>
        <p className="text-sm text-muted-foreground">
          {t("emailNotifications.languageHelp")}
        </p>
      </header>
      {!data.deliveryAvailable && (
        <Alert role="status">
          <AlertDescription>{t("emailNotifications.unavailable")}</AlertDescription>
        </Alert>
      )}
      {data.deliveryFailed && (
        <Alert role="status" variant="destructive">
          <AlertDescription>{t("emailNotifications.deliveryFailed")}</AlertDescription>
        </Alert>
      )}
      <form
        className="flex flex-col gap-6"
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
        <FieldSet
          disabled={busy}
          aria-describedby="notification-frequency-help"
        >
          <FieldLegend variant="label">
            {t("emailNotifications.frequency")}
          </FieldLegend>
          <RadioGroup
            name="notification-frequency"
            value={draft.frequency}
            disabled={busy}
            aria-label={t("emailNotifications.frequency")}
            aria-describedby="notification-frequency-help"
            className="flex flex-wrap gap-x-6 gap-y-2"
            onValueChange={(frequency) => {
              const selected = FREQUENCIES.find((option) => option === frequency);
              if (!selected) return;
              resetFeedback();
              setDraft({ ...draft, frequency: selected });
            }}
          >
            {FREQUENCIES.map((frequency) => (
              <Field key={frequency} orientation="horizontal" className="w-auto gap-2 py-1">
                <RadioGroupItem id={`notification-${frequency}`} value={frequency} />
                <FieldLabel htmlFor={`notification-${frequency}`}>
                  {t(`emailNotifications.${frequency}`)}
                </FieldLabel>
              </Field>
            ))}
          </RadioGroup>
          <FieldDescription id="notification-frequency-help">
            {t("emailNotifications.frequencyHelp")}
          </FieldDescription>
        </FieldSet>
        <FieldSet disabled={busy}>
          <FieldLegend>
            {t("emailNotifications.topics")}
          </FieldLegend>
          <FieldGroup className="gap-0 divide-y">
            {TOPICS.map(({ key: topic, icon: Icon }) => (
              <Field
                orientation="horizontal"
                key={topic}
                className="gap-3 py-4 first:pt-0 last:pb-0"
              >
                <Icon
                  className="mt-0.5 size-4 shrink-0 text-muted-foreground"
                  aria-hidden="true"
                />
                <FieldContent className="min-w-0">
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
                  disabled={busy}
                  onCheckedChange={(value) => {
                    resetFeedback();
                    setDraft({ ...draft, [topic]: value });
                  }}
                />
              </Field>
            ))}
          </FieldGroup>
        </FieldSet>
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
            {save.isPending && <Spinner className="motion-reduce:animate-none" data-icon="inline-start" />}
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
        className="space-y-4 border-t pt-6"
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
              {sendCode.isPending && <Spinner className="motion-reduce:animate-none" data-icon="inline-start" />}
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
                {verify.isPending && <Spinner className="motion-reduce:animate-none" data-icon="inline-start" />}
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
        <Alert role="status">
          <AlertDescription>{t(`emailNotifications.${feedbackKey}`)}</AlertDescription>
        </Alert>
      )}
      {error && (
        <Alert variant="destructive">
          <AlertDescription>
            {(i18n.resolvedLanguage ?? i18n.language).startsWith("zh")
              ? t(errorKey ?? "emailNotifications.errors.unexpected")
              : error.message}
          </AlertDescription>
        </Alert>
      )}
    </div>
  );
}
