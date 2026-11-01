package tn.tunicheque.auth_service.service;

import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Service;
import tn.tunicheque.auth_service.dto.request.LoginRequest;
import tn.tunicheque.auth_service.dto.response.AuthResponse;
import tn.tunicheque.auth_service.entity.User;
import tn.tunicheque.auth_service.entity.enums.Role;
import tn.tunicheque.auth_service.exception.AccountDisabledException;
import tn.tunicheque.auth_service.exception.BadCredentialsException;
import tn.tunicheque.auth_service.exception.UserNotFoundException;
import tn.tunicheque.auth_service.repository.UserRepository;
import tn.tunicheque.auth_service.security.JwtService;

import org.springframework.transaction.annotation.Transactional;
import java.util.UUID;

/**
 * AuthService — Authentification web + mobile.
 *
 * UC "S'authentifier web"   (Table 3.5) → loginWeb()
 * UC "S'authentifier mobile" (Table 3.4) → loginMobile()
 *
 * Ordre de vérification OBLIGATOIRE (scénario 5.1) :
 *   1. Utilisateur existe ?
 *   2. Compte actif ? (is_active=false → AccountDisabledException AVANT Spring Security)
 *   3. Mot de passe / PIN correct ?
 *   4. Générer JWT
 */
@Service
@RequiredArgsConstructor
@Slf4j
public class AuthService {

    private final UserRepository  userRepo;
    private final JwtService      jwtService;
    private final PasswordEncoder passwordEncoder;

    // ── Login Web (Admin + Agent) ──────────────────────────────────

    public AuthResponse loginWeb(LoginRequest req) {
        User user = userRepo.findByEmail(req.getEmail())
                .orElseThrow(() -> new UserNotFoundException(
                        "Identifiants incorrects."));

        // Scénario 5.1 — compte désactivé AVANT Spring Security
        if (!user.isActive()) {
            log.warn("Tentative connexion compte désactivé : {}", req.getEmail());
            throw new AccountDisabledException(
                    "Votre compte a été désactivé. Contactez votre administrateur.");
        }

        if (!passwordEncoder.matches(req.getPassword(), user.getPasswordHash())) {
            throw new BadCredentialsException("Email ou mot de passe incorrect.");
        }

        log.info("Connexion web : {} — role={}", user.getEmail(), user.getRole());

        return AuthResponse.builder()
                .token(jwtService.generateToken(user))
                .role(user.getRole().name())
                .userType(user.getUserType().name())
                .expiresIn(3600)
                .build();
    }

    // ── Login Mobile (CLIENT avec RIB · BENEFICIAIRE KYC — via PIN) ─

    /**
     * Endpoint mobile — rôles acceptés :
     *   • CLIENT      : inscrit via le parcours avec RIB (accès Tireur + Bénéficiaire).
     *   • BENEFICIAIRE: inscrit via KYC sans RIB (réception de chèques uniquement).
     *
     * Les rôles ADMIN et AGENT sont bloqués (accès réservé au portail web).
     *
     * Authentification par email OU numéro de téléphone + PIN à 6 chiffres.
     */
    public AuthResponse loginMobile(LoginRequest req) {
        // Mobile s'authentifie par téléphone (ou email) + PIN
        User user = (req.getEmail() != null && !req.getEmail().isBlank())
                ? userRepo.findByEmail(req.getEmail())
                  .orElseThrow(() -> new UserNotFoundException("Identifiants incorrects."))
                : userRepo.findByPhone(req.getPhone())
                  .orElseThrow(() -> new UserNotFoundException("Identifiants incorrects."));

        if (!user.isActive()) {
            throw new AccountDisabledException(
                    "Votre compte est désactivé. Contactez votre banque.");
        }

        if (!passwordEncoder.matches(req.getPassword(), user.getPasswordHash())) {
            throw new BadCredentialsException("Code PIN incorrect.");
        }

        // Log le rôle effectif (CLIENT ou BENEFICIAIRE) pour audit et traçabilité
        log.info("Connexion mobile : {} — role={}", user.getUsername(), user.getRole());

        return AuthResponse.builder()
                .token(jwtService.generateToken(user))
                .role(user.getRole().name())
                .userType(user.getUserType().name())
                .expiresIn(3600)
                .build();
    }

    // ── Demande réinitialisation mot de passe (depuis page login) ─

    @Transactional
    public void requestPasswordReset(String email) {
        userRepo.findByEmail(email).ifPresent(user -> {
            if (user.getRole() == Role.AGENT || user.getRole() == Role.ADMIN) {
                user.setResetPasswordRequested(true);
                userRepo.save(user);
                log.info("Demande réinitialisation MDP : {}", email);
            }
        });
    }

    // ── Changement de mot de passe (web) ──────────────────────────

    public void updatePassword(UUID userId, String currentPassword, String newPassword) {
        User user = userRepo.findById(userId)
                .orElseThrow(() -> new UserNotFoundException("Utilisateur introuvable."));

        if (!passwordEncoder.matches(currentPassword, user.getPasswordHash())) {
            throw new BadCredentialsException("Mot de passe actuel incorrect.");
        }
        if (newPassword.length() < 8) {
            throw new IllegalArgumentException(
                    "Le nouveau mot de passe doit contenir au moins 8 caractères.");
        }
        user.setPasswordHash(passwordEncoder.encode(newPassword));
        userRepo.save(user);
        log.info("Mot de passe modifié : {}", userId);
    }

    // ── Changement de PIN (mobile) ─────────────────────────────────

    public void updatePin(UUID userId, String currentPin, String newPin, String newPinConfirm) {
        User user = userRepo.findById(userId)
                .orElseThrow(() -> new UserNotFoundException("Utilisateur introuvable."));

        if (!passwordEncoder.matches(currentPin, user.getPasswordHash())) {
            throw new BadCredentialsException("Code PIN actuel incorrect.");
        }
        if (!newPin.equals(newPinConfirm)) {
            throw new IllegalArgumentException("Les codes PIN ne correspondent pas.");
        }
        if (!newPin.matches("[0-9]{6}")) {
            throw new IllegalArgumentException("Le PIN doit contenir 6 chiffres.");
        }
        if (isWeakPin(newPin)) {
            throw new IllegalArgumentException(
                    "Ce PIN est trop simple. Évitez les suites (123456) ou répétitions (000000).");
        }
        user.setPasswordHash(passwordEncoder.encode(newPin));
        userRepo.save(user);
        log.info("PIN modifié : {}", userId);
    }

    private boolean isWeakPin(String pin) {
        return pin.equals("123456") || pin.equals("654321")
                || pin.chars().distinct().count() == 1;
    }
}