package tn.tunicheque.auth_service.entity;

import jakarta.persistence.*;
import lombok.*;
import tn.tunicheque.auth_service.entity.enums.OtpStatus;

import java.time.LocalDateTime;
import java.util.UUID;

/**
 * OtpSession — session temporaire pour l'inscription en 3 étapes.
 *
 * Cycle de vie :
 *   PENDING   → créée quand on envoie le SMS OTP
 *   VERIFIED  → OTP confirmé → token_inscription émis
 *   EXPIRED   → > 2 min sans vérification
 */
@Entity
@Table(name = "otp_sessions")
@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class OtpSession {

    @Id
    @GeneratedValue(strategy = GenerationType.UUID)
    private UUID id;

    @Column(nullable = false, length = 20)
    private String telephone;

    @Column(name = "otp_code", nullable = false, length = 100)
    private String otpCode;            // BCrypt hashé

    @Column(name = "expiration", nullable = false)
    private LocalDateTime expiration;  // maintenant + 2 min

    @Enumerated(EnumType.STRING)
    @Column(nullable = false)
    @Builder.Default
    private OtpStatus status = OtpStatus.PENDING;

    @Column(name = "attempts")
    @Builder.Default
    private int attempts = 0;          // tentatives de vérification

    @Column(name = "created_at")
    @Builder.Default
    private LocalDateTime createdAt = LocalDateTime.now();

    @Column(name = "verified_at")
    private LocalDateTime verifiedAt;

    // ── Helpers ────────────────────────────────────────────────────

    public boolean isExpired() {
        return LocalDateTime.now().isAfter(expiration);
    }

    public boolean isVerified() {
        return status == OtpStatus.VERIFIED;
    }
}