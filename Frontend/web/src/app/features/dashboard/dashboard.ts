import { Component } from '@angular/core';
import { CommonModule } from '@angular/common';

@Component({
  selector: 'app-dashboard',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './dashboard.html',
  styleUrl: './dashboard.css'
})
export class DashboardComponent {
  dateDuJour = new Date().toLocaleDateString('fr-FR', {
    weekday: 'long',
    year: 'numeric',
    month: 'long',
    day: 'numeric'
  });

  // Statistiques du haut
  stats = {
    traites: { count: '1,284', trend: '+12%' },
    valides: { count: '1,156', trend: '+9%' },
    rejetes: { count: '98', trend: '-3%' },
    attente: { count: '30', trend: '+5' }
  };

  // Liste des chèques récents
  chequesRecents = [
    { id: 'CHQ-001', nom: 'Mohamed rayen', banque: 'BTE', montant: '12 500,000 dt', date: '18/02/2026', score: 98, statut: 'Validé', cssClass: 'valide' },
    { id: 'CHQ-002', nom: 'Wajih yahyaoui', banque: 'BTK', montant: '3 200,000 dt', date: '18/02/2026', score: null, statut: 'En analyse', cssClass: 'analyse' },
    { id: 'CHQ-003', nom: 'Raed Amri', banque: 'STB', montant: '87 000,00 dt', date: '17/02/2026', score: 23, statut: 'Fraude détectée', cssClass: 'fraude' }
  ];

  // Performances de l'IA
  aiPerformance = {
    globalScore: 97.3,
    details: [
      { label: 'Détection fraude', score: 96, color: '#dc2626' }, // Rouge
      { label: 'Validation OCR', score: 99, color: '#16a34a' },   // Vert
      { label: 'Vérif. signature', score: 94, color: '#3b82f6' }  // Bleu
    ],
    stats: {
      tempsMoyen: '2.3s',
      uptime: '99.98%',
      fileAttente: '30 chèques'
    }
  };
}
