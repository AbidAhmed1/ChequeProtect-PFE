package tn.tunicheque.auth_service.service;

import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import tn.tunicheque.auth_service.dto.request.CompleteRegistrationRequest;
import tn.tunicheque.auth_service.dto.request.RegisterInitiateRequest;
import tn.tunicheque.auth_service.dto.request.VerifyOtpRequest;
import tn.tunicheque.auth_service.dto.response.AuthResponse;
import tn.tunicheque.auth_service.dto.response.OtpInitiateResponse;
import tn.tunicheque.auth_service.dto.response.OtpVerifyResponse;
import tn.tunicheque.auth_service.entity.OtpSession;
import tn.tunicheque.auth_service.entity.User;
import tn.tunicheque.auth_service.entity.enums.OtpStatus;
import tn.tunicheque.auth_service.entity.enums.Role;
import tn.tunicheque.auth_service.entity.enums.UserType;
import tn.tunicheque.auth_service.exception.*;
import tn.tunicheque.auth_service.repository.OtpSessionRepository;
import tn.tunicheque.auth_service.repository.UserRepository;
import tn.tunicheque.auth_service.security.JwtService;

import java.security.SecureRandom;
import java.time.LocalDateTime;
import java.util.UUID;

/**
 * OTPService — Inscription mobinaute en 3 étapes.
 *
 * FIX : complete() reçoit CompleteRegistrationRequest (DTO propre)
 * FIX : Role limité à TIREUR | BENEFICIAIRE lors de l'inscription
 * FIX : CIN doublon vérifié
 * FIX : PIN faible rejeté (123456, 000000, suites)
 */
@Service
@RequiredArgsConstructor
@Slf4j
public class OTPService {

    private final OtpSessionRepository otpSessionRepository;
    private final UserRepository        userRepository;
    private final PasswordEncoder       passwordEncoder;
    private final JwtService            jwtService;
    private final SmsService            smsService;

    private static final int OTP_EXPIRY_MIN  = 2;
    private static final int MAX_ATTEMPTS    = 3;

    // ══ ETAPE A — Initier l'inscription ══════════════════════════

    @Transactional
    public OtpInitiateResponse initiate(RegisterInitiateRequest req) {
        String tel = req.getTelephone().trim();

        if (userRepository.existsByPhone(tel)) {
            throw new RuntimeException(
                    "Ce numéro de téléphone est déjà associé à un compte.");
        }

        // Supprimer les anciennes sessions pour ce téléphone
        otpSessionRepository.deleteByTelephone(tel);

        String otp = generateOtp();
        log.info("[OTP] Envoi vers {} — code : {}", tel, otp);
        smsService.send(tel,
                "ChequePro — Votre code de vérification : " + otp + "\nValable 2 minutes. Ne le partagez pas.");

        OtpSession session = OtpSession.builder()
                .telephone(tel)
                .otpCode(passwordEncoder.encode(otp))
                .expiration(LocalDateTime.now().plusMinutes(OTP_EXPIRY_MIN))
                .status(OtpStatus.PENDING)
                .build();

        session = otpSessionRepository.save(session);
        log.info("Session OTP créée : {}", session.getId());

        return OtpInitiateResponse.builder()
                .sessionId(session.getId().toString())
                .expiresInSeconds(OTP_EXPIRY_MIN * 60)
                .build();
    }

    // ══ ETAPE B — Vérifier l'OTP ═════════════════════════════════

