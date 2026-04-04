/**
 * utils/format.js
 * Lightweight formatting helpers.
 */

import { format, formatDistanceToNow } from 'date-fns';

/** 1.2 → "1.2 mm" */
export const fmtMm = (v, dp = 1) =>
  v == null ? '—' : `${Number(v).toFixed(dp)} mm`;

/** 0.923 → "92.3 %" */
export const fmtPct = (v, dp = 1) =>
  v == null ? '—' : `${(Number(v) * 100).toFixed(dp)} %`;

/** ISO timestamp → "14:32:07" */
export const fmtTime = (iso) => {
  try { return format(new Date(iso), 'HH:mm:ss'); }
  catch { return '—'; }
};

/** ISO timestamp → relative "2 minutes ago" */
export const fmtRelative = (iso) => {
  try { return formatDistanceToNow(new Date(iso), { addSuffix: true }); }
  catch { return '—'; }
};

/** ISO timestamp → "2024-05-14 14:32:07" */
export const fmtFull = (iso) => {
  try { return format(new Date(iso), 'yyyy-MM-dd HH:mm:ss'); }
  catch { return '—'; }
};

/** score value → colour badge class */
export const scoreBadgeClass = (score) => {
  if (score >= 10) return 'badge-info';
  if (score >= 8)  return 'badge-success';
  if (score >= 6)  return 'badge-warn';
  return 'badge-danger';
};

/** Pad number to always show sign: +3.5 / -1.2 */
export const fmtSigned = (v, dp = 1) =>
  v == null ? '—' : `${v >= 0 ? '+' : ''}${Number(v).toFixed(dp)}`;