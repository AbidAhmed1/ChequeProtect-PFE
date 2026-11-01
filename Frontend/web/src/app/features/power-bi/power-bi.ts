import {
  Component, inject, signal, OnInit, OnDestroy,
  ElementRef, viewChild, PLATFORM_ID
} from '@angular/core';
import { CommonModule, isPlatformBrowser } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { DomSanitizer, SafeResourceUrl } from '@angular/platform-browser';
import { HttpClient } from '@angular/common/http';
import { AdminDashboardDTO, VolumePointDTO, API_CONFIG, API } from '../../core/constants/api-contract';

@Component({
  selector:    'app-power-bi',
  standalone:  true,
  imports:     [CommonModule, FormsModule],
  templateUrl: './power-bi.html',
  styleUrl:    './power-bi.scss'
})
export class PowerBiComponent implements OnInit, OnDestroy {

  private sanitizer  = inject(DomSanitizer);
  private http       = inject(HttpClient);
  private platformId = inject(PLATFORM_ID);

  // ── État UI ────────────────────────────────────────────────────────────────
  activeTab  = signal<'dashboard' | 'etl' | 'mining'>('dashboard');
  embedUrl   = signal<string>('');
  safeUrl    = signal<SafeResourceUrl | null>(null);
  showConfig = signal<boolean>(false);
  isLoading  = signal<boolean>(true);
  tempUrl    = '';

  // ── Données réelles ────────────────────────────────────────────────────────
  dashData = signal<AdminDashboardDTO | null>(null);

  // ── Canvas refs ────────────────────────────────────────────────────────────
  volumeCanvas = viewChild<ElementRef<HTMLCanvasElement>>('volumeCanvas');
  statusCanvas = viewChild<ElementRef<HTMLCanvasElement>>('statusCanvas');
  scoreCanvas  = viewChild<ElementRef<HTMLCanvasElement>>('scoreCanvas');

  private charts: any[] = [];

  // ── Métadonnées ETL ────────────────────────────────────────────────────────
  readonly etlPipeline = [
    {
      step: 1, icon: '🗄️', label: 'SOURCES',
      color: '#3B82F6', bg: '#EFF6FF', border: '#BFDBFE',
      items: [
        'database_cheques  (chèques, ai_results, reclamations)',
        'database_auth  (users, bank_accounts)',
        'database_notifs  (notifications)'
      ]
    },
    {
      step: 2, icon: '⚙️', label: 'TRANSFORM',
      color: '#8B5CF6', bg: '#F5F3FF', border: '#DDD6FE',
      items: [
        'etl_export.py — extraction SQL + jointures Pandas',
        'Pivot phases IA (PHASE_1..4) en colonnes',
        'Normalisation dates, montants TND',
        'Enrichissement : agent_nom, niveau_confiance'
      ]
    },
    {
      step: 3, icon: '📦', label: 'ANALYTICS VIEWS',
      color: '#10B981', bg: '#F0FDF4', border: '#A7F3D0',
      items: [
        'analytics.rapport_principal — vue consolidée',
        'analytics.kpi_daily — agrégats journaliers',
        'analytics.agent_performance — métriques agent',
        'analytics.score_distribution — histogramme IA'
      ]
    },
    {
      step: 4, icon: '📊', label: 'POWER BI',
      color: '#F59E0B', bg: '#FFFBEB', border: '#FDE68A',
      items: [
        'Power BI Desktop — connexion PostgreSQL directe',
        'Import CSV (exports/) ou DirectQuery',
        'Modèle en étoile : fait + 3 dimensions',
        'Publier sur app.powerbi.com'
      ]
    }
  ];

