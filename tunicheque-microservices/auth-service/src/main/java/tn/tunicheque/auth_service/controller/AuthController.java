package tn.tunicheque.auth_service.controller;

import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;
import tn.tunicheque.auth_service.dto.request.LoginRequest;
import tn.tunicheque.auth_service.dto.response.AuthResponse;
import tn.tunicheque.auth_service.security.JwtService;
import tn.tunicheque.auth_service.service.AuthService;

import java.util.Map;
import java.util.UUID;
import tn.tunicheque.auth_service.service.UserService;

/**
 * AuthController — Login web + mobile.
 *
 * FIX : supprimé updateUserPassword/updateUserPIN → déplacé dans ProfileController
 *       (évite la duplication et respecte la séparation des responsabilités)
 */
@RestController
@RequestMapping("/api/auth")
@RequiredArgsConstructor
public class AuthController {

    private final AuthService authService;
    private final JwtService  jwtService;

    // ── Login Web (Admin + Agent) ──────────────────────────────────

    @PostMapping("/login")
    public ResponseEntity<AuthResponse> loginWeb(
            @RequestBody @Valid LoginRequest req) {
        return ResponseEntity.ok(authService.loginWeb(req));
    }

    // ── Login Mobile (CLIENT avec RIB · BENEFICIAIRE KYC) ─────────

    @PostMapping("/login/mobile")
    public ResponseEntity<AuthResponse> loginMobile(
            @RequestBody LoginRequest req) {
        return ResponseEntity.ok(authService.loginMobile(req));
    }

    // ── Mot de passe oublié (public — notifie l'admin) ────────────

    @PostMapping("/forgot-password")
    public ResponseEntity<Map<String, String>> forgotPassword(
            @RequestBody Map<String, String> body) {
        String email = (body.getOrDefault("email", "")).trim();
        if (email.isBlank()) {
            return ResponseEntity.badRequest()
                    .body(Map.of("error", "Adresse e-mail requise."));
        }
        authService.requestPasswordReset(email);
        return ResponseEntity.ok(Map.of(
                "message", "Demande envoyée. L'administrateur vous contactera."));
    }

    // ── Health ────────────────────────────────────────────────────

    @GetMapping("/health")
    public ResponseEntity<Map<String, String>> health() {
        return ResponseEntity.ok(Map.of(
                "status", "UP",
                "service", "auth-service",
                "port", "8081"
        ));
    }
}