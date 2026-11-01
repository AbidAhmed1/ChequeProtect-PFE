import { Injectable, computed, inject, signal, PLATFORM_ID } from '@angular/core';
import { isPlatformBrowser } from '@angular/common';
import { HttpClient, HttpParams } from '@angular/common/http';
import { Observable, catchError, delay, map, of, switchMap, tap, throwError, timer } from 'rxjs';
import {
  API_CONFIG, API,
  BackendChequeDTO, ChequeHistoryItemDTO,
  PagedHistoryResponse, ValiderChequeRequest, HistoryFilter,
  ChequeStatus as BackendStatus, AiResult
} from '../constants/api-contract';
import { AiPhaseResult, Cheque, ChequeStatus, OCRField } from '../models/cheque.model';

type EditableChequeFields = Pick<Cheque,
  'chequeNumber' | 'amountNumeric' | 'amountText' | 'emitterName' |
  'beneficiaryName' | 'date' | 'bank' | 'rib' | 'signatureValid'>;

type ChequeFormData = { [K in keyof EditableChequeFields]: EditableChequeFields[K]['value'] };

@Injectable({ providedIn: 'root' })
export class ChequeService {
  private http       = inject(HttpClient);
  private platformId = inject(PLATFORM_ID);
  private isBrowser  = isPlatformBrowser(this.platformId);

  readonly currentScannedCheque = signal<Cheque | null>(null);
  readonly currentOcrResult     = signal<Cheque | null>(null);
  readonly isProcessing         = signal<boolean>(false);
  readonly isSavingDecision     = signal<boolean>(false);
  readonly error                = signal<string | null>(null);
  readonly history              = signal<Cheque[]>([]);

  readonly processedTodayCount = computed(() =>
    this.history().filter(c =>
      new Date(c.uploadDate).toDateString() === new Date().toDateString()
    ).length
  );
  readonly lastProcessedCheque = computed(() => this.history()[0] ?? null);

  // ── Upload & OCR ──────────────────────────────────────────────────────────

  processChequeImage(recto: File, verso: File): Observable<Cheque> {
    this.isProcessing.set(true);
    this.error.set(null);
    this.currentOcrResult.set(null);

    if (API_CONFIG.USE_MOCK) {
      return this.mockProcessImage(recto);
    }

    const formData = new FormData();
    formData.append('recto', recto);
    formData.append('verso', verso);
    formData.append('source', 'WEB');

    return this.http
      .post<BackendChequeDTO>(`${API_CONFIG.BASE_URL}${API.CHEQUES.UPLOAD}`, formData)
      .pipe(
        switchMap(dto => this.pollUntilReady(dto.id)),
        tap(cheque => {
          this.isProcessing.set(false);
          this.currentScannedCheque.set(cheque);
          this.currentOcrResult.set(cheque);
        }),
        catchError(err => {
          this.isProcessing.set(false);
          this.error.set(err?.error?.message ?? 'Erreur lors du traitement du chèque');
          return throwError(() => err);
        })
      );
  }

  // ── Validate / Reject ─────────────────────────────────────────────────────

  completeCheque(
    status: Exclude<ChequeStatus, 'PENDING'>,
    motif?: string,
    cinBeneficiaire?: string,
    ribBeneficiaire?: string
  ): Observable<Cheque> {
    const cheque = this.currentScannedCheque();
    if (!cheque) {
      this.error.set('Aucun chèque en cours de traitement.');
      return throwError(() => new Error('Aucun chèque en cours de traitement.'));
    }
    if (this.isSavingDecision()) return of(cheque);

    this.isSavingDecision.set(true);

    if (API_CONFIG.USE_MOCK) {
      return this.mockCompleteCheque(cheque, status);
    }

    const payload: ValiderChequeRequest = {
      decision: status === 'VALIDATED' ? 'VALIDE' : 'REJETE',
      ...(motif            ? { motif }           : {}),
      ...(cinBeneficiaire  ? { cinBeneficiaire } : {}),
      ...(ribBeneficiaire  ? { ribBeneficiaire } : {})
    };

    return this.http
      .post<BackendChequeDTO>(
        `${API_CONFIG.BASE_URL}${API.CHEQUES.VALIDER(cheque.id)}`,
        payload
      )
      .pipe(
        map(dto => this.mapBackendCheque(dto)),
        tap(processed => {
          this.isSavingDecision.set(false);
          this.addToHistory(processed);
        }),
        catchError(err => {
          this.isSavingDecision.set(false);
          this.error.set(err?.error?.message ?? 'Erreur lors de la validation');
          return throwError(() => err);
        })
      );
  }

