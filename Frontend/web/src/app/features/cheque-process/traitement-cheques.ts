import { Component, HostListener, OnDestroy, OnInit, computed, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormBuilder, FormGroup, ReactiveFormsModule, Validators } from '@angular/forms';
import { Router } from '@angular/router';
import { HttpClient } from '@angular/common/http';
import { DomSanitizer, SafeUrl } from '@angular/platform-browser';
import { Observable } from 'rxjs';
import { ChequeService } from '../../core/services/cheque.service';
import { NotificationService } from '../../core/services/notification.service';
import { PdfService } from '../../core/services/pdf.service';
import { Cheque, QrInfo } from '../../core/models/cheque.model';
import { ComponentCanDeactivate } from '../../core/guards/pending-changes.guard';

@Component({ selector: 'app-traitement-cheques', standalone: true, imports: [CommonModule, ReactiveFormsModule], templateUrl: './traitement-cheques.html', styleUrl: './traitement-cheques.scss' })
export class TraitementChequesComponent implements OnInit, OnDestroy, ComponentCanDeactivate {
  private chequeService       = inject(ChequeService);
  private notificationService = inject(NotificationService);
  private pdfService          = inject(PdfService);
  private fb                  = inject(FormBuilder);
  private router              = inject(Router);
  private http                = inject(HttpClient);
  private sanitizer           = inject(DomSanitizer);

  isDownloadingPdf = signal(false);

  cheque      = signal<Cheque | null>(null);
  rectoUrl    = signal<SafeUrl | null>(null);
  versoUrl    = signal<SafeUrl | null>(null);
  private blobUrls: string[] = [];

  beneficiaireType = signal<'individu' | 'societe'>('individu');
  ribBeneficiaire  = signal<string>('');

  aiPhases = computed(() => {
    const phases = this.cheque()?.aiPhases ?? [];
    return [...phases].sort((a, b) =>
      this.phaseOrder.indexOf(a.phase) - this.phaseOrder.indexOf(b.phase)
    );
  });

  qrInfo = computed<QrInfo | null>(() => {
    const raw = this.cheque()?.qrData;
    if (!raw) return null;
    return this.parseQrUrl(raw);
  });
  treatmentForm!: FormGroup;
  isSubmitting    = this.chequeService.isSavingDecision;
  isLoading       = signal<boolean>(false);
  cinBeneficiaire = signal<string>('');
  rejectMotif     = signal<string>('');
  showRejectPanel = signal<boolean>(false);
  private allowRouteLeave = signal(false);

  readonly phaseLabel: Record<string, string> = {
    identification: 'Identification',
    compliance:     'Conformité QR',
    ocr:            'Extraction OCR',
    signature:      'Signature'
  };

  readonly phaseOrder = ['identification', 'compliance', 'ocr', 'signature'];

  readonly rejectReasons = [
    'Provision insuffisante',
    'Signature non conforme',
    'Opposition sur chèque',
    'Compte clôturé',
    'Chèque périmé',
    'Falsification détectée',
    'Défaut de forme',
    'Autre',
  ];

  decisionLabel(decision: string | null): string {
    if (!decision) return '—';
    const map: Record<string, string> = {
      'VALID_CHEQUE':                  'Chèque valide',
      'APPROVED':                      'Approuvé',
      'COMPLIANCE_OK':                 'Conformité OK',
      'QR_VALID':                      'QR valide',
      'PENDING_REVIEW':                'À vérifier',
      'PENDING_REVIEW_QR':             'QR à vérifier',
      'PENDING_REVIEW_QR_ILLISIBLE':   'QR illisible',
      'PENDING_REVIEW_QR_ABSENT':      'QR absent',
      'PENDING_MANUAL_REVIEW':         'Saisie manuelle',
      'PENDING_REVIEW_AGENT':          'Décision agent',
      'REJECTED_IMAGE_QUALITY':        'Qualité insuffisante',
      'REJECTED_PRINTED_CHEQUE':       'Chèque imprimé',
      'REJECTED_FAKE_DOCUMENT':        'Document suspect',
      'REJECTED_NO_TUNICHEQUE_QR':     'QR absent',
      'REJECTED_QUALITY':              'Qualité insuffisante',
      'REJECTED_PRINTED':              'Chèque imprimé',
      'REJECTED_FAKE':                 'Document suspect',
      'REJECTED_SIGNATURE_MISMATCH':   'Signature incorrecte',
      'REJECTED_COMPLIANCE':           'Non conforme',
      'REJECTED_NUMERO_INCOHERENT':    'N° incohérent',
      'REJECTED_MONTANT_FALSIFIE':     'Montant falsifié',
      'REJECTED_BANQUE_INCOHERENTE':   'Banque incohérente',
      'REJECTED_RIB_INVALIDE':         'RIB invalide',
      'REJECTED_CHEQUE_PERIME':        'Chèque périmé',
      'ERROR':                         'Erreur phase',
      'REVIEW':                        'À vérifier',
      'OK':                            'OK',
    };
    return map[decision] ?? decision;
  }

