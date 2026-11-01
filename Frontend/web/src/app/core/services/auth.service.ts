import { Injectable, inject, signal, PLATFORM_ID } from '@angular/core';
import { isPlatformBrowser } from '@angular/common';
import { HttpClient } from '@angular/common/http';
import { Observable, of, throwError } from 'rxjs';
import { catchError, delay, map, switchMap, tap } from 'rxjs/operators';
import {
  API_CONFIG, API,
  LoginWebRequest, BackendAuthResponse, UserDTO,
  ProfileUpdateRequest
} from '../constants/api-contract';
import { User, AuthResponse } from '../models/user.model';

@Injectable({ providedIn: 'root' })
export class AuthService {
  private http       = inject(HttpClient);
  private platformId = inject(PLATFORM_ID);
  private isBrowser  = isPlatformBrowser(this.platformId);

  currentUser     = signal<User | null>(null);
  isAuthenticated = signal<boolean>(false);
  token           = signal<string | null>(null);

  constructor() {
    if (this.isBrowser) {
      const savedToken = localStorage.getItem(API_CONFIG.TOKEN_KEY);
      const savedUser  = localStorage.getItem(API_CONFIG.USER_KEY);
      if (savedToken && savedUser) {
        this.token.set(savedToken);
        this.currentUser.set(JSON.parse(savedUser));
        this.isAuthenticated.set(true);
        this.verifyToken();
      }
    }
  }

  // ── Login ─────────────────────────────────────────────────────────────────

  login(email: string, password: string): Observable<AuthResponse> {
    if (API_CONFIG.USE_MOCK) {
      return this.mockLogin(email, password);
    }

    const payload: LoginWebRequest = { email, password };
    return this.http
      .post<BackendAuthResponse>(`${API_CONFIG.BASE_URL}${API.AUTH.LOGIN}`, payload)
      .pipe(
        tap(res => {
          this.token.set(res.token);
          if (this.isBrowser) localStorage.setItem(API_CONFIG.TOKEN_KEY, res.token);
        }),
        switchMap(res =>
          this.http.get<UserDTO>(`${API_CONFIG.BASE_URL}${API.AUTH.ME}`).pipe(
            map(dto => ({ token: res.token, user: this.mapUserDto(dto) }))
          )
        ),
        tap(({ user }) => {
          this.currentUser.set(user);
          this.isAuthenticated.set(true);
          if (this.isBrowser) localStorage.setItem(API_CONFIG.USER_KEY, JSON.stringify(user));
        }),
        catchError(err => {
          this.clearSession();
          const msg = err?.error?.message ?? err?.message ?? 'Identifiants invalides';
          return throwError(() => new Error(msg));
        })
      );
  }

  // ── Mot de passe oublié ───────────────────────────────────────────────────

  forgotPasswordRequest(email: string): Observable<{ message: string }> {
    return this.http.post<{ message: string }>(
      `${API_CONFIG.BASE_URL}${API.AUTH.FORGOT_PASSWORD}`,
      { email }
    );
  }

  // ── Changer mot de passe ─────────────────────────────────────────────────

  changePassword(currentPassword: string, newPassword: string): Observable<{ message: string }> {
    return this.http.put<{ message: string }>(
      `${API_CONFIG.BASE_URL}${API.AUTH.ME_PASSWORD}`,
      { currentPassword, newPassword }
    );
  }

  // ── Profile update ────────────────────────────────────────────────────────

  updateProfile(payload: ProfileUpdateRequest): Observable<User> {
    if (API_CONFIG.USE_MOCK) {
      const updated = { ...this.currentUser()! } as User;
      if (payload.fullName) {
        const [first, ...rest] = payload.fullName.split(' ');
        updated.firstName = first;
        updated.lastName  = rest.join(' ');
      }
      this.updateUser(updated);
      return of(updated).pipe(delay(900));
    }
    return this.http
      .put<UserDTO>(`${API_CONFIG.BASE_URL}${API.AUTH.ME}`, payload)
      .pipe(
        map(dto => this.mapUserDto(dto)),
        tap(user => this.updateUser(user)),
        catchError(() => {
          const current = this.currentUser()!;
          return of(current);
        })
      );
  }

  // ── Local state helpers ───────────────────────────────────────────────────

  updateUser(updates: Partial<User>): void {
    const current = this.currentUser();
    if (!current) return;
    const updated = { ...current, ...updates };
    this.currentUser.set(updated);
    if (this.isBrowser) localStorage.setItem(API_CONFIG.USER_KEY, JSON.stringify(updated));
  }

  logout(): void {
    this.clearSession();
  }

  // ── Private ───────────────────────────────────────────────────────────────

  private verifyToken(): void {
    this.http.get<UserDTO>(`${API_CONFIG.BASE_URL}${API.AUTH.ME}`).subscribe({
      next: dto => {
        const user = this.mapUserDto(dto);
        this.currentUser.set(user);
        if (this.isBrowser) localStorage.setItem(API_CONFIG.USER_KEY, JSON.stringify(user));
      },
      error: (err) => {
        // Only logout on auth errors; keep session on network/server failures
        if (err?.status === 401 || err?.status === 403) this.logout();
      }
    });
  }

  private clearSession(): void {
    this.currentUser.set(null);
    this.isAuthenticated.set(false);
    this.token.set(null);
    if (this.isBrowser) {
      localStorage.removeItem(API_CONFIG.TOKEN_KEY);
      localStorage.removeItem(API_CONFIG.USER_KEY);
    }
  }

  mapUserDto(dto: UserDTO): User {
    const [first, ...rest] = (dto.fullName ?? '').split(' ');
    return {
      id:        dto.id,
      email:     dto.email ?? '',
      firstName: first ?? '',
      lastName:  rest.join(' '),
      role:      dto.role,
      isActive:  dto.active,
    };
  }

  private mockLogin(email: string, password: string): Observable<AuthResponse> {
    const { ADMIN, AGENT } = API_CONFIG.DEMO;
    const isAdmin = email === ADMIN.email && password === ADMIN.password;
    const isAgent = email === AGENT.email && password === AGENT.password;

    if (!isAdmin && !isAgent) {
      return throwError(() => new Error('Identifiants invalides')).pipe(delay(1200));
    }

    const role: 'ADMIN' | 'AGENT' = isAdmin ? 'ADMIN' : 'AGENT';
    const mockToken = 'mock-jwt-' + Math.random().toString(36).slice(2);
    const user: User = {
      id:        '1',
      email,
      firstName: role === 'ADMIN' ? 'Admin' : 'Agent',
      lastName:  'ChèqueProtect',
      role,
      isActive:  true
    };

    return of({ token: mockToken, user }).pipe(
      delay(1500),
      tap(res => {
        this.token.set(res.token);
        this.currentUser.set(res.user);
        this.isAuthenticated.set(true);
        if (this.isBrowser) {
          localStorage.setItem(API_CONFIG.TOKEN_KEY, res.token);
          localStorage.setItem(API_CONFIG.USER_KEY, JSON.stringify(res.user));
        }
      })
    );
  }
}