  // ── History ───────────────────────────────────────────────────────────────

  getHistory(filters?: HistoryFilter): Observable<Cheque[]> {
    if (API_CONFIG.USE_MOCK) {
      return of(this.history()).pipe(delay(900));
    }

    const params = this.toHttpParams(filters ?? {});
    return this.http
      .get<PagedHistoryResponse<ChequeHistoryItemDTO>>(
        `${API_CONFIG.BASE_URL}${API.CHEQUES.AGENT_HISTORY}`,
        { params }
      )
      .pipe(
        map(res => res.content.map(dto => this.mapHistoryDto(dto))),
        tap(cheques => this.history.set(cheques)),
        catchError(() => of(this.history()))
      );
  }

  getAdminHistory(filters?: HistoryFilter): Observable<PagedHistoryResponse<ChequeHistoryItemDTO>> {
    const empty: PagedHistoryResponse<ChequeHistoryItemDTO> = {
      content: [], totalElements: 0, totalPages: 0, currentPage: 0, pageSize: 20,
      hasNext: false, hasPrevious: false
    };

    if (API_CONFIG.USE_MOCK) return of(empty).pipe(delay(800));

    const params = this.toHttpParams(filters ?? {});
    return this.http
      .get<PagedHistoryResponse<ChequeHistoryItemDTO>>(
        `${API_CONFIG.BASE_URL}${API.CHEQUES.ADMIN_HISTORY}`,
        { params }
      )
      .pipe(catchError(() => of(empty)));
  }

  // ── Load single cheque with AI results (mobile panel click) ──────────────

  loadChequeWithAiResults(id: string): Observable<Cheque> {
    return this.http
      .get<BackendChequeDTO>(`${API_CONFIG.BASE_URL}${API.CHEQUES.BY_ID(id)}`)
      .pipe(
        switchMap(dto => {
          const cheque = this.mapBackendCheque(dto);
          return this.http
            .get<AiResult[]>(`${API_CONFIG.BASE_URL}${API.CHEQUES.AI_RESULTS(id)}`)
            .pipe(
              map(results => ({
                ...cheque,
                aiPhases: results.map(r => ({
                  phase:      r.phase,
                  score:      r.score,
                  passed:     r.passed,
                  decision:   r.decision,
                  durationMs: r.durationMs
                } as AiPhaseResult))
              })),
              catchError(() => of(cheque))
            );
        }),
        tap(cheque => {
          this.currentScannedCheque.set(cheque);
          this.currentOcrResult.set(cheque);
          this.isProcessing.set(false);
        }),
        catchError(err => {
          this.error.set(err?.error?.message ?? 'Erreur lors du chargement du chèque');
          return throwError(() => err);
        })
      );
  }

  // ── Reprocess asynchrone : lance le pipeline, poll jusqu'à la fin ────────
  //
  // 1. POST /reprocess → retourne immédiatement avec status EN_TRAITEMENT
  // 2. Poll GET /{id} toutes les 4 secondes jusqu'à status != EN_TRAITEMENT
  // 3. Charge les résultats IA et émet le chèque final

  startReprocessAndPoll(id: string): Observable<Cheque> {
    this.isProcessing.set(true);

    return this.http
      .post<BackendChequeDTO>(`${API_CONFIG.BASE_URL}${API.CHEQUES.REPROCESS(id)}`, {})
      .pipe(
        switchMap(() => this.pollUntilReady(id)),
        tap(cheque => {
          this.isProcessing.set(false);
          this.currentScannedCheque.set(cheque);
          this.currentOcrResult.set(cheque);
        }),
        catchError(err => {
          this.isProcessing.set(false);
          this.error.set(err?.error?.message ?? 'Erreur lors du retraitement');
          return throwError(() => err);
        })
      );
  }

