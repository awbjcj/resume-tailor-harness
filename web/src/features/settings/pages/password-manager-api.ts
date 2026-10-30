import type { components } from "@/lib/api/schema";
import type { passwordManagerEn } from "@/i18n/password-manager";

export type ApplicationAccount = components["schemas"]["AccountOut"];

export type AccountErrorKey = `passwordManager.${keyof typeof passwordManagerEn}`;

export class AccountError extends Error {
  readonly key: AccountErrorKey;

  constructor(key: AccountErrorKey) {
    super(key);
    this.key = key;
  }
}

export function accountErrorKey(error: unknown): AccountErrorKey {
  return error instanceof AccountError ? error.key : "passwordManager.saveError";
}

const errorKeys: Record<string, AccountErrorKey> = {
  ACCOUNT_STALE: "passwordManager.staleError",
  VAULT_STALE: "passwordManager.staleError",
  ACCOUNT_EXISTS: "passwordManager.duplicateError",
  NOT_FOUND: "passwordManager.missingError",
  INVALID_LOGIN_URL: "passwordManager.urlError",
  COMPANY_REQUIRED: "passwordManager.companyError",
  USERNAME_REQUIRED: "passwordManager.usernameError",
  VALIDATION_ERROR: "passwordManager.validationError",
  VAULT_FULL: "passwordManager.capacityError",
  VAULT_BUSY: "passwordManager.busyError",
  VAULT_UNAVAILABLE: "passwordManager.vaultError",
  VAULT_UNREADABLE: "passwordManager.vaultError",
};

/** Keep server text and credential request bodies out of UI errors and caches. */
export async function accountRequest<T>(request: Promise<{ data?: T; error?: unknown }>): Promise<T> {
  let result;
  try {
    result = await request;
  } catch {
    throw new AccountError("passwordManager.saveError");
  }
  if (result.error) {
    const envelope = result.error as { error?: { code?: string } };
    const key = errorKeys[envelope.error?.code ?? ""] ?? "passwordManager.saveError";
    throw new AccountError(key);
  }
  return result.data as T;
}
