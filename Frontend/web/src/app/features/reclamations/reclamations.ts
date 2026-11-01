import { Component, inject, OnInit, signal, computed } from '@angular/core';
import { CommonModule } from '@angular/common';
import { AdminService } from '../../core/services/admin.service';
import { ReclamationDTO } from '../../core/constants/api-contract';
import { NotificationService } from '../../core/services/notification.service';

type ReclamationStatut = 'OUVERTE' | 'EN_COURS' | 'TRANSMISE' | 'RESOLUE' | 'FERMEE';

@Component({
  selector: 'app-reclamations',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './reclamations.html',
  styleUrl: './reclamations.scss'
})
export class ReclamationsComponent implements OnInit {
  private adminService        = inject(AdminService);
  private notificationService = inject(NotificationService);

  isLoading    = signal<boolean>(true);
  reclamations = signal<ReclamationDTO[]>([]);
  filterStatut = signal<string>('');
  transmitting = signal<string | null>(null);   // id en cours de transmission

  filtered = computed(() => {
    const s    = this.filterStatut();
    const list = this.reclamations();
    return s ? list.filter(r => r.statut === s) : list;
  });

  counts = computed(() => {
    const list = this.reclamations();
    return {
      total:      list.length,
      ouvertes:   list.filter(r => r.statut === 'OUVERTE').length,
      enCours:    list.filter(r => r.statut === 'EN_COURS').length,
      transmises: list.filter(r => r.statut === 'TRANSMISE').length,
      resolues:   list.filter(r => r.statut === 'RESOLUE').length,
    };
  });

  ngOnInit() { this.load(); }

  load() {
    this.isLoading.set(true);
    this.adminService.getReclamations().subscribe(data => {
      this.reclamations.set(data);
      this.isLoading.set(false);
    });
  }

  canTransmit(r: ReclamationDTO): boolean {
    return r.statut === 'OUVERTE' || r.statut === 'EN_COURS';
  }

  transmit(id: string) {
    if (this.transmitting()) return;
    this.transmitting.set(id);
    this.adminService.transmitReclamation(id).subscribe({
      next: () => {
        this.transmitting.set(null);
        this.reclamations.update(list =>
          list.map(r => r.id === id ? { ...r, statut: 'TRANSMISE' as ReclamationStatut } : r)
        );
        this.notificationService.show(
          'Réclamation envoyée. Le client a été notifié.',
          'success'
        );
      },
      error: () => {
        this.transmitting.set(null);
        this.notificationService.show('Erreur lors de la transmission.', 'error');
      }
    });
  }

  setFilter(statut: string) { this.filterStatut.set(statut); }

  statutLabel(statut: string): string {
    const map: Record<string, string> = {
      OUVERTE:   'Ouverte',
      EN_COURS:  'En cours',
      TRANSMISE: 'Traitée',
      RESOLUE:   'Résolue',
      FERMEE:    'Clôturée',
    };
    return map[statut] ?? statut;
  }

  formatDate(iso: string): string {
    if (!iso) return '—';
    return new Date(iso).toLocaleString('fr-FR', {
      day: '2-digit', month: '2-digit', year: 'numeric',
      hour: '2-digit', minute: '2-digit'
    });
  }
}