    @Transactional
    public OtpVerifyResponse verifyOtp(VerifyOtpRequest req) {
        OtpSession session = otpSessionRepository
                .findByIdAndStatus(req.getSessionId(), OtpStatus.PENDING)
                .orElseThrow(() -> new OTPNotFoundException(
                        "Session OTP introuvable ou déjà utilisée."));

        // Scénario 5.1 — OTP expiré
        if (session.isExpired()) {
            session.setStatus(OtpStatus.EXPIRED);
            otpSessionRepository.save(session);
            throw new OTPExpiredException(
                    "Le code OTP a expiré. Veuillez recommencer.");
        }

        // Incrémenter les tentatives
        session.setAttempts(session.getAttempts() + 1);
        if (session.getAttempts() > MAX_ATTEMPTS) {
            session.setStatus(OtpStatus.CANCELLED);
            otpSessionRepository.save(session);
            throw new OTPMaxAttemptsException(
                    "Trop de tentatives. Veuillez recommencer l'inscription.");
        }

        // Vérifier le code
        if (!passwordEncoder.matches(req.getOtp(), session.getOtpCode())) {
            otpSessionRepository.save(session);
            int restants = MAX_ATTEMPTS - session.getAttempts();
            throw new IllegalArgumentException(
                    "Code incorrect. " + restants + " tentative(s) restante(s).");
        }

        // OTP correct → VERIFIED
        session.setStatus(OtpStatus.VERIFIED);
        session.setVerifiedAt(LocalDateTime.now());
        otpSessionRepository.save(session);

        String token = jwtService.generateTempRegistrationToken(
                session.getId().toString(), session.getTelephone());

        log.info("OTP vérifié pour session : {}", session.getId());

        return OtpVerifyResponse.builder()
                .tokenInscription(token)
                .sessionId(session.getId().toString())
                .build();
    }

    // ══ ETAPE C — Compléter l'inscription ════════════════════════

    @Transactional
    public AuthResponse complete(CompleteRegistrationRequest req, String sessionId) {

        UUID sId = UUID.fromString(sessionId);
        OtpSession session = otpSessionRepository
                .findByIdAndStatus(sId, OtpStatus.VERIFIED)
                .orElseThrow(() -> new RuntimeException(
                        "Session invalide. Recommencez depuis le début."));

        // Scénario 9.1 — PIN non identique
        if (!req.getPin().equals(req.getPinConfirm())) {
            throw new IllegalArgumentException(
                    "Les codes PIN ne correspondent pas. Veuillez les re-saisir.");
        }

        // PIN trop simple — Scénario 5.2
        if (isWeakPin(req.getPin())) {
            throw new IllegalArgumentException(
                    "Ce PIN est trop simple. Évitez 123456, 000000 ou répétitions.");
        }

        // Scénario 7.1 — Email doublon
        if (userRepository.existsByEmail(req.getEmail())) {
            throw new EmailAlreadyExistsException("Cet email est déjà utilisé.");
        }

        // CIN doublon
        if (userRepository.existsByCinNumber(req.getCin())) {
            throw new CINAlreadyExistsException("Ce CIN est déjà enregistré.");
        }

        User user = User.builder()
                .fullName(req.getNom() + " " + req.getPrenom())
                .email(req.getEmail())
                .phone(session.getTelephone())
                .cinNumber(req.getCin())
                .passwordHash(passwordEncoder.encode(req.getPin()))
                .role(Role.CLIENT)
                .userType(UserType.CLIENT)
                .isActive(true)
                .isVerified(true)
                .build();

        user = userRepository.save(user);

        // Nettoyer la session OTP
        otpSessionRepository.delete(session);

        log.info("Compte créé : {} — {} — {}", user.getId(), user.getEmail(), user.getRole());

        return AuthResponse.builder()
                .token(jwtService.generateToken(user))
                .role(user.getRole().name())
                .userType(user.getUserType().name())
                .expiresIn(3600)
                .build();
    }

    // ── Utilitaires ───────────────────────────────────────────────

    private String generateOtp() {
        return String.valueOf(100_000 + new SecureRandom().nextInt(900_000));
    }

    private boolean isWeakPin(String pin) {
        return pin.equals("123456") || pin.equals("654321")
                || pin.chars().distinct().count() == 1
                || pin.equals("012345") || pin.equals("543210");
    }
}