package tn.tunicheque.auth_service.entity.enums;

public enum OtpStatus {
    PENDING,    // OTP envoyé, en attente de vérification
    VERIFIED,   // OTP validé
    EXPIRED,    // OTP expiré (> 2 min)
    CANCELLED   // Annulé
}