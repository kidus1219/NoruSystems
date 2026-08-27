import { useState } from "react";

/** Calendar date in the local zone.
 *  Not toISOString(), that converts to UTC first and lands on the wrong day. */
export const iso = (date: Date) =>
  `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;

export const shift = (isoDate: string, days: number) => {
  const date = new Date(`${isoDate}T00:00:00`);
  date.setDate(date.getDate() + days);
  return iso(date);
};

export const today = () => iso(new Date());

/** Monday of the week the date falls in. */
export const startOfWeek = (isoDate: string) => {
  const date = new Date(`${isoDate}T00:00:00`);
  const offset = (date.getDay() + 6) % 7;
  date.setDate(date.getDate() - offset);
  return iso(date);
};

export const formatDate = (isoDate: string, options: Intl.DateTimeFormatOptions = { day: "numeric", month: "short" }) =>
  new Date(`${isoDate}T00:00:00`).toLocaleDateString(undefined, options);

export const formatTime = (value: string | null) =>
  value ? new Date(value).toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" }) : "—";

export const clock = (value: string) => value.slice(0, 5);

/** Date range used by the report screens. */
export function usePeriod(days = 27) {
  const end = today();
  const [period, setPeriod] = useState({ start: shift(end, -days), end });
  return {
    period,
    setStart: (start: string) => setPeriod((current) => ({ ...current, start })),
    setEnd: (value: string) => setPeriod((current) => ({ ...current, end: value })),
  };
}
