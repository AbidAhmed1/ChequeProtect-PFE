package tn.tunicheque.auth_service.service;

import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import tn.tunicheque.auth_service.dto.request.RibInitiateRequest;
import tn.tunicheque.auth_service.dto.request.SetPinRequest;
import tn.tunicheque.auth_service.dto.request.VerifyOtpRequest;
import tn.tunicheque.auth_service.dto.response.AuthResponse;
import tn.tunicheque.auth_service.dto.response.OtpVerifyResponse;
import tn.tunicheque.auth_service.dto.response.RibInitiateResponse;
import tn.tunicheque.auth_service.entity.BankAccount;
import tn.tunicheque.auth_service.entity.OtpSession;
import tn.tunicheque.auth_service.entity.User;
import tn.tunicheque.auth_service.entity.enums.OtpStatus;
import tn.tunicheque.auth_service.entity.enums.Role; // <-- AJOUT DE L'IMPORT ICI
import tn.tunicheque.auth_service.entity.enums.UserType;
import tn.tunicheque.auth_service.exception.OTPExpiredException;
import tn.tunicheque.auth_service.exception.OTPMaxAttemptsException;
import tn.tunicheque.auth_service.exception.OTPNotFoundException;
import tn.tunicheque.auth_service.repository.BankAccountRepository;
import tn.tunicheque.auth_service.repository.OtpSessionRepository;
import tn.tunicheque.auth_service.repository.UserRepository;
import tn.tunicheque.auth_service.security.JwtService;

import java.math.BigInteger;
import java.security.SecureRandom;
import java.time.LocalDateTime;
import java.util.UUID;

/**
 * RibRegistrationService — Inscription mobile via RIB bancaire BCT.
 *
 * Flux en 4 étapes :
 * 1. initiate()     → valider RIB Luhn + masquer téléphone
 * 2. confirmPhone() → l'utilisateur confirme que c'est son numéro
 * 3. verifyOtp()    → vérifier code SMS (2 min, max 3 tentatives)
 * 4. createAccount()→ PIN + création compte avec rôle CLIENT unique
 */
@Service
@RequiredArgsConstructor
@Slf4j
public class RibRegistrationService {

    private final BankAccountRepository bankAccountRepo;
    private final OtpSessionRepository  otpRepo;
    private final UserRepository        userRepo;
    private final PasswordEncoder       passwordEncoder;
    private final JwtService            jwtService;
    private final SmsService            smsService;
    private final ChequeServiceClient   chequeServiceClient;

    private static final int OTP_EXPIRY_MIN = 2;
    private static final int MAX_ATTEMPTS   = 3;

    // ══ ETAPE 1 — Initier via RIB ════════════════════════════════

    @Transactional
    public RibInitiateResponse initiate(RibInitiateRequest req) {
        String rib = req.getRib().replaceAll("\\s", "");

        // 1. Validation format (20 chiffres)
        if (!rib.matches("[0-9]{20}")) {
            throw new IllegalArgumentException(
                    "RIB invalide : 20 chiffres requis (sans espaces).");
        }

        // 2. Validation clé Luhn BCT (Modifié avec BigInteger)
        if (!isValidRib(rib)) {
            throw new IllegalArgumentException(
                    "Clé RIB invalide (contrôle Luhn BCT échoué).");
        }

        // 3. Chercher le compte bancaire
        BankAccount compte = bankAccountRepo.findByRib(rib)
                .orElseThrow(() -> new RuntimeException(
                        "Compte introuvable pour ce RIB. Visitez votre agence la plus proche."));

        if (!compte.isActive()) {
            throw new RuntimeException(
                    "Ce compte bancaire est inactif. Contactez votre agence.");
        }

        // 4. Vérifier que l'utilisateur n'a pas déjà un compte
        if (userRepo.existsByPhone(compte.getTelephone())) {
            throw new RuntimeException(
                    "Un compte existe déjà pour ce numéro. Utilisez 'Se connecter'.");
        }

        // 5. Nettoyer les anciennes sessions OTP
        otpRepo.deleteByTelephone(compte.getTelephone());

        // 6. Masquer le téléphone : "+21620123456" → "+216 ** ****56"
        String telMasque = maskPhone(compte.getTelephone());

        // 7. Créer session OTP (sans envoyer l'OTP — en attente de confirmation)
        OtpSession session = OtpSession.builder()
                .telephone(compte.getTelephone())
                .otpCode("")              // vide jusqu'à confirmation
                .expiration(LocalDateTime.now().plusMinutes(10))
                .status(OtpStatus.PENDING)
                .build();
        session = otpRepo.save(session);

        log.info("RIB valide pour compte : {} — tel masqué : {}", rib, telMasque);

        return RibInitiateResponse.builder()
                .sessionId(session.getId().toString())
                .telephoneMasque(telMasque)
                .message("Est-ce votre numéro ? " + telMasque)
                .expiresInSeconds(600)
                .build();
    }

    // ══ ETAPE 2 — Confirmation du numéro + envoi OTP ═════════════

    @Transactional
    public void sendOtp(String sessionId) {
        OtpSession session = otpRepo.findById(UUID.fromString(sessionId))
                .orElseThrow(() -> new OTPNotFoundException("Session introuvable."));

        String otp = generateOtp();
        log.info("[OTP] Envoi vers {} — code : {}", session.getTelephone(), otp);
        smsService.send(session.getTelephone(),
                "ChequePro — Votre code de vérification : " + otp + "\nValable 2 minutes. Ne le partagez pas.");

        session.setOtpCode(passwordEncoder.encode(otp));
        session.setExpiration(LocalDateTime.now().plusMinutes(OTP_EXPIRY_MIN));
        session.setAttempts(0);
        otpRepo.save(session);
    }

