import { Injectable, inject, signal } from '@angular/core';
import { HttpClient, HttpHeaders } from '@angular/common/http';
import { Observable, catchError, delay, map, of, tap } from 'rxjs';
import { AuthService } from './auth.service';
import {
  API_CONFIG, API,
  AdminDashboardDTO, UserDTO,
  CreateUserRequest, CreateUserResponse, UpdateUserRequest,
  VolumePointDTO, ReclamationDTO,
  ChequeHistoryItemDTO, PagedHistoryResponse
} from '../constants/api-contract';
import { AgentActivity, ChartDataPoint, KPIStats, RecentActivity } from '../models/admin.model';
import { User } from '../models/user.model';

@Injectable({ providedIn: 'root' })
export class AdminService {
  private http        = inject(HttpClient);
  private authService = inject(AuthService);

  agents = signal<User[]>([]);

  // ── Dashboard ─────────────────────────────────────────────────────────────

  getDashboardKPIs(): Observable<KPIStats> {
    if (API_CONFIG.USE_MOCK) return this.mockKpis();
    return this.http
      .get<AdminDashboardDTO>(`${API_CONFIG.BASE_URL}${API.CHEQUES.ADMIN_DASHBOARD}`)
      .pipe(
        map(dto => this.mapDashboardToKpi(dto)),
        catchError(() => this.mockKpis())
      );
  }

  getWeeklyProcessingData(): Observable<ChartDataPoint[]> {
    if (API_CONFIG.USE_MOCK) return this.mockWeekly();
    return this.http
      .get<AdminDashboardDTO>(`${API_CONFIG.BASE_URL}${API.CHEQUES.ADMIN_DASHBOARD}`)
      .pipe(
        map(dto => this.mapVolumeToChart(dto.volumeSeptJours ?? [])),
        catchError(() => this.mockWeekly())
      );
  }

  getAgentActivities(): Observable<AgentActivity[]> {
    return of([]).pipe(delay(500));
  }

  getRecentActivities(): Observable<RecentActivity[]> {
    const headers = new HttpHeaders({ 'X-User-Role': 'ADMIN' });
    return this.http.get<PagedHistoryResponse<ChequeHistoryItemDTO>>(
      `${API_CONFIG.BASE_URL}${API.CHEQUES.ADMIN_HISTORY}`,
      { headers, params: { page: '0', size: '5', direction: 'DESC' } }
    ).pipe(
      map(res => (res.content ?? []).map(item => this.mapHistoryToActivity(item))),
      catchError(() => of([]))
    );
  }

  private mapHistoryToActivity(item: ChequeHistoryItemDTO): RecentActivity {
    const agent = this.agents().find(a => a.id === item.agentId);
    const agentName = agent
      ? `${agent.firstName} ${agent.lastName}`.trim()
      : (item.agentId ? 'Agent' : 'Système');
    const status = item.statut === 'VALIDE' ? 'VALIDATED'
                 : (item.statut === 'REJETE' || item.statut === 'FRAUDE_DETECTEE') ? 'REJECTED'
                 : 'PENDING';
    return {
      id:           item.id,
      agentName:    agentName || 'Agent',
      chequeNumber: item.numeroCheque ?? item.id.slice(0, 8).toUpperCase(),
      status,
      time:         this.relativeTime(item.dateTraitement)
    };
  }

  private relativeTime(dateStr: string): string {
    if (!dateStr) return '';
    const diff = Date.now() - new Date(dateStr).getTime();
    const min  = Math.floor(diff / 60000);
    if (min < 1)  return 'À l\'instant';
    if (min < 60) return `${min}m`;
    const h = Math.floor(min / 60);
    if (h < 24)   return `${h}h`;
    return `${Math.floor(h / 24)}j`;
  }

  // ── User / Agent management ───────────────────────────────────────────────

  getAgents(): Observable<User[]> {
    if (API_CONFIG.USE_MOCK) return of(this.agents()).pipe(delay(1000));
    return this.http
      .get<UserDTO[] | any>(`${API_CONFIG.BASE_URL}${API.AUTH.USERS}`)
      .pipe(
        map(res => {
          const dtos: UserDTO[] = Array.isArray(res) ? res : (res.agents ?? res.users ?? []);
          return dtos
            .filter((d: UserDTO) => d.role === 'ADMIN' || d.role === 'AGENT')
            .map((d: UserDTO) => this.mapUserDto(d));
        }),
        tap(list => this.agents.set(list)),
        catchError(() => of(this.agents()))
      );
  }

  addAgent(agent: { firstName: string; lastName: string; email: string; role?: string; password?: string }): Observable<User> {
    if (API_CONFIG.USE_MOCK) {
      const newUser: User = {
        id:        Math.random().toString(36).slice(2, 9),
        email:     agent.email,
        firstName: agent.firstName,
        lastName:  agent.lastName,
        role:      (agent.role as 'ADMIN' | 'AGENT') ?? 'AGENT',
        isActive:  true
      };
      this.agents.update(list => [...list, newUser]);
      return of(newUser).pipe(delay(1200));
    }

    const payload: CreateUserRequest = {
      fullName:  `${agent.firstName} ${agent.lastName}`.trim(),
      email:     agent.email,
      role:      (agent.role as 'ADMIN' | 'AGENT') ?? 'AGENT',
      ...(agent.password ? { password: agent.password } : {})
    };

    return this.http
      .post<CreateUserResponse>(`${API_CONFIG.BASE_URL}${API.AUTH.USERS}`, payload)
      .pipe(
        map(res => this.mapUserDto(res.user)),
        tap(user => this.agents.update(list => [...list, user])),
        catchError(() => {
          const mock: User = {
            id: Math.random().toString(36).slice(2),
            email: agent.email, firstName: agent.firstName, lastName: agent.lastName,
            role: 'AGENT', isActive: true
          };
          this.agents.update(list => [...list, mock]);
          return of(mock);
        })
      );
  }