  private pollUntilReady(id: string): Observable<Cheque> {
    return new Observable<Cheque>(observer => {
      let attempts = 0;
      const MAX_ATTEMPTS = 75; // 75 × 4 s = 5 min max

      const poll = () => {
        if (++attempts > MAX_ATTEMPTS) {
          observer.error(new Error('Le traitement a pris trop de temps. Veuillez réessayer.'));
          return;
        }

        this.http.get<BackendChequeDTO>(`${API_CONFIG.BASE_URL}${API.CHEQUES.BY_ID(id)}`)
          .subscribe({
            next: dto => {
              if (dto.status !== 'EN_TRAITEMENT') {
                // Pipeline terminé — charger les résultats IA
                this.http.get<AiResult[]>(`${API_CONFIG.BASE_URL}${API.CHEQUES.AI_RESULTS(id)}`)
                  .pipe(catchError(() => of([] as AiResult[])))
                  .subscribe(results => {
                    const cheque: Cheque = {
                      ...this.mapBackendCheque(dto),
                      aiPhases: results.map(r => ({
                        phase:      r.phase,
                        score:      r.score,
                        passed:     r.passed,
                        decision:   r.decision,
                        durationMs: r.durationMs
                      } as AiPhaseResult))
                    };
                    observer.next(cheque);
                    observer.complete();
                  });
              } else {
                // Toujours EN_TRAITEMENT → re-poll dans 4 s
                setTimeout(poll, 4000);
              }
            },
            error: err => observer.error(err)
          });
      };
      poll();
    });
  }

  // ── Pending cheques (Agent queue) ─────────────────────────────────────────

  getPendingCheques(): Observable<Cheque[]> {
    if (API_CONFIG.USE_MOCK) return of([]).pipe(delay(800));

    return this.http
      .get<BackendChequeDTO[]>(`${API_CONFIG.BASE_URL}${API.CHEQUES.EN_ATTENTE}`)
      .pipe(
        map(dtos => dtos.map(dto => this.mapBackendCheque(dto))),
        catchError(() => of([]))
      );
  }

  // ── State helpers ─────────────────────────────────────────────────────────

  setCurrentCheque(cheque: Cheque): void {
    this.currentScannedCheque.set(cheque);
    this.currentOcrResult.set(cheque);
    this.isProcessing.set(false);
  }

  clearCurrentFlow(): void {
    this.currentScannedCheque.set(null);
    this.currentOcrResult.set(null);
    this.isProcessing.set(false);
    this.isSavingDecision.set(false);
    this.error.set(null);
  }

  // ── Private helpers ───────────────────────────────────────────────────────

  private addToHistory(cheque: Cheque): void {
    this.history.update(list => {
      const idx = list.findIndex(c => c.id === cheque.id);
      if (idx >= 0) { const copy = [...list]; copy[idx] = cheque; return copy; }
      return [cheque, ...list];
    });
  }

  /** Map backend status → frontend ChequeStatus */
  private mapStatus(backendStatus: BackendStatus): ChequeStatus {
    switch (backendStatus) {
      case 'EN_ATTENTE':
      case 'EN_TRAITEMENT': return 'PENDING';
      case 'VALIDE':        return 'VALIDATED';
      case 'REJETE':
      case 'FRAUDE_DETECTEE': return 'REJECTED';
      default: return 'PENDING';
    }
  }

