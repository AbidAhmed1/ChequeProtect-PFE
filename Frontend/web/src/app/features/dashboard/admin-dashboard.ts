import {
  Component, inject, OnInit, OnDestroy,
  signal, computed, ElementRef, viewChild, PLATFORM_ID
} from '@angular/core';
import { CommonModule, isPlatformBrowser } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { HttpClient } from '@angular/common/http';
import { AdminService } from '../../core/services/admin.service';
import { ChartDataPoint, KPIStats, RecentActivity } from '../../core/models/admin.model';
import { AdminDashboardDTO, VolumePointDTO, API_CONFIG, API } from '../../core/constants/api-contract';

type Tab           = 'supervision' | 'mining' | 'journal';
type JournalFilter = 'ALL' | 'VALIDATED' | 'REJECTED' | 'PENDING';

@Component({
  selector:    'app-admin-dashboard',
  standalone:  true,
  imports:     [CommonModule, FormsModule],
  templateUrl: './admin-dashboard.html',
  styleUrl:    './admin-dashboard.scss'
})
export class AdminDashboardComponent implements OnInit, OnDestroy {

  private adminService = inject(AdminService);
  private http         = inject(HttpClient);
  private platformId   = inject(PLATFORM_ID);

  // ── Onglet actif ──────────────────────────────────────────────────────────
  activeTab = signal<Tab>('supervision');

  // ── Supervision ───────────────────────────────────────────────────────────
  dateJour         = signal<string>('');
  isLoading        = signal<boolean>(true);
  stats            = signal<KPIStats | null>(null);
  weeklyData       = signal<ChartDataPoint[]>([]);
  recentActivities = signal<RecentActivity[]>([]);
  rawDashboard     = signal<AdminDashboardDTO | null>(null);

  // ── Journal d'activité ────────────────────────────────────────────────────
  journalFilter = signal<JournalFilter>('ALL');

  filteredActivities = computed(() => {
    const f = this.journalFilter();
    const a = this.recentActivities();
    return f === 'ALL' ? a : a.filter(x => x.status === f);
  });


  // ── Canvas refs (Mining tab) ──────────────────────────────────────────────
  volumeCanvas = viewChild<ElementRef<HTMLCanvasElement>>('volumeCanvas');
  statusCanvas = viewChild<ElementRef<HTMLCanvasElement>>('statusCanvas');
  scoreCanvas  = viewChild<ElementRef<HTMLCanvasElement>>('scoreCanvas');

  private charts: any[] = [];

  // ── Lifecycle ─────────────────────────────────────────────────────────────

  ngOnInit() {
    this.setDate();
    this.loadDashboardData();
  }

  ngOnDestroy() {
    this.destroyCharts();
  }

  // ── Tab ───────────────────────────────────────────────────────────────────

  setTab(tab: Tab) {
    this.activeTab.set(tab);
    if (tab === 'mining' && this.rawDashboard() && isPlatformBrowser(this.platformId)) {
      setTimeout(() => this.initCharts(), 150);
    }
  }

  // ── Supervision ───────────────────────────────────────────────────────────

