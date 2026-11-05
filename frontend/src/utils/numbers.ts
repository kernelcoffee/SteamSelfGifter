/**
 * Parse the text of a number field: the integer it holds when that integer
 * lies in [min, max] (max optional), otherwise null. An empty or partly typed
 * field is null, never 0, so a cleared input can block saving instead of
 * silently sending a different value.
 */
export function parseBoundedInt(text: string, min: number, max?: number): number | null {
  const trimmed = text.trim();
  if (!/^\d+$/.test(trimmed)) return null;
  const value = Number(trimmed);
  if (!Number.isSafeInteger(value) || value < min) return null;
  if (max !== undefined && value > max) return null;
  return value;
}

/** English ordinal of a positive integer: 1st, 2nd, 3rd, 4th, 11th, 22nd. */
export function ordinal(n: number): string {
  const lastTwo = n % 100;
  if (lastTwo >= 11 && lastTwo <= 13) return `${n}th`;
  switch (n % 10) {
    case 1:
      return `${n}st`;
    case 2:
      return `${n}nd`;
    case 3:
      return `${n}rd`;
    default:
      return `${n}th`;
  }
}
