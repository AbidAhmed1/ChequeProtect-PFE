import { Component, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ReactiveFormsModule, FormGroup, FormControl, Validators } from '@angular/forms';
import { Router } from '@angular/router';
import { AuthService } from '../../../../core/services/auth.service';

@Component({
  selector: 'app-login',
  standalone: true,
  imports: [CommonModule, ReactiveFormsModule],
  templateUrl: './login.html',
  styleUrl: './login.scss'
})
export class LoginComponent {
  private authService = inject(AuthService);
  private router = inject(Router);

  // UI State Signals
  isLoading    = signal(false);
  errorMessage = signal<string | null>(null);
  showPassword = signal(false);

  // Forgot password modal
  showForgotModal  = signal(false);
  forgotEmail      = signal('');
  forgotLoading    = signal(false);
  forgotSuccess    = signal(false);
  forgotError      = signal<string | null>(null);

  openForgotModal() {
    this.showForgotModal.set(true);
    this.forgotEmail.set('');
    this.forgotError.set(null);
    this.forgotSuccess.set(false);
  }

  closeForgotModal() {
    this.showForgotModal.set(false);
  }

  onForgotEmailInput(event: Event) {
    this.forgotEmail.set((event.target as HTMLInputElement).value);
  }

  sendForgotRequest() {
    const email = this.forgotEmail().trim();
    if (!email || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
      this.forgotError.set('Veuillez saisir une adresse e-mail valide.');
      return;
    }
    this.forgotLoading.set(true);
    this.forgotError.set(null);
    this.authService.forgotPasswordRequest(email).subscribe({
      next:  () => { this.forgotLoading.set(false); this.forgotSuccess.set(true); },
      error: () => { this.forgotLoading.set(false); this.forgotSuccess.set(true); }
    });
  }

  loginForm = new FormGroup({
    email: new FormControl('', [Validators.required, Validators.email]),
    password: new FormControl('', [Validators.required, Validators.minLength(6)])
  });

  togglePassword() {
    this.showPassword.update(v => !v);
  }

  onSubmit() {
    if (this.loginForm.invalid) {
      this.loginForm.markAllAsTouched();
      return;
    }

    this.isLoading.set(true);
    this.errorMessage.set(null);

    const { email, password } = this.loginForm.value;

    this.authService.login(email!, password!).subscribe({
      next: (response) => {
        this.isLoading.set(false);
        // Redirect based on role
        if (response.user.role === 'ADMIN') {
          this.router.navigate(['/admin-dashboard']);
        } else {
          this.router.navigate(['/scanner']);
        }
      },
      error: (err) => {
        this.isLoading.set(false);
        this.errorMessage.set(err.message || 'Une erreur est survenue lors de la connexion.');
      }
    });
  }
}
