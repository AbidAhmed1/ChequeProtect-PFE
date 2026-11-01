import { Component, HostListener, OnDestroy, OnInit, computed, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { Router, RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';
import { AuthService } from '../../services/auth.service';
import { NotificationService } from '../../services/notification.service';

type NavSection = {
  title: string;
  items: Array<{
    path: string;
    label: string;
    description: string;
    icon: string;
  }>;
};

@Component({
  selector: 'app-main-layout',
  standalone: true,
  imports: [CommonModule, RouterOutlet, RouterLink, RouterLinkActive],
  templateUrl: './main-layout.html',
  styleUrl: './main-layout.scss'
})
export class MainLayoutComponent implements OnInit, OnDestroy {
  private authService = inject(AuthService);
  private notificationService = inject(NotificationService);
  private router = inject(Router);

  currentUser = this.authService.currentUser;
  toasts = this.notificationService.toasts;
  hasProfilePicture = computed(() => {
    const avatar = this.currentUser()?.avatar;
    return !!avatar && avatar.startsWith('data:');
  });

  isPrivacyMode = signal(false);
  showTimeoutModal = signal(false);
  timeoutCountdown = signal(60);
  isSidebarOpen = signal(false);

  private inactivityTimer?: ReturnType<typeof setTimeout>;
  private countdownInterval?: ReturnType<typeof setInterval>;
  private readonly inactivityLimit = 5 * 60 * 1000;

  @HostListener('window:keydown', ['$event'])
  handleKeyboardEvent(event: KeyboardEvent) {
    const target = event.target as HTMLElement;
    const isTyping = ['INPUT', 'TEXTAREA', 'SELECT'].includes(target.tagName);

    if (event.code === 'Space' && !isTyping) {
      event.preventDefault();
      this.togglePrivacy();
    }

    this.resetInactivityTimer();
  }

  @HostListener('window:mousemove')
  onMouseMove() {
    this.resetInactivityTimer();
  }

  ngOnInit() {
    this.resetInactivityTimer();
  }

  ngOnDestroy() {
    this.clearSessionTimers();
  }

  get navSections(): NavSection[] {
    return this.currentUser()?.role === 'ADMIN'
      ? this.navigation.admin
      : this.navigation.agent;
  }

  toggleSidebar() {
    this.isSidebarOpen.update((value) => !value);
  }

  closeSidebar() {
    this.isSidebarOpen.set(false);
  }

  togglePrivacy() {
    this.isPrivacyMode.update((value) => !value);
    if (this.isPrivacyMode()) {
      this.notificationService.show('Mode confidentialite active', 'info');
    }
  }

  resetInactivityTimer() {
    clearTimeout(this.inactivityTimer);
    clearInterval(this.countdownInterval);
    this.showTimeoutModal.set(false);

    this.inactivityTimer = setTimeout(() => {
      this.startTimeoutCountdown();
    }, this.inactivityLimit);
  }

  startTimeoutCountdown() {
    this.showTimeoutModal.set(true);
    this.timeoutCountdown.set(60);
    this.countdownInterval = setInterval(() => {
      this.timeoutCountdown.update((value) => value - 1);
      if (this.timeoutCountdown() <= 0) {
        this.logout();
      }
    }, 1000);
  }

  logout() {
    this.authService.logout();
    this.clearSessionTimers();
    this.router.navigate(['/login']);
  }

  removeToast(id: number) {
    this.notificationService.remove(id);
  }

  private clearSessionTimers() {
    clearTimeout(this.inactivityTimer);
    clearInterval(this.countdownInterval);
    this.showTimeoutModal.set(false);
  }

  private navigation = {
    agent: [
      {
        title: 'Operations',
        items: [
          { path: '/scanner', label: 'Scanner', description: 'Importer et analyser', icon: 'scan' },
          { path: '/traitement-cheques', label: 'Traitement', description: 'Controler les champs OCR', icon: 'check' },
          { path: '/historique', label: 'Historique', description: 'Suivi des decisions', icon: 'history' },
          { path: '/profile', label: 'Profil', description: 'Compte utilisateur', icon: 'profile' }
        ]
      }
    ],
    admin: [
      {
        title: 'Pilotage',
        items: [
          { path: '/admin-dashboard', label: 'Supervision', description: 'KPI et activite IA', icon: 'dashboard' },
          { path: '/historique', label: 'Cheques traites', description: 'Controle des traitements', icon: 'history' }
        ]
      },
      {
        title: 'Administration',
        items: [
          { path: '/user-management', label: 'Utilisateurs', description: 'Comptes et acces', icon: 'users' },
          { path: '/reclamations', label: 'Réclamations', description: 'Messages chatbot clients', icon: 'recl' },
{ path: '/config', label: 'Mon Profil', description: 'Profil et securite', icon: 'profile' }
        ]
      }
    ]
  };
}
