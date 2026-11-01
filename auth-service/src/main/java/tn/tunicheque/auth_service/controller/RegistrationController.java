package tn.tunicheque.auth_service.controller;

import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;
import tn.tunicheque.auth_service.dto.request.CompleteRegistrationRequest;
import tn.tunicheque.auth_service.dto.request.RegisterInitiateRequest;
import tn.tunicheque.auth_service.dto.request.VerifyOtpRequest;
import tn.tunicheque.auth_service.service.OTPService;

import java.util.Map;

/**
 * RegistrationController — Inscription Mobinaute en 3 étapes.
 *
 * UC "S'inscrire" (Table 3.1/3.2) — sécurité KYC :
 *   possession (téléphone OTP) + connaissance (PIN) + identité (CIN)
 *
 * FIX : endpoint /complete utilise X-Session-Id header (pas @PathVariable)
 * FIX : délègue directement à OTPService (supprimé RegistrationService inutile)
 * FIX : gestion erreurs via GlobalExceptionHandler
 */
@RestController
@RequestMapping("/api/auth/register")
@RequiredArgsConstructor
public class RegistrationController {

    private final OTPService otpService;

    // ── Etape A — Envoyer OTP ─────────────────────────────────────

    @PostMapping("/initiate")
    public ResponseEntity<?> initiate(
            @RequestBody @Valid RegisterInitiateRequest req) {
        return ResponseEntity.ok(otpService.initiate(req));
    }

    // ── Etape B — Vérifier OTP ────────────────────────────────────

    @PostMapping("/verify-otp")
    public ResponseEntity<?> verifyOtp(
            @RequestBody @Valid VerifyOtpRequest req) {
        return ResponseEntity.ok(otpService.verifyOtp(req));
    }

    // ── Etape C — Compléter l'inscription ─────────────────────────
    // X-Session-Id : UUID retourné à l'étape B

    @PostMapping("/complete")
    public ResponseEntity<?> complete(
            @RequestBody @Valid CompleteRegistrationRequest req,
            @RequestHeader("X-Session-Id") String sessionId) {
        return ResponseEntity.ok(otpService.complete(req, sessionId));
    }
}