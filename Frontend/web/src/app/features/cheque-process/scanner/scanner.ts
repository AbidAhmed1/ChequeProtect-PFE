import { Component, OnDestroy, OnInit, computed, inject, signal } from '@angular/core';
import { CommonModule, DatePipe } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { Router } from '@angular/router';
import { ChequeService } from '../../../core/services/cheque.service';
import { NotificationService } from '../../../core/services/notification.service';
import { Cheque } from '../../../core/models/cheque.model';

@Component({
  selector: 'app-scanner',
  standalone: true,
  imports: [CommonModule, DatePipe, FormsModule],
  templateUrl: './scanner.html',
  styleUrl: './scanner.scss'
})
export class ScannerComponent implements OnInit, OnDestroy {
  private chequeService = inject(ChequeService);
  private notificationService = inject(NotificationService);
  private router = inject(Router);

  currentStep = signal<'idle' | 'scanning' | 'analyzing' | 'completed'>('idle');
  scanProgress = signal<number>(0);
  isDragging = signal<boolean>(false);

  rectoFile = signal<File | null>(null);
  versoFile = signal<File | null>(null);
  isDraggingRecto = signal<boolean>(false);
  isDraggingVerso = signal<boolean>(false);
  canSubmit = computed(() => this.rectoFile() !== null && this.versoFile() !== null);

  processedCheque = this.chequeService.currentScannedCheque;
  processedTodayCount = this.chequeService.processedTodayCount;
  lastProcessedCheque = this.chequeService.lastProcessedCheque;

  pendingCheques   = signal<Cheque[]>([]);
  isLoadingPending = signal<boolean>(false);
  openingChequeId  = signal<string | null>(null);
  filterDate       = signal<string>('');

  filteredCheques = computed(() => {
    const date = this.filterDate().trim();
    const all  = this.pendingCheques();
    if (!date) return all;
    return all.filter(c => c.uploadDate.startsWith(date));
  });

  private refreshInterval: ReturnType<typeof setInterval> | null = null;

  ngOnInit() {
    this.loadPendingCheques();
    this.refreshInterval = setInterval(() => this.loadPendingCheques(), 30_000);
  }

  ngOnDestroy() {
    if (this.refreshInterval) clearInterval(this.refreshInterval);
  }

  loadPendingCheques() {
    this.isLoadingPending.set(true);
    this.chequeService.getPendingCheques().subscribe({
      next: (cheques) => {
        this.pendingCheques.set(cheques.filter(c => c.source === 'MOBILE'));
        this.isLoadingPending.set(false);
      },
      error: () => this.isLoadingPending.set(false)
    });
  }

  openMobileCheque(cheque: Cheque) {
    if (this.openingChequeId()) return;
    this.openingChequeId.set(cheque.id);
    this.chequeService.clearCurrentFlow();

    // Phase 1 : animation "Numérisation" jusqu'à 40%
    this.currentStep.set('scanning');
    this.scanProgress.set(0);

    const scanInterval = setInterval(() => {
      this.scanProgress.update(v => v + 8);
      if (this.scanProgress() >= 40) {
        clearInterval(scanInterval);

        // Phase 2 : "Analyse OCR" — lancer le vrai pipeline IA
        this.currentStep.set('analyzing');

        // Progression lente pendant que le pipeline tourne (40% → 97%)
        // Atteint 90% en ~30 s, puis rampe très lente jusqu'à 97% pour montrer l'activité
        const analyzeInterval = setInterval(() => {
          this.scanProgress.update(v => {
            if (v < 90) return v + 1;
            if (v < 97) return Math.min(v + 0.05, 97);
            return v;
          });
        }, 600);

        this.chequeService.startReprocessAndPoll(cheque.id).subscribe({
          next: () => {
            clearInterval(analyzeInterval);
            this.openingChequeId.set(null);
            this.scanProgress.set(100);
            this.currentStep.set('completed');
            setTimeout(() => this.router.navigate(['/traitement-cheques']), 600);
          },
          error: () => {
            clearInterval(analyzeInterval);
            this.openingChequeId.set(null);
            this.notificationService.show('Erreur lors du traitement du chèque', 'error');
            this.reset();
          }
        });
      }
    }, 150);
  }