  updateAgent(id: string, updates: Partial<User> & { newPassword?: string }): Observable<boolean> {
    if (API_CONFIG.USE_MOCK) {
      this.agents.update(list => list.map(u => u.id === id ? { ...u, ...updates } : u));
      return of(true).pipe(delay(1000));
    }

    const payload: UpdateUserRequest = {
      fullName:    `${updates.firstName ?? ''} ${updates.lastName ?? ''}`.trim() || undefined,
      email:       updates.email       || undefined,
      role:        updates.role        || undefined,
      newPassword: updates.newPassword || undefined,
    };

    return this.http
      .put<UserDTO>(`${API_CONFIG.BASE_URL}${API.AUTH.USER_BY_ID(id)}`, payload)
      .pipe(
        map(() => {
          this.agents.update(list => list.map(u => u.id === id
            ? { ...u, ...updates, resetPasswordRequested: updates.newPassword ? false : u.resetPasswordRequested }
            : u));
          return true;
        }),
        catchError(() => {
          this.agents.update(list => list.map(u => u.id === id ? { ...u, ...updates } : u));
          return of(true);
        })
      );
  }

  toggleAgentStatus(id: string): Observable<boolean> {
    const user = this.agents().find(u => u.id === id);
    if (!user) return of(false);

    if (API_CONFIG.USE_MOCK) {
      this.agents.update(list => list.map(u => u.id === id ? { ...u, isActive: !u.isActive } : u));
      return of(true).pipe(delay(800));
    }

    const adminId = this.authService.currentUser()?.id ?? '';
    const headers = new HttpHeaders({
      'X-User-Role': 'ADMIN',
      'X-User-Id':   adminId
    });

    const endpoint = user.isActive
      ? `${API_CONFIG.BASE_URL}${API.AUTH.USER_BLOQUER(id)}`
      : `${API_CONFIG.BASE_URL}${API.AUTH.USER_DEBLOQUER(id)}`;

    return this.http.put<void>(endpoint, { motif: 'Bloqué par l\'administrateur' }, { headers }).pipe(
      map(() => {
        this.agents.update(list => list.map(u => u.id === id ? { ...u, isActive: !u.isActive } : u));
        return true;
      }),
      catchError(() => of(false))
    );
  }

  // ── Réclamations ─────────────────────────────────────────────────────────

  getReclamations(): Observable<ReclamationDTO[]> {
    const headers = new HttpHeaders({ 'X-User-Role': 'ADMIN' });
    return this.http
      .get<ReclamationDTO[]>(`${API_CONFIG.BASE_URL}${API.RECLAMATIONS.ALL}`, { headers })
      .pipe(catchError(() => of([])));
  }

  transmitReclamation(id: string): Observable<boolean> {
    const headers = new HttpHeaders({ 'X-User-Role': 'ADMIN' });
    return this.http
      .put<void>(`${API_CONFIG.BASE_URL}${API.RECLAMATIONS.TRANSMIT(id)}`, {}, { headers })
      .pipe(
        map(() => true),
        catchError(() => of(false))
      );
  }

  updateStatutReclamation(id: string, statut: string, reponseAgent?: string): Observable<ReclamationDTO | null> {
    const headers = new HttpHeaders({ 'X-User-Role': 'ADMIN' });
    return this.http
      .put<ReclamationDTO>(
        `${API_CONFIG.BASE_URL}${API.RECLAMATIONS.UPDATE_STATUT(id)}`,
        { statut, reponseAgent: reponseAgent ?? '' },
        { headers }
      )
      .pipe(catchError(() => of(null)));
  }

  // ── Private helpers ───────────────────────────────────────────────────────

  private mapDashboardToKpi(dto: AdminDashboardDTO): KPIStats {
    return {
      totalProcessedToday: dto.totalTraites,
      totalPending:        dto.enAttente,
      aiErrorRate:         dto.tauxErreurIA,
      activeAgents:        dto.agentsActifs,
      totalFraudDetected:  dto.alertesFraude?.length ?? 0,
      precisionOcrGlobale: dto.precisionOcrGlobale
    };
  }

  private mapVolumeToChart(volumes: VolumePointDTO[]): ChartDataPoint[] {
    const dayNames = ['Dim', 'Lun', 'Mar', 'Mer', 'Jeu', 'Ven', 'Sam'];
    return volumes.slice(0, 7).map(v => ({
      day:   dayNames[new Date(v.date).getDay()] ?? v.date,
      value: v.total
    }));
  }

  mapUserDto(dto: UserDTO): User {
    const [first, ...rest] = (dto.fullName ?? '').split(' ');
    return {
      id:                     dto.id,
      email:                  dto.email ?? '',
      firstName:              first ?? '',
      lastName:               rest.join(' '),
      role:                   dto.role,
      isActive:               dto.active,
      resetPasswordRequested: dto.resetPasswordRequested ?? false,
    };
  }

  private mockKpis(): Observable<KPIStats> {
    return of({ totalProcessedToday: 124, totalPending: 18, aiErrorRate: 4.5, activeAgents: 3, totalFraudDetected: 2, precisionOcrGlobale: 95.5 }).pipe(delay(1000));
  }

  private mockWeekly(): Observable<ChartDataPoint[]> {
    return of([
      { day: 'Lun', value: 85 }, { day: 'Mar', value: 110 }, { day: 'Mer', value: 90 },
      { day: 'Jeu', value: 135 }, { day: 'Ven', value: 124 }, { day: 'Sam', value: 40 }, { day: 'Dim', value: 20 }
    ]).pipe(delay(1000));
  }
}
