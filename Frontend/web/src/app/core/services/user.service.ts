import { Injectable, inject, signal } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable, catchError, delay, map, of, tap } from 'rxjs';
import {
  API_CONFIG, API,
  UserDTO, UserStatsDTO,
  CreateUserRequest, CreateUserResponse,
  UpdateUserRequest
} from '../constants/api-contract';
import { User } from '../models/user.model';

@Injectable({ providedIn: 'root' })
export class UserService {
  private http = inject(HttpClient);

  users = signal<User[]>([]);

  // ── List ──────────────────────────────────────────────────────────────────

  getUsers(): Observable<User[]> {
    if (API_CONFIG.USE_MOCK) return of(this.users()).pipe(delay(800));
    return this.http
      .get<UserDTO[]>(`${API_CONFIG.BASE_URL}${API.AUTH.USERS}`)
      .pipe(
        map(dtos => dtos.map(d => this.mapDto(d))),
        tap(list => this.users.set(list)),
        catchError(() => of(this.users()))
      );
  }

  getAgents(): Observable<User[]> {
    if (API_CONFIG.USE_MOCK) return of(this.users().filter(u => u.role === 'AGENT')).pipe(delay(800));
    return this.http
      .get<{ agents: UserDTO[] } | UserDTO[]>(`${API_CONFIG.BASE_URL}${API.AUTH.AGENTS}`)
      .pipe(
        map(res => {
          const dtos = Array.isArray(res) ? res : (res as any).agents ?? [];
          return dtos.map((d: UserDTO) => this.mapDto(d));
        }),
        tap(list => this.users.update(all => {
          const ids = new Set(list.map((u: User) => u.id));
          return [...all.filter(u => !ids.has(u.id)), ...list];
        })),
        catchError(() => of(this.users().filter(u => u.role === 'AGENT')))
      );
  }

  getUserStats(): Observable<UserStatsDTO> {
    const fallback: UserStatsDTO = { totalUsers: 0, totalAgents: 0, totalAdmins: 0, agentsActifs: 0, agentsBloques: 0 };
    if (API_CONFIG.USE_MOCK) return of(fallback).pipe(delay(600));
    return this.http
      .get<UserStatsDTO>(`${API_CONFIG.BASE_URL}${API.AUTH.USERS_STATS}`)
      .pipe(catchError(() => of(fallback)));
  }

  getUserById(id: string): Observable<User> {
    return this.http
      .get<UserDTO>(`${API_CONFIG.BASE_URL}${API.AUTH.USER_BY_ID(id)}`)
      .pipe(map(d => this.mapDto(d)));
  }

  // ── Create / Update ───────────────────────────────────────────────────────

  createUser(payload: CreateUserRequest): Observable<CreateUserResponse> {
    if (API_CONFIG.USE_MOCK) {
      const parts = payload.fullName.split(' ');
      const newUser: User = {
        id: Math.random().toString(36).slice(2, 9),
        email: payload.email ?? '',
        firstName: parts[0] ?? '',
        lastName:  parts.slice(1).join(' '),
        role: payload.role,
        isActive: true
      };
      this.users.update(list => [...list, newUser]);
      const mockDto: UserDTO = { id: newUser.id, fullName: payload.fullName, email: payload.email ?? null, phone: payload.phone ?? null, role: payload.role, userType: 'INTERNAL', active: true, verified: true, resetPasswordRequested: false, createdAt: new Date().toISOString(), updatedAt: new Date().toISOString() };
      return of({ user: mockDto, temporaryPassword: 'mock', emailStatus: 'SENT', message: 'Utilisateur créé' } as CreateUserResponse).pipe(delay(1200));
    }
    return this.http
      .post<CreateUserResponse>(`${API_CONFIG.BASE_URL}${API.AUTH.USERS}`, payload)
      .pipe(
        tap(() => this.getUsers().subscribe()),
      );
  }

  updateUser(id: string, payload: UpdateUserRequest): Observable<User> {
    if (API_CONFIG.USE_MOCK) {
      this.users.update(list => list.map(u => u.id === id ? { ...u, ...payload } : u));
      return of(this.users().find(u => u.id === id)!).pipe(delay(900));
    }
    return this.http
      .put<UserDTO>(`${API_CONFIG.BASE_URL}${API.AUTH.USER_BY_ID(id)}`, payload)
      .pipe(
        map(d => this.mapDto(d)),
        tap(user => this.users.update(list => list.map(u => u.id === id ? user : u))),
        catchError(() => of(this.users().find(u => u.id === id)!))
      );
  }

  updateUserEmail(id: string, payload: { email: string }): Observable<void> {
    if (API_CONFIG.USE_MOCK) return of(undefined).pipe(delay(800));
    return this.http
      .put<void>(`${API_CONFIG.BASE_URL}${API.AUTH.USER_EMAIL(id)}`, payload)
      .pipe(catchError(() => of(undefined)));
  }

  // ── Status management ─────────────────────────────────────────────────────

  blockUser(id: string): Observable<void> {
    if (API_CONFIG.USE_MOCK) {
      this.users.update(list => list.map(u => u.id === id ? { ...u, isActive: false } : u));
      return of(undefined).pipe(delay(700));
    }
    return this.http
      .post<void>(`${API_CONFIG.BASE_URL}${API.AUTH.USER_BLOQUER(id)}`, {})
      .pipe(
        tap(() => this.users.update(list => list.map(u => u.id === id ? { ...u, isActive: false } : u))),
        catchError(() => of(undefined))
      );
  }

  unblockUser(id: string): Observable<void> {
    if (API_CONFIG.USE_MOCK) {
      this.users.update(list => list.map(u => u.id === id ? { ...u, isActive: true } : u));
      return of(undefined).pipe(delay(700));
    }
    return this.http
      .post<void>(`${API_CONFIG.BASE_URL}${API.AUTH.USER_DEBLOQUER(id)}`, {})
      .pipe(
        tap(() => this.users.update(list => list.map(u => u.id === id ? { ...u, isActive: true } : u))),
        catchError(() => of(undefined))
      );
  }

  reactivateUser(id: string): Observable<void> {
    if (API_CONFIG.USE_MOCK) {
      this.users.update(list => list.map(u => u.id === id ? { ...u, isActive: true } : u));
      return of(undefined).pipe(delay(700));
    }
    return this.http
      .post<void>(`${API_CONFIG.BASE_URL}${API.AUTH.USER_REACTIVATE(id)}`, {})
      .pipe(
        tap(() => this.users.update(list => list.map(u => u.id === id ? { ...u, isActive: true } : u))),
        catchError(() => of(undefined))
      );
  }

  toggleUserStatus(user: User): Observable<void> {
    return user.isActive ? this.blockUser(user.id) : this.unblockUser(user.id);
  }

  // ── Private ───────────────────────────────────────────────────────────────

  private mapDto(dto: UserDTO): User {
    const parts = dto.fullName?.split(' ') ?? [];
    return {
      id:                     dto.id,
      email:                  dto.email ?? '',
      firstName:              parts[0] ?? '',
      lastName:               parts.slice(1).join(' '),
      role:                   dto.role,
      isActive:               dto.active,
      resetPasswordRequested: dto.resetPasswordRequested ?? false,
    };
  }
}