    // ══ ETAPE 3 — Vérifier l'OTP ═════════════════════════════════

    @Transactional
    public OtpVerifyResponse verifyOtp(VerifyOtpRequest req) {
        OtpSession session = otpRepo
                .findByIdAndStatus(req.getSessionId(), OtpStatus.PENDING)
                .orElseThrow(() -> new OTPNotFoundException(
                        "Session OTP introuvable ou déjà utilisée."));

        if (session.isExpired()) {
            session.setStatus(OtpStatus.EXPIRED);
            otpRepo.save(session);
            throw new OTPExpiredException("OTP expiré. Recommencez.");
        }

        session.setAttempts(session.getAttempts() + 1);
        if (session.getAttempts() > MAX_ATTEMPTS) {
            session.setStatus(OtpStatus.CANCELLED);
            otpRepo.save(session);
            throw new OTPMaxAttemptsException("Trop de tentatives. Recommencez.");
        }

        if (!passwordEncoder.matches(req.getOtp(), session.getOtpCode())) {
            otpRepo.save(session);
            throw new IllegalArgumentException(
                    "Code incorrect. " + (MAX_ATTEMPTS - session.getAttempts()) + " tentative(s) restante(s).");
        }

        session.setStatus(OtpStatus.VERIFIED);
        session.setVerifiedAt(LocalDateTime.now());
        otpRepo.save(session);

        String token = jwtService.generateTempRegistrationToken(
                session.getId().toString(), session.getTelephone());

        return OtpVerifyResponse.builder()
                .tokenInscription(token)
                .sessionId(session.getId().toString())
                .build();
    }

    // ══ ETAPE 4 — Créer le compte avec PIN ═══════════════════════

    @Transactional
    public AuthResponse createAccount(SetPinRequest req) {
        UUID sId = UUID.fromString(req.getSessionId());

        OtpSession session = otpRepo.findByIdAndStatus(sId, OtpStatus.VERIFIED)
                .orElseThrow(() -> new RuntimeException(
                        "Session invalide. Recommencez depuis le début."));

        // Validation PIN
        if (!req.getPin().equals(req.getPinConfirm())) {
            throw new IllegalArgumentException(
                    "Les codes PIN ne correspondent pas.");
        }
        if (isWeakPin(req.getPin())) {
            throw new IllegalArgumentException(
                    "Ce PIN est trop simple (ex: 123456, 000000). Choisissez-en un autre.");
        }

        // Récupérer les infos du compte bancaire
        BankAccount compte = bankAccountRepo
                .findAll().stream()
                .filter(b -> b.getTelephone().equals(session.getTelephone()))
                .findFirst()
                .orElseThrow(() -> new RuntimeException("Compte bancaire introuvable."));

        // Créer le compte utilisateur
        String fullName = (compte.getPrenom() != null && !compte.getPrenom().isBlank())
                ? compte.getPrenom().trim() + " " + compte.getNomClient()
                : compte.getNomClient();

        User user = User.builder()
                .fullName(fullName)
                .phone(session.getTelephone())
                .rib(compte.getRib())
                .passwordHash(passwordEncoder.encode(req.getPin()))
                .role(Role.CLIENT)
                .userType(UserType.CLIENT)
                .isActive(true)
                .isVerified(true)
                .build();

        user = userRepo.save(user);
        otpRepo.delete(session);

        log.info("Compte RIB créé : {} — role={}", user.getPhone(), user.getRole());

        // Lier les chèques existants avec ce RIB au nouveau compte tireur
        chequeServiceClient.linkTireur(compte.getRib(), user.getId());

        return AuthResponse.builder()
                .token(jwtService.generateToken(user))
                .role(user.getRole().name())
                .userType(user.getUserType().name())
                .expiresIn(3600)
                .build();
    }

    // ── Utilitaires ───────────────────────────────────────────────

    /**
     * Masque le téléphone : "+21620123456" → "+216 ** ****56"
     */
    private String maskPhone(String tel) {
        if (tel == null || tel.length() < 4) return "***";
        return tel.substring(0, 4) + " ** *** *" + tel.substring(tel.length() - 2);
    }

    private String generateOtp() {
        return String.valueOf(100_000 + new SecureRandom().nextInt(900_000));
    }

    private boolean isWeakPin(String pin) {
        return pin.equals("123456") || pin.equals("654321")
                || pin.equals("000000") || pin.chars().distinct().count() == 1;
    }

    /**
     * Validation RIB BCT — méthode statique réutilisable.
     * Utilise BigInteger pour éviter l'overflow des longs.
     */
    public static boolean isValidRib(String rib) {
        if (rib == null || !rib.matches("[0-9]{20}")) return false;
        try {
            // 1. Extraire les 18 premiers chiffres
            String baseString = rib.substring(0, 18);
            BigInteger base = new BigInteger(baseString);

            // 2. Multiplier par 100
            BigInteger baseTimes100 = base.multiply(BigInteger.valueOf(100));

            // 3. Calculer le reste mod 97
            int reste = baseTimes100.remainder(BigInteger.valueOf(97)).intValue();

            // 4. Calculer la clé attendue (97 - reste)
            int cleAttendue = 97 - reste;

            // 5. Comparer avec la clé fournie (2 derniers chiffres)
            int cleFournie = Integer.parseInt(rib.substring(18));

            return cleAttendue == cleFournie;
        } catch (Exception e) {
            return false;
        }
    }
}