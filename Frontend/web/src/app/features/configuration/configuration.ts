import { Component, OnInit, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { AuthService } from '../../core/services/auth.service';
import { NotificationService } from '../../core/services/notification.service';

@Component({
  selector: 'app-configuration',
  standalone: true,
  imports: [CommonModule, ReactiveFormsModule],
  templateUrl: './configuration.html',
  styleUrl: './configuration.scss'
})
export class ConfigurationComponent implements OnInit {
  private authService = inject(AuthService);
  private notificationService = inject(NotificationService);
  private fb = inject(FormBuilder);

  currentUser = this.authService.currentUser;
  avatarPreview = signal<string | null>(null);
  isSavingProfile = signal(false);
  isSavingPassword = signal(false);
  profileSuccess = signal('');
  passwordSuccess = signal('');

  profileForm = this.fb.group({
    firstName: ['', [Validators.required]],
    lastName:  ['', [Validators.required]],
    email:     ['', [Validators.required, Validators.email]]
  });

  passwordForm = this.fb.group({
    currentPassword: ['', [Validators.required]],
    newPassword:     ['', [Validators.required, Validators.minLength(6)]],
    confirmPassword: ['', [Validators.required]]
  });

  get passwordMismatch(): boolean {
    const { newPassword, confirmPassword } = this.passwordForm.getRawValue();
    return !!newPassword && !!confirmPassword && newPassword !== confirmPassword;
  }

  ngOnInit() {
    const user = this.currentUser();
    if (!user) return;
    this.profileForm.patchValue({
      firstName: user.firstName,
      lastName:  user.lastName,
      email:     user.email
    });
    if (user.avatar?.startsWith('data:')) {
      this.avatarPreview.set(user.avatar);
    }
  }

  onAvatarSelected(event: Event) {
    const file = (event.target as HTMLInputElement).files?.[0];
    if (!file) return;
    if (!file.type.startsWith('image/')) {
      this.notificationService.show('Format invalide. Utilisez JPG ou PNG.', 'error');
      return;
    }
    const reader = new FileReader();
    reader.onload = (e) => {
      const dataUrl = e.target?.result as string;
      this.avatarPreview.set(dataUrl);
      this.authService.updateUser({ avatar: dataUrl });
      this.notificationService.show('Photo de profil mise à jour.', 'success');
    };
    reader.readAsDataURL(file);
  }

  removeAvatar() {
    this.avatarPreview.set(null);
    this.authService.updateUser({ avatar: undefined });
    this.notificationService.show('Photo de profil supprimée.', 'info');
  }

  saveProfile() {
    if (this.profileForm.invalid) {
      this.profileForm.markAllAsTouched();
      return;
    }
    this.isSavingProfile.set(true);
    this.profileSuccess.set('');
    const { firstName, lastName, email } = this.profileForm.getRawValue();
    const fullName = `${firstName!} ${lastName!}`.trim();
    this.authService.updateProfile({ fullName, email: email! }).subscribe({
      next: () => {
        this.isSavingProfile.set(false);
        this.profileSuccess.set('Profil mis à jour avec succès.');
        this.notificationService.show('Profil enregistré.', 'success');
      },
      error: (err) => {
        this.isSavingProfile.set(false);
        const msg = err?.error?.error ?? err?.error?.message ?? 'Erreur lors de la mise à jour.';
        this.notificationService.show(msg, 'error');
      }
    });
  }

  updatePassword() {
    if (this.passwordForm.invalid || this.passwordMismatch) {
      this.passwordForm.markAllAsTouched();
      return;
    }
    this.isSavingPassword.set(true);
    this.passwordSuccess.set('');
    const { currentPassword, newPassword } = this.passwordForm.getRawValue();
    this.authService.changePassword(currentPassword!, newPassword!).subscribe({
      next: () => {
        this.isSavingPassword.set(false);
        this.passwordSuccess.set('Mot de passe mis à jour avec succès.');
        this.passwordForm.reset();
        this.notificationService.show('Mot de passe modifié.', 'success');
      },
      error: (err) => {
        this.isSavingPassword.set(false);
        const msg = err?.error?.message ?? err?.error?.error ?? 'Mot de passe actuel incorrect.';
        this.notificationService.show(msg, 'error');
      }
    });
  }
}