  private mapBackendCheque(dto: BackendChequeDTO): Cheque {
    const score = dto.aiScoreGlobal ?? 0.85;
    return {
      id:               dto.id,
      imagePath:        dto.imageRectoUrl ?? '',
      hasVerso:         dto.imageVersoUrl != null,
      uploadDate:       dto.createdAt ?? new Date().toISOString(),
      status:           this.mapStatus(dto.status),
      source:           dto.source,
      chequeNumber:     { value: dto.numeroCheque    ?? '',    confidence: score },
      amountNumeric:    { value: dto.montantExtrait  ?? 0,     confidence: score },
      amountText:       { value: dto.montantLettres  ?? '',    confidence: score },
      emitterName:      { value: dto.emetteurNom     ?? '',    confidence: score },
      beneficiaryName:  { value: dto.beneficiaireNom ?? '',    confidence: score },
      date:             { value: dto.dateEmission    ?? new Date().toISOString().slice(0, 10), confidence: score },
      bank:             { value: '',                           confidence: score },
      rib:              { value: dto.ribEmetteur     ?? '',    confidence: score },
      signatureValid:   { value: !dto.fraudeDetectee,         confidence: score },
      overallConfidence: score,
      qrData:           dto.qrData ?? null
    };
  }

  private mapHistoryDto(dto: ChequeHistoryItemDTO): Cheque {
    const score = (dto.scoreOcr ?? 0) / 100;
    return {
      id:               dto.id,
      imagePath:        '',
      uploadDate:       dto.dateTraitement,
      status:           this.mapStatus(dto.statut),
      chequeNumber:     { value: dto.numeroCheque    ?? '',    confidence: score },
      amountNumeric:    { value: dto.montant         ?? 0,     confidence: score },
      amountText:       { value: '',                           confidence: score },
      emitterName:      { value: '',                           confidence: score },
      beneficiaryName:  { value: dto.beneficiaireNom ?? '',    confidence: score },
      date:             { value: dto.dateTraitement.slice(0, 10), confidence: score },
      bank:             { value: '',                           confidence: score },
      rib:              { value: dto.ribEmetteur     ?? '',    confidence: score },
      signatureValid:   { value: !dto.fraudeDetectee,         confidence: score },
      overallConfidence: score
    };
  }

  private toHttpParams(filters: HistoryFilter): HttpParams {
    let params = new HttpParams();
    Object.entries(filters).forEach(([key, value]) => {
      if (value !== undefined && value !== null && value !== '') {
        params = params.set(key, String(value));
      }
    });
    return params;
  }

  private updateField<T>(field: OCRField<T>, value: T | undefined): OCRField<T> {
    return value === undefined ? field : { ...field, value, isManuallyVerified: true };
  }

  // ── Mock fallbacks ────────────────────────────────────────────────────────

  private mockProcessImage(file: File): Observable<Cheque> {
    const low = Math.random() > 0.65;
    const cheque: Cheque = {
      id:              `CHQ-${Math.random().toString(36).slice(2, 9).toUpperCase()}`,
      imagePath:       URL.createObjectURL(file),
      uploadDate:      new Date().toISOString(),
      status:          'PENDING',
      chequeNumber:    { value: `${Math.floor(1000000 + Math.random() * 8999999)}`, confidence: 0.98 },
      amountNumeric:   { value: Number((400 + Math.random() * 7000).toFixed(3)),    confidence: 0.93 },
      amountText:      { value: 'Montant détecté automatiquement', confidence: low ? 0.74 : 0.91 },
      emitterName:     { value: low ? 'SOCIETE ?' : 'SOCIETE ALPHA TUNISIE',        confidence: low ? 0.59 : 0.94 },
      beneficiaryName: { value: 'RAED ABID',  confidence: 0.88 },
      date:            { value: new Date().toISOString().slice(0, 10), confidence: 0.97 },
      bank:            { value: 'BIAT',        confidence: 0.99 },
      rib:             { value: '08 123 4567890123456 78', confidence: 0.96 },
      signatureValid:  { value: true, confidence: low ? 0.67 : 0.90 },
      overallConfidence: low ? 0.73 : 0.92
    };
    return of(cheque).pipe(
      delay(1700),
      tap(() => this.isProcessing.set(false))
    );
  }

  private mockCompleteCheque(
    cheque: Cheque,
    status: Exclude<ChequeStatus, 'PENDING'>
  ): Observable<Cheque> {
    const processed: Cheque = { ...cheque, status, uploadDate: new Date().toISOString() };
    return of(processed).pipe(
      delay(1200),
      tap(() => {
        this.isSavingDecision.set(false);
        this.addToHistory(processed);
      })
    );
  }
}
