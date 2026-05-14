import ipscPolygonText from '@cv/Scoring/IPSC/polygon.txt?raw';
import nguoiContourText from '@cv/Scoring/Nguoi/Nguoi_contours.txt?raw';

export const TARGET_TYPES = {
  TRON: {
    id: 'TRON',
    label: 'Circle',
    title: 'BIA TRON',
  },
  IPSC: {
    id: 'IPSC',
    label: 'IPSC',
    title: 'BIA IPSC',
  },
  NGUOI: {
    id: 'NGUOI',
    label: 'Human',
    title: 'BIA NGUOI',
  },
};

export const TARGET_TYPE_IDS = Object.keys(TARGET_TYPES);
export const TARGET_CANVAS_SIZE = 500;

const IMAGE_WIDTH = 2480;
const IMAGE_HEIGHT = 3508;
const IMAGE_SCALE = TARGET_CANVAS_SIZE / IMAGE_HEIGHT;
const IMAGE_OFFSET_X = (TARGET_CANVAS_SIZE - IMAGE_WIDTH * IMAGE_SCALE) / 2;
const IMAGE_OFFSET_Y = 0;

const IPSC_SCORES = [10, 5, 3, 10, 7];
const NGUOI_SCORES = [6, 7, 8, 9, 9, 10, 10];
const TRON_CENTER_PX = { x: 1240, y: 1754 };
const TRON_RINGS = [
  [51, 10, 'X', '#e8f4ff'],
  [141, 9, '9', '#ddeeff'],
  [235.5, 8, '8', '#c4e0ff'],
  [330, 7, '7', '#aad4ff'],
  [424.5, 6, '6', '#88c4ff'],
  [519, 5, '5', '#ffcc44'],
  [613.5, 4, '4', '#ffaa22'],
  [708, 3, '3', '#ff8811'],
  [802.5, 2, '2', '#ff5533'],
  [897, 1, '1', '#ee2222'],
];

export function shotTargetType(shot) {
  const raw = String(shot?.metadata?.target_type ?? 'TRON').toUpperCase();
  return TARGET_TYPES[raw] ? raw : 'TRON';
}

function parseNamedPointSets(text, prefix) {
  const sets = [];
  let current = null;

  text.split(/\r?\n/).forEach((rawLine) => {
    const line = rawLine.trim();
    if (!line) return;

    if (line.startsWith(prefix)) {
      current = { id: line, points: [] };
      sets.push(current);
      return;
    }

    if (line === 'END') {
      current = null;
      return;
    }

    if (!current) return;
    const [x, y] = line.split(',').map(Number);
    if (Number.isFinite(x) && Number.isFinite(y)) current.points.push({ x, y });
  });

  return sets.filter((set) => set.points.length > 2);
}

function polygonArea(points) {
  let area = 0;
  for (let i = 0; i < points.length; i++) {
    const a = points[i];
    const b = points[(i + 1) % points.length];
    area += a.x * b.y - b.x * a.y;
  }
  return Math.abs(area / 2);
}

function pointInPolygon(point, polygon) {
  let inside = false;
  for (let i = 0, j = polygon.length - 1; i < polygon.length; j = i++) {
    const pi = polygon[i];
    const pj = polygon[j];
    const intersects =
      pi.y > point.y !== pj.y > point.y &&
      point.x < ((pj.x - pi.x) * (point.y - pi.y)) / (pj.y - pi.y) + pi.x;
    if (intersects) inside = !inside;
  }
  return inside;
}

export const targetGeometry = {
  TRON: {
    type: TARGET_TYPES.TRON,
    zones: [...TRON_RINGS].reverse().map(([radiusPx, score, label, color]) => ({
      id: `ring-${label}`,
      radiusPx,
      score,
      label,
      color,
    })),
  },
  IPSC: {
    type: TARGET_TYPES.IPSC,
    zones: parseNamedPointSets(ipscPolygonText, 'polygon').map((zone, index) => ({
      ...zone,
      score: IPSC_SCORES[index] ?? 0,
      label: ['A', 'C', 'D', 'A2', 'B'][index] ?? `${index + 1}`,
      color: ['#e8f4ff', '#82d2ff', '#ff7b54', '#d9f99d', '#facc15'][index] ?? '#8fa3bf',
    })),
  },
  NGUOI: {
    type: TARGET_TYPES.NGUOI,
    zones: parseNamedPointSets(nguoiContourText, 'contour').map((zone, index) => ({
      ...zone,
      area: polygonArea(zone.points),
      score: NGUOI_SCORES[index] ?? 0,
      label: `${NGUOI_SCORES[index] ?? 0}`,
      color: ['#6ee7b7', '#67e8f9', '#93c5fd', '#c4b5fd', '#f0abfc', '#fde68a', '#fb7185'][index] ?? '#8fa3bf',
    })),
  },
};

export function cvPointToCanvas(point) {
  return {
    x: IMAGE_OFFSET_X + point.x * IMAGE_SCALE,
    y: IMAGE_OFFSET_Y + point.y * IMAGE_SCALE,
  };
}

export function shotToCanvas(shot, targetType = 'TRON') {
  const x = Number(shot?.x_px ?? shot?.x_mm ?? shot?.x ?? 0);
  const y = Number(shot?.y_px ?? shot?.y_mm ?? shot?.y ?? 0);

  return cvPointToCanvas({ x, y });
}

export function scoreTargetShot(shot, targetType = 'TRON') {
  const x = Number(shot?.x_px ?? shot?.x_mm ?? shot?.x ?? 0);
  const y = Number(shot?.y_px ?? shot?.y_mm ?? shot?.y ?? 0);

  if (targetType === 'TRON') {
    const dx = x - TRON_CENTER_PX.x;
    const dy = y - TRON_CENTER_PX.y;
    const radius = Math.sqrt(dx * dx + dy * dy);
    const ring = TRON_RINGS.find(([radiusPx]) => radius <= radiusPx);
    return ring
      ? { score: ring[1], label: ring[2], color: ring[3], miss: false }
      : { score: 0, label: 'M', color: '#555', miss: true };
  }

  const zones = targetGeometry[targetType]?.zones ?? [];
  const point = { x, y };

  if (targetType === 'NGUOI') {
    let best = null;
    zones.forEach((zone) => {
      if (pointInPolygon(point, zone.points) && (!best || zone.area < best.area)) best = zone;
    });
    return best
      ? { score: best.score, label: best.label, color: best.color, miss: false }
      : { score: 0, label: 'M', color: '#555', miss: true };
  }

  const zone = zones.find((candidate) => pointInPolygon(point, candidate.points));
  return zone
    ? { score: zone.score, label: zone.label, color: zone.color, miss: false }
    : { score: 0, label: 'M', color: '#555', miss: true };
}
