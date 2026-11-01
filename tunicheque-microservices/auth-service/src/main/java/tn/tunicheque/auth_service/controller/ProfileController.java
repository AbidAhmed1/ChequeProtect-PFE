package tn.tunicheque.auth_service.controller;

import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;
import tn.tunicheque.auth_service.dto.request.ProfileUpdateRequest;
import tn.tunicheque.auth_service.dto.response.UserDTO;
import tn.tunicheque.auth_service.entity.User;
import tn.tunicheque.auth_service.exception.UserNotFoundException;
import tn.tunicheque.auth_service.repository.UserRepository;
import tn.tunicheque.auth_service.security.JwtService;
import tn.tunicheque.auth_service.service.AuthService;

import java.util.Map;
import java.util.UUID;

/**
 * ProfileController — Gestion du profil personnel (tous rôles).
 * UC "Gérer profil utilisateur" (Table 3.12)
 *
 * FIX : consolidation — password + PIN ici uniquement (supprimé de AuthController)
 */
@RestController
@RequestMapping("/api/auth/me")
@RequiredArgsConstructor
public class ProfileController {

    private final UserRepository userRepository;
    private final JwtService     jwtService;
    private final AuthService    authService;

    private UUID extractUserId(String authHeader) {
        String token = authHeader.startsWith("Bearer ")
                ? authHeader.substring(7) : authHeader;
        return UUID.fromString(jwtService.extractUserId(token));
    }

    // ── Mon profil ────────────────────────────────────────────────

    @GetMapping
    public ResponseEntity<UserDTO> getMyProfile(
            @RequestHeader("Authorization") String token) {
        UUID userId = extractUserId(token);
        User user = userRepository.findById(userId)
                .orElseThrow(() -> new UserNotFoundException("Utilisateur introuvable."));
        return ResponseEntity.ok(UserDTO.from(user));
    }

    // ── Modifier mon profil (nom, email, téléphone) ────────────────

    @PutMapping
    public ResponseEntity<?> updateProfile(
            @RequestHeader("Authorization") String token,
            @RequestBody @Valid ProfileUpdateRequest req) {
        UUID userId = extractUserId(token);
        User user = userRepository.findById(userId)
                .orElseThrow(() -> new UserNotFoundException("Utilisateur introuvable."));

        if (req.getFullName() != null && !req.getFullName().isBlank())
            user.setFullName(req.getFullName());

        if (req.getEmail() != null && !req.getEmail().equals(user.getEmail())) {
            if (userRepository.existsByEmail(req.getEmail()))
                return ResponseEntity.badRequest()
                        .body(Map.of("error", "Cet email est déjà utilisé."));
            user.setEmail(req.getEmail());
        }

        if (req.getPhone() != null && !req.getPhone().isBlank())
            user.setPhone(req.getPhone());

        userRepository.save(user);
        return ResponseEntity.ok(Map.of("message", "Profil mis à jour avec succès."));
    }

    // ── Changer mot de passe ───────────────────────────────────────
    // Autorisé pour tous les rôles (ADMIN, AGENT, TIREUR, BENEFICIAIRE).

    @PutMapping("/password")
    public ResponseEntity<?> changePassword(
            @RequestHeader("Authorization") String token,
            @RequestBody Map<String, String> req) {

        UUID userId = extractUserId(token);
        userRepository.findById(userId)
                .orElseThrow(() -> new UserNotFoundException("Utilisateur introuvable."));

        authService.updatePassword(userId,
                req.get("currentPassword"),
                req.get("newPassword"));
        return ResponseEntity.ok(Map.of("message", "Mot de passe modifié avec succès."));
    }

    // ── Changer PIN (Mobile — Bénéficiaire/Tireur) ────────────────

    @PutMapping("/pin")
    public ResponseEntity<?> changePin(
            @RequestHeader("Authorization") String token,
            @RequestBody Map<String, String> req) {
        UUID userId = extractUserId(token);
        authService.updatePin(userId,
                req.get("currentPin"),
                req.get("newPin"),
                req.get("newPinConfirm"));
        return ResponseEntity.ok(Map.of("message", "PIN modifié avec succès."));
    }
}