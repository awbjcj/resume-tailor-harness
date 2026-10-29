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
import { Separator } from "@/components/ui/separator";
import { Skeleton } from "@/components/ui/skeleton";
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
import { SaveBar } from "../SaveBar";
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

export function EmailNotificationsPage({ embedded = false }: { embedded?: boolean }) {
  const HeadingTag = embedded ? "h2" : "h1";
  const StatusHeadingTag = embedded ? "h3" : "h2";
  const { t, i18n } = useTranslation();
  const { query, save, sendCode, verify } = useEmailNotifications();
  const data = query.data;
  const { draft, setDraft, dirty, reset } = useDraft<EmailUpdate>(
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
  const preferencesForm = useRef<HTMLFormElement>(null);
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
      <Alert variant="destructive">
        <AlertDescription>
          <p>{t("emailNotifications.loadError")}</p>
          <Button variant="outline" onClick={() => void query.refetch()}>
            {t("emailNotifications.retry")}
          </Button>
        </AlertDescription>
      </Alert>
    );
  if (!draft || !data)
    return (
      <div role="status" aria-label={t("emailNotifications.loading")}>
        <Skeleton className="h-64 w-full motion-reduce:animate-none" />
      </div>
    );

  const needsVerification = data.enabled && !data.verifiedAt;
  const canSave = !draft.enabled || draft.pendingReviews || draft.statistics || draft.reminders;
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
        <HeadingTag className="text-lg font-semibold">
          {t("emailNotifications.title")}
        </HeadingTag>
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
        ref={preferencesForm}
        className="flex flex-col gap-6"
        aria-busy={save.isPending}
        onSubmit={(event) => {
          event.preventDefault();
          if (dirty && !busy && canSave) savePreferences(draft);
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
          <FieldContent className="min-w-0">
            <FieldLabel htmlFor="notification-enabled">
              {t("emailNotifications.optIn")}
            </FieldLabel>
            <FieldDescription id="notification-enabled-help">
              {t("emailNotifications.optInHelp")}
            </FieldDescription>
          </FieldContent>
          <Switch
            id="notification-enabled"
            checked={draft.enabled}
            disabled={busy}
            aria-describedby="notification-enabled-help"
            onCheckedChange={(enabled) => {
              resetFeedback();
              setDraft({ ...draft, enabled });
            }}
          />
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
                  <FieldDescription id={`email-${topic}-help`}>
                    {t(`emailNotifications.${topic}Help`)}
                  </FieldDescription>
                </FieldContent>
                <Switch
                  id={`email-${topic}`}
                  checked={draft[topic]}
                  disabled={busy}
                  aria-describedby={`email-${topic}-help`}
                  onCheckedChange={(value) => {
                    resetFeedback();
                    setDraft({ ...draft, [topic]: value });
                  }}
                />
              </Field>
            ))}
          </FieldGroup>
        </FieldSet>
      </form>
      <Separator />
      <section
        className="flex min-w-0 flex-col gap-4"
        aria-labelledby="notification-delivery-title"
      >
        <div className="flex flex-wrap items-center justify-between gap-3">
          <StatusHeadingTag id="notification-delivery-title" className="text-sm font-medium">
            {t(needsVerification ? "emailNotifications.verifyTitle" : "emailNotifications.deliveryStatus")}
          </StatusHeadingTag>
          {data.enabled && (
            <Button
              type="button"
              variant="outline"
              size="sm"
              disabled={busy}
              onClick={() => savePreferences({
                email: data.email,
                enabled: false,
                frequency: data.frequency,
                pendingReviews: data.pendingReviews,
                statistics: data.statistics,
                reminders: data.reminders,
              })}
            >
              {t("emailNotifications.optOut")}
            </Button>
          )}
        </div>
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
              className="w-fit max-w-full"
              aria-busy={sendCode.isPending}
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
              {sendCode.isPending && <Spinner aria-hidden="true" className="motion-reduce:animate-none" data-icon="inline-start" />}
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
              aria-busy={verify.isPending}
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
                  aria-invalid={verify.error instanceof EmailNotificationError && verify.error.code === "INVALID_CODE"}
                  aria-describedby={verify.error ? "notification-error" : undefined}
                  onChange={(event) => {
                    resetFeedback();
                    setCode(event.target.value);
                  }}
                />
              </Field>
              <Button
                type="submit"
                aria-busy={verify.isPending}
                disabled={busy || dirty || !/^[0-9]{6}$/.test(code)}
              >
                {verify.isPending && <Spinner aria-hidden="true" className="motion-reduce:animate-none" data-icon="inline-start" />}
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
        <Alert id="notification-error" variant="destructive">
          <AlertDescription>
            {(i18n.resolvedLanguage ?? i18n.language).startsWith("zh")
              ? t(errorKey ?? "emailNotifications.errors.unexpected")
              : error.message}
          </AlertDescription>
        </Alert>
      )}
      <SaveBar
        dirty={dirty}
        saving={busy}
        canSave={canSave}
        onSave={() => preferencesForm.current?.requestSubmit()}
        onDiscard={() => {
          reset();
          setCode("");
          resetFeedback();
        }}
      />
    </div>
  );
}
