/**
 * The browser is the authority for a user's current timezone.  API timestamps
 * are always explicit UTC instants; format them here instead of letting each
 * screen choose a mixture of UTC, an event's original timezone, or an implicit
 * local conversion.
 */

export type DateTimeValue = Date | number | string;

const FALLBACK_TIME_ZONE = "UTC";

export function userTimeZone(): string {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || FALLBACK_TIME_ZONE;
  } catch {
    return FALLBACK_TIME_ZONE;
  }
}

function asDate(value: DateTimeValue): Date {
  return value instanceof Date ? value : new Date(value);
}

export function formatDateTimeInTimeZone(
  value: DateTimeValue,
  timeZone: string,
  locale?: string,
  options?: Intl.DateTimeFormatOptions,
): string {
  return asDate(value).toLocaleString(locale, { ...options, timeZone });
}

export function formatDateInTimeZone(
  value: DateTimeValue,
  timeZone: string,
  locale?: string,
  options?: Intl.DateTimeFormatOptions,
): string {
  return asDate(value).toLocaleDateString(locale, { ...options, timeZone });
}

export function formatTimeInTimeZone(
  value: DateTimeValue,
  timeZone: string,
  locale?: string,
  options?: Intl.DateTimeFormatOptions,
): string {
  return asDate(value).toLocaleTimeString(locale, { ...options, timeZone });
}

export function formatUserDateTime(
  value: DateTimeValue,
  locale?: string,
  options?: Intl.DateTimeFormatOptions,
): string {
  return formatDateTimeInTimeZone(value, userTimeZone(), locale, options);
}

export function formatUserDate(
  value: DateTimeValue,
  locale?: string,
  options?: Intl.DateTimeFormatOptions,
): string {
  return formatDateInTimeZone(value, userTimeZone(), locale, options);
}

export function formatUserTime(
  value: DateTimeValue,
  locale?: string,
  options?: Intl.DateTimeFormatOptions,
): string {
  return formatTimeInTimeZone(value, userTimeZone(), locale, options);
}
