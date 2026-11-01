package tn.tunicheque.auth_service.entity;

import jakarta.persistence.*;
import lombok.*;
import org.hibernate.annotations.CreationTimestamp;
import org.hibernate.annotations.UpdateTimestamp;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.userdetails.UserDetails;
import tn.tunicheque.auth_service.entity.enums.Role;
import tn.tunicheque.auth_service.entity.enums.UserType;

import java.time.LocalDateTime;
import java.util.Collection;
import java.util.List;
import java.util.UUID;

/**
 * User — entité principale auth-service.
 *
 * Intègre :
 *   - Authentification web (Admin/Agent) : email + password
 *   - Authentification mobile (Bénéficiaire/Tireur) : phone + PIN
 *   - Inscription RIB : phone uniquement
 *   - Inscription OTP : phone + CIN + email
 *   - Blocage agent : isBlocked + blockReason + blockedAt + blockedBy
 *
 * FIX : id = UUID (cohérent avec UserRepository<User, UUID>)
 * FIX : @Builder.Default sur isActive, isVerified, isBlocked
 * FIX : @Getter + @Setter explicites (évite conflits Lombok avec isActive)
 */
@Entity
@Table(name = "users")
@Getter
@Setter
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class User implements UserDetails {

    // ── Identifiant ────────────────────────────────────────────────

    @Id
    @GeneratedValue(strategy = GenerationType.UUID)
    private UUID id;

    // ── Authentification ───────────────────────────────────────────

    @Column(unique = true)
    private String email;

    @Column(name = "password_hash", nullable = false)
    private String passwordHash;   // BCrypt (password web OU PIN mobile)

    // ── Informations personnelles ──────────────────────────────────

    @Column(name = "full_name")
    private String fullName;

    @Column
    private String phone;

    @Column(name = "cin_number", unique = true)
    private String cinNumber;

    @Column(name = "rib", length = 20)
    private String rib;            // RIB 20 chiffres (bénéficiaire KYC visiteur)

    @Column(name = "face_image_url", columnDefinition = "TEXT")
    private String faceImageUrl;   // URL photo CIN extraite (KYC visiteur)

    // ── Rôle et type ──────────────────────────────────────────────

    @Enumerated(EnumType.STRING)
    @Column(name = "user_type")
    private UserType userType;     // INTERNAL (Agent/Admin) | CLIENT (Bénéficiaire/Tireur)

    @Enumerated(EnumType.STRING)
    private Role role;             // ADMIN | AGENT | TIREUR | BENEFICIAIRE

    // ── Statut du compte ──────────────────────────────────────────

    @Builder.Default
    @Column(name = "is_active")
    private boolean isActive = true;

    @Builder.Default
    @Column(name = "is_verified")
    private boolean isVerified = false;   // true si KYC ou OTP validé

    // ── Demande réinitialisation mot de passe ─────────────────────

    @Builder.Default
    @Column(name = "reset_password_requested", nullable = false, columnDefinition = "boolean DEFAULT false")
    private boolean resetPasswordRequested = false;

    // ── Blocage agent (remplace suppression) ──────────────────────

    @Builder.Default
    @Column(name = "is_blocked")
    private boolean isBlocked = false;

    @Column(name = "block_reason", columnDefinition = "TEXT")
    private String blockReason;

    @Column(name = "blocked_at")
    private LocalDateTime blockedAt;

    @Column(name = "blocked_by")          // UUID de l'admin qui a bloqué
    private UUID blockedBy;

    // ── OTP champs (inscription mobile) ───────────────────────────

    @Column(name = "otp_code")
    private String otpCode;               // Conservé pour compatibilité

    @Column(name = "otp_expires_at")
    private LocalDateTime otpExpiresAt;

    // ── Timestamps ────────────────────────────────────────────────

    @CreationTimestamp
    @Column(name = "created_at", updatable = false)
    private LocalDateTime createdAt;

    @UpdateTimestamp
    @Column(name = "updated_at")
    private LocalDateTime updatedAt;

    // ── Spring Security ────────────────────────────────────────────

    @Override
    public Collection<? extends GrantedAuthority> getAuthorities() {
        return List.of(new SimpleGrantedAuthority("ROLE_" + role.name()));
    }

    @Override
    public String getPassword() {
        return passwordHash;
    }

    @Override
    public String getUsername() {
        // Email pour web (Admin/Agent), téléphone pour mobile (Bénéficiaire/Tireur)
        return email != null ? email : phone;
    }

    @Override
    public boolean isEnabled() {
        return isActive;
    }

    @Override
    public boolean isAccountNonExpired() {
        return true;
    }

    @Override
    public boolean isAccountNonLocked() {
        // Compte bloqué → refus de connexion automatique par Spring Security
        return !isBlocked;
    }

    @Override
    public boolean isCredentialsNonExpired() {
        return true;
    }
}