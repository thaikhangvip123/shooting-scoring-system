/**
 * utils/session.js
 * Helpers for displaying and grouping shooting sessions.
 */

export function sessionNumberFromShot(shot) {
  const fromMetadata = Number(shot?.metadata?.session_number);
  if (Number.isFinite(fromMetadata) && fromMetadata > 0) return fromMetadata;

  const match = String(shot?.session_id ?? '').match(/^session-(\d+)$/i);
  if (match) return Number(match[1]);

  return null;
}

export function sessionLabelFromShot(shot) {
  const number = sessionNumberFromShot(shot);
  if (number != null) return `Session ${number}`;
  return shot?.session_id || 'Session -';
}

export function compareSessionsDesc(a, b) {
  const an = a.sessionNumber ?? -Infinity;
  const bn = b.sessionNumber ?? -Infinity;
  if (an !== bn) return bn - an;
  return String(b.sessionId).localeCompare(String(a.sessionId));
}