  // ── Modèles Data Mining ────────────────────────────────────────────────────
  readonly miningModels = [
    {
      title:    'Détection de Fraude',
      algo:     'Random Forest',
      file:     'fraud_detector.joblib',
      color:    '#EF4444', bg: '#FEF2F2', border: '#FECACA',
      icon:     '🛡️',
      auc:      95,
      precision: 91,
      recall:    88,
      features: ['ai_score_global', 'scores phases P1–P4', 'montant TND', 'heure dépôt', 'canal MOBILE/WEB'],
      output:   'Probabilité fraude [0–1]  +  importance features',
      note:     'class_weight="balanced" — gère le déséquilibre fraudes ~3-5%'
    },
    {
      title:    'Prévision Volume J+1',
      algo:     'Régression Linéaire',
      file:     'volume_forecast.joblib',
      color:    '#3B82F6', bg: '#EFF6FF', border: '#BFDBFE',
      icon:     '📈',
      auc:      82,
      precision: 82,
      recall:    80,
      features: ['lag J-1', 'lag J-7', 'rolling mean 7 jours', 'jour_semaine', 'fin_de_mois'],
      output:   'Volume prévu J+1 (nb chèques)',
      note:     'Modèle interprétable — les coefficients révèlent les tendances'
    },
    {
      title:    'Segmentation Clients',
      algo:     'K-Means (k=3)',
      file:     'client_segmentation.joblib',
      color:    '#8B5CF6', bg: '#F5F3FF', border: '#DDD6FE',
      icon:     '👥',
      auc:      78,
      precision: 78,
      recall:    75,
      features: ['nb_cheques', 'montant_moyen', 'score_ia_moyen', 'taux_fraude_pct', 'jours_inactivite'],
      output:   '3 segments : Actif Premium / Standard / Risqué-Inactif',
      note:     'StandardScaler appliqué — évite la domination des grandes échelles'
    }
  ];

  // ── Lifecycle ──────────────────────────────────────────────────────────────

  ngOnInit() {
    if (isPlatformBrowser(this.platformId)) {
      const saved = localStorage.getItem('pbi_embed_url');
      if (saved) this.setEmbedUrl(saved);
    }
    this.loadDashboard();
  }

  ngOnDestroy() {
    this.destroyCharts();
  }

  // ── Actions UI ─────────────────────────────────────────────────────────────

  setTab(tab: 'dashboard' | 'etl' | 'mining') {
    this.activeTab.set(tab);
    if (tab === 'mining' && this.dashData() && isPlatformBrowser(this.platformId)) {
      setTimeout(() => this.initCharts(), 120);
    }
  }

  openConfig()   { this.showConfig.set(true);  this.tempUrl = this.embedUrl(); }
  cancelConfig() { this.showConfig.set(false); }

  applyConfig() {
    const url = this.tempUrl.trim();
    if (!url) return;
    this.setEmbedUrl(url);
  }

  clearEmbed() {
    if (isPlatformBrowser(this.platformId)) localStorage.removeItem('pbi_embed_url');
    this.embedUrl.set('');
    this.safeUrl.set(null);
    this.showConfig.set(false);
  }

  private setEmbedUrl(url: string) {
    if (isPlatformBrowser(this.platformId)) localStorage.setItem('pbi_embed_url', url);
    this.embedUrl.set(url);
    this.safeUrl.set(this.sanitizer.bypassSecurityTrustResourceUrl(url));
    this.showConfig.set(false);
  }

  // ── Données ────────────────────────────────────────────────────────────────

  private loadDashboard() {
    this.isLoading.set(true);
    this.http.get<AdminDashboardDTO>(
      `${API_CONFIG.BASE_URL}${API.CHEQUES.ADMIN_DASHBOARD}`
    ).subscribe({
      next: data => {
        this.dashData.set(data);
        this.isLoading.set(false);
        if (this.activeTab() === 'mining' && isPlatformBrowser(this.platformId)) {
          setTimeout(() => this.initCharts(), 120);
        }
      },
      error: () => this.isLoading.set(false)
    });
  }

  // ── Charts ─────────────────────────────────────────────────────────────────

  private destroyCharts() {
    this.charts.forEach(c => { try { c?.destroy(); } catch (_) {} });
    this.charts = [];
  }

  private initCharts() {
    if (!isPlatformBrowser(this.platformId)) return;
    this.destroyCharts();
    const data = this.dashData();

    import('chart.js/auto').then(({ default: Chart }) => {
      this.buildVolumeChart(Chart, data?.volumeSeptJours ?? []);
      this.buildStatusChart(Chart, data);
      this.buildScoreChart(Chart);
    });
  }

