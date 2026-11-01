import { inject, PLATFORM_ID } from '@angular/core';
import { isPlatformBrowser } from '@angular/common';
import { Router, CanActivateFn } from '@angular/router';
import { AuthService } from '../services/auth.service';
import { API_CONFIG } from '../constants/api-contract';

// ── Helper ─────────────────────────────────────────────────────────────────────
// All guards return true on the server (SSR): localStorage is unavailable there.
// The browser takes over at hydration and applies auth checks normally.

export const authGuard: CanActivateFn = () => {
  const platformId = inject(PLATFORM_ID);
  if (!isPlatformBrowser(platformId)) return true;

  const authService = inject(AuthService);
  const router      = inject(Router);

  if (authService.isAuthenticated()) return true;

  const hasToken = !!localStorage.getItem(API_CONFIG.TOKEN_KEY);
  if (hasToken) return true;

  return router.createUrlTree(['/login']);
};

export const roleGuard: CanActivateFn = (route) => {
  const platformId = inject(PLATFORM_ID);
  if (!isPlatformBrowser(platformId)) return true;

  const authService  = inject(AuthService);
  const router       = inject(Router);
  const currentUser  = authService.currentUser();
  const expectedRole = route.data['role'] as string;

  if (currentUser?.role === expectedRole) return true;

  return currentUser?.role === 'ADMIN'
    ? router.createUrlTree(['/admin-dashboard'])
    : router.createUrlTree(['/scanner']);
};

export const adminGuard: CanActivateFn = () => {
  const platformId = inject(PLATFORM_ID);
  if (!isPlatformBrowser(platformId)) return true;

  const authService = inject(AuthService);
  const router      = inject(Router);
  const user        = authService.currentUser();

  if (user?.role === 'ADMIN') return true;
  return router.createUrlTree(['/scanner']);
};

export const agentGuard: CanActivateFn = () => {
  const platformId = inject(PLATFORM_ID);
  if (!isPlatformBrowser(platformId)) return true;

  const authService = inject(AuthService);
  const router      = inject(Router);
  const user        = authService.currentUser();

  if (user?.role === 'AGENT') return true;
  return router.createUrlTree(['/admin-dashboard']);
};

export const rootRedirectGuard: CanActivateFn = () => {
  const platformId = inject(PLATFORM_ID);
  if (!isPlatformBrowser(platformId)) return true;

  const authService = inject(AuthService);
  const router      = inject(Router);
  const user        = authService.currentUser();

  if (!user) return router.createUrlTree(['/login']);
  return user.role === 'ADMIN'
    ? router.createUrlTree(['/admin-dashboard'])
    : router.createUrlTree(['/scanner']);
};
