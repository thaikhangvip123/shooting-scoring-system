/**
 * components/shared/ExportButtons.jsx
 * CSV export runs fully client-side.
 * PDF export uses jsPDF + jsPDF-AutoTable.
 */

import { useState } from 'react';
import { fmtFull, fmtMm } from '@/utils/format';
import { scoreShot, calcCEP, calcR50, calcGroupSize, radialDeviation } from '@/utils/scoring';

// ─── CSV helper ──────────────────────────────────────────────────────────────

function shotsToCSV(shots) {
  const header = ['#', 'Timestamp', 'Score', 'Ring', 'X_mm', 'Y_mm', 'Radius_mm', 'Session'];
  const rows   = shots.map((s, i) => {
    const { label }  = scoreShot(s.x_mm, s.y_mm);
    const radius     = radialDeviation(s.x_mm, s.y_mm);
    return [
      shots.length - i,
      fmtFull(s.timestamp),
      s.score,
      label,
      s.x_mm?.toFixed(3),
      s.y_mm?.toFixed(3),
      radius.toFixed(3),
      s.session_id ?? '',
    ].join(',');
  });
  return [header.join(','), ...rows].join('\n');
}

function downloadText(text, filename, mime = 'text/csv') {
  const blob = new Blob([text], { type: mime });
  const url  = URL.createObjectURL(blob);
  const a    = document.createElement('a');
  a.href     = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

// ─── PDF helper (lazy import jsPDF) ──────────────────────────────────────────

async function exportPDF(shots) {
  const { jsPDF }          = await import('jspdf');
  const { default: auto }  = await import('jspdf-autotable');

  const doc = new jsPDF({ orientation: 'portrait', unit: 'mm', format: 'a4' });

  // Title
  doc.setFontSize(18);
  doc.setTextColor(30, 30, 40);
  doc.text('Shooting Score Report', 14, 20);

  doc.setFontSize(10);
  doc.setTextColor(120, 120, 140);
  doc.text(`Generated: ${new Date().toLocaleString()}`, 14, 27);
  doc.text(`Total shots: ${shots.length}`, 14, 33);

  // Stats
  const radii  = shots.map((s) => radialDeviation(s.x_mm, s.y_mm));
  const cep    = calcCEP(radii);
  const r50    = calcR50(shots);
  const group  = calcGroupSize(shots);
  const avg    = shots.length
    ? shots.reduce((s, sh) => s + (sh.score ?? 0), 0) / shots.length
    : 0;

  doc.setFontSize(11);
  doc.setTextColor(30, 30, 40);
  doc.text('Summary Statistics', 14, 43);

  auto(doc, {
    startY: 47,
    head:   [['Metric', 'Value']],
    body:   [
      ['CEP (Circular Error Probable)', fmtMm(cep)],
      ['R50 (Group Centre Radius)',      fmtMm(r50)],
      ['Group Size (Extreme Spread)',    fmtMm(group)],
      ['Average Score',                 avg.toFixed(2)],
      ['Total Score',                   String(shots.reduce((s, sh) => s + (sh.score ?? 0), 0))],
    ],
    theme:      'grid',
    headStyles: { fillColor: [35, 60, 140], fontSize: 10 },
    bodyStyles: { fontSize: 10 },
    margin:     { left: 14, right: 14 },
  });

  // Shot table
  const startY = doc.lastAutoTable?.finalY + 10 ?? 120;
  doc.setFontSize(11);
  doc.text('Shot Details', 14, startY);

  auto(doc, {
    startY: startY + 4,
    head:   [['#', 'Time', 'Score', 'Ring', 'X (mm)', 'Y (mm)', 'R (mm)']],
    body:   shots.map((s, i) => {
      const { label } = scoreShot(s.x_mm, s.y_mm);
      const r         = radialDeviation(s.x_mm, s.y_mm);
      return [
        shots.length - i,
        fmtFull(s.timestamp),
        s.score,
        label,
        s.x_mm?.toFixed(2),
        s.y_mm?.toFixed(2),
        r.toFixed(2),
      ];
    }),
    theme:      'striped',
    headStyles: { fillColor: [35, 60, 140], fontSize: 9 },
    bodyStyles: { fontSize: 9 },
    margin:     { left: 14, right: 14 },
  });

  doc.save(`shoot-report-${Date.now()}.pdf`);
}

// ─── Component ────────────────────────────────────────────────────────────────

export default function ExportButtons({ shots = [] }) {
  const [pdfLoading, setPdfLoading] = useState(false);

  const handleCSV = () => {
    if (!shots.length) return;
    downloadText(shotsToCSV(shots), `shots-${Date.now()}.csv`);
  };

  const handlePDF = async () => {
    if (!shots.length || pdfLoading) return;
    setPdfLoading(true);
    try {
      await exportPDF(shots);
    } catch (e) {
      console.error('PDF export failed', e);
    } finally {
      setPdfLoading(false);
    }
  };

  return (
    <>
      <button className="btn" onClick={handleCSV} disabled={!shots.length} title="Export CSV">
        ⬇ CSV
      </button>
      <button className="btn" onClick={handlePDF} disabled={!shots.length || pdfLoading} title="Export PDF">
        {pdfLoading ? '…' : '⬇ PDF'}
      </button>
    </>
  );
}