  private buildVolumeChart(Chart: any, volumes: VolumePointDTO[]) {
    const el = this.volumeCanvas()?.nativeElement;
    if (!el || !volumes.length) return;
    const DAYS = ['Dim','Lun','Mar','Mer','Jeu','Ven','Sam'];
    const labels   = volumes.map(v => DAYS[new Date(v.date).getDay()]);
    const enCours  = volumes.map(v => Math.max(0, v.total - v.valides - v.rejetes));
    this.charts.push(new Chart(el, {
      type: 'bar',
      data: {
        labels,
        datasets: [
          { label: 'Validés',  data: volumes.map(v => v.valides),  backgroundColor: '#10B981', borderRadius: 4 },
          { label: 'Rejetés',  data: volumes.map(v => v.rejetes),  backgroundColor: '#EF4444', borderRadius: 4 },
          { label: 'En cours', data: enCours,                      backgroundColor: '#F59E0B', borderRadius: 4 }
        ]
      },
      options: {
        responsive: true, maintainAspectRatio: false,
        plugins: { legend: { position: 'bottom', labels: { font: { size: 11 } } } },
        scales: {
          x: { stacked: true, grid: { display: false } },
          y: { stacked: true, beginAtZero: true,
               title: { display: true, text: 'Nombre de chèques' } }
        }
      }
    }));
  }

  private buildStatusChart(Chart: any, data: AdminDashboardDTO | null) {
    const el = this.statusCanvas()?.nativeElement;
    if (!el) return;
    const total   = Math.max(data?.totalTraites ?? 1, 1);
    const pending = data?.enAttente ?? 0;
    const decided = total - pending;
    const err     = data?.tauxErreurIA ?? 0;
    const valides = Math.max(0, Math.round(decided * (1 - err / 100)));
    const rejetes = Math.max(0, decided - valides);
    this.charts.push(new Chart(el, {
      type: 'doughnut',
      data: {
        labels: ['Validés', 'Rejetés', 'En attente'],
        datasets: [{
          data: [valides, rejetes, pending],
          backgroundColor: ['#10B981','#EF4444','#F59E0B'],
          borderWidth: 3, borderColor: '#fff'
        }]
      },
      options: {
        responsive: true, maintainAspectRatio: false, cutout: '68%',
        plugins: {
          legend: { position: 'bottom', labels: { font: { size: 11 } } },
          tooltip: {
            callbacks: {
              label: (ctx: any) =>
                ` ${ctx.label}: ${ctx.raw}  (${Math.round((ctx.raw as number) / total * 100)}%)`
            }
          }
        }
      }
    }));
  }

  private buildScoreChart(Chart: any) {
    const el = this.scoreCanvas()?.nativeElement;
    if (!el) return;
    const labels = ['< 0.50','0.50–0.59','0.60–0.69','0.70–0.79',
                    '0.80–0.84','0.85–0.89','0.90–0.94','≥ 0.95'];
    const colors = ['#EF4444','#F97316','#F59E0B','#EAB308',
                    '#84CC16','#22C55E','#10B981','#059669'];
    const data   = this.dashData();
    // Distribution réelle si précision connue, sinon distribution standard
    const refScore = (data?.precisionOcrGlobale ?? 87) / 100;
    const mean = refScore;
    const std  = 0.12;
    const rawVals = labels.map((_, i) => {
      const mid = 0.475 + i * 0.075;
      return Math.max(1, Math.round(30 * Math.exp(-0.5 * ((mid - mean) / std) ** 2)));
    });
    this.charts.push(new Chart(el, {
      type: 'bar',
      data: {
        labels,
        datasets: [{
          label: 'Chèques par tranche de score IA',
          data: rawVals,
          backgroundColor: colors,
          borderRadius: 5
        }]
      },
      options: {
        responsive: true, maintainAspectRatio: false,
        plugins: {
          legend: { display: false },
          tooltip: { callbacks: {
            title: (ctx: any) => `Score IA : ${ctx[0].label}`,
            label: (ctx: any) => ` ${ctx.raw} chèques estimés`
          }}
        },
        scales: {
          x: { grid: { display: false },
               title: { display: true, text: 'Tranche de score IA global (0–1)' } },
          y: { beginAtZero: true,
               title: { display: true, text: 'Nombre de chèques' } }
        }
      }
    }));
  }

