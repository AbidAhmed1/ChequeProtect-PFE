import { Component, inject, OnInit, OnDestroy, signal, computed } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormBuilder, FormGroup, ReactiveFormsModule, Validators } from '@angular/forms';
import { Subscription, interval } from 'rxjs';
import { switchMap } from 'rxjs/operators';
import { AdminService } from '../../core/services/admin.service';
import { NotificationService } from '../../core/services/notification.service';
import { User } from '../../core/models/user.model';

@Component({
  selector: 'app-user-management',
  standalone: true,
  imports: [CommonModule, ReactiveFormsModule],
  templateUrl: './user-management.html',
  styleUrl: './user-management.scss'
})
export class UserManagementComponent implements OnInit, OnDestroy {
  private adminService       = inject(AdminService);
  private notificationService = inject(NotificationService);
  private fb                 = inject(FormBuilder);
  private refreshSub?: Subscription;

  isLoading    = signal<boolean>(true);
  isModalOpen  = signal<boolean>(false);
  isSubmitting = signal<boolean>(false);
  submitSuccess = signal<string | null>(null);
  submitError   = signal<string | null>(null);

  modalMode      = signal<'ADD' | 'EDIT'>('ADD');
  selectedUser   = signal<User | null>(null);
  searchTerm     = signal<string>('');

  userForm: FormGroup = this.fb.group({
    firstName:   ['', Validators.required],
    lastName:    ['', Validators.required],
    email:       ['', [Validators.required, Validators.email]],
    role:        ['AGENT', Validators.required],
    newPassword: [''],
  });

  agentsCount = computed(() => this.adminService.agents().filter(u => u.role === 'AGENT').length);
  adminsCount = computed(() => this.adminService.agents().filter(u => u.role === 'ADMIN').length);

  resetRequestsCount = computed(() =>
    this.adminService.agents().filter(u => u.resetPasswordRequested).length
  );

  filteredUsers = computed(() => {
    const search = this.searchTerm().toLowerCase().trim();
    if (!search) return this.adminService.agents();
    return this.adminService.agents().filter(user => {
      const fullName = `${user.firstName} ${user.lastName}`.toLowerCase();
      return fullName.includes(search) || user.email.toLowerCase().includes(search) || user.role.toLowerCase().includes(search);
    });
  });

  ngOnInit() {
    this.loadUsers();
    // Rafraîchissement automatique toutes les 30s pour détecter les nouvelles demandes reset MDP
    this.refreshSub = interval(30000).pipe(
      switchMap(() => this.adminService.getAgents())
    ).subscribe();
  }

  ngOnDestroy() {
    this.refreshSub?.unsubscribe();
  }

  loadUsers() {
    this.isLoading.set(true);
    this.adminService.getAgents().subscribe(() => this.isLoading.set(false));
  }

  refreshUsers() {
    this.adminService.getAgents().subscribe();
  }

  get users() { return this.adminService.agents; }

  openAddModal() {
    this.modalMode.set('ADD');
    this.selectedUser.set(null);
    this.submitSuccess.set(null);
    this.submitError.set(null);
    this.userForm.reset({ role: 'AGENT' });
    this.userForm.get('newPassword')?.clearValidators();
    this.userForm.get('newPassword')?.updateValueAndValidity();
    this.isModalOpen.set(true);
  }

  openEditModal(user: User) {
    this.modalMode.set('EDIT');
    this.selectedUser.set(user);
    this.submitSuccess.set(null);
    this.submitError.set(null);
    this.userForm.get('newPassword')?.clearValidators();
    this.userForm.get('newPassword')?.updateValueAndValidity();
    this.userForm.patchValue({
      firstName:   user.firstName,
      lastName:    user.lastName,
      email:       user.email,
      role:        user.role,
      newPassword: '',
    });
    this.isModalOpen.set(true);
  }

  closeModal() {
    this.isModalOpen.set(false);
    this.userForm.reset({ role: 'AGENT' });
    this.submitSuccess.set(null);
    this.submitError.set(null);
  }

  onSubmit() {
    if (this.userForm.invalid) { this.userForm.markAllAsTouched(); return; }
    this.isSubmitting.set(true);
    this.submitError.set(null);
    const v = this.userForm.value;

    if (this.modalMode() === 'ADD') {
      this.adminService.addAgent({
        firstName: v.firstName,
        lastName:  v.lastName,
        email:     v.email,
        role:      v.role,
      }).subscribe({
        next: () => {
          this.isSubmitting.set(false);
          this.submitSuccess.set(`Compte créé. Le mot de passe a été envoyé à ${v.email}.`);
          setTimeout(() => this.closeModal(), 2500);
        },
        error: (err: any) => {
          this.isSubmitting.set(false);
          this.submitError.set(err?.error?.error ?? err?.message ?? 'Erreur lors de la création.');
        }
      });
    } else {
      const userId = this.selectedUser()?.id;
      if (!userId) return;
      const newPwd = v.newPassword?.trim() || undefined;
      this.adminService.updateAgent(userId, {
        firstName:   v.firstName,
        lastName:    v.lastName,
        email:       v.email,
        role:        v.role,
        newPassword: newPwd,
      }).subscribe({
        next: () => {
          this.isSubmitting.set(false);
          const msg = newPwd
            ? `Modifications enregistrées. Nouveau mot de passe : ${newPwd} — Un email a été envoyé à ${v.email}.`
            : 'Modifications enregistrées.';
          this.submitSuccess.set(msg);
          setTimeout(() => this.closeModal(), newPwd ? 6000 : 1800);
        },
        error: (err: any) => {
          this.isSubmitting.set(false);
          this.submitError.set(err?.error?.error ?? err?.message ?? 'Erreur lors de la modification.');
        }
      });
    }
  }

  toggleStatus(user: User) {
    const wasActive = user.isActive;
    this.adminService.toggleAgentStatus(user.id).subscribe(ok => {
      if (ok) {
        const msg = wasActive ? 'Compte bloqué avec succès.' : 'Compte activé avec succès.';
        this.notificationService.show(msg, 'success');
      } else {
        this.notificationService.show('Erreur : impossible de modifier le statut.', 'error');
      }
    });
  }

  getInitials(user: User): string {
    return ((user.firstName[0] ?? '') + (user.lastName[0] ?? '')).toUpperCase();
  }

  onSearchChange(event: Event) {
    this.searchTerm.set((event.target as HTMLInputElement).value);
  }
}
