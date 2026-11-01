# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
npm start          # dev server on http://localhost:4200 (hot reload)
npm test           # unit tests with Vitest (NOT Jest)
npm run build      # production build
npm run watch      # incremental dev build
npm run serve:ssr:Front-end  # SSR Node server (port 4000)
```

Run a single test file:
```bash
npx vitest run src/app/features/auth/pages/login/login.spec.ts
```

## Architecture

Angular 21 SPA with **standalone components**, **signals** (no NgRx), and **functional route guards**. TypeScript strict mode is enabled.

### Role-Based Routing

Two distinct user roles drive the entire UX:

| Role | Entry point | Key routes |
|------|-------------|------------|
| `AGENT` | `/scanner` | `/scanner` → `/traitement-cheques` → `/historique` |
| `ADMIN` | `/admin-dashboard` | `/admin-dashboard`, `/user-management`, `/config` |

`rootRedirectGuard` on `/` picks the right entry by role. `roleGuard` blocks cross-role access. `pendingChangesGuard` on `/traitement-cheques` prevents losing unsaved OCR edits.

### Core Services (all in `src/app/core/services/`)

**Everything is mocked — there is no real backend or HTTP client.**

- **`auth.service.ts`** — Signal-based auth (`currentUser`, `isAuthenticated`, `token`). Mock login: email containing "admin" → ADMIN role, otherwise AGENT. State persisted to `localStorage` (SSR-safe via `isPlatformBrowser`).
- **`cheque.service.ts`** — OCR workflow state machine. Signals: `currentScannedCheque`, `currentOcrResult`, `isProcessing`, `history`. Mock OCR returns variable confidence scores (~1.7 s delay). History is in-memory only.
- **`admin.service.ts`** — Admin dashboard data and user CRUD. All methods return `of(...)` observables with 800–1500 ms artificial delays. In-memory user list (4 mock users).
- **`notification.service.ts`** — Toast system (auto-dismiss after 5 s). Types: `'success' | 'error' | 'warning' | 'info'`.

### Main Layout (`src/app/core/layout/main-layout/`)

Hosts all authenticated routes. Manages:
- Role-aware sidebar navigation
- 5-minute inactivity session timeout with 60 s warning modal
- Privacy mode toggled by spacebar (blurs content)
- Toast rendering from `NotificationService`

### Key Data Models (`src/app/core/models/`)

```ts
// Cheque OCR field — every extracted field has this shape
{ value: string; confidence: number; isManuallyVerified?: boolean }

// Cheque statuses
'PENDING' | 'VALIDATED' | 'REJECTED'

// User roles
'ADMIN' | 'AGENT'
```

### Agent Cheque Workflow

1. **ScannerComponent** — drag-drop upload, simulates scan progress, navigates to step 2
2. **TraitementChequesComponent** — displays OCR fields, agent corrects low-confidence values (Enter = approve, Esc = reject), calls `cheque.service.completeCheque()`
3. **HistoriqueComponent** — searchable/filterable history with pagination (shared by both roles)

### Styling

Global design tokens are CSS variables in `src/styles.scss` (primary `#1d4ed8`, success `#059669`, danger `#dc2626`). Reusable utility classes: `.white-card`, `.white-card-premium`, `.input-modern`. Component-level styles use `.scss` files co-located with each component.

### SSR

`@angular/ssr` 21.2.0 with an Express 5 server (`src/server.ts`). The dev server and the SSR server share the same Angular app; use `isPlatformBrowser(platformId)` before touching `localStorage` or browser-only APIs.

## Backend Integration (already done)

Le backend est branché (`USE_MOCK: false` dans `api-contract.ts`). Points à retenir :

- `proxy.conf.json` redirige `/api/*` → `http://localhost:8080` en dev (évite CORS)
- `provideHttpClient(withFetch(), withInterceptors([authInterceptor]))` est déjà configuré
- **UserDTO** du backend utilise `fullName` (pas `firstName`+`lastName`) — les services splittent sur l'espace
- **Statuts chèque** : backend `EN_ATTENTE/EN_TRAITEMENT` → frontend `PENDING` ; `VALIDE` → `VALIDATED` ; `REJETE/FRAUDE_DETECTEE` → `REJECTED`
- **Décision valider** : envoyer `'VALIDE'` ou `'REJETE'` (pas `VALIDATED/REJECTED`)
- **CreateUserRequest** : pas de champ `password` — auto-généré par le backend et envoyé par email. La réponse inclut `temporaryPassword` si l'email a échoué.
- **Dashboard** : `volumeSeptJours` est un tableau de `VolumePointDTO { date, total, valides, rejetes }` (pas un tableau de nombres)
- **alertesFraude** dans AdminDashboardDTO est un tableau de `FraudeAlertDTO[]` (pas un nombre)