  private parseQrUrl(raw: string): QrInfo | null {
    try {
      // Format : pecc.tn/TYPE/NUM/RIB/IND/NOM/MONTANT_MILLIMES/DATE/SERIE
      const path = raw.replace(/^https?:\/\//i, '').replace(/^pecc\.tn\//i, '');
      const parts = path.split('/');
      if (parts.length < 7) return null;
      const montantMillimes = parseInt(parts[5], 10);
      return {
        raw,
        type:          parts[0] ?? '',
        numeroCheque:  parts[1] ?? '',
        rib:           parts[2] ?? '',
        beneficiaire:  decodeURIComponent(parts[4]?.replace(/\+/g, ' ') ?? ''),
        montant:       isNaN(montantMillimes) ? 0 : montantMillimes / 1000,
        date:          this.formatQrDate(parts[6] ?? ''),
        serie:         parts[7] ?? '',
        actif:         true,
      };
    } catch {
      return null;
    }
  }

  private formatQrDate(yymmdd: string): string {
    if (yymmdd.length !== 6) return yymmdd;
    return `20${yymmdd.slice(0,2)}-${yymmdd.slice(2,4)}-${yymmdd.slice(4,6)}`;
  }

  @HostListener('window:keydown', ['$event'])
  handleKeyboardShortcuts(event: KeyboardEvent) {
    if (event.key === 'Enter' && !this.showRejectPanel()) { event.preventDefault(); this.onSubmit(); }
    if (event.key === 'Escape') {
      event.preventDefault();
      if (this.showRejectPanel()) { this.cancelReject(); } else { this.onReject(); }
    }
  }

  canDeactivate(): boolean | Observable<boolean> {
    if (this.allowRouteLeave() || this.isSubmitting() || !this.treatmentForm?.dirty) {
      return true;
    }
    return window.confirm('Un cheque est en cours de controle. Voulez-vous vraiment quitter cette page ?');
  }

  ngOnInit() { this.loadCurrentCheque(); }

  ngOnDestroy() {
    this.blobUrls.forEach(u => URL.revokeObjectURL(u));
  }

  private loadCurrentCheque() {
    const current = this.chequeService.currentScannedCheque();
    if (!current) return void this.router.navigate(['/scanner']);
    this.isLoading.set(true);
    setTimeout(() => {
      this.cheque.set(current);
      this.initForm(current);
      this.isLoading.set(false);
      this.loadImages(current.id, current.hasVerso ?? false);
    }, 1200);
  }

  private loadImages(chequeId: string, hasVerso: boolean) {
    this.http.get(`/api/cheques/${chequeId}/image/recto`, { responseType: 'blob' }).subscribe({
      next: blob => {
        const url = URL.createObjectURL(blob);
        this.blobUrls.push(url);
        this.rectoUrl.set(this.sanitizer.bypassSecurityTrustUrl(url));
      },
      error: () => this.rectoUrl.set(null)
    });

    if (hasVerso) {
      this.http.get(`/api/cheques/${chequeId}/image/verso`, { responseType: 'blob' }).subscribe({
        next: blob => {
          const url = URL.createObjectURL(blob);
          this.blobUrls.push(url);
          this.versoUrl.set(this.sanitizer.bypassSecurityTrustUrl(url));
        },
        error: () => this.versoUrl.set(null)
      });
    }
  }

  private initForm(cheque: Cheque) {
    this.treatmentForm = this.fb.group({
      chequeNumber:    [cheque.chequeNumber.value,    Validators.required],
      amountNumeric:   [cheque.amountNumeric.value,   [Validators.required, Validators.min(0)]],
      amountText:      [cheque.amountText.value,      Validators.required],
      emitterName:     [cheque.emitterName.value,     Validators.required],
      beneficiaryName: [cheque.beneficiaryName.value, Validators.required],
      date:            [cheque.date.value,            Validators.required],
      bank:            [cheque.bank.value,            Validators.required],
      rib:             [cheque.rib.value,             Validators.required],
      signatureValid:  [cheque.signatureValid.value,  Validators.requiredTrue]
    });
    this.cinBeneficiaire.set('');
    this.ribBeneficiaire.set('');
    this.beneficiaireType.set('individu');
    this.rejectMotif.set('');
    this.showRejectPanel.set(false);
    this.allowRouteLeave.set(false);
  }

  onSubmit() {
    if (this.treatmentForm.invalid || !this.cheque() || this.isSubmitting()) return;
    const cin = this.beneficiaireType() === 'individu' ? (this.cinBeneficiaire().trim() || undefined) : undefined;
    const rib = this.beneficiaireType() === 'societe'  ? (this.ribBeneficiaire().trim()  || undefined) : undefined;
    this.chequeService.completeCheque('VALIDATED', undefined, cin, rib).subscribe({
      next: () => {
        this.notificationService.show('Chèque validé et ajouté à l\'historique', 'success');
        this.chequeService.clearCurrentFlow();
        this.allowRouteLeave.set(true);
        this.router.navigate(['/scanner']);
      },
      error: () => this.notificationService.show('Erreur lors de la validation', 'error')
    });
  }

  onReject() {
    if (!this.cheque() || this.isSubmitting()) return;
    this.showRejectPanel.set(true);
  }

  confirmReject() {
    if (!this.cheque() || this.isSubmitting()) return;
    const motif = this.rejectMotif().trim() || undefined;
    const cin   = this.beneficiaireType() === 'individu' ? (this.cinBeneficiaire().trim() || undefined) : undefined;
    const rib   = this.beneficiaireType() === 'societe'  ? (this.ribBeneficiaire().trim()  || undefined) : undefined;
    this.chequeService.completeCheque('REJECTED', motif, cin, rib).subscribe({
      next: () => {
        this.notificationService.show('Chèque rejeté et ajouté à l\'historique', 'warning');
        this.chequeService.clearCurrentFlow();
        this.allowRouteLeave.set(true);
        this.router.navigate(['/scanner']);
      },
      error: () => this.notificationService.show('Erreur lors du rejet', 'error')
    });
  }

  cancelReject() {
    this.showRejectPanel.set(false);
    this.rejectMotif.set('');
  }

  async downloadRapportPdf() {
    const cheque = this.cheque();
    if (!cheque || this.isDownloadingPdf()) return;
    this.isDownloadingPdf.set(true);
    try {
      await this.pdfService.generateRapportCheque(cheque, this.qrInfo());
    } finally {
      this.isDownloadingPdf.set(false);
    }
  }

}