  onDragOver(event: DragEvent) { event.preventDefault(); this.isDragging.set(true); }
  onDragLeave(event: DragEvent) { event.preventDefault(); this.isDragging.set(false); }
  onDrop(event: DragEvent) { event.preventDefault(); this.isDragging.set(false); }

  onDragOverRecto(e: DragEvent)  { e.preventDefault(); this.isDraggingRecto.set(true); }
  onDragLeaveRecto(e: DragEvent) { e.preventDefault(); this.isDraggingRecto.set(false); }
  onDropRecto(e: DragEvent) {
    e.preventDefault(); this.isDraggingRecto.set(false);
    const f = e.dataTransfer?.files?.[0];
    if (f) this.setRecto(f);
  }
  onRectoSelected(e: Event) {
    const f = (e.target as HTMLInputElement).files?.[0];
    if (f) this.setRecto(f);
  }

  onDragOverVerso(e: DragEvent)  { e.preventDefault(); this.isDraggingVerso.set(true); }
  onDragLeaveVerso(e: DragEvent) { e.preventDefault(); this.isDraggingVerso.set(false); }
  onDropVerso(e: DragEvent) {
    e.preventDefault(); this.isDraggingVerso.set(false);
    const f = e.dataTransfer?.files?.[0];
    if (f) this.setVerso(f);
  }
  onVersoSelected(e: Event) {
    const f = (e.target as HTMLInputElement).files?.[0];
    if (f) this.setVerso(f);
  }

  private validateFormat(file: File): boolean {
    if (!file.type.startsWith('image/') && file.type !== 'application/pdf') {
      this.notificationService.show('Format non supporté. Utilisez JPG, PNG ou PDF.', 'error');
      return false;
    }
    return true;
  }

  private setRecto(file: File) { if (this.validateFormat(file)) this.rectoFile.set(file); }
  private setVerso(file: File) { if (this.validateFormat(file)) this.versoFile.set(file); }

  removeRecto(e: MouseEvent) { e.stopPropagation(); this.rectoFile.set(null); }
  removeVerso(e: MouseEvent) { e.stopPropagation(); this.versoFile.set(null); }

  launchAnalysis() {
    const recto = this.rectoFile();
    const verso = this.versoFile();
    if (!recto || !verso) return;
    this.chequeService.clearCurrentFlow();
    this.startScanProcess(recto, verso);
  }

  private startScanProcess(recto: File, verso: File) {
    this.currentStep.set('scanning');
    this.scanProgress.set(0);

    // Phase 1: scan animation up to 40%
    const scanInterval = setInterval(() => {
      this.scanProgress.update(v => v + 8);
      if (this.scanProgress() >= 40) {
        clearInterval(scanInterval);

        // Phase 2: upload + pipeline (polls until AI finishes)
        this.currentStep.set('analyzing');

        const analyzeInterval = setInterval(() => {
          this.scanProgress.update(v => {
            if (v < 90) return v + 1;
            if (v < 97) return Math.min(v + 0.05, 97);
            return v;
          });
        }, 600);

        this.chequeService.processChequeImage(recto, verso).subscribe({
          next: (cheque) => {
            clearInterval(analyzeInterval);
            this.chequeService.setCurrentCheque(cheque);
            this.scanProgress.set(100);
            this.currentStep.set('completed');
            setTimeout(() => this.router.navigate(['/traitement-cheques']), 600);
          },
          error: (err) => {
            clearInterval(analyzeInterval);
            console.error('Upload error:', err);
            this.notificationService.show(
              'Erreur lors du traitement du chèque. Vérifiez votre connexion et réessayez.',
              'error'
            );
            this.reset();
          }
        });
      }
    }, 150);
  }

  validateCheque() { this.router.navigate(['/traitement-cheques']); }
  reset() {
    this.chequeService.clearCurrentFlow();
    this.currentStep.set('idle');
    this.scanProgress.set(0);
    this.rectoFile.set(null);
    this.versoFile.set(null);
  }
}
