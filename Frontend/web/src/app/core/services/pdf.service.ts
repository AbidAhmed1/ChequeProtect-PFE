import { inject, Injectable, PLATFORM_ID } from '@angular/core';
import { isPlatformBrowser } from '@angular/common';
import { Cheque, QrInfo } from '../models/cheque.model';

const BLUE   = [29, 78, 216]  as const;
const SLATE  = [71, 85, 105]  as const;
const MUTED  = [148, 163, 184] as const;
const DARK   = [15, 23, 42]   as const;
const LIGHT  = [241, 245, 249] as const;
const GREEN  = [22, 101, 52]  as const;
const RED    = [153, 27, 27]  as const;

@Injectable({ providedIn: 'root' })
export class PdfService {

  private platformId = inject(PLATFORM_ID);

  // ── Rapport complet d'un chèque traité ────────────────────────────────────

  async generateRapportCheque(cheque: Cheque, qrInfo: QrInfo | null): Promise<void> {
    if (!isPlatformBrowser(this.platformId)) return;

    const { default: jsPDF }    = await import('jspdf');
    const { default: autoTable } = await import('jspdf-autotable');

    const doc    = new jsPDF({ orientation: 'portrait', unit: 'mm', format: 'a4' });
    const W      = doc.internal.pageSize.getWidth();
    const H      = doc.internal.pageSize.getHeight();
    const M      = 15;
    let y        = 0;

    // ── En-tête bleu ─────────────────────────────────────────────────────────
    doc.setFillColor(...BLUE);
    doc.rect(0, 0, W, 32, 'F');

    doc.setTextColor(255, 255, 255);
    doc.setFontSize(17);
    doc.setFont('helvetica', 'bold');
    doc.text('ChèqueProtect', M, 13);

    doc.setFontSize(9.5);
    doc.setFont('helvetica', 'normal');
    doc.text('Rapport de Traitement de Chèque', M, 22);

    const now = new Date().toLocaleString('fr-FR', {
      day: '2-digit', month: '2-digit', year: 'numeric',
      hour: '2-digit', minute: '2-digit'
    });
    doc.text(`Généré le : ${now}`, W - M, 22, { align: 'right' });

    y = 44;
    doc.setTextColor(...DARK);

    // ── Section 1 : Informations du chèque ───────────────────────────────────
    y = this.section(doc, 'INFORMATIONS DU CHÈQUE', M, y, W);

    autoTable(doc, {
      startY: y,
      body: [
        ['Référence',          cheque.id.slice(0, 8).toUpperCase()],
        ['N° Chèque',          cheque.chequeNumber.value    || '—'],
        ['Date émission',      cheque.date.value            || '—'],
        ['Montant',            `${cheque.amountNumeric.value} DT`],
        ['Montant (lettres)',   cheque.amountText.value      || '—'],
        ['Bénéficiaire',       cheque.beneficiaryName.value || '—'],
        ['RIB émetteur',       cheque.rib.value             || '—'],
        ['Source',             cheque.source ?? '—'],
      ],
      ...this.kv(M),
    });

    y = (doc as any).lastAutoTable.finalY + 7;

    // ── Section 2 : Code QR BCT ───────────────────────────────────────────────
    y = this.section(doc, 'CODE QR BCT (pecc.tn)', M, y, W);

    if (qrInfo) {
      autoTable(doc, {
        startY: y,
        body: [
          ['Statut QR',        'Actif — enregistré BCT'],
          ['Bénéficiaire BCT', qrInfo.beneficiaire  || '—'],
          ['Montant BCT',      `${qrInfo.montant.toFixed(3)} DT`],
          ['N° Chèque BCT',    qrInfo.numeroCheque  || '—'],
          ['RIB BCT',          qrInfo.rib           || '—'],
          ['Date validité',    qrInfo.date          || '—'],
          ['Série',            qrInfo.serie         || '—'],
        ],
        ...this.kv(M),
        didParseCell: (data: any) => {
          if (data.row.index === 0 && data.column.index === 1) {
            data.cell.styles.textColor = [...GREEN];
            data.cell.styles.fontStyle = 'bold';
          }
        },
      });
    } else {
      autoTable(doc, {
        startY: y,
        body: [['Statut QR', 'Inactif — QR absent ou illisible sur ce chèque']],
        ...this.kv(M),
        didParseCell: (data: any) => {
          if (data.column.index === 1) {
            data.cell.styles.textColor = [...RED];
            data.cell.styles.fontStyle = 'bold';
          }
        },
      });
    }

    y = (doc as any).lastAutoTable.finalY + 7;

    // ── Section 3 : Phases IA ─────────────────────────────────────────────────
    const phases = cheque.aiPhases ?? [];
    if (phases.length > 0) {
      y = this.section(doc, 'ANALYSE IA — RÉSULTATS PAR PHASE', M, y, W);

      const phaseLabel: Record<string, string> = {
        identification: 'Identification',
        compliance:     'Conformité QR',
        ocr:            'Extraction OCR',
        signature:      'Signature',
      };

      autoTable(doc, {
        startY: y,
        head: [['Phase', 'Score', 'Statut', 'Décision', 'Durée']],
        body: phases
          .slice()
          .sort((a, b) =>
            ['identification','compliance','ocr','signature'].indexOf(a.phase) -
            ['identification','compliance','ocr','signature'].indexOf(b.phase))
          .map(ph => [
            phaseLabel[ph.phase] ?? ph.phase,
            `${(ph.score * 100).toFixed(0)} %`,
            ph.passed ? 'Validé' : 'Échoué',
            ph.decision ?? '—',
            ph.durationMs ? `${ph.durationMs} ms` : '—',
          ]),
        headStyles: {
          fillColor: [...BLUE] as [number, number, number],
          textColor: 255,
          fontSize: 9,
          fontStyle: 'bold',
        },
        styles: { fontSize: 8.5, cellPadding: 3 },
        columnStyles: {
          0: { cellWidth: 38 },
          1: { cellWidth: 18, halign: 'center' },
          2: { cellWidth: 20, halign: 'center' },
          4: { cellWidth: 22, halign: 'right' },
        },
        alternateRowStyles: { fillColor: [248, 250, 252] },
        margin: { left: M, right: M },
        didParseCell: (data: any) => {
          if (data.section === 'body' && data.column.index === 2) {
            data.cell.styles.textColor =
              data.cell.raw === 'Validé' ? [...GREEN] : [...RED];
            data.cell.styles.fontStyle = 'bold';
          }
        },
      });

      y = (doc as any).lastAutoTable.finalY + 7;
    }

    // ── Section 4 : Décision agent ────────────────────────────────────────────
    y = this.section(doc, 'DÉCISION AGENT', M, y, W);

    const decisionText = cheque.status === 'VALIDATED' ? 'VALIDÉ'
                       : cheque.status === 'REJECTED'  ? 'REJETÉ'
                       : 'EN ATTENTE';

    autoTable(doc, {
      startY: y,
      body: [
        ['Score global IA',   `${(cheque.overallConfidence * 100).toFixed(0)} %`],
        ['Décision',          decisionText],
        ['Date traitement',   cheque.uploadDate
            ? new Date(cheque.uploadDate).toLocaleString('fr-FR')
            : '—'],
      ],
      ...this.kv(M),
      didParseCell: (data: any) => {
        if (data.row.index === 1 && data.column.index === 1) {
          data.cell.styles.textColor =
            decisionText === 'VALIDÉ' ? [...GREEN] :
            decisionText === 'REJETÉ' ? [...RED]   : [...SLATE];
          data.cell.styles.fontStyle = 'bold';
          data.cell.styles.fontSize  = 10;
        }
      },
    });

    // ── Pied de page ──────────────────────────────────────────────────────────
    doc.setDrawColor(...MUTED);
    doc.setLineWidth(0.3);
    doc.line(M, H - 18, W - M, H - 18);
    doc.setFontSize(7.5);
    doc.setTextColor(...MUTED);
    doc.text('ChèqueProtect — Système de traitement de chèques bancaires', M, H - 12);
    doc.text('Document confidentiel — Usage interne banque uniquement', W - M, H - 12, { align: 'right' });
    doc.text(
      `Réf. ${cheque.id.slice(0,8).toUpperCase()}  •  Page 1/1`,
      W / 2, H - 7, { align: 'center' }
    );

    const filename = `rapport_cheque_${cheque.id.slice(0,8)}_${new Date().toISOString().slice(0,10)}.pdf`;
    doc.save(filename);
  }

