/**
 * Date formatting utilities for consistent timestamp display.
 * 
 * All timestamps from the API are in UTC (ISO 8601 Z format).
 * These utilities render them in the viewer's local timezone.
 */

/**
 * Format ISO Z timestamp in viewer's local timezone.
 * 
 * @param iso - ISO 8601 Z timestamp (e.g., "2025-10-27T02:56:54Z")
 * @returns Formatted string in viewer's local timezone
 * 
 * @example
 * formatLocal("2025-10-27T02:56:54Z")
 * // In Central Time (UTC-5): "Oct 26, 2025 9:56 PM"
 * // In Eastern Time (UTC-4): "Oct 26, 2025 10:56 PM"
 */
export function formatLocal(iso: string): string {
  try {
    return new Date(iso).toLocaleString(undefined, {
      year: "numeric",
      month: "short",
      day: "2-digit",
      hour: "numeric",
      minute: "2-digit",
      hour12: true,
    });
  } catch {
    return iso;
  }
}

/**
 * Format ISO Z timestamp as short date (no time).
 * 
 * @param iso - ISO 8601 Z timestamp
 * @returns Short date string (e.g., "Oct 26, 2025")
 */
export function formatLocalDate(iso: string): string {
  try {
    return new Date(iso).toLocaleDateString(undefined, {
      year: "numeric",
      month: "short",
      day: "2-digit",
    });
  } catch {
    return iso;
  }
}

/**
 * Format ISO Z timestamp as relative time (e.g., "2 hours ago").
 * 
 * @param iso - ISO 8601 Z timestamp
 * @returns Relative time string
 */
export function formatRelative(iso: string): string {
  try {
    const date = new Date(iso);
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffMins = Math.floor(diffMs / 60000);
    const diffHours = Math.floor(diffMs / 3600000);
    const diffDays = Math.floor(diffMs / 86400000);

    if (diffMins < 1) return "just now";
    if (diffMins < 60) return `${diffMins} minute${diffMins !== 1 ? "s" : ""} ago`;
    if (diffHours < 24) return `${diffHours} hour${diffHours !== 1 ? "s" : ""} ago`;
    if (diffDays < 7) return `${diffDays} day${diffDays !== 1 ? "s" : ""} ago`;
    
    return formatLocalDate(iso);
  } catch {
    return iso;
  }
}

/**
 * Get start and end of current month in viewer's local timezone,
 * converted to UTC ISO strings for API filtering.
 * 
 * @returns Object with startIsoUtc and endIsoUtc
 * 
 * @example
 * const { startIsoUtc, endIsoUtc } = getLocalMTDRange()
 * fetch(`/api/ads/cards?start=${startIsoUtc}&end=${endIsoUtc}`)
 */
export function getLocalMTDRange(): { startIsoUtc: string; endIsoUtc: string } {
  const now = new Date();
  const startLocal = new Date(now.getFullYear(), now.getMonth(), 1, 0, 0, 0);
  const endLocal = now;

  return {
    startIsoUtc: startLocal.toISOString(),
    endIsoUtc: endLocal.toISOString(),
  };
}

/**
 * Get start and end of current year in viewer's local timezone,
 * converted to UTC ISO strings for API filtering.
 * 
 * @returns Object with startIsoUtc and endIsoUtc
 */
export function getLocalYTDRange(): { startIsoUtc: string; endIsoUtc: string } {
  const now = new Date();
  const startLocal = new Date(now.getFullYear(), 0, 1, 0, 0, 0);
  const endLocal = now;

  return {
    startIsoUtc: startLocal.toISOString(),
    endIsoUtc: endLocal.toISOString(),
  };
}

/**
 * Get custom date range in viewer's local timezone,
 * converted to UTC ISO strings for API filtering.
 * 
 * @param startDate - Start date (YYYY-MM-DD)
 * @param endDate - End date (YYYY-MM-DD)
 * @returns Object with startIsoUtc and endIsoUtc
 */
export function getLocalCustomRange(
  startDate: string,
  endDate: string
): { startIsoUtc: string; endIsoUtc: string } {
  const [startYear, startMonth, startDay] = startDate.split("-").map(Number);
  const [endYear, endMonth, endDay] = endDate.split("-").map(Number);

  const startLocal = new Date(startYear, startMonth - 1, startDay, 0, 0, 0);
  const endLocal = new Date(endYear, endMonth - 1, endDay, 23, 59, 59);

  return {
    startIsoUtc: startLocal.toISOString(),
    endIsoUtc: endLocal.toISOString(),
  };
}
