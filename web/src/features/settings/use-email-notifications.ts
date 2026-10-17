import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, unwrap } from "@/lib/api/client";
import type { components } from "@/lib/api/schema";

export type EmailPreferences = components["schemas"]["EmailNotificationOut"];
export type EmailUpdate = components["schemas"]["EmailNotificationUpdate"];
const KEY = ["email-notification-preferences"];

export function useEmailNotifications() {
  const queryClient = useQueryClient();
  const refresh = () => queryClient.invalidateQueries({ queryKey: KEY });
  const query = useQuery({ queryKey: KEY, queryFn: () => unwrap(api.GET("/api/email-notifications")) });
  const save = useMutation({
    mutationFn: (body: EmailUpdate) => unwrap(api.PUT("/api/email-notifications", { body })),
    onSuccess: (data) => queryClient.setQueryData(KEY, data),
  });
  const sendCode = useMutation({
    mutationFn: () => unwrap(api.POST("/api/email-notifications/verification")),
    onSettled: refresh,
  });
  const verify = useMutation({
    mutationFn: (body: { email: string; code: string }) => unwrap(api.POST("/api/email-notifications/verify", { body })),
    onSuccess: (data) => queryClient.setQueryData(KEY, data),
    onSettled: refresh,
  });
  return { query, save, sendCode, verify };
}
