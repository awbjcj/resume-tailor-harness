import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "@/lib/api/client";
import type { components } from "@/lib/api/schema";

export type EmailPreferences = components["schemas"]["EmailNotificationOut"];
export type EmailUpdate = components["schemas"]["EmailNotificationUpdate"];
const KEY = ["email-notification-preferences"];

export class EmailNotificationError extends Error {
  readonly code: string;

  constructor(code: string, message: string) {
    super(message);
    this.code = code;
  }
}

async function unwrapEmail<T>(
  request: Promise<{ data?: T; error?: unknown }>,
): Promise<T> {
  const { data, error } = await request;
  if (error) {
    const envelope = error as { error?: { code: string; message: string } };
    throw new EmailNotificationError(
      envelope.error?.code ?? "UNKNOWN",
      envelope.error?.message ?? "Request failed",
    );
  }
  return data as T;
}

export function useEmailNotifications() {
  const queryClient = useQueryClient();
  const refresh = () => queryClient.invalidateQueries({ queryKey: KEY });
  const query = useQuery({ queryKey: KEY, queryFn: () => unwrapEmail(api.GET("/api/email-notifications")) });
  const save = useMutation({
    mutationFn: (body: EmailUpdate) => unwrapEmail(api.PUT("/api/email-notifications", { body })),
    onSuccess: (data) => queryClient.setQueryData(KEY, data),
  });
  const sendCode = useMutation({
    mutationFn: () => unwrapEmail(api.POST("/api/email-notifications/verification")),
    onSettled: refresh,
  });
  const verify = useMutation({
    mutationFn: (body: { email: string; code: string }) => unwrapEmail(api.POST("/api/email-notifications/verify", { body })),
    onSuccess: (data) => queryClient.setQueryData(KEY, data),
    onSettled: refresh,
  });
  return { query, save, sendCode, verify };
}
