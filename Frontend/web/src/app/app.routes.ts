import { Routes } from '@angular/router';
import { LoginComponent } from './features/auth/pages/login/login';
import { MainLayoutComponent } from './core/layout/main-layout/main-layout';
import { TraitementChequesComponent } from './features/cheque-process/traitement-cheques';
import { ScannerComponent } from './features/cheque-process/scanner/scanner';
import { HistoriqueComponent } from './features/historique/historique';
import { AdminDashboardComponent } from './features/dashboard/admin-dashboard';
import { UserManagementComponent } from './features/user-management/user-management';
import { ConfigurationComponent } from './features/configuration/configuration';
import { ProfileComponent } from './features/profile/profile';
import { ReclamationsComponent } from './features/reclamations/reclamations';

import { authGuard, roleGuard, rootRedirectGuard } from './core/guards/auth.guard';
import { pendingChangesGuard } from './core/guards/pending-changes.guard';

export const routes: Routes = [
  { path: 'login', component: LoginComponent },
  {
    path: '',
    component: MainLayoutComponent,
    canActivate: [authGuard],
    children: [
      {
        path: '',
        pathMatch: 'full',
        canActivate: [rootRedirectGuard],
        component: ScannerComponent
      },
      {
        path: 'dashboard',
        redirectTo: 'scanner',
        pathMatch: 'full'
      },
      {
        path: 'scanner',
        component: ScannerComponent,
        canActivate: [roleGuard],
        data: { role: 'AGENT' }
      },
      {
        path: 'traitement-cheques',
        component: TraitementChequesComponent,
        canActivate: [roleGuard],
        canDeactivate: [pendingChangesGuard],
        data: { role: 'AGENT' }
      },
      {
        path: 'historique',
        component: HistoriqueComponent
      },
      {
        path: 'admin-dashboard',
        component: AdminDashboardComponent,
        canActivate: [roleGuard],
        data: { role: 'ADMIN' }
      },
      {
        path: 'user-management',
        component: UserManagementComponent,
        canActivate: [roleGuard],
        data: { role: 'ADMIN' }
      },
      {
        path: 'reclamations',
        component: ReclamationsComponent,
        canActivate: [roleGuard],
        data: { role: 'ADMIN' }
      },
      {
        path: 'config',
        component: ConfigurationComponent,
        canActivate: [roleGuard],
        data: { role: 'ADMIN' }
      },
      {
        path: 'profile',
        component: ProfileComponent
      },
      {
        path: 'admin-profile',
        redirectTo: 'profile',
        pathMatch: 'full'
      }
    ]
  }
];
