package tn.tunicheque.auth_service.controller;

import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;
import tn.tunicheque.auth_service.dto.request.RibInitiateRequest;
import tn.tunicheque.auth_service.dto.request.SetPinRequest;
import tn.tunicheque.auth_service.dto.request.VerifyOtpRequest;
import tn.tunicheque.auth_service.service.RibRegistrationService;

import java.util.Map;

/**
 * RibRegistrationController — Inscription mobile via RIB bancaire BCT.
 *
 * ETAPE 1 : POST /api/auth/register/rib/initiate       → valider RIB + masquer tel
 * ETAPE 2 : POST /api/auth/register/rib/confirm-phone  → confirmer + envoyer OTP
 * ETAPE 3 : POST /api/auth/register/rib/verify-otp     → vérifier code SMS
 * ETAPE 4 : POST /api/auth/register/rib/set-pin        → créer PIN + compte
 */
@RestController
@RequestMapping("/api/auth/register/rib")
@RequiredArgsConstructor
@Slf4j
public class RibRegistrationController {

    private final RibRegistrationService ribService;

    // ── Etape 1 — Saisie et validation RIB ───────────────────────

    @PostMapping("/initiate")
    public ResponseEntity<?> initiateRib(
            @RequestBody @Valid RibInitiateRequest req) {
        return ResponseEntity.ok(ribService.initiate(req));
    }

    // ── Etape 2 — Confirmation numéro de téléphone ────────────────
    // Le client voit "+216 ** ****35" et répond OUI ou NON

    @PostMapping("/confirm-phone")
    public ResponseEntity<?> confirmPhone(
            @RequestBody Map<String, Object> req) {

        String sessionId = (String) req.get("sessionId");
        Boolean confirmed = (Boolean) req.get("confirmed");

        if (confirmed == null) {
            return ResponseEntity.badRequest()
                .body(Map.of("error", "Le champ 'confirmed' est obligatoire (true/false)."));
        }

        if (!confirmed) {
            // Le numéro affiché n'est pas le sien → orienter vers l'agence
            return ResponseEntity.ok(Map.of(
                "action", "VISIT_AGENCY",
                "message", "S'il vous plaît, visitez votre agence la plus proche pour " +
                           "mettre à jour votre numéro de téléphone."
            ));
        }

        // Numéro confirmé → envoyer l'OTP SMS
        ribService.sendOtp(sessionId);
        return ResponseEntity.ok(Map.of(
            "message", "Code OTP envoyé. Valable 2 minutes."
        ));
    }

    // ── Etape 3 — Vérification OTP ────────────────────────────────

    @PostMapping("/verify-otp")
    public ResponseEntity<?> verifyOtp(
            @RequestBody @Valid VerifyOtpRequest req) {
        return ResponseEntity.ok(ribService.verifyOtp(req));
    }

    // ── Etape 4 — Création PIN + compte ──────────────────────────

    @PostMapping("/set-pin")
    public ResponseEntity<?> setPin(
            @RequestBody @Valid SetPinRequest req) {
        return ResponseEntity.ok(ribService.createAccount(req));
    }
}