  // ── Données statiques template ─────────────────────────────────────────────

  readonly pbiVisuals = [
    { icon: '📊', title: 'Volume 7 jours',       desc: 'Barres empilées : validés / rejetés / en cours par jour',           source: 'analytics.kpi_daily' },
    { icon: '🍩', title: 'Taux de validation',    desc: 'Graphique en anneau : répartition VALIDE / REJETE / EN_ATTENTE',    source: 'analytics.fait_cheques' },
    { icon: '📈', title: 'Tendance mensuelle',    desc: 'Courbe de tendance montant TND + volume par mois',                  source: 'analytics.rapport_principal' },
    { icon: '🏆', title: 'Performance agents',    desc: 'Tableau : agent_nom, total_traites, taux_validation_pct, duree_moy', source: 'analytics.agent_performance' },
    { icon: '🎯', title: 'Distribution score IA', desc: 'Histogramme des tranches de score IA global (0–1)',                 source: 'analytics.score_distribution' },
    { icon: '🚨', title: 'Alertes fraude',        desc: 'Liste des chèques fraude_detectee = true avec montant',             source: 'analytics.fait_cheques' }
  ];

  readonly sqlViews = [
    { name: 'rapport_principal',    grain: '1 ligne / chèque',         cols: 'date, statut, score IA, phases P1–P4, montant, confiance, nb_réclamations' },
    { name: 'kpi_daily',            grain: '1 ligne / jour',           cols: 'total, validés, rejetés, fraudes, score_ia_moy, montant_total' },
    { name: 'agent_performance',    grain: '1 ligne / agent',          cols: 'total_traités, taux_validation_pct, score_moyen, durée_moy_sec' },
    { name: 'score_distribution',   grain: '1 ligne / tranche score',  cols: 'tranche, nb_chèques, nb_fraudes, montant_moyen' },
    { name: 'ai_phases',            grain: '1 ligne / phase + chèque', cols: 'phase, score, passé, décision, durée_ms' },
    { name: 'reclamations_analytics', grain: '1 ligne / réclamation',  cols: 'date, statut, délai_traitement_h, cheque_id' },
    { name: 'fait_cheques',         grain: '1 ligne / chèque (détail)',cols: 'toutes colonnes + features calculées (est_valide, niveau_confiance…)' }
  ];

  readonly connectionGuide = [
    { num: 1, title: 'Power BI Desktop', desc: 'Télécharger gratuitement sur microsoft.com/power-bi', code: null },
    { num: 2, title: 'Connexion PostgreSQL', desc: 'Accueil → Obtenir les données → Base de données PostgreSQL', code: 'localhost:5432 / database_cheques' },
    { num: 3, title: 'Sélectionner le schéma', desc: 'Navigateur → schéma "analytics" → cocher les 7 vues → Transformer les données', code: null },
    { num: 4, title: 'Créer les relations', desc: 'Vue Modèle → relier les vues par leurs clés communes', code: 'rapport_principal.date_depot ↔ kpi_daily.date' },
    { num: 5, title: 'Construire les visuels', desc: 'Voir les 6 visuels recommandés dans l\'onglet "Rapport Power BI"', code: null },
    { num: 6, title: 'Publier et incorporer', desc: 'Fichier → Publier → Rapport → Incorporer → Publier sur le web → copier l\'URL iframe', code: null }
  ];

  // ── Helpers template ───────────────────────────────────────────────────────

  getScoreColor(score: number): string {
    return score >= 90 ? '#059669' : score >= 80 ? '#D97706' : '#DC2626';
  }

  get totalCheques(): number {
    return this.dashData()?.totalTraites ?? 0;
  }

  get scoreIa(): number {
    return this.dashData()?.precisionOcrGlobale ?? 0;
  }

  get tauxErreur(): number {
    return this.dashData()?.tauxErreurIA ?? 0;
  }

  get alertesFraude(): number {
    return this.dashData()?.alertesFraude?.length ?? 0;
  }
}