/**
 * utils/units.js
 * UI-only conversion between OpenCV pixel coordinates and A4 millimetres.
 * Backend and CV still exchange x_px/y_px.
 */

export const A4_WIDTH_MM = 210;
export const A4_HEIGHT_MM = 297;
export const A4_WIDTH_PX = 2480;
export const A4_HEIGHT_PX = 3508;
export const A4_CENTER_PX = {
  x: A4_WIDTH_PX / 2,
  y: A4_HEIGHT_PX / 2,
};

export const PX_PER_MM_X = A4_WIDTH_PX / A4_WIDTH_MM;
export const PX_PER_MM_Y = A4_HEIGHT_PX / A4_HEIGHT_MM;
export const PX_PER_MM = (PX_PER_MM_X + PX_PER_MM_Y) / 2;

export const shotPx = (shot) => ({
  x: Number(shot?.x_px ?? shot?.x_mm ?? shot?.x ?? 0),
  y: Number(shot?.y_px ?? shot?.y_mm ?? shot?.y ?? 0),
});

export const pxToPageMm = ({ x, y }) => ({
  x: x / PX_PER_MM_X,
  y: y / PX_PER_MM_Y,
});

export const pxToOffsetMm = ({ x, y }) => ({
  x: (x - A4_CENTER_PX.x) / PX_PER_MM_X,
  y: (A4_CENTER_PX.y - y) / PX_PER_MM_Y,
});

export const distancePxToMm = (px) => Number(px ?? 0) / PX_PER_MM;

export const shotPageMm = (shot) => pxToPageMm(shotPx(shot));

export const shotOffsetMm = (shot) => pxToOffsetMm(shotPx(shot));

export const shotRadiusMm = (shot) => {
  const p = shotOffsetMm(shot);
  return Math.sqrt(p.x * p.x + p.y * p.y);
};

export const fmtMm = (value, dp = 1) =>
  value == null ? '-' : `${Number(value).toFixed(dp)} mm`;

export const fmtSignedMm = (value, dp = 1) =>
  value == null ? '-' : `${value >= 0 ? '+' : ''}${Number(value).toFixed(dp)} mm`;