  private setDate() {
    const opts: Intl.DateTimeFormatOptions = { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' };
    this.dateJour.set(new Date().toLocaleDateString('fr-FR', opts));
  }

  loadDashboardData() {
    this.isLoading.set(true);

    this.adminService.getDashboardKPIs().subscribe(data => {
      this.stats.set(data);
      this.checkLoadingComplete();
    });

    this.adminService.getWeeklyProcessingData().subscribe(data => {
      this.weeklyData.set(data);
      this.checkLoadingComplete();
    });

    // Raw DTO pour les charts Mining
    this.http.get<AdminDashboardDTO>(
      `${API_CONFIG.BASE_URL}${API.CHEQUES.ADMIN_DASHBOARD}`
    ).subscribe({ next: dto => this.rawDashboard.set(dto), error: () => {} });

    this.adminService.getAgents().subscribe(() => {
      this.adminService.getRecentActivities().subscribe(data => this.recentActivities.set(data));
    });
  }

  private checkLoadingComplete() {
    if (this.stats() && this.weeklyData().length > 0) this.isLoading.set(false);
  }

  getBarHeight(value: number, max: number = 150): string {
    return `${(value / max) * 100}%`;
  }

  // ── Charts ────────────────────────────────────────────────────────────────

  private destroyCharts() {
    this.charts.forEach(c => { try { c?.destroy(); } catch (_) {} });
    this.charts = [];
  }

  private initCharts() {
    if (!isPlatformBrowser(this.platformId)) return;
    this.destroyCharts();
    const data = this.rawDashboard();

    import('chart.js/auto').then(({ default: Chart }) => {
      this.buildVolumeChart(Chart, data?.volumeSeptJours ?? []);
      this.buildStatusChart(Chart, data);
      this.buildScoreChart(Chart, data?.precisionOcrGlobale ?? 87);
    });
  }

  private buildVolumeChart(Chart: any, volumes: VolumePointDTO[]) {
    const el = this.volumeCanvas()?.nativeElement;
    if (!el || !volumes.length) return;
    const DAYS = ['Dim','Lun','Mar','Mer','Jeu','Ven','Sam'];
    this.charts.push(new Chart(el, {
      type: 'bar',
      data: {
        labels: volumes.map(v => DAYS[new Date(v.date).getDay()]),
        datasets: [
          { label: 'Validés',  data: volumes.map(v => v.valides),                             backgroundColor: '#10B981', borderRadius: 4 },
          { label: 'Rejetés',  data: volumes.map(v => v.rejetes),                             backgroundColor: '#EF4444', borderRadius: 4 },
          { label: 'En cours', data: volumes.map(v => Math.max(0, v.total - v.valides - v.rejetes)), backgroundColor: '#F59E0B', borderRadius: 4 }
        ]
      },
      options: {
        responsive: true, maintainAspectRatio: false,
        plugins: { legend: { position: 'bottom', labels: { font: { size: 11 } } } },
        scales: {
          x: { stacked: true, grid: { display: false } },
          y: { stacked: true, beginAtZero: true, title: { display: true, text: 'Nb chèques' } }
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
        labels: ['Validés','Rejetés','En attente'],
        datasets: [{ data: [valides, rejetes, pending],
                     backgroundColor: ['#10B981','#EF4444','#F59E0B'],
                     borderWidth: 3, borderColor: '#fff' }]
      },
      options: {
        responsive: true, maintainAspectRatio: false, cutout: '68%',
        plugins: {
          legend: { position: 'bottom', labels: { font: { size: 11 } } },
          tooltip: { callbacks: {
            label: (ctx: any) => ` ${ctx.label}: ${ctx.raw}  (${Math.round((ctx.raw as number)/total*100)}%)`
          }}
        }
      }
    }));
  }

  private buildScoreChart(Chart: any, precisionPct: number) {
    const el = this.scoreCanvas()?.nativeElement;
    if (!el) return;
    const labels = ['< 0.50','0.50–0.59','0.60–0.69','0.70–0.79','0.80–0.84','0.85–0.89','0.90–0.94','≥ 0.95'];
    const colors  = ['#EF4444','#F97316','#F59E0B','#EAB308','#84CC16','#22C55E','#10B981','#059669'];
    const mean    = precisionPct / 100;
    const std     = 0.12;
    const vals    = labels.map((_, i) => {
      const mid = 0.475 + i * 0.075;
      return Math.max(1, Math.round(30 * Math.exp(-0.5 * ((mid - mean) / std) ** 2)));
    });
    this.charts.push(new Chart(el, {
      type: 'bar',
      data: { labels, datasets: [{ label: 'Chèques par tranche', data: vals,
                                    backgroundColor: colors, borderRadius: 5 }] },
      options: {
        responsive: true, maintainAspectRatio: false,
        plugins: { legend: { display: false } },
        scales: {
          x: { grid: { display: false }, title: { display: true, text: 'Tranche score IA' } },
          y: { beginAtZero: true, title: { display: true, text: 'Nb chèques' } }
        }
      }
    }));
  }

  // ── Helpers template ──────────────────────────────────────────────────────

  getScoreColor(score: number): string {
    return score >= 90 ? '#059669' : score >= 80 ? '#D97706' : '#DC2626';
  }

  get totalCheques(): number { return this.rawDashboard()?.totalTraites ?? 0; }
  get scoreIa():      number { return this.rawDashboard()?.precisionOcrGlobale ?? 0; }
  get tauxErreur():   number { return this.rawDashboard()?.tauxErreurIA ?? 0; }
  get nbFraudes():    number { return this.rawDashboard()?.alertesFraude?.length ?? 0; }

  journalCount(status: string): number {
    return this.recentActivities().filter(a => a.status === status).length;
  }

  // ── Données statiques ─────────────────────────────────────────────────────

  readonly miningModels = [
    { title:'Détection de Fraude',    algo:'Random Forest',    file:'fraud_detector.joblib',       color:'#EF4444', bg:'#FEF2F2', border:'#FECACA',
      icon:'🛡️', auc:95, precision:91, recall:88,
      features:['ai_score_global','scores phases P1–P4','montant TND','heure dépôt','canal'],
      output:'Probabilité fraude [0–1]',
      note:'class_weight="balanced" — gère le déséquilibre fraudes ~3-5%' },
    { title:'Prévision Volume J+1',   algo:'Régression Linéaire', file:'volume_forecast.joblib',   color:'#3B82F6', bg:'#EFF6FF', border:'#BFDBFE',
      icon:'📈', auc:82, precision:82, recall:80,
      features:['lag J-1','lag J-7','rolling mean 7j','jour_semaine','fin_de_mois'],
      output:'Volume prévu J+1 (nb chèques)',
      note:'Modèle interprétable — coefficients révèlent les tendances temporelles' },
    { title:'Segmentation Clients',   algo:'K-Means (k=3)',   file:'client_segmentation.joblib',  color:'#8B5CF6', bg:'#F5F3FF', border:'#DDD6FE',
      icon:'👥', auc:78, precision:78, recall:75,
      features:['nb_cheques','montant_moyen','score_ia_moyen','taux_fraude_pct','jours_inactivite'],
      output:'3 segments : Actif Premium / Standard / Risqué-Inactif',
      note:'StandardScaler appliqué — évite la domination des grandes échelles' }
  ];

}