  // ── Export PDF de la liste historique ─────────────────────────────────────

  async generateHistoriquePdf(cheques: Cheque[]): Promise<void> {
    if (!isPlatformBrowser(this.platformId) || cheques.length === 0) return;

    const { default: jsPDF }    = await import('jspdf');
    const { default: autoTable } = await import('jspdf-autotable');

    const doc = new jsPDF({ orientation: 'landscape', unit: 'mm', format: 'a4' });
    const W   = doc.internal.pageSize.getWidth();
    const H   = doc.internal.pageSize.getHeight();
    const M   = 12;

    // En-tête
    doc.setFillColor(...BLUE);
    doc.rect(0, 0, W, 22, 'F');
    doc.setTextColor(255, 255, 255);
    doc.setFontSize(14);
    doc.setFont('helvetica', 'bold');
    doc.text('ChèqueProtect — Historique des traitements', M, 10);
    doc.setFontSize(9);
    doc.setFont('helvetica', 'normal');
    const now = new Date().toLocaleString('fr-FR', { day:'2-digit', month:'2-digit', year:'numeric', hour:'2-digit', minute:'2-digit' });
    doc.text(`Exporté le : ${now}  •  ${cheques.length} enregistrement(s)`, M, 18);

    autoTable(doc, {
      startY: 28,
      head: [['ID', 'Date', 'Bénéficiaire', 'Émetteur', 'Montant', 'RIB', 'Statut', 'Score']],
      body: cheques.map(c => [
        c.id.slice(0, 8).toUpperCase(),
        new Date(c.uploadDate).toLocaleString('fr-FR', { day:'2-digit', month:'2-digit', year:'numeric' }),
        c.beneficiaryName.value || '—',
        c.emitterName.value     || '—',
        `${c.amountNumeric.value} DT`,
        c.rib.value             || '—',
        c.status === 'VALIDATED' ? 'Validé' : c.status === 'REJECTED' ? 'Rejeté' : 'En attente',
        `${(c.overallConfidence * 100).toFixed(0)} %`,
      ]),
      headStyles: { fillColor: [...BLUE] as [number,number,number], textColor: 255, fontSize: 9, fontStyle: 'bold' },
      styles: { fontSize: 8, cellPadding: 2.5 },
      alternateRowStyles: { fillColor: [248, 250, 252] },
      margin: { left: M, right: M },
      didParseCell: (data: any) => {
        if (data.section === 'body' && data.column.index === 6) {
          data.cell.styles.textColor =
            data.cell.raw === 'Validé'   ? [...GREEN] :
            data.cell.raw === 'Rejeté'   ? [...RED]   : [...SLATE];
          data.cell.styles.fontStyle = 'bold';
        }
      },
    });

    // Pied de page
    const pages = (doc as any).internal.getNumberOfPages();
    for (let i = 1; i <= pages; i++) {
      doc.setPage(i);
      doc.setFontSize(7.5);
      doc.setTextColor(...MUTED);
      doc.text('ChèqueProtect — Document confidentiel', M, H - 6);
      doc.text(`Page ${i} / ${pages}`, W - M, H - 6, { align: 'right' });
    }

    doc.save(`historique_cheques_${new Date().toISOString().slice(0,10)}.pdf`);
  }

  // ── Helpers ───────────────────────────────────────────────────────────────

  private section(doc: any, title: string, x: number, y: number, W: number): number {
    doc.setFillColor(...LIGHT);
    doc.rect(x - 2, y - 4.5, W - (x - 2) * 2, 8, 'F');
    doc.setFontSize(8.5);
    doc.setFont('helvetica', 'bold');
    doc.setTextColor(...SLATE);
    doc.text(title, x, y);
    doc.setFont('helvetica', 'normal');
    doc.setTextColor(...DARK);
    return y + 6;
  }

  private kv(margin: number): object {
    return {
      theme: 'plain' as const,
      styles: { fontSize: 9, cellPadding: { top: 2.5, bottom: 2.5, left: 3, right: 3 } },
      columnStyles: {
        0: { fontStyle: 'bold', cellWidth: 48, textColor: [...SLATE] as [number,number,number] },
        1: { textColor: [...DARK] as [number,number,number] },
      },
      alternateRowStyles: { fillColor: [248, 250, 252] },
      margin: { left: margin, right: margin },
    };
  }
}
