"""
backend/services/export_service.py
Generates CSV and PDF exports from shot data.
PDF uses fpdf2 (pure-Python, no system deps).
"""

from __future__ import annotations

import csv
import io
import math
from datetime import datetime

from fpdf import FPDF

from backend.models.shot import ShotRecord
from backend.services.analytics_service import (
    compute_cep, compute_r50, compute_group_size, compute_mean_poi,
)


# ─── CSV ──────────────────────────────────────────────────────────────────────

HEADERS = ["#", "Timestamp", "Score", "Ring", "X_mm", "Y_mm", "Radius_mm", "Session"]


def shots_to_csv(shots: list[ShotRecord]) -> bytes:
    buf = io.StringIO()
    w   = csv.writer(buf)
    w.writerow(HEADERS)
    for i, s in enumerate(shots, 1):
        w.writerow([
            i,
            s.timestamp.isoformat(),
            s.score,
            s.ring,
            round(s.x_mm,    3),
            round(s.y_mm,    3),
            round(s.radius_mm, 3),
            s.session_id or "",
        ])
    return buf.getvalue().encode()


# ─── PDF ──────────────────────────────────────────────────────────────────────

class ReportPDF(FPDF):
    """Custom FPDF subclass with header/footer."""

    def header(self):
        self.set_font("Helvetica", "B", 14)
        self.set_text_color(30, 50, 120)
        self.cell(0, 10, "Shooting Score Report", align="L")
        self.set_font("Helvetica", "", 9)
        self.set_text_color(120, 120, 140)
        self.set_x(-50)
        self.cell(40, 10, f"Generated {datetime.utcnow().strftime('%Y-%m-%d %H:%M')} UTC", align="R")
        self.ln(6)
        self.set_draw_color(200, 210, 230)
        self.line(10, self.get_y(), 200, self.get_y())
        self.ln(4)

    def footer(self):
        self.set_y(-13)
        self.set_font("Helvetica", "I", 8)
        self.set_text_color(160, 160, 180)
        self.cell(0, 10, f"Page {self.page_no()}", align="C")


def _summary_table(pdf: ReportPDF, shots: list[ShotRecord]) -> None:
    cep   = compute_cep(shots)
    r50   = compute_r50(shots)
    group = compute_group_size(shots)
    poi   = compute_mean_poi(shots)
    total = sum(s.score for s in shots)
    avg   = total / len(shots) if shots else 0

    rows = [
        ("Total shots",                 str(len(shots))),
        ("Total score",                 str(total)),
        ("Average score",               f"{avg:.2f}"),
        ("CEP (Circular Error Probable)", f"{cep:.2f} mm"),
        ("R50 (group centre radius)",    f"{r50:.2f} mm"),
        ("Group size (extreme spread)",  f"{group:.2f} mm"),
        ("Mean POI (X / Y)",            f"{poi.x_mm:.2f} mm / {poi.y_mm:.2f} mm"),
    ]

    pdf.set_font("Helvetica", "B", 10)
    pdf.set_fill_color(230, 235, 250)
    pdf.cell(90, 7, "Metric", fill=True, border=1)
    pdf.cell(90, 7, "Value", fill=True, border=1)
    pdf.ln()

    pdf.set_font("Helvetica", "", 10)
    for label, value in rows:
        pdf.cell(90, 6, label, border=1)
        pdf.cell(90, 6, value, border=1)
        pdf.ln()


def _shots_table(pdf: ReportPDF, shots: list[ShotRecord]) -> None:
    cols   = ["#", "Timestamp", "Score", "Ring", "X (mm)", "Y (mm)", "R (mm)"]
    widths = [10,   44,          14,      12,     24,        24,       24]

    pdf.set_font("Helvetica", "B", 9)
    pdf.set_fill_color(230, 235, 250)
    for col, w in zip(cols, widths):
        pdf.cell(w, 7, col, fill=True, border=1)
    pdf.ln()

    pdf.set_font("Helvetica", "", 9)
    for i, s in enumerate(shots, 1):
        fill = i % 2 == 0
        pdf.set_fill_color(245, 247, 252) if fill else pdf.set_fill_color(255, 255, 255)
        row = [
            str(i),
            s.timestamp.strftime("%H:%M:%S"),
            str(s.score),
            s.ring,
            f"{s.x_mm:.2f}",
            f"{s.y_mm:.2f}",
            f"{s.radius_mm:.2f}",
        ]
        for val, w in zip(row, widths):
            pdf.cell(w, 6, val, border=1, fill=fill)
        pdf.ln()


def shots_to_pdf(shots: list[ShotRecord]) -> bytes:
    pdf = ReportPDF(orientation="P", unit="mm", format="A4")
    pdf.set_margins(10, 15, 10)
    pdf.add_page()

    # ── Session info ──────────────────────────────────────────────────────────
    pdf.set_font("Helvetica", "B", 12)
    pdf.set_text_color(30, 50, 120)
    pdf.cell(0, 8, "Session Summary", ln=True)
    pdf.ln(2)

    _summary_table(pdf, shots)
    pdf.ln(8)

    # ── Shot log ──────────────────────────────────────────────────────────────
    pdf.set_font("Helvetica", "B", 12)
    pdf.set_text_color(30, 50, 120)
    pdf.cell(0, 8, "Shot Log", ln=True)
    pdf.ln(2)

    _shots_table(pdf, shots)

    return bytes(pdf.output())