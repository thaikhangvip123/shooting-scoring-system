/**
 * utils/scoring.js
 * Pure-function scoring helpers that mirror backend logic.
 * Used for instant client-side display before the server confirms.
 */

// Target ring definitions: [maxRadius_mm, score, label, color]
export const RINGS = [
  [  11.25,  10, '10', '#e8f4ff' ],  // X-ring (innermost)
  [  22.5,   9, '9','#ddeeff' ],
  [  45,      8, '8', '#c4e0ff' ],
  [  67.5,    7, '7', '#aad4ff' ],
  [  90,      6, '6', '#88c4ff' ],
  [ 112.5,    5, '5', '#ffcc44' ],
  [ 135,      4, '4', '#ffaa22' ],
  [ 157.5,    3, '3', '#ff8811' ],
  [ 180,      2, '2', '#ff5533' ],
  [ 202.5,    1, '1', '#ee2222' ],
  [ 225,      0, '0', '#cc0000' ],
];

export const TARGET_RADIUS_MM = 225; // outermost scoring ring

/**
 * Euclidean distance from target centre (0,0) in millimetres.
 * @param {number} x
 * @param {number} y
 * @returns {number}
 */
export const radialDeviation = (x, y) => Math.sqrt(x * x + y * y);

/**
 * Returns the score (1–10) and ring label for a given position.
 * @param {number} x_mm
 * @param {number} y_mm
 * @returns {{ score: number, label: string, color: string, miss: boolean }}
 */
export const scoreShot = (x_mm, y_mm) => {
  const r = radialDeviation(x_mm, y_mm);
  for (const [maxR, score, label, color] of RINGS) {
    if (r <= maxR) return { score, label, color, miss: false };
  }
  return { score: 0, label: 'M', color: '#555', miss: true };
};

/**
 * Circular Error Probable: radius containing 50% of hits.
 * Uses simple median-rank method.
 * @param {number[]} radii – array of radial deviations in mm
 * @returns {number} CEP in mm
 */
export const calcCEP = (radii) => {
  if (!radii.length) return 0;
  const sorted = [...radii].sort((a, b) => a - b);
  const mid = Math.floor(sorted.length / 2);
  return sorted.length % 2 !== 0
    ? sorted[mid]
    : (sorted[mid - 1] + sorted[mid]) / 2;
};

/**
 * R50: radius of the smallest circle centred on the mean point
 * that contains 50% of shots.
 * @param {{ x_mm: number, y_mm: number }[]} shots
 * @returns {number}
 */
export const calcR50 = (shots) => {
  if (!shots.length) return 0;
  const mx = shots.reduce((s, p) => s + p.x_mm, 0) / shots.length;
  const my = shots.reduce((s, p) => s + p.y_mm, 0) / shots.length;
  const radii = shots.map((p) => radialDeviation(p.x_mm - mx, p.y_mm - my));
  return calcCEP(radii);
};

/**
 * Group size: distance between the two furthest shots.
 * @param {{ x_mm: number, y_mm: number }[]} shots
 * @returns {number} diameter in mm
 */
export const calcGroupSize = (shots) => {
  if (shots.length < 2) return 0;
  let max = 0;
  for (let i = 0; i < shots.length; i++) {
    for (let j = i + 1; j < shots.length; j++) {
      const d = radialDeviation(
        shots[i].x_mm - shots[j].x_mm,
        shots[i].y_mm - shots[j].y_mm
      );
      if (d > max) max = d;
    }
  }
  return max;
};

/**
 * Mean point-of-impact (centroid of all shots).
 * @param {{ x_mm: number, y_mm: number }[]} shots
 * @returns {{ x: number, y: number }}
 */
export const calcMeanPOI = (shots) => {
  if (!shots.length) return { x: 0, y: 0 };
  return {
    x: shots.reduce((s, p) => s + p.x_mm, 0) / shots.length,
    y: shots.reduce((s, p) => s + p.y_mm, 0) / shots.length,
  };
};

/**
 * Ring-score distribution (count per score value).
 * @param {object[]} shots – each must have `.score`
 * @returns {Record<number, number>}
 */
export const scoreDistribution = (shots) => {
  const dist = {};
  for (let i = 0; i <= 10; i++) dist[i] = 0;
  shots.forEach((s) => { if (s.score != null) dist[s.score]++; });
  return dist;
};

/**
 * Colour gradient for score value (green → red).
 */
export const scoreColor = (score) => {
  const colors = ['#555','#cc0000','#ee2222','#ff5533','#ff8811',
                   '#ffaa22','#ffcc44','#88c4ff','#aad4ff','#c4e0ff','#e8f4ff'];
  return colors[Math.max(0, Math.min(10, score))] ?? '#888';
};