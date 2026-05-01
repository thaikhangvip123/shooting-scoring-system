"""
coords.py — Coordinate conversion between pixel, mm, and scoring spaces.

All functions are pure (no side effects) and stateless.
"""

from typing import Tuple
from config import CENTER_X_PX, CENTER_Y_PX, PIXELS_PER_MM, SCALE_FACTOR


def px_to_mm(x_px: float, y_px: float) -> Tuple[float, float]:
    """
    Warped-image pixel → Cartesian millimetres.
    Origin is at target centre, Y axis points UP.
    """
    return (
        (x_px - CENTER_X_PX) / PIXELS_PER_MM,
        -(y_px - CENTER_Y_PX) / PIXELS_PER_MM,
    )


def mm_to_px(x_mm: float, y_mm: float) -> Tuple[float, float]:
    """Cartesian mm → warped-image pixel."""
    return (
        x_mm * PIXELS_PER_MM + CENTER_X_PX,
        -y_mm * PIXELS_PER_MM + CENTER_Y_PX,
    )


def px_to_score_px(x_px: float, y_px: float) -> Tuple[int, int]:
    """
    Warped pixel → scoring coordinate space (2480 px wide canvas).
    Scoring polygons and ring radii were originally defined at that scale.
    """
    return int(x_px * SCALE_FACTOR), int(y_px * SCALE_FACTOR)
